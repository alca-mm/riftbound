"""notify.py — NOTIFY-ONLY Discord sender for the riot watcher.

This module does exactly one thing: POST a short message to a Discord webhook.
It never logs in, buys, checks out, solves captchas, or bypasses anything.

SECURITY: the webhook URL is a secret. It must NEVER appear in any log line,
exception message, traceback, or repr. Failures raise ``WebhookError`` with a
generic reason, and anything we log is passed through :func:`redact_secrets`
first (we prefer not to log the URL at all).
"""
import logging
import re
from urllib.parse import urljoin, urlparse

logger = logging.getLogger("riot.notify")

# Discord rejects message ``content`` longer than 2000 characters.
MAX_CONTENT = 2000

# Leading line for every notification message.
MESSAGE_HEADER = "New Riftbound × T1 match found:"

# Leading lines for a NEW watch hit. Every new Riot-merch Riftbound shop item is
# posted with NEW_ITEM_HEADER; a T1 / Worlds / Signature / Player Bundle / Faker
# / Galio item is additionally HIGHLIGHTED. The highlight is a marker, never a
# precondition for posting.
NEW_ITEM_HEADER = "New Riftbound merch item found:"
HIGHLIGHT_ITEM_HEADER = "🔥 New highlighted Riftbound × T1 merch item found:"

# Leading line for the periodic status / heartbeat report.
STATUS_HEADER = "[STATUS] Riftbound merch check"

# Leading line for the short daily heartbeat message.
HEARTBEAT_HEADER = "[STATUS] Riftbound × T1 watcher heartbeat"

# Path fragments that mark a more specific product / store / collection link.
_STORE_PATH_HINTS = (
    "/product",
    "/products",
    "/shop",
    "/store",
    "/buy",
    "/p/",
    "/item",
    "/collection",
    "/collections",
)
# Keywords (anywhere in the URL) tied to this specific drop.
_KEYWORD_HINTS = (
    "riftbound",
    "worlds-champion",
    "signature-edition",
    "player-bundle",
    "t1",
)
# Path fragments that hint at a general news/overview page (weakly positive).
_OVERVIEW_PATH_HINTS = (
    "/news",
    "/article",
    "/blog",
    "drawing",
    "lottery",
    "raffle",
)


# --- is_shop_candidate signals (pure/offline shop-vs-article classification) ---
# Path fragments that mark a merch shop / product / category / collection page.
_SHOP_PATH_SIGNALS = (
    "/de-de/category/riftbound",
    "/category/riftbound",
    "/product",
    "/products",
    "/shop",
    "/store",
    "/collection",
    "/collections",
)
# Keywords (anywhere in title+text+url) that mark a merch shop/product item.
_SHOP_TEXT_SIGNALS = (
    "merch",
    "product",
    "shop",
    "store",
    "collection",
    "availability",
    "drawing",
    "lottery",
    "player bundle",
    "signature edition",
    "worlds champion collection",
)
# Keywords that mark a general article / news / how-to-play page (negative-only).
_ARTICLE_TEXT_SIGNALS = (
    "get-started",
    "how to play",
    "top decks",
    "top-decks",
    "newsletter",
    "/news",
    "/blog",
    "/article",
)


def is_shop_candidate(item) -> bool:
    """True if the item looks like a Riot merch shop/product item, rather than a
    general article / news / how-to-play page. Pure/offline — no network.

    A positive shop signal (merch host, a shop/category/collection path, or a
    merch keyword) always wins. Otherwise the item is not a shop candidate — a
    recognisably general page (get-started / how-to-play / news / …) is False,
    and so is anything else that carries no positive shop signal.
    """
    item = item or {}
    url = str(item.get("url", "") or "")
    title = str(item.get("title", "") or "")
    text = str(item.get("text", "") or "")

    parsed = urlparse(url.lower())
    host = parsed.netloc
    path = parsed.path

    # Combined lowercased title+text+url is used for keyword signals.
    combined = " ".join((title, text, url)).lower()

    positive = (
        "merch.riotgames.com" in host
        or any(sig in path for sig in _SHOP_PATH_SIGNALS)
        or any(sig in combined for sig in _SHOP_TEXT_SIGNALS)
    )
    if positive:
        return True

    # No positive shop signal: a general article/news/how-to-play page is False,
    # and any other page with no shop signal is False too.
    if any(sig in combined for sig in _ARTICLE_TEXT_SIGNALS):
        return False
    return False


