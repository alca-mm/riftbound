# Uploading `riot` to GitHub

A manual, copy-paste guide for publishing this **notify-only** Riftbound × T1
Discord watcher to GitHub safely. This project only *notifies* — it never buys,
logs in, checks out, solves captchas, or scrapes aggressively.

> **Important:** every Git/GitHub command in this document is **documentation
> only**. Run them **yourself**. Automation (including Claude) must never run
> Git on your behalf.

---

## 1. Pre-upload checklist

Verify all of the following **before** you push anything:

- [ ] **Tests pass** locally (see [Run the tests locally](#2-run-the-tests-locally)).
- [ ] **No `.env` file is staged** — it holds your real secret and is git-ignored.
- [ ] **No `state.json` file is staged** — it is local runtime state and is git-ignored.
- [ ] **No real webhook value appears anywhere** in the code, docs, tests, or
      example files. Only placeholders such as `REPLACE_ME` or
      `FAKE_TOKEN_DO_NOT_USE` are allowed.
- [ ] `.gitignore` is present and still excludes `.env`, `state.json`,
      `__pycache__/`, `.pytest_cache/`, and the virtual-environment folders.

`tests/test_repo_hygiene.py` enforces the ignore rules and the no-real-webhook
rule automatically, so a green test run covers most of this checklist.

### Secrets that must NEVER be uploaded

- **`.env`** — your local configuration file. It **must never be committed**;
  it is git-ignored for exactly this reason.
- **`state.json`** — local "already seen" state. It **must never be committed**;
  it is git-ignored too.
- **`DISCORD_WEBHOOK_URL`** — the Discord webhook is a **secret**. Its value
  **must never be committed** to GitHub. Keep it in your local `.env` (which is
  ignored) or in an environment variable only.

If you ever suspect a real webhook URL was committed, treat it as leaked:
delete the webhook in Discord and create a new one.

---

## 2. Run the tests locally

From the repository root, with the project virtual environment active:

```bash
python -m pytest tests/ -q
python -m py_compile watcher.py fetch.py relevance.py state.py notify.py
```

The first command runs the full pytest suite. The second confirms every source
module byte-compiles cleanly. Both should complete without errors before you
upload.

---

## 3. Push to GitHub (manual steps)

**Only run these yourself — Claude/automation must never run Git.**

First, in your browser, create a **new empty repository** on
[github.com](https://github.com/new):

- Do **not** add a README, `.gitignore`, or license from the GitHub UI (this
  repo already ships its own), so the first push stays clean.
- Copy the repository URL it shows you (e.g. `https://github.com/<you>/riot.git`).

Then, locally, from the repository root, a typical first-time flow is:

```bash
# Initialize the local repository (only needed once)
git init

# Stage the project. .gitignore keeps .env, state.json, caches, and the
# virtual environment out automatically.
git add .

# Sanity check: make sure .env and state.json are NOT listed below.
git status

git commit -m "Initial commit: notify-only Riftbound x T1 Discord watcher"

# Name the default branch and connect it to your empty GitHub repo.
git branch -M main
git remote add origin https://github.com/<you>/riot.git

# Publish.
git push -u origin main
```

Optionally, if you use the GitHub CLI, you can create the remote repo from the
terminal instead of the browser (again, **run it yourself**):

```bash
gh repo create riot --private --source . --remote origin --push
```

After the first push, subsequent updates are the usual `git add` /
`git commit` / `git push` — always run by you.

---

## 4. Configure after cloning

On any machine where you clone the repo, set up your local secret **without**
committing it:

```bash
# 1. Create a local .env from the tracked template.
#    Windows PowerShell:
copy .env.example .env
#    Linux/Mac:
cp .env.example .env

# 2. Edit .env and set your real webhook value, e.g.:
#    DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/REPLACE_ME
```

Alternatively, skip `.env` entirely and export the variable in your shell:

```bash
# Windows PowerShell
$env:DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/REPLACE_ME"

# Linux/Mac
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/REPLACE_ME"
```

Either way: **never commit `.env`.** It stays on your machine only.

See [`DISCORD_WEBHOOK_SETUP.md`](DISCORD_WEBHOOK_SETUP.md) for how to create the
webhook in Discord and obtain its URL.

---

## 5. Run the watcher on a schedule (gentle, notify-only)

The watcher performs one polite pass per invocation. Schedule it at a **gentle
interval** — a few times per hour at most — to stay respectful of the public
pages it checks. It is **notify-only**: it just posts to your Discord webhook
and updates local `state.json`; it never buys or logs in.

Do **not** schedule this from GitHub Actions to post on your behalf. Run it on a
machine you control.

### Linux/Mac — cron (documentation example)

Run every 15 minutes:

```cron
*/15 * * * * cd /path/to/riot && /path/to/riot/.venv/bin/python watcher.py >> watcher.log 2>&1
```

### Windows — Task Scheduler

Create a Basic Task that runs `\.venv\Scripts\python.exe watcher.py` from the
repository folder every 15 minutes (set "Start in" to the repo directory so it
finds `.env` and `state.json`).

Tip: use `python watcher.py --dry-run` first to preview relevance analysis
without sending any Discord message or touching `state.json`.

---

## See also

- [Project README](../README.md) — overview, modes, and security boundaries.
- [`DISCORD_WEBHOOK_SETUP.md`](DISCORD_WEBHOOK_SETUP.md) — creating and
  configuring the Discord webhook.
