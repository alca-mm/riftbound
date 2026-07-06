Date: 2026-07-06
Time: 08:15 Europe/Berlin
Branch: main
Commit: not recorded

# Create riot watcher

Backend version: not applicable
Frontend/Userscript/App version changed: No
Server restart needed: No
Client/browser refresh needed: No
Config/migration/manual step needed: Yes

## Goal

Create a new, small Python project `riot`: a **notify-only** watcher that
observes public Riot / Riftbound pages and sends a Discord webhook notification
when something new and relevant to the **Riftbound × T1 Worlds Champion
Collection** appears (Riftbound, T1, Signature Edition, Player Bundle,
Faker/Galio and other T1 references, drawing/lottery/availability in the Riot
merch store). The bot only notifies — it never buys, logs in, checks out, solves
captchas, bypasses rate limits, scrapes aggressively, or exposes secrets.

## User-Reported Problem

Not a bug fix — this is a new project created from a specification. The user
wanted a safe, minimal watcher for the Riftbound × T1 collection that notifies
via Discord without any automated purchasing or account interaction.

## Files Changed

New files (all created; nothing pre-existing was modified):

- `watcher.py` — CLI + orchestration (fetch → relevance → state → notify), three modes.
- `fetch.py` — defensive public-page fetching + stdlib link extraction.
- `relevance.py` — narrow Riftbound × T1 relevance filter.
- `state.py` — robust, atomic state persistence + stable item ids.
- `notify.py` — Discord webhook sender + secret redaction.
- `requirements.txt` — runtime dependency: `requests`.
- `.gitignore` — excludes `.env`, `state.json`, `__pycache__/`, `.pytest_cache/`, `.venv/`/`venv/`/`env/`.
- `state.example.json` — dummy example state (no secrets).
- `README.md` — setup, modes, environment variable, security boundaries.
- `tests/test_fetch.py`, `tests/test_relevance.py`, `tests/test_state.py`,
  `tests/test_notify.py`, `tests/test_watcher.py` — pytest suite.
- `tests/__init__.py` — makes `tests` a package.
- `docs/changes/2026-07-06-0815-create-riot-watcher.md` — this change note.

## Implementation Details

- **Modules kept small and decoupled.** `relevance.py`, `state.py`, `notify.py`
  and `fetch.py` are independent leaf modules; `watcher.py` wires them together
  via dependency injection (`fetch_fn`, `send_fn`, `rng`) so the whole flow is
  testable without any network or real Discord call.
- **Relevance filter (narrow focus).** An item is relevant iff its combined
  lowercased title+text+url contains at least one focus subject: `riftbound`,
  `worlds champion collection`, `signature edition`, `player bundle`, `faker`,
  `galio`, `t1` (whole-word only, via `\bt1\b`), or a known T1 player
  (`gumayusi`, `keria`, `oner`, `zeus`, `doran`). Drawing/lottery and
  availability terms are recognized for richer logging but are **not** sufficient
  on their own — so generic merch/League news without a focus subject is
  correctly rejected.
- **State.** Stable item id = sha256 of the normalized url (title fallback).
  Reads are robust (missing/corrupt/invalid → fresh baseline + warning, never
  raises). Writes are atomic (temp file + fsync + `os.replace`).
- **Discord/security.** `send_discord` posts `{"content": …}`, single attempt,
  no retry loop, honors a timeout, imports `requests` lazily. On failure it
  raises `WebhookError` with a generic reason and `raise … from None` so the URL
  cannot resurface via a traceback; any debug log is passed through
  `redact_secrets` first. The webhook URL is never logged, raised, or written to
  state.
- **HTTP is defensive.** One GET per target, sequentially (no parallelism), a
  clear honest `User-Agent`, a sensible timeout, and no retry loops. Non-200 /
  errors return `None` and are skipped.

## Pipeline order

1. `fetch.fetch_targets()` → list of candidate items `{title,url,source,text}`.
2. `relevance.filter_relevant()` → keep only Riftbound × T1 hits.
3. Mode branch:
   - **normal:** first run → write baseline to `state.json`, send nothing;
     later runs → `state.new_items()` → post each new hit via
     `notify.send_discord()` → record delivered items → atomic `save_state()`.
   - **dry-run:** compute + log what would be posted; never send, never write state.
   - **test-webhook-random-riftbound:** pick one random `is_riftbound` hit →
     send exactly one message; never write state; clean abort if none.
