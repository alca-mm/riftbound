Date: 2026-07-06
Time: 10:41 Europe/Berlin
Branch: main
Commit: not recorded

# Discord product link

Backend version: not applicable
Frontend/Userscript/App version changed: No
Server restart needed: No
Client/browser refresh needed: No
Config/migration/manual step needed: No

## Goal

Make every Discord notification carry the best available, directly clickable
link so the user can jump straight to the relevant product / store / collection /
article. Preference order: direct Riot-merch-store/product link → Riftbound/T1
collection link → article/news/drawing link → source page (only as a last
resort). The bot stays notify-only: it opens/buys nothing; the user clicks the
link manually.

## User-Reported Problem

Notifications did include the item URL, but there was no explicit "best link"
selection, no product/store preference, and no guarantee that the (test) message
always carried a working clickable link. This adds a deterministic best-link
chooser and a clearer message layout.

## Files Changed

Modified:
- `notify.py` — added `best_item_url(item)` (pure/offline best-link chooser) and a
  `MESSAGE_HEADER`; `format_message` now emits the best link as a bare URL on its
  own line (clickable), omitting the link line entirely when there is no valid link.
- `tests/test_notify.py` — +11 tests for `best_item_url` and the message layout.
- `watcher.py` — `_run_test_webhook` pool now requires a valid `best_item_url`, so
  the single test message always contains a working link (empty pool → clean abort).
- `tests/test_watcher.py` — +4 tests (best product URL in the sent message, product
  link preferred over general source, test-webhook clickable Riftbound link,
  test-webhook skips a link-less Riftbound item).
- `tests/test_readme.py` — +1 doc-guard test (README mentions the best clickable link).
- `README.md` — new "Notifications" section (best clickable link, product preferred,
  manual click, no auto-buy).
- `docs/DISCORD_WEBHOOK_SETUP.md` — note that notifications include the best
  clickable link and the test message contains a clickable Riftbound link.

New:
- `docs/changes/2026-07-06-1041-discord-product-link.md` — this note.

Unchanged: `fetch.py`, `relevance.py`, `state.py`, `config.py`, `.env.example`,
`.gitignore`, CI. The normal-mode delivery loop was NOT changed — messages get the
best link automatically because `format_message` now calls `best_item_url`.

## Implementation Details

- `best_item_url(item)` considers `item['url']` (the specific found link) and
  `item['source']` (the page it was found on). It resolves a relative `url`
  against `source` (`urllib.parse.urljoin`), rejects empty / `#` / `javascript:` /
  `mailto:` / `tel:` and any non-http(s) URL, and ranks candidates deterministically:
  host `merch.riotgames.com` (+100), store/collection path fragments like
  `/product(s)`, `/shop`, `/store`, `/buy`, `/collection(s)` (+40), drop keywords
  `riftbound`/`worlds-champion`/`signature-edition`/`player-bundle`/`t1` (+15), and
  overview paths `/news`, `/article`, `/blog`, `drawing`, `lottery`, `raffle` (+5).
  The specific `url` is preferred; the general `source` only wins when the `url`
  carries no positive signal at all. It makes NO network request (no extra scraping).
- `format_message` layout (each on its own line): `MESSAGE_HEADER`, then the title
  (truncated with an ellipsis if needed), then the best link as a bare URL, then a
  `Match: …` line when reasons are present. The header, link, and Match line always
  survive truncation; total length stays ≤ 2000. A link-less item never emits `None`,
  an empty line, or a broken link. No secret ever appears in the content.
- `watcher.py` test-webhook: the Riftbound pool is filtered to items with a valid
  `best_item_url`, guaranteeing the one test message has a working link; an empty
  pool still aborts cleanly (no send, no state change).

## Pipeline order

Unchanged (fetch → relevance → state → notify). The only new logic is inside
message building: `notify.format_message` → `notify.best_item_url` picks the link.
Test-webhook adds a `best_item_url` filter when selecting the random Riftbound hit.

## Tests

- Test-driven; existing tests kept green. The test-webhook "skip link-less item"
  test was RED before the pool filter, GREEN after.
- **Test count before:** 181 passing.
- **Test count after:** 197 passing (+16: notify 11, watcher 4, readme 1).
- Final commands:
  - `python -m pytest tests/ -q` → `197 passed`
  - `python -m py_compile watcher.py fetch.py relevance.py state.py notify.py config.py` → OK

## Manual Test Checklist

- [ ] `python -m pytest tests/ -q` → 197 passed.
- [ ] Configure `DISCORD_WEBHOOK_URL` (env var or local `.env`).
- [ ] `python watcher.py --test-webhook-random-riftbound` → exactly one message
      whose body contains a clickable Riftbound link; `state.json` unchanged.
- [ ] `python watcher.py` first run → baseline only, no message.
- [ ] Later run with a new relevant hit → one message containing the best clickable
      link (product/store link when available).
- [ ] `python watcher.py --dry-run` → no message, no `state.json`.

## Required User Actions

- Server restart needed: No
- Frontend/client/browser refresh needed: No
- Config/migration/manual step needed: No (behavioral change only; no new config).
- Discord webhook setup needed: Yes — set `DISCORD_WEBHOOK_URL` (env var or local
  `.env`) to receive messages; the message will contain the clickable link.
- GitHub upload / manual git steps needed: Yes — run all Git commands yourself.
- Environment variable needed: `DISCORD_WEBHOOK_URL` (name only — value never shown/stored).
- `.env` optional supported: Yes (unchanged; env var takes precedence).

## Known Limitations

- Items expose only `url` and `source`; "product vs source preference" is chosen
  between those two. No extra requests are made to discover a better product URL
  (by design — no aggressive scraping).
- Link ranking is heuristic (host/path/keyword scoring); an unusual store URL
  structure could rank a general link higher, but the specific found `url` is
  preferred whenever it carries any positive signal.
- A relevant item with no valid link at all is dropped from the test-webhook pool;
  in normal mode `format_message` simply omits the link line (in practice fetched
  items always have an absolute `url`).

## Next Recommended Improvements

- Optionally wrap the link in a short call-to-action line ("Open in store:") while
  keeping the bare URL clickable.
- Optional per-source link-preference tuning if new target pages are added.

## Autonomous Decisions Made

- Put `best_item_url` in `notify.py` and had `format_message` use it, so BOTH normal
  and test-webhook messages get the best link with no change to the normal-mode
  delivery loop (lower regression risk).
- Preferred the specific `item['url']` over the general `source` unless the url has
  zero positive signal — matching "prefer the product/store link, fall back to the
  best available link".
- Added a test-webhook pool filter so the single test message always has a working
  link, keeping the clean-abort behavior when no linked Riftbound hit exists.
- Used only fake example URLs (`merch.riotgames.com/...`, `example.com/...`) in tests;
  no real webhook value anywhere.

## Git note
No git commands were run. Per project rule, all Git is done manually by the user.