# --- availability_status signals (pure/offline; derived from item text only) ---
# Ordered so negatives (which CONTAIN positives as substrings) win first.
# "not available"/"unavailable" contain "available"; "nicht verfügbar"/"nicht
# lieferbar" contain "verfügbar"/"lieferbar" — checking sold_out FIRST keeps them
# out of the available bucket.
_SOLD_OUT_SIGNALS = (
    "sold out",
    "sold-out",
    "soldout",
    "out of stock",
    "out-of-stock",
    "not available",
    "unavailable",
    "ausverkauft",
    "nicht verfügbar",
    "nicht lieferbar",
)
_PREORDER_SIGNALS = (
    "preorder",
    "pre-order",
    "pre order",
    "vorbestellung",
    "vorbestellbar",
)
_AVAILABLE_SIGNALS = (
    "available",
    "in stock",
    "in-stock",
    "lieferbar",
    "verfügbar",
    "auf lager",
)
_COMING_SOON_SIGNALS = (
    "coming soon",
    "coming-soon",
)

# Higher rank = more sendable in the test webhook.
AVAILABILITY_RANK = {
    "available": 4,
    "preorder": 3,
    "unknown": 2,
    "coming_soon": 1,
    "sold_out": 0,
}


def availability_status(item) -> str:
    """Classify an item's availability from its own text as one of:
    'available', 'preorder', 'coming_soon', 'sold_out', 'unknown'. Pure/offline
    — derived solely from the item's title/text/url/source fields, no network.

    Classified in a fixed order (first match wins) because the negative phrases
    contain the positive phrases as substrings: sold_out is checked before
    available so "not available"/"unavailable"/"nicht verfügbar"/"nicht lieferbar"
    classify as sold_out rather than available.
    """
    item = item or {}
    title = str(item.get("title", "") or "")
    text = str(item.get("text", "") or "")
    url = str(item.get("url", "") or "")
    source = str(item.get("source", "") or "")
    combined = (title + " " + text + " " + url + " " + source).lower()

    if any(sig in combined for sig in _SOLD_OUT_SIGNALS):
        return "sold_out"
    if any(sig in combined for sig in _PREORDER_SIGNALS):
        return "preorder"
    if any(sig in combined for sig in _AVAILABLE_SIGNALS):
        return "available"
    if any(sig in combined for sig in _COMING_SOON_SIGNALS):
        return "coming_soon"
    return "unknown"


def availability_score(item) -> int:
    """``AVAILABILITY_RANK[availability_status(item)]`` — higher = more sendable
    in the test webhook. Pure/offline."""
    return AVAILABILITY_RANK[availability_status(item)]


class WebhookError(Exception):
    """Raised when sending a Discord message fails.

    Its message must NEVER contain the webhook URL or any other secret.
    """


def redact_secrets(text, secrets):
    """Replace every occurrence of each non-empty secret with ``"***"``.

    ``secrets`` is any iterable of strings; ``None`` and empty entries are
    ignored. Returns the redacted text.
    """
    if text is None:
        return text
    result = str(text)
    if not secrets:
        return result
    for secret in secrets:
        if not secret:
            continue
        result = result.replace(str(secret), "***")
    return result


def _resolve_candidate(raw, base):
    """Resolve one raw candidate into a valid absolute http/https URL, or None.

    Relative candidates are resolved against ``base`` (the source page) with
    :func:`urllib.parse.urljoin`. Empty, fragment-only (``"#"``), and non-web
    schemes (``javascript:``, ``mailto:``, ``tel:``) are rejected. Purely
    offline — makes NO network request.
    """
    if raw is None:
        return None
    raw = str(raw).strip()
    if not raw:
        return None
    low = raw.lower()
    if low.startswith("#"):  # bare fragment / "#" is not a real destination
        return None
    if low.startswith(("javascript:", "mailto:", "tel:")):
        return None

    resolved = raw
    base = str(base).strip() if base else ""
    if base:
        try:
            resolved = urljoin(base, raw)
        except Exception:  # pragma: no cover - urljoin is very forgiving
            resolved = raw

    parsed = urlparse(resolved)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return resolved