4. Summary logged: mode, checked, relevant, new, posted, state_written.

## Tests

- Framework: `pytest`. Approach: strictly test-driven (RED → GREEN per module).
- **Test count before:** 0 (new project).
- **Test count after:** 98 passing.
  - `tests/test_fetch.py`: 12
  - `tests/test_relevance.py`: 22
  - `tests/test_state.py`: 27
  - `tests/test_notify.py`: 15
  - `tests/test_watcher.py`: 22
- Commands run at the end:
  - `python -m pytest tests/ -q` → `98 passed`
  - `python -m py_compile watcher.py` → OK (also compiled the four other modules).
- Coverage of required scenarios: first-run baseline (no send, state written),
  second run without new hits (no send, no state change, no duplicates), new
  relevant hit posted + state updated (only new items posted), dry run (no send,
  no state created/modified), `--test-webhook-random-riftbound` (exactly one
  message, no state change, clean abort on zero Riftbound hits), relevance
  filter positive+negative examples, and secret protection (webhook URL never in
  logs or exceptions on success or failure).

## Manual Test Checklist

- [ ] `pip install -r requirements.txt`
- [ ] `python watcher.py --dry-run` → logs checked/relevant counts, sends
      nothing, creates no `state.json`.
- [ ] Set `DISCORD_WEBHOOK_URL`, then `python watcher.py` once → writes baseline
      `state.json`, sends nothing.
- [ ] `python watcher.py` again with no new hits → no message, no duplicate.
- [ ] `python watcher.py --test-webhook-random-riftbound` → exactly one test
      message in Discord, `state.json` unchanged.
- [ ] Confirm no webhook URL appears anywhere in the console logs.

## Required User Actions

- Set the `DISCORD_WEBHOOK_URL` environment variable before any real send
  (normal mode after the first baseline run, or the test-webhook mode). Do NOT
  commit it. Dry-run needs no webhook.
- Optionally schedule the normal watcher (e.g. cron / Task Scheduler) at a gentle
  interval. Keep it infrequent — this is a low-load, respectful watcher.
- Git is intentionally untouched: stage/commit/push yourself when ready.

## Known Limitations

- `DEFAULT_TARGETS` in `fetch.py` is a small, best-effort list of public pages;
  Riot may change page structure/URLs, which can change how many candidate links
  are found. Adjust the list as needed.
- Link extraction is intentionally simple (stdlib anchor parsing), so it keys off
  link titles/URLs rather than deep page semantics. The baseline mechanism keeps
  this from spamming: only items new since the last run are posted.
- On the very first real run there may be many pre-existing relevant links; these
  are absorbed silently into the baseline (by design) and never posted.
- No proxy/robots handling beyond a single respectful GET per target.

## Next Recommended Improvements

- Add a `--targets-file` option to configure watched URLs without editing code.
- Optional richer Discord embeds (thumbnail/price) instead of plain content.
- Persist a `last_run` timestamp and per-target fetch status in state for
  observability.
- Add a lightweight per-target politeness delay if the target list grows.

## Autonomous Decisions Made

- Split the code into small modules (`fetch`, `relevance`, `state`, `notify`,
  `watcher`) — allowed by the spec ("kleine Module … falls technisch sinnvoller")
  and required so three subagents could work in parallel on disjoint files
  without conflicts.
- Used dependency injection in `watcher.run()` so all end-to-end tests run with
  no network and no real Discord webhook.
- Relevance rule: focus subjects make an item relevant on their own; drawing/
  availability terms are treated as context signals (logged, not sufficient
  alone) so generic merch/League news is correctly rejected.
- `t1` is matched as a whole word to avoid false positives (e.g. "t100").
- Test-webhook mode selects from candidates where `is_riftbound` is true and
  prefixes the message with `[TEST]`.
- Normal mode does not rewrite `state.json` when there are no new hits (state is
  only changed when it actually changes).
- Chose a small `DEFAULT_TARGETS` set of public Riot/Riftbound pages.

## Git note
No git commands were run. Per project rule, all Git is done manually by the user.
