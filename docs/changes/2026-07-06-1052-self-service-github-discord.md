Date: 2026-07-06
Time: 10:52 Europe/Berlin
Branch: main
Commit: not recorded

# Self-service GitHub and Discord setup

Backend version: not applicable
Frontend/Userscript/App version changed: No
Server restart needed: No
Client/browser refresh needed: No
Config/migration/manual step needed: Yes

## Goal

Prepare `riot` for fully self-service use: a single, practical walkthrough so the
user can — without any assistant — upload the project to GitHub, create a Discord
webhook, configure a local `.env`, run the webhook test, understand the first
baseline run, and operate the watcher safely. Documentation-only step; the bot
stays notify-only and no production module was changed.

## User-Reported Problem

The setup knowledge was spread across README, `DISCORD_WEBHOOK_SETUP.md`, and
`GITHUB_UPLOAD.md`. The user wanted one end-to-end guide to do everything alone.

## Files Changed

New:
- `docs/SELF_SERVICE_SETUP.md` — the standalone end-to-end guide (8 sections).
- `tests/test_self_service_setup.py` — 10 guard tests for the guide + README link.
- `docs/changes/2026-07-06-1052-self-service-github-discord.md` — this note.

Modified:
- `README.md` — added a prominent top pointer:
  "**Start here for GitHub upload and Discord setup:** [docs/SELF_SERVICE_SETUP.md]".

Unchanged: all production modules (`watcher.py`, `fetch.py`, `relevance.py`,
`state.py`, `notify.py`, `config.py`), `.env.example`, `.gitignore`, and the CI
workflow. No production code was touched.

## Implementation Details

Fanned out to three subagents on disjoint files: (1) wrote
`docs/SELF_SERVICE_SETUP.md`, (2) a READ-ONLY secret/repo-safety audit, (3) added
the README pointer. The main session then wrote the guard test against the actual
document content, ran the full suite, and wrote this note.

`docs/SELF_SERVICE_SETUP.md` sections:
1. Before the GitHub upload — never upload `.env`/`state.json`, no real webhook
   URLs in files, never share tokens, run tests locally, CI is test-only and never
   posts to Discord / never live-polls; read-only manual check commands allowed.
2. Do the GitHub upload manually — create the repo, check files, stage/commit/push,
   with ALL git/gh commands under the bold marker "Only run these yourself —
   automation must never run Git." Git is done only by the user.
3. Create a Discord webhook — step by step (Channel Settings → Integrations →
   Webhooks → New Webhook → Copy URL), keep it secret, placeholders only.
4. Configure a local `.env` — copy `.env.example` → `.env`, set
   `DISCORD_WEBHOOK_URL`, replace `REPLACE_ME`, never commit `.env`, shell env var
   takes precedence, unedited placeholder = not configured, `.env` optional.
5. Local test flow — exact order: install dev deps → pytest → `--dry-run` (no send,
   no state) → `--test-webhook-random-riftbound` (exactly one message with a
   clickable link, state unchanged, real webhook required) → first run (baseline,
   no message) → second run (only new hits, best clickable link).
6. Running / scheduling — gentle interval, no aggressive polling, no GitHub Action
   for real polling/posting, no auto-buy/login/checkout/captcha automation; cron /
   Task Scheduler only as optional manual hints.
7. Troubleshooting — baseline-first-run, `--dry-run` never sends, test needs a real
   local webhook, `REPLACE_ME` doesn't send, corrupt `state.json` re-baselines,
   fix false hits via relevance tests not scraping, run the webhook test first,
   "no new messages" can be correct.
8. Safety reminder — notify-only; no auto-buy/login/checkout/captcha/aggressive
   scraping; no secrets in GitHub; the user clicks product links manually.

The guide uses only `REPLACE_ME` placeholders; no real webhook value anywhere.

## Pipeline order

No runtime change. The watcher pipeline (fetch → relevance → state → notify,
best-link selection in the message) and the CI pipeline are unchanged.

## Tests

- Test-driven guard added; no production code changed.
- **Test count before:** 197 passing.
- **Test count after:** 207 passing (+10 self-service guard tests).
- The guard test asserts the guide mentions `DISCORD_WEBHOOK_URL`, "never commit"
  + `.env`, `state.json` not uploaded, `--dry-run`, `--test-webhook-random-riftbound`,
  `baseline`, `clickable link`, "Only run these yourself", the safety boundaries
  (auto-buy/login/checkout/captcha/aggressive scraping), "GitHub Actions are
  test-only" + "never post to Discord", contains no real webhook token, and that
  README links the guide.
- Final commands:
  - `python -m pytest tests/ -q` → `207 passed`
  - `python -m py_compile watcher.py fetch.py relevance.py state.py notify.py config.py` → OK
- A parallel READ-ONLY secret audit verified: no real webhook token in any tracked
  file (including the new guide), `.gitignore` complete, `.env.example`
  placeholders-only, no real `.env` / no `state.json` on disk, CI inert →
  verdict SAFE TO UPLOAD.

## Manual Test Checklist

- [ ] Open `docs/SELF_SERVICE_SETUP.md` and follow sections 1–8.
- [ ] `python -m pip install -r requirements-dev.txt` then `python -m pytest tests/ -q` → 207 passed.
- [ ] `python watcher.py --dry-run` → no message, no `state.json`.
- [ ] Configure `.env` (or export the env var), then
      `python watcher.py --test-webhook-random-riftbound` → exactly one message
      with a clickable link; `state.json` unchanged.
- [ ] `python watcher.py` (first run) → baseline only, no message.
- [ ] Before uploading, confirm `git status` does not list `.env` or `state.json`;
      run all Git commands yourself.

## Required User Actions

- Server restart needed: No
- Frontend/client/browser refresh needed: No
- Config/migration/manual step needed: Yes — copy `.env.example` → `.env` and set
  your webhook locally (or export `DISCORD_WEBHOOK_URL`); replace `REPLACE_ME`.
- Discord webhook setup needed: Yes — create a webhook and configure it locally.
- GitHub upload / manual git steps needed: Yes — follow `docs/SELF_SERVICE_SETUP.md`;
  run all Git commands yourself; never push `.env` or `state.json`.
- Environment variable needed: `DISCORD_WEBHOOK_URL` (name only — value never shown/stored).
- `.env` optional supported: Yes (unchanged; shell env var takes precedence).

## Known Limitations

- The guide's Git and cron/Task Scheduler commands are documentation examples only
  — nothing here executes them.
- The guide reflects the current CLI and behavior; if modes/flags change later, the
  guide and its guard test must be updated together.

## Next Recommended Improvements

- Optionally add a short screenshot-free diagram of the run order to the guide.
- Add a CI status badge to the README once the repository URL is known.

## Autonomous Decisions Made

- Kept all production modules untouched (documentation-only step, as instructed).
- Had the main session write the guard test against the actual guide content
  (rather than a subagent) to avoid fragile cross-agent phrase coordination.
- Reused the existing placeholder conventions (`REPLACE_ME`, elided `…`,
  `FAKE_TOKEN_DO_NOT_USE`) so the new file passes the repo secret scan.
- Made the guard test assertions robust (case-insensitive component substrings,
  needle built by concatenation) so they do not self-trigger the hygiene scan.

## Git note
No git commands were run. Per project rule, all Git is done manually by the user.
