"""fetch.py — NOTIFY-ONLY page watcher for Riftbound x T1 merch.

This module fetches a small set of PUBLIC pages and extracts anchor links as
candidate items for later relevance matching. It performs NO logins, NO
purchases, NO checkout, NO captcha solving and NO aggressive scraping: a single
GET per target, sequentially, with an honest User-Agent.

A "candidate item" is a dict with EXACTLY these four string keys:
    {"title": str, "url": str, "source": str, "text": str}
"""
from __future__ import annotations

import logging
from html.parser import HTMLParser
from urllib.parse import urljoin

logger = logging.getLogger("riot.fetch")

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
    return items


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
