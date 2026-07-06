"""watcher.py — NOTIFY-ONLY Discord watcher for the Riftbound x T1 collection.

The watcher checks a small set of PUBLIC pages, keeps a narrow relevance filter
focused on the Riftbound x T1 Worlds Champion Collection, and posts NEW relevant
hits to a Discord webhook. It is strictly notify-only:

  * It NEVER logs in, buys, checks out, solves captchas, bypasses rate limits,
    or scrapes aggressively.
  * The Discord webhook URL is a secret and is NEVER written to logs, exceptions
    or state.

CLI modes
---------
  python watcher.py
      Normal run. First ever run only writes a baseline to state.json and sends
      nothing; later runs post only NEW relevant hits and update state.json.

  python watcher.py --dry-run
      Check and log the analysis. Never sends, never touches state.json.

  python watcher.py --test-webhook-random-riftbound
      Send exactly ONE test message for a random Riftbound hit from the fetched
      results. Never touches state.json. Aborts cleanly if there is no Riftbound
      hit.

Configuration comes from the environment variable ``DISCORD_WEBHOOK_URL``,
optionally loaded from a local ``.env`` file (the environment variable takes
precedence). See ``config.py``.
"""
from __future__ import annotations

import argparse
import logging
import random

import config
import fetch
import notify
import relevance
import state as state_mod

logger = logging.getLogger("riot.watcher")

STATE_PATH = state_mod.DEFAULT_STATE_PATH

MODE_NORMAL = "normal"
MODE_DRY_RUN = "dry-run"
MODE_TEST_WEBHOOK = "test-webhook-random-riftbound"


def _new_summary(mode: str) -> dict:
    return {
        "mode": mode,
        "checked": 0,
        "relevant": 0,
        "new": 0,
        "posted": 0,
        "state_written": False,
    }


def run(
    mode: str = MODE_NORMAL,
    *,
    targets=None,
    state_path: str = STATE_PATH,
    webhook_url=None,
    fetch_fn=None,
    send_fn=None,
    rng=None,
) -> dict:
    """Run one watcher pass in ``mode`` and return a summary dict.

    Dependencies are injectable for testing:
      * ``fetch_fn(targets) -> list[item]``     (default: fetch.fetch_targets)
      * ``send_fn(webhook_url, content) -> ...`` (default: notify.send_discord)
      * ``rng``                                  (default: the random module)

    The summary contains: mode, checked, relevant, new, posted, state_written.
    """
    if mode not in (MODE_NORMAL, MODE_DRY_RUN, MODE_TEST_WEBHOOK):
        raise ValueError(
            "Unknown mode %r; expected one of %r"
            % (mode, (MODE_NORMAL, MODE_DRY_RUN, MODE_TEST_WEBHOOK))
        )

    fetch_fn = fetch_fn or fetch.fetch_targets
    send_fn = send_fn or notify.send_discord
    rng = rng or random

    summary = _new_summary(mode)

    candidates = fetch_fn(targets) or []
    summary["checked"] = len(candidates)
    relevant = relevance.filter_relevant(candidates)
    summary["relevant"] = len(relevant)
    logger.info("Mode=%s: checked %d item(s), %d relevant.", mode, summary["checked"], summary["relevant"])

    if mode == MODE_TEST_WEBHOOK:
        return _run_test_webhook(summary, candidates, webhook_url, send_fn, rng)
    if mode == MODE_DRY_RUN:
        return _run_dry_run(summary, relevant, state_path)
    return _run_normal(summary, relevant, state_path, webhook_url, send_fn)


def _run_test_webhook(summary, candidates, webhook_url, send_fn, rng) -> dict:
    """Send exactly one test message for a random Riftbound hit; never write state."""
    # Only Riftbound hits that also yield a valid clickable link, so the single
    # test message always contains a working link.
    pool = [
        it for it in candidates
        if relevance.is_riftbound(it) and notify.best_item_url(it)
    ]
    logger.info("Mode=%s: %d Riftbound hit(s) available for the test message.", MODE_TEST_WEBHOOK, len(pool))

    if not pool:
        logger.info("No Riftbound hit found; sending nothing and leaving state unchanged.")
        return summary

    if not webhook_url:
        logger.error("DISCORD_WEBHOOK_URL is not set; cannot send the test message. State unchanged.")
        return summary

    chosen = rng.choice(pool)
    content = "[TEST] " + notify.format_message(chosen, relevance.relevance_reasons(chosen))
    send_fn(webhook_url, content)
    summary["posted"] = 1
    logger.info("Sent exactly one test message for a random Riftbound hit. State unchanged.")
    return summary


