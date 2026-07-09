# riot — Riftbound × T1 Discord Watcher

A small, **notify-only** Python watcher. It checks a handful of **public**
Riot / Riftbound pages and posts a message to a Discord webhook whenever a new
Riot merch **Riftbound shop item** appears. This README is the single source of
truth — everything you need to install it, use Discord, upload it to GitHub, and
run it on GitHub Actions is here.

**Primary watch focus — Riot merch shop items in the Riftbound category:**

```
https://merch.riotgames.com/de-de/category/riftbound/
```

The newest-first variant `…/riftbound/?page=1&sort=dateDesc` is also watched.

## What gets reported

The automatic watch reports **all new** Riot merch Riftbound **shop** items. It
is **not T1-only**.

- **Every** new Riftbound merch shop product is posted — a plain
  `Riftbound: Origins Champion Deck - Jinx` counts just as much as a T1 drop.
- A product still counts when its title or slug never spells out "Riftbound",
  as long as it is a product in the Riot merch Riftbound category.
- T1 items are **highlighted**, they are **not required**. A hit matching **T1**,
  **Worlds Champion Collection**, **Signature Edition**, **Player Bundle**,
  **Faker / Galio** or another T1 player/champion reference is posted with a 🔥
  highlight header and an extra `Match:` line. Everything else is posted with the
  plain header.

General Riftbound pages are **not** reported and are never sent to Discord:

- news / blog articles without a shop product
- newsletters
- "how to play" / get-started articles
- top decks

Both gates apply to every hit: it must be a **shop / product / merch** item
**and** it must be a Riftbound merch item.

## Notifications

Each new-hit Discord notification contains the **best available clickable link**.
A direct product / Riot merch store / collection link is preferred; if no product
link is available, a relevant article / news / drawing / source link is used
instead. The bot does **not** open or buy anything automatically — you click the
link yourself.

A normal new-hit message looks like this:

```
New Riftbound merch item found:
Riftbound: Origins Champion Deck - Jinx
https://merch.riotgames.com/de-de/product/riftbound-origins-champion-deck-jinx
Status: available
```

A highlighted (T1 / Worlds / Signature / Player Bundle / Faker / Galio) hit adds
the 🔥 header and a `Match:` line:

```
🔥 New highlighted Riftbound × T1 merch item found:
Riftbound x T1 Worlds Champion Collection
https://merch.riotgames.com/de-de/product/riftbound-t1-worlds-champion-collection
Match: t1, worlds champion collection
Status: available
```

The daily heartbeat carries **no links** — only counts. New-hit notifications
always carry the clickable link.

## How products are discovered

The Riot merch Riftbound category page loads its products client-side, but the
initial HTML **embeds the product data as JSON**, and the watcher parses that
**embedded product data** to find the real Riot merch Riftbound **products**
(product name, product URL like `https://merch.riotgames.com/de-de/product/<slug>`,
and availability when present). It also still reads visible product / shop links
from the page. It never uses a browser, never logs in, never buys — it only reads
public page data (the **embedded product data** JSON) and notifies. If no product
data is found in the HTML, the watcher finds nothing; you can set `WATCH_TARGETS`
to concrete product / collection URLs (for example a specific
`https://merch.riotgames.com/de-de/product/<slug>`) so the watcher and the
test-webhook have something to send.

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
exceptions, tests, workflows, or change files. You click product links manually.

## Local install

Requires Python 3.9+ (developed on 3.12).

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate

pip install -r requirements.txt          # runtime dependency (requests)
pip install -r requirements-dev.txt      # dev extras (pytest) — only to run the tests
python -m pytest tests/ -q               # everything should pass
```

## Create a Discord webhook

You need **Manage Webhooks** permission on the target server/channel.

1. Open Discord and go to the server and channel you want notifications in.
2. Open **Channel Settings** (the gear icon next to the channel name).
3. Go to **Integrations** → **Webhooks**.
4. Click **New Webhook** (optionally name it / confirm the channel).
5. Click **Copy Webhook URL**.

The copied URL looks like `https://discord.com/api/webhooks/…/…` — a numeric id
segment and a long token segment. **Both are secret.** Never post it in GitHub,
the README, issues, logs, or screenshots. If it ever leaks, delete the webhook in
Discord and create a new one.

## Configure the webhook locally (`.env`)

Set the webhook via the `DISCORD_WEBHOOK_URL` environment variable, or a local
`.env` file. Copy the placeholder template and edit the copy:

```bash
# Windows PowerShell
copy .env.example .env
# Linux/Mac
cp .env.example .env
```

