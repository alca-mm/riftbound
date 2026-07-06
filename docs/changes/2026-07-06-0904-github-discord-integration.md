Date: 2026-07-06
Time: 09:04 Europe/Berlin
Branch: main
Commit: not recorded

# GitHub and Discord integration prep

Backend version: not applicable
Frontend/Userscript/App version changed: No
Server restart needed: No
Client/browser refresh needed: No
Config/migration/manual step needed: Yes

## Goal

Make the existing `riot` watcher GitHub-ready and prepare a safe Discord webhook
integration, without executing any Git commands or creating any real secrets.
Only local project files were prepared and documented. The bot stays notify-only
(no auto-buy, login, checkout, captcha, or aggressive scraping).

## User-Reported Problem

None. This is a packaging/documentation step so the user can manually upload the
project to GitHub and safely configure a Discord webhook locally.

## Files Changed

New files:
- `.env.example` — placeholder-only env template (`DISCORD_WEBHOOK_URL=…/REPLACE_ME/REPLACE_ME`) with a "never commit `.env`" warning.
- `requirements-dev.txt` — `-r requirements.txt` + `pytest`.
- `.github/workflows/tests.yml` — test-only CI (pytest + py_compile), no secrets, no schedule, never runs the watcher.
- `docs/DISCORD_WEBHOOK_SETUP.md` — how to create/use a Discord webhook safely and test locally.
- `docs/GITHUB_UPLOAD.md` — manual GitHub-upload guide (all Git steps run only by the user).
- `tests/test_repo_hygiene.py` — `.gitignore` + no-real-secret + upload-doc guards.
- `tests/test_env_example.py` — `.env.example` placeholder + setup-doc guards.
- `tests/test_ci_workflow.py` — CI safety guards (no secrets/schedule/watcher run).
- `tests/test_readme.py` — README contract guards (modes, env var, safety, doc links).
- `docs/changes/2026-07-06-0904-github-discord-integration.md` — this note.

Modified files:
- `.gitignore` — kept all existing entries; added `.idea/`, `.mypy_cache/`, `.ruff_cache/`, `*.egg-info/`, `build/`, `dist/`, `.DS_Store`.
- `README.md` — added `.env.example`/`requirements-dev.txt` setup steps, a "Secrets & GitHub safety" section linking the two new docs, an updated project layout, and a CI note.

No production module (`watcher.py`, `fetch.py`, `relevance.py`, `state.py`,
`notify.py`) was changed — this step is packaging/docs only.

## Implementation Details

Work was fanned out to three parallel subagents on disjoint files, each working
test-driven (guard test written first → RED → file created → GREEN):
1. GitHub readiness/hygiene → `.gitignore`, `docs/GITHUB_UPLOAD.md`, `tests/test_repo_hygiene.py`.
2. Discord docs/secrets → `.env.example`, `docs/DISCORD_WEBHOOK_SETUP.md`, `tests/test_env_example.py`.
3. CI hardening → `.github/workflows/tests.yml`, `requirements-dev.txt`, `tests/test_ci_workflow.py`.
The main session then improved `README.md`, added `tests/test_readme.py`, ran the
full suite, and wrote this change note.

Safety properties enforced by the new guard tests:
- Every `discord.com/api/webhooks/` reference in tracked files is a placeholder
  (`REPLACE_ME`, `FAKE_TOKEN_DO_NOT_USE`, or an elided `…`) — no real secret.
- `.gitignore` excludes `.env`, `state.json`, `__pycache__/`, `.pytest_cache/`,
  `.venv/`, `venv/`, `env/`.
- `.env.example` contains only `REPLACE_ME` placeholders and a do-not-commit warning.
- CI references no `DISCORD_WEBHOOK_URL`, uses no `secrets.`, has no `schedule:`
  trigger, and never runs `python watcher.py` (only `py_compile`).
- README documents the three modes, the env var, the safety boundaries, the
  secret/Git rules, and links both docs.

## Pipeline order

Runtime pipeline is unchanged (fetch → relevance → state → notify). New CI
pipeline (GitHub Actions, on push/pull_request only): checkout → setup-python 3.12
→ `pip install -r requirements-dev.txt` → `python -m pytest tests/ -q` →
`python -m py_compile watcher.py fetch.py relevance.py state.py notify.py`.

## Tests

- Strictly test-driven; existing tests kept green.
- **Test count before:** 115 passing.
- **Test count after:** 143 passing (+28: repo-hygiene 5, env-example 9, ci-workflow 8, readme 6).
- Final commands:
  - `python -m pytest tests/ -q` → `143 passed`
  - `python -m py_compile watcher.py fetch.py relevance.py state.py notify.py` → OK
- Secret scan and CI-safety checks pass; no `state.json` and no `.env` present in the repo.

## Manual Test Checklist

- [ ] `pip install -r requirements-dev.txt` then `python -m pytest tests/ -q` → 143 passed.
- [ ] Read `docs/DISCORD_WEBHOOK_SETUP.md`; create a webhook in Discord; copy
      `.env.example` to `.env`; set `DISCORD_WEBHOOK_URL` locally (never commit).
- [ ] `python watcher.py --dry-run` → no message, no `state.json`.
- [ ] `python watcher.py --test-webhook-random-riftbound` → exactly one test
      message, `state.json` unchanged.
- [ ] `python watcher.py` (first run) → baseline only, no message.
- [ ] Read `docs/GITHUB_UPLOAD.md`; verify no `.env`/`state.json` before upload;
      run the Git steps yourself.

## Required User Actions

- Discord webhook setup needed: **Yes** — create a webhook and set the env var
  `DISCORD_WEBHOOK_URL` locally to actually send messages (never commit/share it).
- GitHub upload / manual git steps needed: **Yes** — follow `docs/GITHUB_UPLOAD.md`
  and run all Git commands yourself; do not upload `.env` or `state.json`.
- Config/migration/manual step needed: **Yes** — copy `.env.example` → `.env`
  and set the webhook locally; optionally schedule the watcher via cron / Task
  Scheduler at a gentle interval.
- Environment variable needed: `DISCORD_WEBHOOK_URL` (name only — never store the value).

## Known Limitations

- CI pins Python 3.12 and installs `requirements-dev.txt`; it intentionally does
  not run the watcher, so it validates code/tests only, not live fetching.
- The GitHub-upload guide gives Git commands as documentation examples; they are
  never executed here.
- No automated posting or scheduling is provided from GitHub Actions (by design).

## Next Recommended Improvements

- Add a CI status badge to the README once the repository URL is known.
- Optional: a lightweight `pre-commit` config (ruff/black) if desired later.
- Optional: matrix CI across multiple Python versions.

## Autonomous Decisions Made

- Added `requirements-dev.txt` (pytest) rather than putting pytest in the runtime
  `requirements.txt`, keeping runtime deps minimal.
- Added a test-only GitHub Actions workflow (no secrets, no schedule, no watcher
  run) since safe CI is clearly beneficial and low-risk.
- Kept README as the single integration hub (owned by the main session) so the
  three subagents never edited the same file.
- Added guard tests for docs/config invariants (env placeholders, `.gitignore`,
  CI safety, README contract) so regressions in packaging are caught by pytest.
- Left all production modules untouched (packaging/docs-only step).

## Git note
No git commands were run. Per project rule, all Git is done manually by the user.
