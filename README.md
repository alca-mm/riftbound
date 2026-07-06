# riot — Riftbound × T1 Discord Watcher

A small, **notify-only** Python watcher. It checks a handful of **public**
Riot / Riftbound pages and, when something new and relevant to the
**Riftbound × T1 Worlds Champion Collection** appears, posts a message to a
Discord webhook.

> **Start here for GitHub upload and Discord setup:** [`docs/SELF_SERVICE_SETUP.md`](docs/SELF_SERVICE_SETUP.md)

It focuses narrowly on:

- Riftbound
- T1
- Worlds Champion Collection
- Signature Edition
- Player Bundle
- Faker / Galio and other T1 player/champion references
- Drawing / lottery / availability in the Riot merch store

## Notifications

Each Discord notification contains the **best available clickable link**. A
direct product / Riot merch store / collection link is preferred; if no product
link is available, a relevant article / news / drawing / source link is used
instead. The bot does **not** open or buy anything automatically — you click the
link yourself.

## Security boundaries (what this bot does NOT do)

This project is deliberately limited. It **only notifies**. It does **not**, and
will not:

- ❌ buy anything automatically
- ❌ log in to any account
- ❌ perform a checkout
- ❌ solve or bypass captchas
- ❌ bypass rate limits
- ❌ scrape aggressively (one GET per target, sequentially, honest User-Agent)
- ❌ print or log secrets

The Discord webhook URL is treated as a **secret**. It is never written to logs,
exceptions, tests, state, or the change docs.

## Setup

Requires Python 3.9+ (developed on 3.12).

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate

pip install -r requirements.txt          # runtime dependency (requests)
pip install -r requirements-dev.txt      # dev extras (pytest) — only to run the tests
```

Copy `.env.example` to `.env` and set your real webhook there (`.env` is
git-ignored — **never commit it**), or set the environment variable directly
(never commit or share the value):

```bash
# Windows PowerShell
$env:DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/…"

# Linux/Mac
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/…"
```

| Environment variable  | Purpose                                   |
| --------------------- | ----------------------------------------- |
| `DISCORD_WEBHOOK_URL` | Discord webhook to send notifications to. |

> **Webhook resolution:** `DISCORD_WEBHOOK_URL` can be set either as a real
> environment variable **or** loaded from a local `.env` file. The environment
> variable **takes precedence** over `.env`. Copying `.env.example` to `.env` is
> allowed, but `.env` must **never** be committed. `.env.example` contains only
> placeholders — a value still containing `REPLACE_ME` is treated as **not
> configured**, so nothing is sent. `--dry-run` needs no webhook and works even
> without a `.env`, while `--test-webhook-random-riftbound` needs a real local
> webhook and sends exactly one test message.

## Modes

### Normal watcher

```bash
python watcher.py
```

- Checks the public target pages and detects relevant hits.
- **First ever run:** writes a baseline to `state.json` and sends **no** Discord
  message.
- **Later runs:** posts only **new** relevant hits and updates `state.json`.
- Already-known hits are never re-posted.
- `state.json` is only ever modified in this mode.

### Dry run

```bash
python watcher.py --dry-run
```

- Checks the pages and logs the relevance analysis.
- Sends **no** Discord message.
- Never creates or modifies `state.json`.
- Ideal for local testing without side effects.

### Webhook test with a random Riftbound hit

```bash
python watcher.py --test-webhook-random-riftbound
```

- Picks exactly **one** random Riftbound hit from the fetched public results.
- Sends exactly **one** Discord test message.
- Never modifies `state.json`.
- If no Riftbound hit is found, it aborts cleanly and logs clearly — without
  changing state.

Optional: `--state-path PATH` points at an alternative state file.

## Secrets & GitHub safety

- `DISCORD_WEBHOOK_URL` is a **secret** — never commit it and never paste it into
  the README, issues, logs, or screenshots.
- `.env` and `state.json` are git-ignored and must **never** be uploaded.
- A safe template with placeholders only is provided in
  [`.env.example`](.env.example).

See the dedicated guides:

- [`docs/DISCORD_WEBHOOK_SETUP.md`](docs/DISCORD_WEBHOOK_SETUP.md) — how to create
  and safely use a Discord webhook, and how to test locally.
- [`docs/GITHUB_UPLOAD.md`](docs/GITHUB_UPLOAD.md) — how to upload this project to
  GitHub yourself. All Git steps are run **only by you**, never by automation.

## State file

`state.json` stores the ids of items already seen so they are not re-posted. It
is created/updated only by the normal watcher. A dummy example of the schema is
in [`state.example.json`](state.example.json). The real `state.json` is
git-ignored.

State handling is robust: a missing file yields a fresh baseline, a
corrupt/invalid file is ignored (fresh baseline + a warning), and writes are
atomic (temp file + `os.replace`) so a crash never leaves a half-written file.

## Project layout

```
riot/
  watcher.py            # CLI + orchestration (fetch → relevance → state → notify)
  fetch.py              # defensive public-page fetching + link extraction
  relevance.py          # narrow Riftbound × T1 relevance filter
  state.py              # robust, atomic state persistence + stable item ids
  notify.py             # Discord webhook sender + secret redaction
  requirements.txt      # runtime dependency (requests)
  requirements-dev.txt  # dev extras (pytest)
  state.example.json    # dummy example state (no secrets)
  .env.example          # placeholder env template (copy to .env, never commit .env)
  .gitignore
  .github/workflows/    # CI: runs tests + compile (no secrets, never posts)
  docs/                 # DISCORD_WEBHOOK_SETUP.md, GITHUB_UPLOAD.md, changes/
  tests/                # pytest suite
```

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
python -m py_compile watcher.py fetch.py relevance.py state.py notify.py
```

The suite covers first-run baseline behavior, no-duplicate posting, posting only
new hits, dry-run isolation, the single-message test-webhook mode (including the
zero-Riftbound-hit case), the relevance filter (positive and negative examples),
and that the webhook URL never leaks into logs or exceptions.

On GitHub, [`.github/workflows/tests.yml`](.github/workflows/tests.yml) runs the
same tests and compile checks on every push and pull request. CI never runs the
watcher against real pages, never sends a Discord message, and needs no secrets.
