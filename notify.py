"""notify.py — NOTIFY-ONLY Discord sender for the riot watcher.

This module does exactly one thing: POST a short message to a Discord webhook.
It never logs in, buys, checks out, solves captchas, or bypasses anything.

SECURITY: the webhook URL is a secret. It must NEVER appear in any log line,
exception message, traceback, or repr. Failures raise ``WebhookError`` with a
generic reason, and anything we log is passed through :func:`redact_secrets`
first (we prefer not to log the URL at all).
"""
import logging
from urllib.parse import urljoin, urlparse

logger = logging.getLogger("riot.notify")

# Discord rejects message ``content`` longer than 2000 characters.
MAX_CONTENT = 2000

# Leading line for every notification message.
MESSAGE_HEADER = "New Riftbound × T1 match found:"

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
