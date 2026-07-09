"""End-to-end tests for watcher.run() — the CLI orchestration layer.

Everything is driven through dependency injection: a fake ``fetch_fn`` returns a
fixed list of candidate items and a ``Recorder`` captures Discord sends, so no
network and no real Discord webhook are ever touched. The webhook value used
here is an OBVIOUS placeholder — never a real secret.
"""
import logging
import os

import pytest

import fetch
import watcher
import state as state_mod
import notify

# Obvious placeholder — NOT a real webhook. Used to prove it never leaks.
WEBHOOK = "https://discord.com/api/webhooks/000000000000000000/FAKE_TOKEN_DO_NOT_USE"


def make_candidates():
    """Four candidates: two relevant (Riftbound WCC, Faker Galio Sig. Ed.),
    two irrelevant (generic hoodie, patch notes)."""
    return [
        {
            "title": "Riftbound x T1 Worlds Champion Collection",
            "url": "https://merch.riotgames.com/riftbound-t1-wcc",
            "source": "https://merch.riotgames.com/",
            "text": "",
        },
        {
            "title": "Faker Galio Signature Edition",
            "url": "https://merch.riotgames.com/faker-galio-signature-edition",
            "source": "https://merch.riotgames.com/",
            "text": "",
        },
        {
            "title": "New League of Legends hoodie",
            "url": "https://merch.riotgames.com/lol-hoodie",
            "source": "https://merch.riotgames.com/",
            "text": "",
        },
        {
            "title": "Patch 14.13 balance changes for League of Legends",
            "url": "https://www.leagueoflegends.com/news/patch-14-13",
            "source": "https://www.leagueoflegends.com/en-us/news/",
            "text": "",
        },
    ]


NEW_RELEVANT = {
    "title": "T1 Player Bundle drop is live",
    "url": "https://merch.riotgames.com/t1-player-bundle",
    "source": "https://merch.riotgames.com/",
    "text": "",
}


def fetch_fn_factory(items):
    def _fetch(targets=None):
        return list(items)

    return _fetch


class Recorder:
    """Test double for send_discord: records every (webhook_url, content) call."""

    def __init__(self):
        self.calls = []

    def __call__(self, webhook_url, content):
        self.calls.append((webhook_url, content))
        return True


def _state_path(tmp_path):
    return str(tmp_path / "state.json")


# --- Scenario 1: first normal run -------------------------------------------

def test_first_run_writes_baseline_and_sends_nothing(tmp_path):
    sp = _state_path(tmp_path)
    send = Recorder()

    summary = watcher.run(
        "normal",
        state_path=sp,
        webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(make_candidates()),
        send_fn=send,
    )

    assert send.calls == []               # no Discord message on first run
    assert os.path.exists(sp)             # baseline written
    st = state_mod.load_state(sp)
    assert len(st["seen"]) == 2           # exactly the two relevant items
    assert summary["checked"] == 4
    assert summary["relevant"] == 2
    assert summary["posted"] == 0
    assert summary["state_written"] is True


# --- Scenario 2: second normal run, no new hits -----------------------------

def test_second_run_without_new_hits_posts_nothing(tmp_path):
    sp = _state_path(tmp_path)
    fetch = fetch_fn_factory(make_candidates())

    watcher.run("normal", state_path=sp, webhook_url=WEBHOOK, fetch_fn=fetch, send_fn=Recorder())
    before = open(sp, "r", encoding="utf-8").read()

    send2 = Recorder()
    summary = watcher.run("normal", state_path=sp, webhook_url=WEBHOOK, fetch_fn=fetch, send_fn=send2)

    assert send2.calls == []              # no duplicate posting
    assert summary["new"] == 0
    assert summary["posted"] == 0
    after = open(sp, "r", encoding="utf-8").read()
    assert before == after                # state unchanged


# --- Scenario 3: normal run with a brand-new relevant hit -------------------

