"""relevance.py — Riftbound merch scope + T1/special highlight detection.

A "candidate item" is a dict with EXACTLY these keys:
    {"title": str, "url": str, "source": str, "text": str}

Two separate questions, deliberately NOT the same one:

  * WATCH SCOPE — :func:`is_riftbound_merch_relevant`: is this a Riot-merch
    Riftbound shop item? This decides whether a new item is posted at all.
  * SPECIAL FOCUS — :func:`is_special_focus`: is it a T1 / Worlds Champion
    Collection / Signature Edition / Player Bundle / Faker / Galio item? This
    only MARKS the item as a highlight; it is never a precondition for posting.

Most matching is performed against the combined, lowercased text of
title + text + url. The watch scope additionally consults ``source``, so a
product scraped from the Riftbound category page stays in scope even when its
title and slug never spell out "Riftbound".

The legacy :func:`is_relevant` / :func:`filter_relevant` pair is unchanged and
retained for the narrow Riftbound×T1 question.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# Strong subjects: each makes an item relevant on its own.
STRONG_SUBJECTS: tuple[str, ...] = (
    "riftbound",
    "worlds champion collection",
    "signature edition",
    "player bundle",
    "t1",
)

# Ambiguous champion / T1-player tokens. On their own they appear all over
# generic League content (e.g. "Doran's Blade", a "Galio" patch note), so they
# only count when a Riftbound/T1 anchor is also present. They are matched as
# whole words so "commissioner" does not match "oner".
CONDITIONAL_SUBJECTS: tuple[str, ...] = (
    "faker",
    "galio",
    # Known T1 players.
    "gumayusi",
    "keria",
    "oner",
    "zeus",
    "doran",
)

# Anchors that establish a Riftbound/T1 context for the conditional tokens.
ANCHOR_SUBJECTS: tuple[str, ...] = ("riftbound", "t1")

# Public union — unchanged membership so callers and logging keep seeing every
# focus token.
FOCUS_SUBJECTS: tuple[str, ...] = STRONG_SUBJECTS + CONDITIONAL_SUBJECTS

# Signals recognized for richer logging but NOT sufficient on their own.
CONTEXT_SIGNALS: tuple[str, ...] = (
    # Drawing / lottery signals.
    "drawing",
    "lottery",
    "raffle",
    "sweepstakes",
    # Availability signals.
    "in stock",
    "available",
    "restock",
    "sold out",
    "drop",
)

# Subjects that must match as a whole word (avoid false positives such as
# "t100" matching "t1", or "commissioner" matching "oner").
_WHOLE_WORD_SUBJECTS = frozenset({"t1", *CONDITIONAL_SUBJECTS})


def _combined_text(item: dict) -> str:
    """Combined, lowercased title + text + url of a candidate item."""
    return " ".join(
        (
            item.get("title", ""),
            item.get("text", ""),
            item.get("url", ""),
        )
    ).lower()


def _contains(haystack: str, needle: str) -> bool:
    """True if `needle` is present in `haystack`.

    Subjects in `_WHOLE_WORD_SUBJECTS` are matched on word boundaries only.
    """
    if needle in _WHOLE_WORD_SUBJECTS:
        return re.search(r"\b" + re.escape(needle) + r"\b", haystack) is not None
    return needle in haystack


def _has_anchor(text: str) -> bool:
    """True if a Riftbound/T1 anchor is present in the combined text."""
    return any(_contains(text, a) for a in ANCHOR_SUBJECTS)


def is_relevant(item: dict) -> bool:
    """True iff the item is about the Riftbound x T1 collection.

    A strong subject matches on its own. The ambiguous champion/player tokens
    only count when a Riftbound/T1 anchor is also present, so generic League
    news (e.g. a "Doran's Blade" or "Galio" patch note) is not flagged.
    """
    text = _combined_text(item)
    if any(_contains(text, s) for s in STRONG_SUBJECTS):
        return True
    if _has_anchor(text):
        return any(_contains(text, c) for c in CONDITIONAL_SUBJECTS)
    return False


def relevance_reasons(item: dict) -> list[str]:
    """Return the sorted list of matched signal labels for a relevant item.

    Includes matched strong subjects, matched conditional tokens (only when a
    Riftbound/T1 anchor is present), and any matched context signals. Returns an
    empty list when the item is not relevant. Used for logging only; the result
    is deterministic (sorted).
    """
    text = _combined_text(item)
    strong = [s for s in STRONG_SUBJECTS if _contains(text, s)]
    conditional = (
        [c for c in CONDITIONAL_SUBJECTS if _contains(text, c)]
        if _has_anchor(text)
        else []
    )
    if not strong and not conditional:
        return []
    context = [s for s in CONTEXT_SIGNALS if _contains(text, s)]
    return sorted(set(strong + conditional + context))


def filter_relevant(items: list[dict]) -> list[dict]:
    """Return only the relevant items, preserving order."""
    return [it for it in items if is_relevant(it)]


def is_riftbound(item: dict) -> bool:
    """True iff the combined text contains "riftbound".

    Used by the test-webhook mode.
    """
    return "riftbound" in _combined_text(item)


# --- Shop relevance vs special relevance ------------------------------------
#
# WATCH SCOPE (is_riftbound_merch_relevant): any Riot-merch Riftbound SHOP
# product. This is what decides whether a NEW item gets posted at all. It is
# deliberately NOT limited to T1.
#
# SPECIAL FOCUS (is_special_focus): T1 / Worlds Champion Collection / Signature
# Edition / Player Bundle / Faker / Galio. This only MARKS an item as a
# highlight — it is never a precondition for posting.

# Special-focus subjects that count on their own. Note that "riftbound" is
# deliberately absent: it is the watch SCOPE, not a highlight reason.
SPECIAL_STRONG_SUBJECTS: tuple[str, ...] = (
    "worlds champion collection",
    "signature edition",
    "player bundle",
    "t1",
)

# Context signals worth naming as a HIGHLIGHT reason. Availability signals are
# deliberately excluded: the message carries its own "Status:" line, so repeating
# "available" in the "Match:" line would be noise.
SPECIAL_CONTEXT_SIGNALS: tuple[str, ...] = (
    "drawing",
    "lottery",
    "raffle",
    "sweepstakes",
)

MERCH_HOST = "merch.riotgames.com"

# The Riot merch Riftbound category page(s) we watch. Any locale prefix and any
# query string (e.g. "?page=1&sort=dateDesc") is tolerated.
_RIFTBOUND_CATEGORY_PATH = "/category/riftbound"

# Path fragments that mark the item itself as a concrete shop product. Required
# when relevance is derived from the CATEGORY SOURCE alone, so that navigation,
# footer and legal links on the category page never become "new merch items".
_PRODUCT_PATH_HINTS: tuple[str, ...] = ("/product/", "/products/", "/p/")


def _is_riftbound_category_product(item: dict) -> bool:
    """True if the item is a concrete merch PRODUCT whose SOURCE is the Riot
    merch Riftbound category page.

    This is the case the title+text+url filter misses: a product such as
    "Champion Deck - Jinx" whose title, slug and ip.label never spell out
    "Riftbound", but which was scraped from the Riftbound category page.
    Requiring a product URL keeps nav/footer links on that page out.
    """
    item = item or {}
    source = urlparse(str(item.get("source", "") or "").lower())
    if MERCH_HOST not in source.netloc:
        return False
    if _RIFTBOUND_CATEGORY_PATH not in source.path:
        return False

    url = urlparse(str(item.get("url", "") or "").lower())
    if MERCH_HOST not in url.netloc:
        return False
    return any(hint in url.path for hint in _PRODUCT_PATH_HINTS)


def is_special_focus(item: dict) -> bool:
    """True iff the item is a T1 / Worlds Champion Collection / Signature Edition
    / Player Bundle / Faker / Galio highlight.

    A HIGHLIGHT MARKER ONLY — never a precondition for posting. The ambiguous
    champion/player tokens still require a Riftbound/T1 anchor so a generic
    "Galio" patch note is not flagged.
    """
    text = _combined_text(item)
    if any(_contains(text, s) for s in SPECIAL_STRONG_SUBJECTS):
        return True
    if _has_anchor(text):
        return any(_contains(text, c) for c in CONDITIONAL_SUBJECTS)
    return False


def special_reasons(item: dict) -> list[str]:
    """Sorted highlight labels for a special-focus item, else an empty list.

    Includes matched special subjects, matched conditional tokens (only with a
    Riftbound/T1 anchor) and any matched drawing/lottery signals. Deterministic.
    Unlike :func:`relevance_reasons` this reports neither "riftbound" (the watch
    scope, not a highlight reason) nor availability signals (the message carries
    its own "Status:" line).
    """
    if not is_special_focus(item):
        return []
    text = _combined_text(item)
    strong = [s for s in SPECIAL_STRONG_SUBJECTS if _contains(text, s)]
    conditional = (
        [c for c in CONDITIONAL_SUBJECTS if _contains(text, c)]
        if _has_anchor(text)
        else []
    )
    context = [s for s in SPECIAL_CONTEXT_SIGNALS if _contains(text, s)]
    return sorted(set(strong + conditional + context))


def is_riftbound_merch_relevant(item: dict) -> bool:
    """True iff the item is in the watch SCOPE: a Riot-merch Riftbound shop item.

    Riftbound scope is established by any of:
      * the literal "riftbound" token in title/text/url (covers ip.label, which
        :mod:`fetch` folds into ``text``), or
      * a merch PRODUCT scraped from the Riftbound category page (source-based),
        which catches products whose title/slug omit the token entirely, or
      * a special-focus match (T1 / Worlds / Signature / Player Bundle / …),
        which keeps historic T1 items in scope even without the token.

    This is only the SCOPE. Callers must still apply the shop gate
    (``notify.is_shop_candidate``) so general Riftbound articles — get-started,
    how-to-play, newsletters, top decks — never reach Discord.
    """
    return (
        is_riftbound(item)
        or _is_riftbound_category_product(item)
        or is_special_focus(item)
    )