Then set your real webhook in `.env`, replacing `REPLACE_ME`:

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/…/…
```

Or export it in your shell instead of using `.env`:

```bash
# Windows PowerShell
$env:DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/…"
# Linux/Mac
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/…"
```

| Environment variable  | Purpose                                   |
| --------------------- | ----------------------------------------- |
| `DISCORD_WEBHOOK_URL` | Discord webhook to send notifications to. |

Rules:

- The shell environment variable **takes precedence** over `.env`.
- **Never commit `.env`** (it is git-ignored). `.env.example` keeps only
  `REPLACE_ME` placeholders.
- A value still containing `REPLACE_ME` is treated as **not configured**, so
  nothing is sent.
- `--dry-run` needs no webhook and works even without a `.env`.

## Local modes

### Dry run

```bash
python watcher.py --dry-run
```

- Sends **no** Discord message.
- Never creates or modifies `state.json`.
- Logs the relevance analysis only — the safest way to preview.

### Webhook test with a random Riftbound hit

```bash
python watcher.py --test-webhook-random-riftbound
```

- Sends exactly **one** Discord test message (prefixed `[TEST]`) for one
  Riftbound **shop / merch item**, containing a **clickable link**. It now prefers
  an **available** or **pre-order** item, using availability signals like
  "available" / "in stock" / "lieferbar" / "pre-order" / "vorbestellbar".
- When real Riot merch Riftbound products are found in the page's **embedded
  product data**, `--test-webhook-random-riftbound` sends exactly one of them (a
  real product with a clickable Riot merch product link), preferring available /
  pre-order; if none are found it sends nothing and logs how to set
  `WATCH_TARGETS`.
- If a shop item is found but its availability is unknown, it still sends one test
  message clearly marked that **availability is not confirmed** — it never falsely
  claims the item is available.
- Never modifies `state.json`.
- Needs a real local `DISCORD_WEBHOOK_URL`. If only general articles are found
  (e.g. "how to play" / get-started, newsletters, top decks), it aborts cleanly
  and sends nothing — it will **not** send a get-started / how-to-play link.
- If the merch page is JavaScript-rendered and exposes no product links in the
  static HTML, the test sends nothing and logs that no shop / product link was
  found — set `WATCH_TARGETS` to a concrete product / collection URL to test in
  that case.
- The bot never buys anything; you click the link yourself.

### Normal watcher

```bash
python watcher.py
```

- **First ever run:** writes a baseline to `state.json` and sends **no** message.
- **Later runs:** post only **new** relevant hits (no duplicates) and update
  `state.json`, each message with the best clickable link.
- `state.json` is only ever modified in this mode.
- Optional: `--state-path PATH` points at an alternative state file.

### Status report (manual only)

```bash
python watcher.py --status-report
```

- **Manual only** — the **status report** is **not** part of the automatic
  schedule. Run it locally with `--status-report`, or on GitHub via **Actions →
  Riftbound Watch → Run workflow → `status-report`**.
- Posts a **status report** summary to Discord **even when there is nothing new** —
  it is not gated on new hits. This is exactly why it is **manual only**: keeping it
  off the automatic schedule is what leaves that schedule quiet, with **no status
  spam**.
- Lists **all** currently **available** Riot merch Riftbound items (newest first),
  not only the T1 ones, and additionally states whether there were any
  T1 / Worlds Champion Collection hits among them.
- Contains **no links** — the status report has **no links** at all (no product
  URLs), so it is purely a summary you read.
- Never changes `state.json` and never writes a baseline.
- If no webhook is configured it aborts cleanly (no crash, no send).

### Daily heartbeat

```bash
python watcher.py --heartbeat
```

- Sends exactly **one** short Discord status message so you know the watcher is
  still alive — a deliberate **once-a-day** liveness ping, **not** a return to
  frequent status spam.
- **Counts only:** it reports simple counts and does **not** list the full product
  catalog.
- Contains **no links** at all (no product URLs) — it is purely a short
  "still running" confirmation.
- **Never** writes or changes `state.json` and never writes a baseline.
- On GitHub Actions this same mode runs once daily at **09:00 UTC** (see below);
  the automatic `watch` schedule is unchanged and still posts only new hits.
- If no webhook is configured it aborts cleanly (no crash, no send).

## Upload to GitHub (you run all Git yourself)

Git is done **only by you** — no automation runs Git. `.env` and `state.json` are
git-ignored and must **never** be pushed. Before uploading: run the tests, and
confirm no `.env`, no `state.json`, and no real webhook value are staged.

> **Only run these yourself — automation must never run Git.**

```bash
# 1. Create a new EMPTY repo in your browser at https://github.com/new
#    (do not let GitHub add a README/.gitignore/license).

