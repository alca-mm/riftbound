Date: 2026-07-06
Time: 08:47 Europe/Berlin
Branch: main
Commit: not recorded

# Audit riot watcher

Backend version: not applicable
Frontend/Userscript/App version changed: No
Server restart needed: No
Client/browser refresh needed: No
Config/migration/manual step needed: No

## Goal

Validate the freshly-created `riot` project against its specification and harden
it as a safe, notify-only watcher for the Riftbound × T1 Worlds Champion
Collection. Apply only necessary corrections (no large refactors, no new
features), test-driven, keeping existing tests green.

## User-Reported Problem

No runtime bug was reported. This was a requested audit pass: verify the three
CLI modes and their side effects, the secret/notify-only guarantees, the
relevance filter breadth, state robustness, and the webhook path — then fix real
issues found.

## Files Changed

Production code (5 targeted fixes):
- `relevance.py` — fixed over-broad filter (champion/player tokens).
- `notify.py` — closed a DEBUG-log token leak and an exception-context leak.
- `state.py` — added `state_status()` to distinguish missing/valid/corrupt.
- `watcher.py` — corrupt-state re-baseline, unknown-mode guard, `main()` error backstop.
- `fetch.py` — reuse and close a single HTTP session (no per-URL session leak).

Tests (regression coverage; +17 tests, 98 → 115):
- `tests/test_relevance.py` — over-breadth negatives + anchored-conditional positives.
- `tests/test_notify.py` — split-URL leak + no-leaky-`__context__`.
- `tests/test_state.py` — `state_status` missing/valid/corrupt/wrong-schema.
- `tests/test_watcher.py` — corrupt-state re-baseline, unknown-mode raises, `main()` redacts + exits 1.
- `tests/test_fetch.py` — single reused session, self-created session closed.

