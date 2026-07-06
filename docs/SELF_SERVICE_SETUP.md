# Self-Service Setup

A single, self-contained walkthrough for the **notify-only** Riftbound × T1
Discord watcher. Follow it top to bottom and you can, entirely on your own:
upload the project to GitHub, create a Discord webhook, configure a local `.env`,
test the webhook, understand the first baseline run, and run the watcher safely.

This bot is **notify-only**. It never buys, logs in, checks out, solves captchas,
or scrapes aggressively. It performs a few polite public GET requests and, when
something new and relevant appears, posts a message containing the best
**clickable link** to your Discord webhook. You click the product link yourself.

> Every value shown below uses `REPLACE_ME` placeholders only. Never write a real
> `discord.com/api/webhooks/<id>/<token>` value into any file, screenshot, issue,
> log, or change document.

---

## 1. Before the GitHub upload

Read this section first — it is the safety contract for everything that follows.

- **`.env` must never be uploaded.** It holds your real webhook secret and is
  git-ignored for exactly that reason.
- **`state.json` must never be uploaded.** It is local runtime state and is
  git-ignored too.
- **No real Discord webhook URLs in any file.** Code, docs, tests, and example
  files must contain placeholders such as `REPLACE_ME` only.
- **Never share tokens** in screenshots, issues, the README, logs, or change
  docs. Anyone who sees the webhook URL can post to your channel.