def _score_url(resolved):
    """Deterministic ranking score for a resolved URL (higher = better).

    Ranking only — every valid http/https candidate is eligible regardless of
    score. No network request.
    """
    low = resolved.lower()
    parsed = urlparse(low)
    host = parsed.netloc
    path = parsed.path

    score = 0
    if "merch.riotgames.com" in host:
        score += 100
    if any(hint in path for hint in _STORE_PATH_HINTS):
        score += 40
    if any(hint in low for hint in _KEYWORD_HINTS):
        score += 15
    if any(hint in path for hint in _OVERVIEW_PATH_HINTS):
        score += 5
    return score


def best_item_url(item):
    """Return the best clickable URL for ``item``, or ``None`` if none is valid.

    Considers ``item['url']`` (the specific link found) and ``item['source']``
    (the page it was found on), resolving a relative ``url`` against ``source``.
    Prefers a more specific product / Riot-merch-store / collection link via
    :func:`_score_url`; on a tie the item's own ``url`` wins over ``source``.
    Purely offline — makes NO network request.
    """
    item = item or {}
    source = item.get("source")

    resolved_url = _resolve_candidate(item.get("url"), source)
    resolved_source = _resolve_candidate(source, source)

    # With only one valid candidate the choice is forced (either may be None).
    if resolved_url is None:
        return resolved_source
    if resolved_source is None:
        return resolved_url

    score_url = _score_url(resolved_url)
    score_source = _score_url(resolved_source)

    # ``item['url']`` is the SPECIFIC link that was found; ``item['source']`` is
    # the general page it sits on. Prefer the specific url — and on an exact tie
    # prefer it too. Only fall back to a higher-scoring source when the url
    # carries no positive signal at all (score 0), i.e. it is a bare/offsite link
    # while the source is a real merch / product / collection page.
    if score_url > 0 or score_url >= score_source:
        return resolved_url
    return resolved_source


def format_message(item, reasons=None):
    """Build a concise Discord message content string for a relevant hit.

    Layout (each on its own line)::

        <MESSAGE_HEADER>
        <title>                     # truncated if needed
        <best_item_url(item)>       # omitted entirely when there is no valid link
        Match: a, b                 # only when ``reasons`` is a non-empty list

    The best link is emitted as a BARE URL on its own line so Discord renders it
    clickable. Never contains a secret and stays under Discord's 2000-character
    content limit (the title is truncated so the header, link, and Match line
    always survive).
    """
    item = item or {}
    title = str(item.get("title", "")).strip()
    link = best_item_url(item)

    tail_lines = []
    if link:
        tail_lines.append(link)
    if reasons:
        reason_str = ", ".join(str(r) for r in reasons if r is not None and str(r) != "")
        if reason_str:
            tail_lines.append("Match: " + reason_str)

    # Everything except the title is fixed and must survive truncation. Reserve
    # its characters plus one newline per fixed line (the header/link/match joins
    # and the title's own leading newline).
    fixed_lines = [MESSAGE_HEADER] + tail_lines
    reserve = sum(len(line) for line in fixed_lines) + len(fixed_lines)
    budget = max(MAX_CONTENT - reserve, 0)
    if len(title) > budget:
        if budget >= 1:
            title = title[: budget - 1].rstrip() + "…"
        else:
            title = ""

    lines = [MESSAGE_HEADER]
    if title:
        lines.append(title)
    lines.extend(tail_lines)
    msg = "\n".join(lines)
    if len(msg) > MAX_CONTENT:  # final safety net
        msg = msg[:MAX_CONTENT]
    return msg