def test_new_relevant_hit_is_posted_and_state_updated(tmp_path):
    sp = _state_path(tmp_path)

    # baseline
    watcher.run(
        "normal", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(make_candidates()), send_fn=Recorder(),
    )

    more = make_candidates() + [NEW_RELEVANT]
    send = Recorder()
    summary = watcher.run(
        "normal", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(more), send_fn=send,
    )

    assert len(send.calls) == 1           # exactly the one new hit
    assert send.calls[0][0] == WEBHOOK
    assert "t1-player-bundle" in send.calls[0][1]
    assert summary["new"] == 1
    assert summary["posted"] == 1
    assert summary["state_written"] is True

    st = state_mod.load_state(sp)
    assert len(st["seen"]) == 3           # two baseline + one new


def test_only_new_hits_are_posted_not_the_whole_set(tmp_path):
    sp = _state_path(tmp_path)
    watcher.run(
        "normal", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(make_candidates()), send_fn=Recorder(),
    )
    more = make_candidates() + [NEW_RELEVANT]
    send = Recorder()
    watcher.run(
        "normal", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(more), send_fn=send,
    )
    # The two already-known relevant items must NOT be re-posted.
    assert len(send.calls) == 1


# --- Scenario 4: dry run -----------------------------------------------------

def test_dry_run_sends_nothing_and_never_creates_state(tmp_path):
    sp = _state_path(tmp_path)
    send = Recorder()

    summary = watcher.run(
        "dry-run", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(make_candidates()), send_fn=send,
    )

    assert send.calls == []
    assert not os.path.exists(sp)         # state file never created
    assert summary["state_written"] is False


def test_dry_run_does_not_modify_existing_state(tmp_path):
    sp = _state_path(tmp_path)
    watcher.run(
        "normal", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(make_candidates()), send_fn=Recorder(),
    )
    before = open(sp, "r", encoding="utf-8").read()

    more = make_candidates() + [NEW_RELEVANT]
    send = Recorder()
    summary = watcher.run(
        "dry-run", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(more), send_fn=send,
    )

    assert send.calls == []
    assert open(sp, "r", encoding="utf-8").read() == before   # unchanged
    assert summary["state_written"] is False
    assert summary["new"] == 1            # reports it WOULD post the new hit


# --- Scenario 5: --test-webhook-random-riftbound ----------------------------

def test_test_webhook_sends_exactly_one_and_leaves_state_untouched(tmp_path):
    sp = _state_path(tmp_path)
    send = Recorder()

    summary = watcher.run(
        "test-webhook-random-riftbound", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(make_candidates()), send_fn=send,
    )

    assert len(send.calls) == 1           # exactly ONE test message
    assert "riftbound" in send.calls[0][1].lower()   # chosen hit is a Riftbound one
    assert not os.path.exists(sp)         # state never touched
    assert summary["posted"] == 1
    assert summary["state_written"] is False


def test_test_webhook_with_no_riftbound_hit_aborts_cleanly(tmp_path):
    sp = _state_path(tmp_path)
    send = Recorder()
    items = [
        {"title": "New League of Legends hoodie", "url": "https://merch.riotgames.com/lol-hoodie",
         "source": "https://merch.riotgames.com/", "text": ""},
    ]

    summary = watcher.run(
        "test-webhook-random-riftbound", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(items), send_fn=send,
    )

    assert send.calls == []               # nothing sent
    assert not os.path.exists(sp)         # state unchanged
    assert summary["posted"] == 0
    assert summary["state_written"] is False


# --- Scenario 6: relevance filter (positive / negative) ---------------------

POSITIVE_TITLES = [
    "Riftbound x T1 Worlds Champion Collection now live",
    "Worlds Champion Collection revealed",
    "T1 Signature Edition set details",
    "T1 Player Bundle available now",
    "New Faker Galio card revealed for Riftbound",
    "Gumayusi and Keria featured in the T1 collection",
    "Riftbound x T1 Signature Edition drawing registration is open",
    "Riftbound T1 Worlds Champion Collection now in stock at the Riot merch store",
]

NEGATIVE_TITLES = [
    "Riot Games announces new anti-cheat system for League",
    "New League of Legends hoodie now in the merch store",
    "Patch 14.13 balance changes for League of Legends",
]


@pytest.mark.parametrize("title", POSITIVE_TITLES)
def test_relevance_positive_examples(title):
    import relevance
    assert relevance.is_relevant({"title": title, "text": "", "url": "", "source": ""}) is True


@pytest.mark.parametrize("title", NEGATIVE_TITLES)
def test_relevance_negative_examples(title):
    import relevance
    assert relevance.is_relevant({"title": title, "text": "", "url": "", "source": ""}) is False


