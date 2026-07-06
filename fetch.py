"""fetch.py — NOTIFY-ONLY page watcher for Riftbound x T1 merch.

This module fetches a small set of PUBLIC pages and extracts anchor links as
candidate items for later relevance matching. It performs NO logins, NO
purchases, NO checkout, NO captcha solving and NO aggressive scraping: a single
GET per target, sequentially, with an honest User-Agent.

A "candidate item" is a dict with EXACTLY these four string keys:
    {"title": str, "url": str, "source": str, "text": str}
"""
from __future__ import annotations

import json
import logging
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

logger = logging.getLogger("riot.fetch")

# The Riot merch store host and its product URL pattern
# (https://merch.riotgames.com/<locale>/product/<slug>).
MERCH_HOST = "merch.riotgames.com"

# The Riot merch store renders its product grid client-side but embeds the
# product data in the initial HTML as backslash-escaped JSON (Next.js streamed
# data). Each product object contains a `"title"` shortly before a
# `"slug":"<slug>","ip":{"label":"..."` marker, plus a `"contentType":"product"`
# and an `"availability"` field. We parse that embedded product data — no browser,
# no login, no API calls, no extra requests: it is already in the page we GET.
_PRODUCT_ANCHOR_RE = re.compile(r'"slug":"([a-z0-9][a-z0-9-]{2,80})","ip":\{"label":"([^"]*)"')
_TITLE_RE = re.compile(r'"title":"((?:\\.|[^"\\])*)"')
_AVAIL_RE = re.compile(
    r'"availability":\s*("(?:[^"\\]|\\.)*"|true|false|null|\{[^{}]*\}|\[[^\]]*\]|[a-zA-Z0-9_]+)'
)
_LOCALE_RE = re.compile(r"^[a-z]{2}-[a-z]{2}$")

# Honest User-Agent identifying this as a notify-only watcher.
USER_AGENT = "riot-watcher/0.1 (+notify-only; no automated purchase)"

# Default network timeout, in seconds.
DEFAULT_TIMEOUT = 15

# A small handful of PUBLIC Riot / Riftbound merch pages.
DEFAULT_TARGETS = [
    # PRIMARY: Riot merch store, Riftbound category (shop items).
    "https://merch.riotgames.com/de-de/category/riftbound/",
    # Same category, newest-first variant.
    "https://merch.riotgames.com/de-de/category/riftbound/?page=1&sort=dateDesc",
    # Riot merch home (still merch; filtered downstream).
    "https://merch.riotgames.com/",
]


