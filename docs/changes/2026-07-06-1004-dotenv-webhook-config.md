Date: 2026-07-06
Time: 10:04 Europe/Berlin
Branch: main
Commit: not recorded

# Dotenv webhook config

Backend version: not applicable
Frontend/Userscript/App version changed: No
Server restart needed: No
Client/browser refresh needed: No
Config/migration/manual step needed: Yes

## Goal

Make the local Discord-webhook integration practical: resolve `DISCORD_WEBHOOK_URL`
from the environment and, if it is not set there, optionally load it from a local
`.env` file — with the environment variable always taking precedence. A value that
still contains a placeholder (e.g. an unedited `REPLACE_ME`) is treated as "not
configured" so the watcher never tries to send with it. No real secrets are ever
created, shown, logged, or stored; the bot stays notify-only.

## User-Reported Problem

The docs told users to copy `.env.example` to `.env`, but the watcher only read
`DISCORD_WEBHOOK_URL` from the process environment, so `.env` had no effect and the
webhook test kept getting skipped ("env var not set"). This closes that gap.

## Files Changed

New:
- `config.py` — stdlib-only webhook resolver (`resolve_webhook_url`,
  `is_placeholder_webhook`, `parse_env_file`, `load_env_file`).
- `tests/test_config.py` — 27 unit tests for the resolver.
- `docs/changes/2026-07-06-1004-dotenv-webhook-config.md` — this note.

Modified:
- `watcher.py` — `main()` now resolves the webhook via `config.resolve_webhook_url()`
  and gates placeholders; the error backstop redacts both the gated and the raw
  resolved value; dropped the now-unused `import os`; docstring updated.
- `tests/test_watcher.py` — added `import fetch` and 7 integration tests for
  env-priority, `.env` fallback, none, placeholder gating, no-secret-leak, one-send
  via `.env`, and dry-run without env/`.env`.
- `tests/test_readme.py` — 2 doc-guard tests (README + setup doc mention optional
  `.env` and "takes precedence").
- `README.md` — added a "Webhook resolution" note (env or `.env`, env takes
  precedence, placeholder = not configured).
- `docs/DISCORD_WEBHOOK_SETUP.md` — added a "Local `.env` (optional)" subsection.

Unchanged (verified): `docs/GITHUB_UPLOAD.md` (already states `.env`/`state.json`
must not be uploaded), `.env.example` (placeholders only), `.gitignore`, CI.

## Implementation Details

- Resolution (in `config.py`), ENVIRONMENT-WINS:
  1. non-empty `DISCORD_WEBHOOK_URL` in the environment → used;
  2. else, if a local `.env` exists, its `DISCORD_WEBHOOK_URL` value → used;
  3. else `None`. Only that one key is ever consulted — no other `.env` key is
     exported. The resolver never mutates the environment, never creates a file,
     and never logs the value (only the env-var *name*).
- `.env` parsing is minimal and stdlib-only: `KEY=VALUE`, ignores blank/`#` lines,
  splits on the first `=`, strips one surrounding quote pair. No new dependency
  (no `python-dotenv`).
- Placeholder protection: `is_placeholder_webhook()` returns True for
  empty/whitespace values or any value containing `REPLACE_ME` /
  `FAKE_TOKEN_DO_NOT_USE` (case-insensitive). `main()` gates such values to `None`,
  so the test-webhook and normal modes treat them as "not configured".
- Secret-leak fix: gating a placeholder to `None` would have disarmed the existing
  error-redaction (redacting `[None]` redacts nothing), so `main()` now redacts
  BOTH `webhook_url` and the raw resolved value in its error backstop. `raw` is
  never logged directly — it only appears as an argument to `is_placeholder_webhook`
  and inside the redaction list.
- `run()` and its injectable `fetch_fn`/`send_fn`/`rng` signature are unchanged;
  this is a `main()`-local change plus a new leaf module.

## Pipeline order

Unchanged runtime pipeline (fetch → relevance → state → notify). New step at the
front of `main()`: resolve webhook (`config.resolve_webhook_url()`) → gate
placeholder (`is_placeholder_webhook`) → pass the usable URL (or `None`) into
`run(...)` exactly as before.