def format_new_item_message(item, special_reasons=None):
    """Build the Discord message for a NEW Riot-merch Riftbound shop item.

    Layout (each on its own line)::

        <NEW_ITEM_HEADER>            # or HIGHLIGHT_ITEM_HEADER when special
        <title>                      # truncated if needed
        <best_item_url(item)>        # omitted entirely when there is no valid link
        Match: t1, worlds champion collection   # only when special_reasons is non-empty
        Status: available

    ``special_reasons`` is the (possibly empty) list from
    :func:`relevance.special_reasons`. A non-empty list switches the header to
    the highlight variant and adds the ``Match:`` line — it never decides
    WHETHER a message is sent. The link is a bare URL on its own line so Discord
    renders it clickable. Never contains a secret; stays under Discord's
    2000-character limit (the title is truncated so header, link, Match and
    Status always survive). Pure/offline.
    """
    item = item or {}
    title = str(item.get("title", "")).strip()
    link = best_item_url(item)

    reason_str = ""
    if special_reasons:
        reason_str = ", ".join(
            str(r) for r in special_reasons if r is not None and str(r) != ""
        )
    header = HIGHLIGHT_ITEM_HEADER if reason_str else NEW_ITEM_HEADER

    tail_lines = []
    if link:
        tail_lines.append(link)
    if reason_str:
        tail_lines.append("Match: " + reason_str)
    tail_lines.append("Status: " + availability_status(item))

    # Everything except the title is fixed and must survive truncation. Reserve
    # its characters plus one newline per fixed line.
    fixed_lines = [header] + tail_lines
    reserve = sum(len(line) for line in fixed_lines) + len(fixed_lines)
    budget = max(MAX_CONTENT - reserve, 0)
    if len(title) > budget:
        title = title[: budget - 1].rstrip() + "…" if budget >= 1 else ""

    lines = [header]
    if title:
        lines.append(title)
    lines.extend(tail_lines)
    msg = "\n".join(lines)
    if len(msg) > MAX_CONTENT:  # final safety net
        msg = msg[:MAX_CONTENT]
    return msg


# --- format_status_report helpers (pure/offline; NEVER emit a URL) ---
# Any http/https URL substring — stripped from titles so no link ever leaks.
_URL_IN_TEXT_RE = re.compile(r"https?://\S+")
# "t1" as a whole word (so "battle"/"attic" do NOT count as a T1 highlight).
_T1_WORD_RE = re.compile(r"\bt1\b")
# Phrases that mark an available item as a Riftbound × T1 / Worlds highlight.
_T1_HIGHLIGHT_KEYWORDS = (
    "worlds champion collection",
    "signature edition",
    "player bundle",
    "faker",
    "galio",
)


def _clean_title(title):
    """Sanitize a title for the status report: drop any embedded ``http(s)://``
    URL substring and collapse all runs of whitespace to single spaces. Pure —
    guarantees the returned string contains no link. Never network."""
    cleaned = _URL_IN_TEXT_RE.sub("", str(title or ""))
    return " ".join(cleaned.split())


def _is_t1_highlight(item):
    """True if ``item`` (assumed already available) is a Riftbound × T1 / Worlds
    Champion Collection highlight — its lowercased title+text contains one of the
    highlight keywords or the whole word ``t1``. Pure/offline."""
    item = item or {}
    combined = (
        str(item.get("title", "") or "") + " " + str(item.get("text", "") or "")
    ).lower()
    if any(kw in combined for kw in _T1_HIGHLIGHT_KEYWORDS):
        return True
    return bool(_T1_WORD_RE.search(combined))


def _numbered_section(items, max_items, noun):
    """Return the numbered lines for one section (available/preorder), capped at
    ``max_items`` with a ``"...and N more <noun> item(s)."`` tail when truncated.
    Titles are run through :func:`_clean_title` so no URL can leak."""
    lines = []
    shown = items[:max_items]
    for i, it in enumerate(shown, 1):
        lines.append("%d. %s" % (i, _clean_title((it or {}).get("title", ""))))
    extra = len(items) - len(shown)
    if extra > 0:
        lines.append("...and %d more %s item(s)." % (extra, noun))
    return lines