def test_watcher_filters_to_relevant_only(tmp_path):
    """Given 4 candidates (2 relevant), the summary reports 2 relevant."""
    sp = _state_path(tmp_path)
    summary = watcher.run(
        "dry-run", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(make_candidates()), send_fn=Recorder(),
    )
    assert summary["checked"] == 4
    assert summary["relevant"] == 2


# --- Scenario 7: secret protection ------------------------------------------

def test_webhook_url_never_appears_in_logs_when_send_fails(tmp_path, caplog):
    sp = _state_path(tmp_path)
    # baseline first so the next run has a new item to post
    watcher.run(
        "normal", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(make_candidates()), send_fn=Recorder(),
    )

    def failing_send(webhook_url, content):
        raise notify.WebhookError("request failed")

    more = make_candidates() + [NEW_RELEVANT]
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(notify.WebhookError):
            watcher.run(
                "normal", state_path=sp, webhook_url=WEBHOOK,
                fetch_fn=fetch_fn_factory(more), send_fn=failing_send,
            )

    assert WEBHOOK not in caplog.text
    assert "FAKE_TOKEN_DO_NOT_USE" not in caplog.text


def test_webhook_url_never_appears_in_logs_on_success(tmp_path, caplog):
    sp = _state_path(tmp_path)
    with caplog.at_level(logging.DEBUG):
        watcher.run(
            "normal", state_path=sp, webhook_url=WEBHOOK,
            fetch_fn=fetch_fn_factory(make_candidates()), send_fn=Recorder(),
        )
    assert WEBHOOK not in caplog.text
    assert "FAKE_TOKEN_DO_NOT_USE" not in caplog.text


# --- Regression: corrupt state.json must re-baseline, not mass-post ---------

def test_corrupt_state_rebaselines_without_mass_posting(tmp_path):
    sp = _state_path(tmp_path)
    with open(sp, "w", encoding="utf-8") as fh:
        fh.write("{ this is not valid json ]]")

    send = Recorder()
    summary = watcher.run(
        "normal", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(make_candidates()), send_fn=send,
    )

    assert send.calls == []                 # NOT a mass re-post
    assert summary["posted"] == 0
    assert summary["state_written"] is True
    st = state_mod.load_state(sp)
    assert len(st["seen"]) == 2             # rewrote a clean baseline

    # A later run with a genuinely new hit posts only that one.
    more = make_candidates() + [NEW_RELEVANT]
    send2 = Recorder()
    watcher.run(
        "normal", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(more), send_fn=send2,
    )
    assert len(send2.calls) == 1


# --- Regression: unknown mode must not silently do a state-writing run ------

def test_unknown_mode_raises_value_error(tmp_path):
    with pytest.raises(ValueError):
        watcher.run(
            "dryrun",  # typo — not a real mode
            state_path=_state_path(tmp_path), webhook_url=WEBHOOK,
            fetch_fn=fetch_fn_factory(make_candidates()), send_fn=Recorder(),
        )


# --- Regression: main() reports run errors without leaking the webhook ------

def test_main_redacts_error_and_returns_nonzero(monkeypatch, caplog):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", WEBHOOK)

    def boom(*args, **kwargs):
        raise RuntimeError("failed talking to " + WEBHOOK)

    monkeypatch.setattr(watcher, "run", boom)
    with caplog.at_level(logging.ERROR):
        rc = watcher.main([])
    assert rc == 1
    assert "FAKE_TOKEN_DO_NOT_USE" not in caplog.text


# --- Optional .env loading for the webhook (main-level resolution) ----------
# Fake values that are NOT real Discord URLs and contain no placeholder markers,
# so they are treated as "configured" without tripping the repo secret scan.
ENV_FAKE = "https://hooks.example.test/env-value"
DOTENV_FAKE = "https://hooks.example.test/dotenv-value"
# A copied-but-unedited .env value still carrying the REPLACE_ME placeholder.
PLACEHOLDER_WEBHOOK = "https://discord.com/api/webhooks/REPLACE_ME/REPLACE_ME"