class _AnchorExtractor(HTMLParser):
    """Collect <a href> anchors and their visible text using only stdlib.

    Produces a list of (href, text) tuples for all anchors seen.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[tuple[str, str]] = []
        self._depth = 0  # nesting depth of <a> tags currently open
        self._href: str | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        if self._depth == 0:
            # Begin a fresh anchor capture.
            href = None
            for name, value in attrs:
                if name == "href":
                    href = value
                    break
            self._href = href
            self._text_parts = []
        self._depth += 1

    def handle_endtag(self, tag):
        if tag != "a" or self._depth == 0:
            return
        self._depth -= 1
        if self._depth == 0:
            text = " ".join(" ".join(self._text_parts).split())
            self.anchors.append((self._href or "", text))
            self._href = None
            self._text_parts = []

    def handle_data(self, data):
        if self._depth > 0 and data:
            self._text_parts.append(data)


def extract_items(source_url: str, html: str) -> list[dict]:
    """Parse anchors from `html` into candidate item dicts.

    Uses ONLY the stdlib html.parser. Relative hrefs are resolved against
    `source_url`. Empty links and pure "#" anchors are skipped.
    """
    if not html:
        return []

    parser = _AnchorExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:  # malformed HTML should never crash the watcher
        logger.warning("failed to parse HTML from %s: %s", source_url, type(exc).__name__)

    items: list[dict] = []
    for href, text in parser.anchors:
        href = (href or "").strip()
        if not href or href.startswith("#"):
            continue
        absolute = urljoin(source_url, href)
        title = text.strip()
        items.append(
            {
                "title": title,
                "url": absolute,
                "source": source_url,
                "text": title,
            }
        )

    # Also parse products embedded as JSON in the page (the merch store renders
    # its grid client-side but ships the product data in the initial HTML).
    seen_urls = {it["url"] for it in items}
    for product in extract_products_json(source_url, html):
        if product["url"] not in seen_urls:
            items.append(product)
            seen_urls.add(product["url"])
    return items


def _locale_from_source(source_url: str) -> str:
    """Return the locale segment (e.g. 'de-de') from a merch URL; default 'de-de'."""
    try:
        for part in urlparse(source_url).path.split("/"):
            if _LOCALE_RE.match(part):
                return part
    except Exception:
        pass
    return "de-de"


def _availability_text(raw_value: str) -> str:
    """Map a product's embedded availability value to a phrase the availability
    detector understands ('sold out' / 'pre-order' / 'available' / 'coming soon'),
    or '' when unknown. Best-effort and honest — never invents availability.
    """
    v = (raw_value or "").lower()
    if any(k in v for k in ("sold", "out_of", "out-of", "outofstock", "unavail", "not_avail", "notavail", "ausverkauft")):
        return "sold out"
    if "preorder" in v or "vorbestell" in v or ("pre" in v and "order" in v):
        return "pre-order"
    if any(k in v for k in ("in_stock", "instock", "in stock", "available", "auf lager", "lieferbar", "verfugbar", "verfügbar")):
        return "available"
    if "coming" in v or "soon" in v:
        return "coming soon"
    return ""


def extract_products_json(source_url: str, html: str) -> list[dict]:
    """Extract Riot merch product items from product data embedded in the page.

    The merch store renders products client-side but embeds the product data as
    backslash-escaped JSON in the initial HTML. We reverse one level of escaping
    and pull each product's title, slug (built into a product URL) and
    availability. Returns candidate item dicts {title, url, source, text}.
    Pure/offline; never raises and never makes a request.
    """
    if not html:
        return []
    try:
        # Reverse one level of JSON-string escaping used by the streamed data.
        un = html.replace('\\"', '"').replace('\\/', '/')
        locale = _locale_from_source(source_url)
        base = "https://%s/%s/product/" % (MERCH_HOST, locale)
        items: list[dict] = []
        seen: set[str] = set()
        anchors = list(_PRODUCT_ANCHOR_RE.finditer(un))
        for idx, m in enumerate(anchors):
            slug = m.group(1)
            ip_label = (m.group(2) or "").strip()
            if slug in seen:
                continue
            seen.add(slug)
            # Title: the nearest preceding "title":"..." (the product title sits
            # just before the slug marker; "trackingTitle" does not match).
            before = un[max(0, m.start() - 600):m.start()]
            titles = _TITLE_RE.findall(before)
            raw_title = titles[-1] if titles else slug
            try:
                title = json.loads('"' + raw_title + '"')
            except Exception:
                title = raw_title
            # Availability: search only within this product's object (bounded by
            # the next product marker). Honest 'unknown' when absent.
            end = anchors[idx + 1].start() if idx + 1 < len(anchors) else min(len(un), m.end() + 2500)
            after = un[m.end():end]
            av = _AVAIL_RE.search(after)
            # Include the availability phrase AND the product's IP label (e.g.
            # "Riftbound") in the item text, so relevance stays correct even if a
            # slug/title omits the token (relevance ignores `source`).
            text = " ".join(
                t for t in (_availability_text(av.group(1) if av else ""), ip_label) if t
            ).strip()
            items.append(
                {
                    "title": (title or slug).strip() or slug,
                    "url": base + slug,
                    "source": source_url,
                    "text": text,
                }
            )
        return items
    except Exception as exc:  # never let a parser hiccup crash the watcher
        logger.warning(
            "failed to parse embedded product JSON from %s: %s",
            source_url, type(exc).__name__,
        )
        return []


def fetch_page(url: str, *, session=None, timeout: int = DEFAULT_TIMEOUT) -> str | None:
    """GET `url` once with an honest User-Agent and return its text, or None.

    DEFENSIVE: exactly ONE attempt (no retry loop). On any exception, timeout,
    or non-200 status, log a warning and return None. Never logs secrets or
    dumps response bodies.
    """
    own_session = False
    if session is None:
        try:
            import requests  # imported lazily so importing this module is cheap
        except Exception as exc:
            logger.warning("requests unavailable, cannot fetch %s: %s", url, type(exc).__name__)
            return None
        session = requests.Session()
        own_session = True

    headers = {"User-Agent": USER_AGENT}
    try:
        try:
            response = session.get(url, headers=headers, timeout=timeout)
        except Exception as exc:
            logger.warning("fetch failed for %s: %s", url, type(exc).__name__)
            return None

        status = getattr(response, "status_code", None)
        if status != 200:
            logger.warning("non-200 status %s for %s", status, url)
            return None

        return getattr(response, "text", "") or ""
    finally:
        # Close a session we created ourselves (a caller-supplied session is the
        # caller's to close).
        if own_session:
            try:
                session.close()
            except Exception:
                pass


def fetch_targets(
    targets: list[str] | None = None,
    *,
    session=None,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict]:
    """Fetch each target sequentially and return combined candidate items.

    Targets whose fetch_page returns None are skipped. No threads/async — this
    is a low-load, notify-only watcher.
    """
    if targets is None:
        targets = DEFAULT_TARGETS

    own_session = False
    if session is None:
        try:
            import requests  # imported lazily so importing this module is cheap
        except Exception as exc:
            logger.warning("requests unavailable, cannot fetch targets: %s", type(exc).__name__)
            return []
        session = requests.Session()
        own_session = True

    items: list[dict] = []
    try:
        for url in targets:
            html = fetch_page(url, session=session, timeout=timeout)
            if html is None:
                continue
            items.extend(extract_items(url, html))
    finally:
        # Reuse one session across all targets, then close it if we own it.
        if own_session:
            try:
                session.close()
            except Exception:
                pass
    return items