def format_status_report(items, *, max_items=15):
    """Build a periodic heartbeat message listing currently AVAILABLE Riftbound
    merch items, WITHOUT any links. Pure/offline — the caller passes items that
    are already relevant shop/merch items ({title,url,source,text}); this splits
    them by :func:`availability_status` and formats. NEVER emits a URL.

    Items are deduped by title (case-insensitive) preserving input order (the
    source is date-desc sorted, so the newest item stays on top); empty titles
    are skipped. Available and preorder items are listed in separate numbered
    sections (each capped at ``max_items``). The status line highlights any
    available Riftbound × T1 / Worlds Champion Collection items. The whole
    message is sanitized (no ``http(s)://``) and truncated to ``MAX_CONTENT``.
    """
    seen = set()
    deduped = []
    for it in items or []:
        it = it or {}
        title = str(it.get("title", "") or "").strip()
        if not title:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)

    available = [it for it in deduped if availability_status(it) == "available"]
    preorder = [it for it in deduped if availability_status(it) == "preorder"]
    t1_hits = [it for it in available if _is_t1_highlight(it)]

    lines = [STATUS_HEADER]
    if t1_hits:
        lines.append(
            "Riftbound × T1 / Worlds Champion Collection items available: %d"
            % len(t1_hits)
        )
    else:
        lines.append("No new Riftbound × T1 / Worlds Champion Collection hits found.")
    lines.append("")

    if available:
        lines.append("Available Riftbound merch items:")
        lines.extend(_numbered_section(available, max_items, "available"))
    else:
        lines.append(
            "No available Riftbound merch items detected in the static product data."
        )

    if preorder:
        lines.append("")
        lines.append("Preorder Riftbound merch items:")
        lines.extend(_numbered_section(preorder, max_items, "preorder"))

    msg = "\n".join(lines)
    if len(msg) > MAX_CONTENT:
        # Titles are already link-free, so a mid-string cut can never expose a
        # stray URL. End with a single-character ellipsis, staying <= MAX_CONTENT.
        msg = msg[: MAX_CONTENT - 1].rstrip() + "…"
    return msg


def format_heartbeat(items):
    """Build a SHORT daily heartbeat message: just availability counts, no list.

    Pure/offline — the caller passes items that are already relevant shop/merch
    items ({title,url,source,text}); this counts them by :func:`availability_status`
    and formats a few fixed lines. It emits NO URL, NO item titles (counts only),
    handles an empty list (all counts 0) without crashing, and is truncated to
    ``MAX_CONTENT`` defensively. It reads/writes NO state.
    """
    counts = {"available": 0, "preorder": 0, "unknown": 0}
    for it in items or []:
        status = availability_status(it)
        if status in counts:
            counts[status] += 1

    lines = [
        HEARTBEAT_HEADER,
        "The watcher is running.",
        "Merch items detected — available: %d, preorder: %d, unknown: %d."
        % (counts["available"], counts["preorder"], counts["unknown"]),
        "New relevant hits are posted automatically by the scheduled watch runs; "
        "this daily heartbeat sends no links and changes no state.",
    ]
    msg = "\n".join(lines)
    if len(msg) > MAX_CONTENT:  # defensive: these fixed lines are always short
        msg = msg[: MAX_CONTENT - 1].rstrip() + "…"
    return msg


def send_discord(webhook_url, content, *, session=None, timeout=10):
    """POST JSON ``{"content": content}`` to ``webhook_url``.

    Uses ``session`` if provided (any object exposing ``.post``); otherwise
    creates a ``requests.Session`` lazily. ``requests`` is imported lazily so
    importing this module does not hard-require it.

    Returns ``True`` on a 2xx response. On a non-2xx response or any network
    exception, raises :class:`WebhookError` with a generic reason that never
    includes the webhook URL. Single attempt, no retry loop.
    """
    if session is None:
        import requests  # lazy import: importing this module must not require requests

        session = requests.Session()

    network_failed = False
    response = None
    try:
        response = session.post(webhook_url, json={"content": content}, timeout=timeout)
    except Exception as exc:
        # Log ONLY the exception TYPE. str(exc) can embed the webhook URL/token
        # (requests splits the URL across its message, e.g. host + "url: /path"),
        # so redacting the full-URL string would miss the bare token — never log it.
        logger.debug("Discord send failed (network error): %s", type(exc).__name__)
        network_failed = True

    if network_failed:
        # Raise OUTSIDE the except block so the original (URL-bearing) exception
        # is not attached to WebhookError via __context__/__cause__.
        raise WebhookError("request failed")

    status = getattr(response, "status_code", None)
    if isinstance(status, int) and 200 <= status < 300:
        return True

    logger.debug("Discord send failed with status %s", status)
    raise WebhookError("Discord returned status %s" % status)