# 2. Locally, sanity-check that .env and state.json are NOT listed:
git status

# 3. Initialize, stage, commit, and push:
git init
git add .
git status                 # confirm .env and state.json do NOT appear
git commit -m "Initial commit: notify-only Riftbound x T1 Discord watcher"
git branch -M main
git remote add origin https://github.com/<you>/riot.git
git push -u origin main
```

Optional, with the GitHub CLI (again, **run it yourself**):

```bash
gh repo create riot --private --source . --remote origin --push
```

## Run on GitHub Actions (no laptop needed)

GitHub Actions does not continuously or live-check the pages — it runs on two
separate **schedules** (intervals), not continuously live monitoring. **All
GitHub Actions cron schedules run in UTC** (there is no DST logic):

1. **`watch` — every 2 hours (new hits only).** On each scheduled `watch` run it
   posts to Discord **only when it finds new relevant hits** — when nothing new is
   found it sends **no Discord message** (there is **no status spam**, i.e. no
   "nothing new" noise). This schedule is unchanged.
2. **`heartbeat` — once daily at 09:00 UTC (one liveness ping).** A separate
   schedule runs the new **heartbeat** mode **once a day** and posts exactly **one**
   short Discord status message so you know the watcher is alive. Its cron is
   `0 9 * * *`, which is **09:00 UTC** (GitHub cron is UTC, not Berlin time). The
   heartbeat reports **counts only** (no full catalog), contains **no links**, and
   **never** writes or changes state. This is a single short message once per day —
   **not** a return to frequent status spam.

Once the workflow is enabled and the `DISCORD_WEBHOOK_URL` repository Secret is
set, **your laptop does not need to stay on** — GitHub Actions runs it for you.
Beyond the schedules you can additionally trigger any mode manually: **Actions →
Riftbound Watch → Run workflow**, choosing `dry-run`, `test-webhook`, `watch`,
`heartbeat`, or `status-report`.

- Workflow: **Riftbound Watch** (`.github/workflows/riftbound-watch.yml`).
- `schedule`: two cron schedules, **both in UTC**. (1) The **watch** mode runs
  **every 2 hours** and posts **only new relevant hits**, each with a clickable
  product link; when there is nothing new it sends **no Discord message** — **no
  status spam**. It is still an **interval**, not continuously live monitoring. The
  first scheduled `watch` run writes a **baseline** to the state **cache** and sends
  **no message**; later runs post only new relevant hits, each with a **clickable
  link**. (2) The **heartbeat** mode runs **once daily at 09:00 UTC** (cron
  `0 9 * * *`) and posts exactly **one** short liveness message (counts only, **no
  links**) and **never** writes state.
- `workflow_dispatch`: **manual** runs with a `mode` input — `dry-run`,
  `test-webhook`, `watch`, `heartbeat`, or `status-report`. `status-report` and
  `test-webhook` are **manual only** (never scheduled); `dry-run` is **manual** and
  safe (no send, no state write). `heartbeat` also runs on its own daily schedule.
- Mode behavior: `dry-run` never sends and writes no state; `test-webhook`
  (**manual only**) sends exactly one real product with a clickable link when a
  shop/merch candidate is found; `watch` writes a baseline on the first run (no
  message) and later posts **only new relevant hits**, each with a clickable link
  (no duplicate spam, no "nothing new" message); `status-report` (**manual only**)
  posts the available-items list **without links** and never writes state. The bot
  never buys anything.
- The webhook comes **only** from the GitHub repository **Secret**
  `DISCORD_WEBHOOK_URL` — never from `.env` on the runner (local runs still use
  `.env`). No secret value ever appears in the YAML.
- **State / duplicate protection:** `state.json` is persisted between runs via
  GitHub Actions **cache** (rolling key). A cache miss simply starts a fresh
  baseline and sends nothing, so a miss can never cause duplicate spam.
- The first scheduled `watch` run writes a **baseline** and sends nothing; later
  runs post **only new relevant hits**, each with a **clickable link**. It stays
  **notify-only**.

The separate `.github/workflows/tests.yml` is test-only: it runs the pytest suite
and compile checks, never runs the watcher against real pages, never sends a
Discord message, and needs no secrets.

### Set the GitHub Secret

In your GitHub repository:

1. **Settings → Secrets and variables → Actions**.
2. Click **New repository secret**.
3. Name: `DISCORD_WEBHOOK_URL`. Value: your real Discord webhook URL.

Never share the secret or write it into any file.

### Trigger a run manually

- GitHub UI: **Actions → Riftbound Watch → Run workflow**, then pick a mode.
- Optional user-only CLI (documentation examples — **you** run these, never
  automation):

> **Only run these yourself.**

```bash
gh workflow run riftbound-watch.yml -f mode=dry-run
gh workflow run riftbound-watch.yml -f mode=test-webhook
gh workflow run riftbound-watch.yml -f mode=watch
```

## Operation / scheduling

- GitHub Actions is enough; your laptop does not need to stay on.
- Keep any schedule **gentle** — the bundled workflow runs the `watch` mode
  **every 2 hours** (recommended); do not poll aggressively.
- To run it yourself instead, use cron / Task Scheduler at a gentle interval,
  e.g. cron: `0 */2 * * * cd /path/to/riot && /path/to/riot/.venv/bin/python watcher.py >> watcher.log 2>&1`.
- Never add auto-buy, login, checkout, or captcha automation.

## Configurable targets

By default the watcher checks the Riot merch Riftbound category page (primary),
its newest-first variant, and the merch home — all on `merch.riotgames.com`. It
only notifies about **shop / merch items** (see the primary focus above). You can
override the target list without editing code by setting the `WATCH_TARGETS`
environment variable to a comma- or newline-separated list of URLs; the bundled
GitHub Actions workflow sets it to the merch Riftbound category. Unset → the
merch-primary defaults are used.

## Documentation

This root `README.md` is the single tracked documentation and the central GitHub
doc. Any other local Markdown files — extra guides or local change notes under
`docs/` — may exist on your machine but are **git-ignored** (`.gitignore` ignores
`*.md` except the root `README.md`), so they are never published to GitHub.

## Troubleshooting

- **First normal run sent nothing** — correct; the first run only writes a
  baseline. Messages start on later runs, for new relevant hits only.
- **`--dry-run` never sends** — by design it logs analysis and never touches
  `state.json`.
- **The webhook test needs a real local `DISCORD_WEBHOOK_URL`** — set it in your
  shell or `.env` before `--test-webhook-random-riftbound`.
- **An unedited `.env.example` / `REPLACE_ME` does not send** — replace it with
  your real webhook.
- **A corrupt `state.json` is safely re-baselined** — a missing/invalid state
  file logs a warning and starts a fresh baseline; it never crashes.
- **No new messages can be correct** — only new relevant hits after the baseline
  are posted, so a quiet channel usually just means nothing new appeared.
- **The merch page is JavaScript-rendered**, so a plain HTML GET may expose fewer
  product anchors than the live page. If coverage is thin, add specific stable
  product / collection URLs via `WATCH_TARGETS` — do not scrape more aggressively.
- **Fix false hits by extending the relevance tests**, not by scraping harder.

## State file

`state.json` stores the ids of items already seen so they are not re-posted. It
is created/updated only by the normal watcher. A dummy example of the schema is
in [`state.example.json`](state.example.json). The real `state.json` is
git-ignored and must never be committed.

State handling is robust: a missing file yields a fresh baseline, a
corrupt/invalid file is re-baselined (with a warning), and writes are atomic
(temp file + `os.replace`) so a crash never leaves a half-written file.

## Project layout

```
riot/
  watcher.py            # CLI + orchestration (fetch → relevance → state → notify)
  fetch.py              # defensive public-page fetching + link extraction
  relevance.py          # Riftbound merch scope + T1/special highlight detection
  state.py              # robust, atomic state persistence + stable item ids
  notify.py             # Discord webhook sender + secret redaction + best-link
  config.py             # webhook + target resolution (env / .env, WATCH_TARGETS)
  requirements.txt      # runtime dependency (requests)
  requirements-dev.txt  # dev extras (pytest)
  state.example.json    # dummy example state (no secrets)
  .env.example          # placeholder env template (copy to .env, never commit .env)
  .gitignore
  .github/workflows/    # tests.yml (test-only CI) + riftbound-watch.yml (scheduled watcher)
  tests/                # pytest suite
```

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
python -m py_compile watcher.py fetch.py relevance.py state.py notify.py config.py
```

The suite covers first-run baseline behavior, no-duplicate posting, posting only
new hits, dry-run isolation, the single-message test-webhook mode (including the
zero-Riftbound-hit case), the relevance filter, the best-clickable-link
selection, target resolution, workflow safety, and that the webhook URL never
leaks into logs or exceptions.