## Tests

- Test-driven; existing tests kept green. Two integration tests were RED first
  (`.env` fallback, one-send-via-`.env`), then GREEN after the change.
- **Test count before:** 145 passing.
- **Test count after:** 181 passing (+36: config 27, watcher 7, readme 2).
- Final commands:
  - `python -m pytest tests/ -q` → `181 passed`
  - `python -m py_compile watcher.py fetch.py relevance.py state.py notify.py config.py` → OK

## Smoke Tests

- `python watcher.py --dry-run` (no env var, no `.env`) → RAN: `checked=63
  relevant=24 new=0 posted=0 state_written=False`; no send; no `state.json`
  created; exit 0 — confirms the integrated `main()` still runs cleanly.
- `python watcher.py --test-webhook-random-riftbound` with a real webhook → not run
  here (no real webhook configured; none requested). Its `.env`-driven behavior
  (exactly one send, `state.json` unchanged) is covered by
  `tests/test_watcher.py::test_main_test_webhook_sends_once_via_dotenv`.
- No real `.env` was created; no `state.json` present; secret scan clean.

## Manual Test Checklist

- [ ] `python -m pytest tests/ -q` → 181 passed.
- [ ] Copy `.env.example` to `.env`, replace `REPLACE_ME` with your real webhook
      (never commit `.env`).
- [ ] `python watcher.py --dry-run` → no message, no `state.json` (works without `.env`).
- [ ] `python watcher.py --test-webhook-random-riftbound` → exactly one test
      message; `state.json` unchanged.
- [ ] Leave `.env` as the unedited placeholder → the watcher logs "placeholder …
      no messages can be sent" and sends nothing.
- [ ] Set `DISCORD_WEBHOOK_URL` in the shell → it overrides `.env`.

## Required User Actions

- Server restart needed: No
- Frontend/client/browser refresh needed: No
- Config/migration/manual step needed: Yes — create `.env` from `.env.example` and
  set your real webhook (or export `DISCORD_WEBHOOK_URL`); replace `REPLACE_ME`.
- Discord webhook setup needed: Yes — create a webhook and configure it locally.
- GitHub upload / manual git steps needed: Yes — run all Git commands yourself; do
  not upload `.env` or `state.json`.
- Environment variable needed: `DISCORD_WEBHOOK_URL` (name only — value never shown/stored).
- `.env` optional supported: Yes.

## Known Limitations

- The `.env` parser handles simple `KEY=VALUE` lines only (no interpolation,
  multiline, or `export` prefixes) — sufficient for the single webhook variable.
- Placeholder detection is marker-based (`REPLACE_ME`, `FAKE_TOKEN_DO_NOT_USE`); a
  syntactically wrong but non-placeholder URL is passed through to Discord, which
  simply fails the send (reported without leaking the value).
- Only `DISCORD_WEBHOOK_URL` is read from `.env`; other keys are ignored by design.

## Next Recommended Improvements

- Optional `--env-file PATH` flag to point at a non-default `.env` location.
- Optional one-line "webhook configured: yes/no" status in the startup log (never
  the value) for quick local diagnosis.

## Autonomous Decisions Made

- Implemented a small stdlib-only `config.py` rather than adding `python-dotenv`,
  keeping dependencies minimal.
- Treated placeholder values (`REPLACE_ME`/`FAKE_TOKEN_DO_NOT_USE`) as
  "not configured" so a copied-but-unedited `.env` never triggers a bad send.
- Redacted BOTH the gated and raw webhook values in `main()`'s error backstop to
  preserve the no-secret-leak guarantee after placeholder gating.
- Kept `run()` and all mode handlers unchanged; confined the change to `main()`
  plus the new module.
- Used only fake, non-Discord test values (`hooks.example.test/...`) and
  `REPLACE_ME` placeholders in tests so nothing trips the repo secret scan.

## Git note
No git commands were run. Per project rule, all Git is done manually by the user.