def _run_dry_run(summary, relevant, state_path) -> dict:
    """Log what a normal run WOULD do; never send, never touch state."""
    status = state_mod.state_status(state_path)
    st = state_mod.load_state(state_path)
    baseline = status in ("missing", "corrupt")
    would_new = [] if baseline else state_mod.new_items(relevant, st)
    summary["new"] = len(would_new)
    logger.info(
        "DRY-RUN: relevant=%d would_post=%d (baseline=%s). Nothing sent, state unchanged.",
        summary["relevant"], summary["new"], baseline,
    )
    return summary


def _run_normal(summary, relevant, state_path, webhook_url, send_fn) -> dict:
    """Normal mode: baseline on first run (or corrupt state), else post NEW hits."""
    status = state_mod.state_status(state_path)
    st = state_mod.load_state(state_path)

    if status in ("missing", "corrupt"):
        # First run OR an unreadable/invalid state: (re)write a clean baseline and
        # send nothing, so corruption never triggers a mass re-post of every hit.
        state_mod.record_items(st, relevant)
        state_mod.save_state(state_path, st)
        summary["state_written"] = True
        if status == "corrupt":
            logger.warning(
                "Existing state was unreadable/invalid; rewrote a fresh baseline "
                "of %d relevant item(s) and sent nothing.",
                summary["relevant"],
            )
        else:
            logger.info(
                "First run: wrote baseline of %d relevant item(s); no messages sent.",
                summary["relevant"],
            )
        return summary

    new = state_mod.new_items(relevant, st)
    summary["new"] = len(new)

    if not new:
        logger.info("No new relevant items; nothing sent, state unchanged.")
        return summary

    if not webhook_url:
        logger.error(
            "%d new relevant item(s) found but DISCORD_WEBHOOK_URL is not set; "
            "not posting and NOT updating state so they can be posted later.",
            len(new),
        )
        return summary

    delivered = []
    try:
        for item in new:
            content = notify.format_message(item, relevance.relevance_reasons(item))
            send_fn(webhook_url, content)
            delivered.append(item)
    finally:
        # Persist only what was actually delivered so a mid-run failure never
        # loses a delivered item (no re-post) nor marks an undelivered one seen.
        if delivered:
            state_mod.record_items(st, delivered)
            state_mod.save_state(state_path, st)
            summary["state_written"] = True

    summary["posted"] = len(delivered)
    logger.info(
        "Posted %d new relevant item(s); state %s.",
        summary["posted"],
        "updated" if summary["state_written"] else "unchanged",
    )
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="watcher",
        description="NOTIFY-ONLY Discord watcher for the Riftbound x T1 collection.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Check and log the analysis; never send, never touch state.json.",
    )
    group.add_argument(
        "--test-webhook-random-riftbound",
        action="store_true",
        dest="test_webhook_random_riftbound",
        help="Send exactly one test message for a random Riftbound hit; never touch state.json.",
    )
    parser.add_argument(
        "--state-path",
        dest="state_path",
        default=STATE_PATH,
        help="Path to the state file (default: %(default)s).",
    )
    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.dry_run:
        mode = MODE_DRY_RUN
    elif args.test_webhook_random_riftbound:
        mode = MODE_TEST_WEBHOOK
    else:
        mode = MODE_NORMAL

    # Resolve the webhook from the environment or an optional local .env
    # (environment wins). A placeholder value (e.g. an unedited REPLACE_ME) is
    # treated as "not configured" so the watcher never tries to send with it.
    raw = config.resolve_webhook_url()
    webhook_url = None if config.is_placeholder_webhook(raw) else raw
    if mode in (MODE_NORMAL, MODE_TEST_WEBHOOK) and not webhook_url:
        # Never echo any value; only note whether it is absent or a placeholder.
        if raw:
            logger.warning(
                "DISCORD_WEBHOOK_URL looks like a placeholder; replace it with your "
                "real webhook to send. No messages can be sent."
            )
        else:
            logger.warning("DISCORD_WEBHOOK_URL is not set; no messages can be sent.")

    try:
        summary = run(mode, state_path=args.state_path, webhook_url=webhook_url)
    except Exception as exc:
        # Backstop: never let an error reach the user with a secret attached.
        # Redact both the gated value and the raw resolved value — the raw value
        # may hold a real webhook even when it was gated to None as a placeholder.
        safe = notify.redact_secrets(str(exc), [webhook_url, raw])
        logger.error("Watcher run failed: %s", safe)
        return 1

    logger.info(
        "Done. mode=%s checked=%d relevant=%d new=%d posted=%d state_written=%s",
        summary["mode"], summary["checked"], summary["relevant"],
        summary["new"], summary["posted"], summary["state_written"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
