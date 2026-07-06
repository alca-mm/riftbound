"""relevance.py — narrowly-focused relevance filter for the Riftbound x T1
Worlds Champion Collection.

A "candidate item" is a dict with EXACTLY these keys:
    {"title": str, "url": str, "source": str, "text": str}

Matching is performed against the combined, lowercased text of
title + text + url.
"""
from __future__ import annotations

import re

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
