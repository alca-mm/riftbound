Date: 2026-07-06
Time: 09:11 Europe/Berlin
Branch: main
Commit: not recorded

# Final GitHub and Discord webhook preflight

Backend version: not applicable
Frontend/Userscript/App version changed: No
Server restart needed: No
Client/browser refresh needed: No
Config/migration/manual step needed: Yes

## Goal

Final safety/repo/usage preflight for `riot` before the user manually uploads it
to GitHub and uses it locally with a Discord webhook. Confirm the repo is safe to
upload, the Discord webhook usage is clearly documented and locally testable, and
the CI is inert. No Git commands executed, no secrets shown, no real webhook
values stored. The bot stays notify-only.

## User-Reported Problem

None. This is a pre-upload verification pass. The project was already created,
audited, and prepared for GitHub in prior steps.

## Files Changed

- `tests/test_ci_workflow.py` — added two CI-safety guard tests (least-privilege
  `permissions`, and triggers restricted to `push`/`pull_request` only). These
  close a regression gap: nothing previously prevented a future edit from widening
  permissions or adding an unsafe trigger (`workflow_dispatch`/`workflow_run`/
  `repository_dispatch`/`schedule`).
- `docs/changes/2026-07-06-0911-final-github-webhook-preflight.md` — this note.

No production module and no doc/config file needed changes — all three audits
came back clean (see below).

## Implementation Details

Three READ-ONLY audit subagents ran in parallel and reported; the main session
integrated the findings, ran the safe smoke tests, and added the two guard tests
test-first (they pass against the already-compliant workflow and now protect it).

Audit verdicts:
- **Repo & secret safety: SAFE TO UPLOAD (7/7 PASS).** `.gitignore` excludes
  `.env`, `state.json`, `__pycache__/`, `.pytest_cache/`, `.venv/`, `venv/`,
  `env/`. `.env.example` is placeholders-only. No real `.env` and no `state.json`
  on disk. All 17 `discord.com/api/webhooks/` occurrences in tracked files are
  placeholders (`REPLACE_ME`, `FAKE_TOKEN_DO_NOT_USE`, or elided `…`) — no real
  id/token anywhere. README/docs are placeholder-only. The workflow is inert.
- **Docs: PASS (all points).** `docs/DISCORD_WEBHOOK_SETUP.md` and
  `docs/GITHUB_UPLOAD.md` cover every required point, match the actual CLI
  behavior, and contain no secrets; README links both docs.
- **CI: SAFE.** `.github/workflows/tests.yml` runs only pytest + py_compile on
  push/pull_request, references no `DISCORD_WEBHOOK_URL`, uses no `secrets.`, has
  no `schedule:`, never runs `python watcher.py`, and uses `permissions: contents: read`.

## Pipeline order

Runtime pipeline unchanged (fetch → relevance → state → notify). CI pipeline
unchanged (checkout → setup-python 3.12 → install `requirements-dev.txt` → pytest
→ py_compile of the five modules).

## Tests

- Strictly test-driven; existing tests kept green.
- **Test count before:** 143 passing.
- **Test count after:** 145 passing (+2 CI-safety guard tests).
- Final commands:
  - `python -m pytest tests/ -q` → `145 passed`
  - `python -m py_compile watcher.py fetch.py relevance.py state.py notify.py` → OK
  - `python -m py_compile tests/*.py` → OK (all further Python files compile)

## Smoke Tests

- `python watcher.py --dry-run` → **RAN, safe.** Output: `checked=63 relevant=24
  new=0 posted=0 state_written=False`; no Discord message sent; **no `state.json`
  created or modified**. Exit code 0.
- `python watcher.py --test-webhook-random-riftbound` → **SKIPPED: env var not
  set.** `DISCORD_WEBHOOK_URL` was not present in the environment (checked without
  ever printing its value); per instructions it was not requested and the mode was
  not run. When set locally it sends exactly one `[TEST]` message and does not
  modify `state.json` (covered by existing tests
  `tests/test_watcher.py::test_test_webhook_sends_exactly_one_and_leaves_state_untouched`
  and `...with_no_riftbound_hit_aborts_cleanly`).
- Normal mode `python watcher.py` → **NOT run** (would create a real baseline);
  its behavior is covered by existing tests (first-run baseline/no-send, no
  duplicates, only-new-hits posted, corrupt-state re-baseline).

## Manual Test Checklist

- [ ] `pip install -r requirements-dev.txt` then `python -m pytest tests/ -q` → 145 passed.
- [ ] `python watcher.py --dry-run` → no message, no `state.json`.
- [ ] Create a webhook (see `docs/DISCORD_WEBHOOK_SETUP.md`); copy `.env.example`
      to `.env`; set `DISCORD_WEBHOOK_URL` locally (never commit/share it).
- [ ] `python watcher.py --test-webhook-random-riftbound` → exactly one test
      message; `state.json` unchanged.
- [ ] `python watcher.py` (first run) → baseline only, no message.
- [ ] Before upload, confirm `.env` and `state.json` are absent from what you push
      (see `docs/GITHUB_UPLOAD.md`); run all Git commands yourself.

## Required User Actions

- Server restart needed: No
- Frontend/client/browser refresh needed: No
- Config/migration/manual step needed: Yes — copy `.env.example` → `.env` and set
  the webhook locally; optionally schedule via cron / Task Scheduler at a gentle interval.
- Discord webhook setup needed: Yes — create a webhook and set `DISCORD_WEBHOOK_URL`
  locally to send messages (never commit/share the value).
- GitHub upload / manual git steps needed: Yes — follow `docs/GITHUB_UPLOAD.md`;
  run all Git commands yourself; do not upload `.env` or `state.json`.
- Environment variable needed: `DISCORD_WEBHOOK_URL` (name only — value never stored/shown).

## Known Limitations

- The live webhook send path was not exercised in this preflight because
  `DISCORD_WEBHOOK_URL` is intentionally not set here; it is covered by unit tests
  with injected fakes.
- The dry-run smoke test depends on live public pages; the `checked`/`relevant`
  counts vary with those pages and are informational only.

## Next Recommended Improvements

- Add a CI status badge to the README once the repository URL is known.
- Optional: harmonize placeholder style (`.../REPLACE_ME/REPLACE_ME`) across all
  docs for consistency (purely cosmetic; all current placeholders are safe).

## Autonomous Decisions Made

- Ran the three preflight subagents READ-ONLY and applied the only actionable
  finding (two CI-safety guard tests) from the main session.
- Did NOT run normal mode (would create a real baseline) and did NOT set or request
  `DISCORD_WEBHOOK_URL`; the webhook smoke test is documented as skipped.
- Made no doc/production changes since all audits were clean; kept the change
  surface to the two regression guards only.

## Git note
No git commands were run. Per project rule, all Git is done manually by the user.