- **Run the tests locally** before you upload (see [section 5](#5-local-test-flow)).
- **GitHub Actions are test-only.** The bundled CI runs the pytest suite and a
  byte-compile check on every push and pull request. It **never** runs or posts
  the Discord webhook and **never** live-polls the watcher against real pages. It
  needs no secrets and will **never post to Discord**.

Manual check commands (read-only, safe to run yourself) are allowed, for example
inspecting what Git would include before you commit:

```bash
git status
git ls-files
```

Those two commands only *show* you the state of your working tree — they upload
nothing.

---

## 2. Do the GitHub upload manually

You publish this project yourself. Automation never touches Git on your behalf.
`.env` and `state.json` are **never** pushed — `.gitignore` already excludes
them, and Git here is done **only by you**.

First, in your browser, create a **new empty repository** on
[github.com/new](https://github.com/new):

- Do **not** let GitHub add a README, `.gitignore`, or license (this repo already
  ships its own), so the first push stays clean.
- Copy the repository URL it shows you, e.g. `https://github.com/<you>/riot.git`.

Then, locally, check your files before staging anything:

**Only run these yourself — automation must never run Git.**

```bash
# Read-only sanity check: confirm .env and state.json are NOT listed.
git status
```

Once you have confirmed no secrets are staged, initialize, commit, and push:

**Only run these yourself — automation must never run Git.**

```bash
# Initialize the local repository (only needed once).
git init

# Stage the project. .gitignore keeps .env, state.json, caches, and the
# virtual environment out automatically.
git add .

# Confirm again that .env and state.json do NOT appear below.
git status

git commit -m "Initial commit: notify-only Riftbound x T1 Discord watcher"

# Name the default branch and connect it to your empty GitHub repo.
git branch -M main
git remote add origin https://github.com/<you>/riot.git

# Publish.
git push -u origin main
```

Optionally, with the GitHub CLI you can create the remote from the terminal
instead of the browser — again, **run it yourself**:

**Only run these yourself — automation must never run Git.**

```bash
gh repo create riot --private --source . --remote origin --push
```

After the first push, later updates are the usual `git add` / `git commit` /
`git push`, always run by you. `.env` and `state.json` stay local and are never
pushed.

---

## 3. Create a Discord webhook

You need **Manage Webhooks** permission on the target server/channel.

1. **Open Discord** and go to the server and channel you want notifications in.
2. **Pick the server / channel** where the messages should land.
3. Open **Channel Settings** (the gear icon next to the channel name).
4. Go to **Integrations**.
5. Open **Webhooks**.
6. Click **New Webhook**.
7. (Optional) Give it a name and confirm the channel it posts to.
8. Click **Copy Webhook URL**.

The copied URL is the value the watcher needs. It looks like
`https://discord.com/api/webhooks/REPLACE_ME/REPLACE_ME` — a numeric id segment
followed by a long token segment. **Both segments are secret.**

**Keep it secret.** Never post the webhook URL in GitHub, screenshots, the
README, issues, or logs. If it ever leaks, delete the webhook in Discord and
create a new one. Use `REPLACE_ME` placeholders everywhere except your own local
`.env`.

---

## 4. Configure a local `.env`

The watcher reads the webhook URL from `DISCORD_WEBHOOK_URL`. Set it only on your
own machine. A local `.env` file is **optionally supported** — you can use it, or
you can export the variable in your shell instead.

Copy the shipped template and edit the copy:

```bash
# Windows PowerShell
copy .env.example .env

# Linux/Mac
cp .env.example .env
```

Then open `.env`, set `DISCORD_WEBHOOK_URL`, and **replace `REPLACE_ME`** with
your real, copied webhook URL:

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/REPLACE_ME/REPLACE_ME
```

Important rules:

- **Never commit `.env`.** It is git-ignored and stays on your machine only. The
  committed `.env.example` must always keep its `REPLACE_ME` placeholders.
- The shell environment variable **takes precedence** over `.env`. If
  `DISCORD_WEBHOOK_URL` is exported in your shell, that value wins; otherwise the
  watcher reads it from `.env`.
- An **unedited placeholder** is treated as "not configured": a value still
  containing `REPLACE_ME` means the watcher considers the webhook unset and sends
  **nothing**.

To export the variable in your shell instead of using `.env`:

```bash
# Windows PowerShell
$env:DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/REPLACE_ME/REPLACE_ME"

# Linux/Mac
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/REPLACE_ME/REPLACE_ME"
```

Either way, the value is local only and must **never** be shared in GitHub, the
README, logs, or screenshots.

---

## 5. Local test flow

Run these commands from the repository root, in this exact order, and check the
expected result at each step.

**Step 1 — install the dev dependencies:**

```bash
python -m pip install -r requirements-dev.txt
```

This installs pytest so you can run the suite locally.

**Step 2 — run the tests:**

```bash
python -m pytest tests/ -q
```

Everything should pass before you go further. The suite covers baseline
behavior, no-duplicate posting, dry-run isolation, the test-webhook mode, the
relevance filter, and that the webhook URL never leaks into logs.

**Step 3 — dry run (no side effects):**

```bash
python watcher.py --dry-run
```

Expected: **no Discord message**, **no `state.json`** created or modified, logs
only. `--dry-run` needs no webhook and is the safest way to preview relevance
analysis.

**Step 4 — webhook test:**

```bash
python watcher.py --test-webhook-random-riftbound
```

Expected: **exactly one** Discord test message that contains a clickable
Riftbound / product / best link; `state.json` is left **unchanged**. Only run
this once `DISCORD_WEBHOOK_URL` is correctly set locally — it needs a real local
webhook. If no Riftbound hit is found, it aborts cleanly and sends nothing.

**Step 5 — first normal run (writes the baseline):**

```bash
python watcher.py
```

Expected: the first ever run writes a **baseline** to `state.json` and sends
**NO** message. It simply records everything currently relevant as "already
seen" so you are not flooded on the first pass.

**Step 6 — second normal run (posts only new hits):**

```bash
python watcher.py
```

Expected: it sends a message **only** when new relevant hits appeared since the
baseline. Already-known hits are never re-posted — no duplicate spam. Any message
it does send contains the best **clickable link** (a product / store link is
preferred, otherwise a relevant article / source link).

Optional: `--state-path PATH` points the watcher at an alternative state file.

---

## 6. Running / scheduling

- Run the watcher **locally or on your own server**, at a **gentle interval** — a
  few times per hour at most. One polite pass per invocation.
- **Do not poll aggressively.** Respect the public pages the watcher checks.
- **Do NOT set up a GitHub Action for real polling or Discord posting.** The
  bundled GitHub Actions are test-only; they must never live-poll or post. Run
  the watcher on a machine you control.
- **Do NOT add auto-buy, login, checkout, or captcha automation.** This project
  is notify-only by design.

Cron and Task Scheduler are shown below only as **optional manual hints** — set
them up yourself if you want unattended runs.

### Linux/Mac — cron (optional manual hint)

Run every 15 minutes:

```cron
*/15 * * * * cd /path/to/riot && /path/to/riot/.venv/bin/python watcher.py >> watcher.log 2>&1
```

### Windows — Task Scheduler (optional manual hint)

Create a Basic Task that runs `.venv\Scripts\python.exe watcher.py` from the
repository folder every 15 minutes. Set "Start in" to the repo directory so it
finds `.env` and `state.json`.

Tip: run `python watcher.py --dry-run` first to preview the relevance analysis
without sending any Discord message or touching `state.json`.

---

## 7. Troubleshooting

- **The first normal run sent nothing.** Correct — the first run only writes a
  `baseline` to `state.json`. Messages start on later runs, and only for new
  relevant hits.
- **`--dry-run` never sends.** By design it logs analysis only and never touches
  `state.json`. Use a normal run or the webhook test if you expect a message.
- **The webhook test needs a real local `DISCORD_WEBHOOK_URL`.** Set it in your
  shell or `.env` before running `--test-webhook-random-riftbound`.
- **An unedited `.env.example` / `REPLACE_ME` does not send.** A value still
  containing `REPLACE_ME` is treated as "not configured", so nothing is sent.
  Replace it with your real webhook URL.
- **A corrupt `state.json` is safely re-baselined.** If the state file is
  missing or invalid, the watcher logs a warning and starts a fresh baseline; it
  never crashes on a bad state file.
- **Fix false hits by extending the relevance tests**, not by scraping harder.
  Add positive/negative examples to the relevance test suite so the filter is
  tightened — never respond by polling more aggressively.
- **No Discord message arrives?** Run the webhook test first
  (`python watcher.py --test-webhook-random-riftbound`) to confirm the webhook is
  wired up. If that message lands, delivery works.
- **No new messages can be correct.** Only new relevant hits after the baseline
  are posted, so a quiet channel usually just means nothing new appeared.

---

## 8. Safety reminder

This project is **notify-only**. It does **not**, and will not:

- ❌ **auto-buy** anything automatically
- ❌ **login** to any account
- ❌ perform a **checkout**
- ❌ solve or bypass a **captcha**
- ❌ do **aggressive scraping** or bypass rate limits
- ❌ put secrets in GitHub, logs, screenshots, or change docs

It only notifies. You click the product links manually. Keep
`DISCORD_WEBHOOK_URL` secret, **never commit `.env` or `state.json`**, and let
Git and the webhook stay entirely under your control.

---

## See also

- [Project README](../README.md) — overview, modes, and security boundaries.
- [`DISCORD_WEBHOOK_SETUP.md`](DISCORD_WEBHOOK_SETUP.md) — creating and
  configuring the Discord webhook.
- [`GITHUB_UPLOAD.md`](GITHUB_UPLOAD.md) — uploading to GitHub yourself.