Docs:
- `docs/changes/2026-07-06-0847-audit-riot-watcher.md` — this note.
- `README.md` — reviewed, already complete (setup, `DISCORD_WEBHOOK_URL`, all three
  modes, first-run baseline, dry-run/test-webhook no-state, safety boundaries,
  don't-commit `.env`/`state.json`); no change required.

## Implementation Details

Findings came from three parallel READ-ONLY audit subagents (CLI/flow;
security/secret/webhook; relevance/fetch/state). Each real finding got a
regression test written first (RED), then a minimal fix (GREEN).

1. **Relevance over-breadth (BUG).** `faker, galio, gumayusi, keria, oner, zeus,
   doran` were each relevant on their own, so generic League content ("Doran's
   Blade build guide", a "Galio" patch note, "Zeus streams tonight") was flagged;
   `oner` even matched the substring in "commissioner"/"toner". Fix: split into
   `STRONG_SUBJECTS` (riftbound, worlds champion collection, signature edition,
   player bundle, t1) that match alone, and `CONDITIONAL_SUBJECTS` (the
   champion/player tokens) that count only with a Riftbound/T1 anchor and are
   matched as whole words. `FOCUS_SUBJECTS` stays the union (public API/logging
   unchanged).

2. **Webhook token could leak at DEBUG (BUG).** `send_discord` logged
   `redact_secrets(str(exc), [webhook_url])`, but real `requests`/`urllib3`
   exceptions split the URL (host separate from `url: /path`), so replacing the
   full URL missed the bare token. Fix: log only `type(exc).__name__` (the pattern
   `fetch.py` already uses).

3. **Leaky exception context (HARDENING).** `raise WebhookError(...) from None`
   hides the rendered traceback but `__context__` still referenced the original
   URL-bearing exception. Fix: raise `WebhookError` outside the `except` block so
   `__context__`/`__cause__` are `None`.

4. **Corrupt `state.json` → mass re-post (borderline BUG).** `first_run` was
   derived from file existence, while `load_state` returns a fresh empty state on
   corruption; the two disagreed, so every relevant item was treated as new and
   posted at once. Fix: `state.state_status()` classifies missing/valid/corrupt;
   normal mode treats missing OR corrupt as a baseline (record + save, send
   nothing); dry-run mirrors it.

5. **`main()` error backstop (HARDENING).** Wrapped the `run()` call in `main()`
   with `try/except` that logs `redact_secrets(str(exc), [webhook_url])` and
   returns exit code 1, so no error can reach the user with a secret attached.

6. **Unknown mode guard (HARDENING).** `run()` now validates `mode` and raises
   `ValueError`, instead of letting a typo fall through to a real, state-writing
   normal run.

7. **HTTP session leak (HARDENING).** `fetch_targets` created a new
   `requests.Session` per URL and never closed it. Fix: create one session,
   reuse it across all targets, and close it in a `finally`; a caller-supplied
   session is left for the caller to close.

Deliberately NOT changed (out of scope / unnecessary): tuple connect/read
timeout, empty-key `item_id` collapse (unreachable — `extract_items` always
yields a non-empty URL), and the unused `filter_relevant` call in test-webhook
mode.

## Pipeline order

Unchanged: `fetch.fetch_targets` → `relevance.filter_relevant` → mode branch
(normal: baseline-or-corrupt → re-baseline & send nothing; else diff new →
`notify.send_discord` per new hit → record delivered → atomic save. dry-run:
compute + log, no send, no state. test-webhook: one random `is_riftbound` hit →
exactly one send, no state, clean abort if none). Summary logged with mode,
checked, relevant, new, posted, state_written.

## Tests

- Framework: `pytest`, strictly test-driven (17 new tests written RED first, then
  fixes to GREEN; the 2 anchored-conditional relevance tests passed immediately
  and stayed green).
- **Test count before:** 98 passing.
- **Test count after:** 115 passing.
- Final commands:
  - `python -m pytest tests/ -q` → `115 passed`
  - `python -m py_compile watcher.py fetch.py relevance.py state.py notify.py` → OK
- Also verified end-to-end: `python watcher.py --dry-run` runs against the live
  public pages (checked=63, relevant=24, posted=0, state_written=False, no
  `state.json` created).

## Manual Test Checklist

- [ ] `python -m pytest tests/ -q` → 115 passed.
- [ ] `python watcher.py --dry-run` → logs counts, sends nothing, creates no `state.json`.
- [ ] Corrupt `state.json` on purpose, then `python watcher.py` → logs a warning,
      rewrites a clean baseline, sends nothing (no mass re-post).
- [ ] Set `DISCORD_WEBHOOK_URL`, first `python watcher.py` → baseline, no send;
      run again with a genuinely new hit → exactly that one is posted.
- [ ] `python watcher.py --test-webhook-random-riftbound` → exactly one message,
      `state.json` unchanged; with zero Riftbound hits → clean abort, no send.
- [ ] Confirm no webhook URL appears anywhere in console logs (even at DEBUG).

## Required User Actions

- No migration and no new configuration. Behavior change to be aware of: a
  corrupt/invalid `state.json` is now safely re-baselined (a warning is logged and
  nothing is posted) instead of causing a burst of notifications.
- To actually send messages, the environment variable `DISCORD_WEBHOOK_URL` must
  be set (unchanged requirement; value never to be committed or shared). Dry-run
  needs no webhook.
- Git remains untouched — stage/commit yourself when ready.

## Known Limitations

- `DEFAULT_TARGETS` remains a small best-effort list of public pages; Riot may
  change page structure/URLs.
- Link extraction is intentionally shallow (stdlib anchor parsing), keying on
  link titles/URLs; the baseline mechanism prevents spam.
- The relevance filter now requires a Riftbound/T1 anchor for champion/player
  tokens; a hypothetical post that references only a champion with no Riftbound/T1
  wording would not be flagged (acceptable trade-off to avoid generic-LoL false
  positives).

## Next Recommended Improvements

- Optional `(connect, read)` tuple timeout in `fetch.py` for slow-drip servers.
- A `--targets-file` option to configure watched URLs without editing code.
- Persist `last_run`/per-target fetch status in state for observability.

## Autonomous Decisions Made

- Ran the three audit subagents READ-ONLY (analysis only) and applied all fixes
  from the main session, so agents could not conflict on shared files.
- Kept `FOCUS_SUBJECTS` as the strong+conditional union so the existing
  `test_focus_subjects_present` stays valid while the matching logic tightens.
- Made all champion/player tokens whole-word matched (not just `t1`) to kill the
  "commissioner"→"oner" substring hit.
- Treated a corrupt state file as a re-baseline (record + save, send nothing)
  rather than as an empty state, prioritizing "never spam" over "post immediately".
- Chose to fix the HTTP session leak (clear resource bug) but skip tuple-timeout
  and the unreachable empty-key `item_id` nit to honor "only necessary changes".

## Git note
No git commands were run. Per project rule, all Git is done manually by the user.
