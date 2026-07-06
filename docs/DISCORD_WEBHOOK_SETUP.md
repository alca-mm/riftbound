# Discord Webhook Setup

This guide explains how to point the **notify-only** Riftbound × T1 watcher at a
Discord channel, how to keep the webhook URL safe, and how to test it locally.

> The webhook URL is a **secret**. Treat it like a password. The rest of this
> guide uses `REPLACE_ME` placeholders only — never paste your real URL anywhere
> that could be committed, shared, or logged.

## 1. Create a Discord webhook

You need **Manage Webhooks** permission on the target server/channel.

1. Open Discord and go to the channel you want notifications in.
2. Open **Channel Settings** (the gear icon next to the channel) —
   or **Server Settings** for a server-wide integration.
3. Go to **Integrations → Webhooks**.
4. Click **New Webhook**.
5. (Optional) Give it a name and choose the channel it posts to.
6. Click **Copy Webhook URL**.

That copied URL is the value the watcher needs. It looks like
`https://discord.com/api/webhooks/REPLACE_ME/REPLACE_ME` — a numeric id segment
followed by a long token segment. **Both segments are secret.**

## 2. The webhook URL is a SECRET

Anyone who has the URL can post to your channel. Because of that:

- **Never** commit it to git (not in code, config, or `.env`).
- **Never** put it in `README.md`, issues, pull requests, or any docs.
- **Never** paste it into logs, screenshots, chat messages, or bug reports.
- If it ever leaks, delete the webhook in Discord and create a new one.

The watcher is written to treat the URL as a secret: it is never written to
logs, exceptions, `state.json`, or the change notes.

## 3. Set the value LOCALLY

The watcher reads the webhook URL from the environment variable
`DISCORD_WEBHOOK_URL`. Set it only on your own machine.

### Option A — a local `.env` file (not committed)

Copy the shipped example and edit the copy:

```bash
cp .env.example .env
```

Then open `.env` and replace the placeholder with your real URL. `.env` is
git-ignored, so it stays local. **Never commit `.env`.** The committed
`.env.example` must always keep the `REPLACE_ME` placeholders.

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/REPLACE_ME/REPLACE_ME
```

### Option B — export it in your shell

Windows PowerShell:

```powershell
$env:DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/REPLACE_ME/REPLACE_ME"
```

Linux / macOS (bash/zsh):

```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/REPLACE_ME/REPLACE_ME"
```

Replace the placeholder with your real, copied URL. Again: this is done
**locally only** and the value must **never** be shared in GitHub, the README,
logs, screenshots, or chat.

### Local `.env` (optional)

The environment variable **takes precedence** over `.env`. If
`DISCORD_WEBHOOK_URL` is not set in the environment, the watcher optionally reads
`DISCORD_WEBHOOK_URL` from a local `.env` file instead. You must replace the
`REPLACE_ME` placeholder with your real webhook — a value still containing
`REPLACE_ME` will be treated as **not configured** and nothing will be sent.
Never commit `.env`, and never share the webhook URL in GitHub, logs, or
screenshots.

## 4. Test the webhook locally

Once `DISCORD_WEBHOOK_URL` is set, verify delivery with the test mode:

```bash
python watcher.py --test-webhook-random-riftbound
```

This mode:

- Picks exactly **one** random Riftbound hit from the fetched public results.
- Sends **exactly one** Discord test message (prefixed `[TEST]`).
- Does **not** modify `state.json`.
- If there is **no** Riftbound hit, it **aborts cleanly** and sends nothing,
  leaving state unchanged.

If the message arrives in your channel, the webhook is wired up correctly.

Every notification includes the **best clickable link** (a product / store link
is preferred, otherwise a relevant article / source link).
`--test-webhook-random-riftbound` sends exactly one test message that also
contains a clickable Riftbound link. The bot only notifies — it does not open,
add to cart, or buy anything; you click manually.

## 5. First normal run only writes a baseline

```bash
python watcher.py
```

The **first ever run** writes a **baseline** to `state.json` and sends **no**
Discord message. It simply records everything currently relevant as "already
seen" so you are not flooded on the first pass. Later normal runs post only
**new** relevant hits and update `state.json`.

## 6. Dry run sends nothing and never touches state

```bash
python watcher.py --dry-run
```

Dry run checks the pages and logs the relevance analysis. It sends **no**
Discord message and does **not** create or modify `state.json`. It is the safest
way to see what the watcher would do without side effects.

## Reminder: this bot is notify-only

This project **only notifies**. It does not — and will not — auto-buy, log in,
check out, solve or bypass captchas, or scrape aggressively. It performs a
small number of polite public GET requests and, when something new and relevant
appears, sends a Discord message. Nothing more.

---

See the project overview in [`../README.md`](../README.md).