def _capture_run_webhook(monkeypatch):
    """Replace watcher.run with a stub that records the webhook_url it receives."""
    captured = {}

    def capture(mode, **kwargs):
        captured["mode"] = mode
        captured["webhook_url"] = kwargs.get("webhook_url")
        captured["targets"] = kwargs.get("targets")
        return watcher._new_summary(mode)

    monkeypatch.setattr(watcher, "run", capture)
    return captured


def test_main_env_var_takes_precedence_over_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", ENV_FAKE)
    (tmp_path / ".env").write_text("DISCORD_WEBHOOK_URL=" + DOTENV_FAKE, encoding="utf-8")
    captured = _capture_run_webhook(monkeypatch)
    assert watcher.main(["--dry-run"]) == 0
    assert captured["webhook_url"] == ENV_FAKE   # env wins over .env


def test_main_falls_back_to_dotenv_when_env_unset(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    (tmp_path / ".env").write_text("DISCORD_WEBHOOK_URL=" + DOTENV_FAKE, encoding="utf-8")
    captured = _capture_run_webhook(monkeypatch)
    assert watcher.main(["--dry-run"]) == 0
    assert captured["webhook_url"] == DOTENV_FAKE   # loaded from local .env


def test_main_no_env_and_no_dotenv_resolves_to_none(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    captured = _capture_run_webhook(monkeypatch)
    assert watcher.main(["--dry-run"]) == 0
    assert captured["webhook_url"] is None


def test_main_placeholder_dotenv_is_treated_as_unconfigured(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    (tmp_path / ".env").write_text(
        "DISCORD_WEBHOOK_URL=" + PLACEHOLDER_WEBHOOK, encoding="utf-8"
    )
    captured = _capture_run_webhook(monkeypatch)
    assert watcher.main(["--dry-run"]) == 0
    assert captured["webhook_url"] is None   # REPLACE_ME placeholder is not usable


def test_main_dotenv_webhook_value_never_logged(monkeypatch, tmp_path, caplog):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    (tmp_path / ".env").write_text("DISCORD_WEBHOOK_URL=" + DOTENV_FAKE, encoding="utf-8")
    _capture_run_webhook(monkeypatch)
    with caplog.at_level(logging.DEBUG):
        assert watcher.main(["--test-webhook-random-riftbound"]) == 0
    assert DOTENV_FAKE not in caplog.text
    assert "dotenv-value" not in caplog.text


def test_main_test_webhook_sends_once_via_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    (tmp_path / ".env").write_text("DISCORD_WEBHOOK_URL=" + DOTENV_FAKE, encoding="utf-8")
    # Keep it fully offline: fake the fetch and the Discord sender at module level.
    monkeypatch.setattr(fetch, "fetch_targets", lambda targets=None: list(make_candidates()))
    recorder = Recorder()
    monkeypatch.setattr(notify, "send_discord", recorder)

    assert watcher.main(["--test-webhook-random-riftbound"]) == 0
    assert len(recorder.calls) == 1                     # exactly one test message
    assert recorder.calls[0][0] == DOTENV_FAKE          # webhook came from .env
    assert not os.path.exists(str(tmp_path / "state.json"))   # state untouched


def test_main_dry_run_without_env_or_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(fetch, "fetch_targets", lambda targets=None: list(make_candidates()))
    recorder = Recorder()
    monkeypatch.setattr(notify, "send_discord", recorder)

    assert watcher.main(["--dry-run"]) == 0
    assert recorder.calls == []                          # no send
    assert not os.path.exists(str(tmp_path / "state.json"))   # no state written


# --- Best clickable link in the Discord message -----------------------------

def test_normal_run_message_contains_best_product_url(tmp_path):
    sp = _state_path(tmp_path)
    # baseline first
    watcher.run(
        "normal", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(make_candidates()), send_fn=Recorder(),
    )
    product = {
        "title": "Riftbound T1 WCC box",
        "url": "https://merch.riotgames.com/products/riftbound-t1-wcc-box",
        "source": "https://www.riftbound.com/",
        "text": "",
    }
    send = Recorder()
    summary = watcher.run(
        "normal", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(make_candidates() + [product]), send_fn=send,
    )
    assert len(send.calls) == 1
    content = send.calls[0][1]
    assert "https://merch.riotgames.com/products/riftbound-t1-wcc-box" in content
    assert summary["posted"] == 1


def test_product_link_preferred_over_general_source(tmp_path):
    sp = _state_path(tmp_path)
    watcher.run(
        "normal", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(make_candidates()), send_fn=Recorder(),
    )
    item = {
        "title": "Riftbound T1 collection",
        "url": "https://merch.riotgames.com/collections/riftbound-t1",
        "source": "https://www.leagueoflegends.com/en-us/news/",
        "text": "",
    }
    send = Recorder()
    watcher.run(
        "normal", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(make_candidates() + [item]), send_fn=send,
    )
    assert len(send.calls) == 1
    content = send.calls[0][1]
    assert "https://merch.riotgames.com/collections/riftbound-t1" in content
    # the general news source page must NOT be the emitted link
    assert "leagueoflegends.com/en-us/news" not in content


def test_test_webhook_message_contains_clickable_riftbound_link(tmp_path):
    sp = _state_path(tmp_path)
    item = {
        "title": "Riftbound x T1 Worlds Champion Collection",
        "url": "https://merch.riotgames.com/products/riftbound-t1-wcc",
        "source": "https://merch.riotgames.com/",
        "text": "",
    }
    send = Recorder()
    summary = watcher.run(
        "test-webhook-random-riftbound", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory([item]), send_fn=send,
    )
    assert len(send.calls) == 1
    content = send.calls[0][1]
    assert "http" in content
    assert "https://merch.riotgames.com/products/riftbound-t1-wcc" in content
    assert "riftbound" in content.lower()
    assert not os.path.exists(sp)
    assert summary["posted"] == 1


def test_test_webhook_skips_riftbound_without_usable_link(tmp_path):
    sp = _state_path(tmp_path)
    # Riftbound by title, but no usable link at all → must be skipped (clean abort).
    item = {"title": "Riftbound T1 drop", "url": "", "source": "", "text": ""}
    send = Recorder()
    summary = watcher.run(
        "test-webhook-random-riftbound", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory([item]), send_fn=send,
    )
    assert send.calls == []
    assert summary["posted"] == 0
    assert not os.path.exists(sp)


# --- Configurable watch targets (WATCH_TARGETS env / DEFAULT_TARGETS) --------

# The primary merch shop target is the (non-sorted) Riftbound category page.
MERCH_CATEGORY_URL = "https://merch.riotgames.com/de-de/category/riftbound/"
# The newest-first sorted variant (used as a WATCH_TARGETS override in a test).
MERCH_RIFTBOUND_URL = (
    "https://merch.riotgames.com/de-de/category/riftbound/?page=1&sort=dateDesc"
)


def test_main_defaults_to_default_targets(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("WATCH_TARGETS", raising=False)
    captured = _capture_run_webhook(monkeypatch)
    assert watcher.main(["--dry-run"]) == 0
    assert captured["targets"] == fetch.DEFAULT_TARGETS
    # The primary target is the Riot merch Riftbound category page (non-sorted).
    assert captured["targets"][0] == MERCH_CATEGORY_URL


def test_main_uses_watch_targets_env_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("WATCH_TARGETS", MERCH_RIFTBOUND_URL)
    captured = _capture_run_webhook(monkeypatch)
    assert watcher.main(["--dry-run"]) == 0
    assert captured["targets"] == [MERCH_RIFTBOUND_URL]


# --- Shop/merch focus: only real Riot merch items are watched / sent ---------

GET_STARTED_ITEM = {
    "title": "HOW TO PLAY",
    "url": "https://www.riftbound.com/en-us/get-started/",
    "source": "https://www.riftbound.com/",
    "text": "",
}
MERCH_PRODUCT_ITEM = {
    "title": "Riftbound x T1 Worlds Champion Collection",
    "url": "https://merch.riotgames.com/de-de/category/riftbound/riftbound-t1-wcc",
    "source": "https://merch.riotgames.com/de-de/category/riftbound/",
    "text": "",
}


def test_test_webhook_skips_get_started_article(tmp_path):
    # A get-started / how-to-play page is a Riftbound link but NOT a shop item.
    sp = _state_path(tmp_path)
    send = Recorder()
    summary = watcher.run(
        "test-webhook-random-riftbound", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory([GET_STARTED_ITEM]), send_fn=send,
    )
    assert send.calls == []          # "HOW TO PLAY" must never be sent
    assert summary["posted"] == 0
    assert not os.path.exists(sp)


def test_test_webhook_prefers_merch_shop_candidate(tmp_path):
    sp = _state_path(tmp_path)
    send = Recorder()
    summary = watcher.run(
        "test-webhook-random-riftbound", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory([GET_STARTED_ITEM, MERCH_PRODUCT_ITEM]), send_fn=send,
    )
    assert len(send.calls) == 1
    content = send.calls[0][1]
    assert "merch.riotgames.com" in content   # a shop/product link
    assert "get-started" not in content       # not the general article
    assert summary["posted"] == 1
    assert not os.path.exists(sp)


def test_normal_run_does_not_post_get_started_article(tmp_path):
    sp = _state_path(tmp_path)
    # Baseline with a merch product.
    watcher.run(
        "normal", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory([MERCH_PRODUCT_ITEM]), send_fn=Recorder(),
    )
    # Later run adds a get-started article (relevant via 'riftbound' in the url),
    # but it is not a shop item, so nothing new should be posted.
    send = Recorder()
    summary = watcher.run(
        "normal", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory([MERCH_PRODUCT_ITEM, GET_STARTED_ITEM]), send_fn=send,
    )
    assert send.calls == []
    assert summary["posted"] == 0


def test_normal_run_posts_new_merch_shop_item(tmp_path):
    sp = _state_path(tmp_path)
    watcher.run(
        "normal", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory([MERCH_PRODUCT_ITEM]), send_fn=Recorder(),
    )
    new_product = {
        "title": "T1 Player Bundle",
        "url": "https://merch.riotgames.com/de-de/category/riftbound/t1-player-bundle",
        "source": "https://merch.riotgames.com/de-de/category/riftbound/",
        "text": "",
    }
    send = Recorder()
    summary = watcher.run(
        "normal", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory([MERCH_PRODUCT_ITEM, new_product]), send_fn=send,
    )
    assert len(send.calls) == 1
    assert "t1-player-bundle" in send.calls[0][1]
    assert summary["posted"] == 1


# --- Test-webhook prefers available / pre-order merch items ------------------

AVAILABLE_MERCH = {
    "title": "Riftbound T1 Signature Edition",
    "url": "https://merch.riotgames.com/de-de/category/riftbound/signature-edition",
    "source": "https://merch.riotgames.com/de-de/category/riftbound/",
    "text": "In stock — available now",
}
PREORDER_MERCH = {
    "title": "Riftbound T1 Player Bundle",
    "url": "https://merch.riotgames.com/de-de/category/riftbound/player-bundle",
    "source": "https://merch.riotgames.com/de-de/category/riftbound/",
    "text": "Pre-order",
}
SOLDOUT_MERCH = {
    "title": "Riftbound Worlds Champion Collection",
    "url": "https://merch.riotgames.com/de-de/category/riftbound/worlds-champion-collection",
    "source": "https://merch.riotgames.com/de-de/category/riftbound/",
    "text": "Sold out",
}
UNKNOWN_MERCH = {
    "title": "Riftbound T1 Deck Box",
    "url": "https://merch.riotgames.com/de-de/category/riftbound/deck-box",
    "source": "https://merch.riotgames.com/de-de/category/riftbound/",
    "text": "",
}


def test_test_webhook_prefers_available_over_sold_out(tmp_path):
    sp = _state_path(tmp_path)
    send = Recorder()
    summary = watcher.run(
        "test-webhook-random-riftbound", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory([SOLDOUT_MERCH, AVAILABLE_MERCH]), send_fn=send,
    )
    assert len(send.calls) == 1
    content = send.calls[0][1]
    assert "signature-edition" in content                 # the available item
    assert "worlds-champion-collection" not in content    # not the sold-out one
    assert summary["posted"] == 1
    assert not os.path.exists(sp)


def test_test_webhook_prefers_preorder_over_unknown(tmp_path):
    sp = _state_path(tmp_path)
    send = Recorder()
    watcher.run(
        "test-webhook-random-riftbound", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory([UNKNOWN_MERCH, PREORDER_MERCH]), send_fn=send,
    )
    assert len(send.calls) == 1
    content = send.calls[0][1]
    assert "player-bundle" in content                     # the pre-order item
    assert "pre-order" in content.lower()


def test_test_webhook_unknown_availability_is_marked_not_confirmed(tmp_path):
    sp = _state_path(tmp_path)
    send = Recorder()
    summary = watcher.run(
        "test-webhook-random-riftbound", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory([UNKNOWN_MERCH]), send_fn=send,
    )
    assert len(send.calls) == 1
    content = send.calls[0][1]
    assert "availability not confirmed" in content        # honest fallback
    assert "in stock" not in content.lower()              # never falsely claims availability
    assert "deck-box" in content
    assert summary["posted"] == 1
    assert not os.path.exists(sp)


def test_test_webhook_prefers_available_merch_over_get_started(tmp_path):
    sp = _state_path(tmp_path)
    send = Recorder()
    watcher.run(
        "test-webhook-random-riftbound", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory([GET_STARTED_ITEM, AVAILABLE_MERCH]), send_fn=send,
    )
    assert len(send.calls) == 1
    content = send.calls[0][1]
    assert "merch.riotgames.com" in content
    assert "get-started" not in content


def test_test_webhook_only_articles_aborts_cleanly_with_log(tmp_path, caplog):
    sp = _state_path(tmp_path)
    send = Recorder()
    with caplog.at_level(logging.INFO):
        summary = watcher.run(
            "test-webhook-random-riftbound", state_path=sp, webhook_url=WEBHOOK,
            fetch_fn=fetch_fn_factory([GET_STARTED_ITEM]), send_fn=send,
        )
    assert send.calls == []
    assert summary["posted"] == 0
    assert not os.path.exists(sp)
    assert "no riftbound shop/product link" in caplog.text.lower()


def test_test_webhook_sends_product_extracted_from_embedded_json(tmp_path):
    # End-to-end: real HTML with embedded product JSON -> fetch.extract_items ->
    # watcher picks a shop product and sends exactly one message with its link.
    import json
    product = {
        "id": "1", "title": "Riftbound Unleashed Vault", "sku": "1",
        "slug": "riftbound-unleashed-vault",
        "ip": {"label": "Riftbound", "slug": "riftbound"},
        "contentType": "product", "availability": "available",
    }
    blob = json.dumps([product], separators=(",", ":")).replace('"', '\\"')
    html = '<html><body><script>self.__next_f.push([1,"' + blob + '"])</script></body></html>'
    src = "https://merch.riotgames.com/de-de/category/riftbound/"
    sp = _state_path(tmp_path)
    send = Recorder()
    summary = watcher.run(
        "test-webhook-random-riftbound", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=lambda t=None: fetch.extract_items(src, html), send_fn=send,
    )
    assert len(send.calls) == 1
    content = send.calls[0][1]
    assert "https://merch.riotgames.com/de-de/product/riftbound-unleashed-vault" in content
    assert summary["posted"] == 1
    assert not os.path.exists(sp)


# --- Status report (heartbeat) mode -----------------------------------------

GENERIC_AVAILABLE_MERCH = {
    "title": "Riftbound Unleashed Vault",
    "url": "https://merch.riotgames.com/de-de/product/riftbound-unleashed-vault",
    "source": "https://merch.riotgames.com/de-de/category/riftbound/",
    "text": "available Riftbound",
}


def test_status_report_sends_one_message_without_links_and_no_state(tmp_path):
    sp = _state_path(tmp_path)
    send = Recorder()
    summary = watcher.run(
        "status-report", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory([GENERIC_AVAILABLE_MERCH]), send_fn=send,
    )
    assert len(send.calls) == 1
    content = send.calls[0][1]
    assert "[STATUS]" in content
    assert "http://" not in content and "https://" not in content   # NO links
    assert "Riftbound Unleashed Vault" in content                    # available item
    assert "No new Riftbound" in content                             # non-T1 status line
    assert summary["posted"] == 1
    assert not os.path.exists(sp)                                     # never writes state


def test_status_report_separates_available_from_unavailable_items(tmp_path):
    sp = _state_path(tmp_path)
    send = Recorder()
    watcher.run(
        "status-report", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory([GENERIC_AVAILABLE_MERCH, SOLDOUT_MERCH, UNKNOWN_MERCH]),
        send_fn=send,
    )
    content = send.calls[0][1]
    assert "Available Riftbound merch items:" in content

    # The available section holds only the available item.
    avail = content.split("Available Riftbound merch items:")[1].split(
        notify.UNAVAILABLE_HEADER
    )[0]
    assert "Riftbound Unleashed Vault" in avail            # available listed
    assert "Deck Box" not in avail                         # unknown NOT in available list
    assert "Worlds Champion Collection" not in avail       # sold-out NOT in available list

    # The sold-out item is now surfaced in its own section instead of vanishing.
    unavail = content.split(notify.UNAVAILABLE_HEADER)[1]
    assert "Worlds Champion Collection" in unavail

    # Counts are consistent: 3 detected = 1 available + 1 sold out + 1 unknown.
    assert "Detected Riftbound merch items: 3" in content
    assert "Available: 1" in content
    assert "Unavailable / sold out: 1" in content
    assert "Unknown: 1" in content


def test_status_report_without_webhook_aborts_cleanly(tmp_path):
    sp = _state_path(tmp_path)
    send = Recorder()
    summary = watcher.run(
        "status-report", state_path=sp, webhook_url=None,
        fetch_fn=fetch_fn_factory([GENERIC_AVAILABLE_MERCH]), send_fn=send,
    )
    assert send.calls == []
    assert summary["posted"] == 0
    assert not os.path.exists(sp)


# --- Daily heartbeat mode ----------------------------------------------------

def test_heartbeat_sends_one_short_message_without_links_and_no_state(tmp_path):
    sp = _state_path(tmp_path)
    send = Recorder()
    summary = watcher.run(
        "heartbeat", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory([GENERIC_AVAILABLE_MERCH]), send_fn=send,
    )
    assert len(send.calls) == 1
    content = send.calls[0][1]
    assert "[STATUS]" in content
    assert "heartbeat" in content.lower()
    assert "running" in content.lower()
    assert "http" not in content                         # NO links at all
    assert "Riftbound Unleashed Vault" not in content    # NO product titles
    assert summary["posted"] == 1
    assert not os.path.exists(sp)                         # never writes state


def test_heartbeat_reports_counts_from_relevant_merch(tmp_path):
    sp = _state_path(tmp_path)
    send = Recorder()
    watcher.run(
        "heartbeat", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory(
            [GENERIC_AVAILABLE_MERCH, PREORDER_MERCH, UNKNOWN_MERCH, SOLDOUT_MERCH]
        ),
        send_fn=send,
    )
    content = send.calls[0][1]
    assert "available: 1" in content
    assert "preorder: 1" in content
    assert "unknown: 1" in content


def test_heartbeat_without_webhook_aborts_cleanly(tmp_path):
    sp = _state_path(tmp_path)
    send = Recorder()
    summary = watcher.run(
        "heartbeat", state_path=sp, webhook_url=None,
        fetch_fn=fetch_fn_factory([GENERIC_AVAILABLE_MERCH]), send_fn=send,
    )
    assert send.calls == []
    assert summary["posted"] == 0
    assert not os.path.exists(sp)


def test_heartbeat_never_touches_state_or_new_hit_logic(tmp_path):
    sp = _state_path(tmp_path)
    # Pre-seed a baseline that does NOT contain the item we will fetch, so any
    # new-hit/diff logic WOULD react to it — the heartbeat must not.
    st = state_mod.load_state(sp)
    state_mod.record_items(st, [PREORDER_MERCH])
    state_mod.save_state(sp, st)
    snapshot = open(sp, "r", encoding="utf-8").read()

    send = Recorder()
    summary = watcher.run(
        "heartbeat", state_path=sp, webhook_url=WEBHOOK,
        fetch_fn=fetch_fn_factory([GENERIC_AVAILABLE_MERCH]), send_fn=send,
    )
    assert len(send.calls) == 1
    content = send.calls[0][1]
    assert "[STATUS]" in content
    # It is the heartbeat, NOT a new-hit notification.
    assert notify.MESSAGE_HEADER not in content
    assert summary["state_written"] is False
    # State file is byte-identical: no baseline write, no diff, no read-for-update.
    assert open(sp, "r", encoding="utf-8").read() == snapshot
