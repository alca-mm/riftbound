"""state.py — persistence layer for already-seen items.

State schema (a plain dict)::

    {
        "version": 1,
        "seen": {
            "<item_id>": {"url": str, "title": str, "first_seen": <ISO8601 str>}
        }
    }

All disk writes are atomic (temp file + os.replace) so a crash never leaves a
half-written state file behind. Reads are robust: a missing, corrupt, or
schema-invalid file yields a fresh state instead of raising.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone

logger = logging.getLogger("riot.state")

DEFAULT_STATE_PATH: str = "state.json"
STATE_VERSION: int = 1


def fresh_state() -> dict:
    """Return a brand-new, empty state dict."""
    return {"version": STATE_VERSION, "seen": {}}


def item_id(item: dict) -> str:
    """Return a stable sha256 id for a candidate item.

    The id is derived from the normalized url (lowercased, stripped) when the
    url is non-empty, otherwise from the normalized title. The same logical
    item always maps to the same id.
    """
    url = (item.get("url") or "").strip().lower()
    title = (item.get("title") or "").strip().lower()
    key = url if url else title
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def state_exists(path: str = DEFAULT_STATE_PATH) -> bool:
    """True if a state file exists at `path`."""
    return os.path.exists(path)


def _is_valid_state(data: object) -> bool:
    return (
        isinstance(data, dict)
        and "version" in data
        and isinstance(data.get("seen"), dict)
    )


def load_state(path: str = DEFAULT_STATE_PATH) -> dict:
    """Load state from `path`, robustly.

    Returns a fresh state (never raises) if the file is missing, contains
    invalid JSON, or is missing required keys. Corruption is logged as a
    warning.
    """
    if not os.path.exists(path):
        return fresh_state()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        logger.warning("Could not read state file %s: %s; using fresh state", path, exc)
        return fresh_state()
    if not _is_valid_state(data):
        logger.warning("State file %s is missing required keys; using fresh state", path)
        return fresh_state()
    return data


def state_status(path: str = DEFAULT_STATE_PATH) -> str:
    """Classify the state file at `path` as 'missing', 'valid', or 'corrupt'.

    Lets the caller tell a genuine first run (missing) apart from an unreadable
    or schema-invalid file (corrupt), so corruption can trigger a fresh baseline
    instead of being mistaken for an empty state — which would otherwise re-post
    every relevant item.
    """
    if not os.path.exists(path):
        return "missing"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return "corrupt"
    return "valid" if _is_valid_state(data) else "corrupt"


def save_state(path: str, state: dict) -> None:
    """Atomically write `state` to `path`.

    Writes to a temp file in the same directory, then os.replace() onto the
    target path so readers never observe a partially-written file. The parent
    directory is created if needed.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        # Never leave a stray temp file behind on failure.
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def new_items(items: list[dict], state: dict) -> list[dict]:
    """Return items whose id is not already present in state["seen"]."""
    seen = state.get("seen", {})
    return [it for it in items if item_id(it) not in seen]


def record_items(state: dict, items: list[dict], *, now: str | None = None) -> dict:
    """Record `items` into `state`, returning the updated state.

    Each item's id is added to state["seen"] with its url, title, and
    first_seen timestamp. Items already present keep their original
    first_seen. `now` defaults to the current UTC time in ISO8601 form.
    """
    if now is None:
        now = datetime.now(timezone.utc).isoformat()
    seen = state.setdefault("seen", {})
    for it in items:
        iid = item_id(it)
        if iid in seen:
            continue
        seen[iid] = {
            "url": it.get("url", ""),
            "title": it.get("title", ""),
            "first_seen": now,
        }
    return state
