"""Tests for state.py — the seen-items persistence layer.

Uses pytest's tmp_path fixture for all file paths; never touches the real
state.json in the project root.
"""
import json
import os

import state


def item(title="Title", url=""):
    return {"title": title, "url": url, "source": "", "text": ""}


# ---------------------------------------------------------------------------
# fresh_state / constants
# ---------------------------------------------------------------------------
def test_fresh_state_shape():
    fs = state.fresh_state()
    assert fs == {"version": state.STATE_VERSION, "seen": {}}
    assert state.STATE_VERSION == 1


def test_default_state_path_constant():
    assert state.DEFAULT_STATE_PATH == "state.json"


# ---------------------------------------------------------------------------
# item_id
# ---------------------------------------------------------------------------
def test_item_id_stable_for_same_item():
    it = item("Something", "https://example.com/a")
    assert state.item_id(it) == state.item_id(it)


def test_item_id_same_url_same_id():
    a = item("Title A", "https://example.com/thing")
    b = item("Totally Different Title", "https://example.com/thing")
    assert state.item_id(a) == state.item_id(b)


def test_item_id_differs_for_different_urls():
    a = item("Title", "https://example.com/a")
    b = item("Title", "https://example.com/b")
    assert state.item_id(a) != state.item_id(b)


def test_item_id_url_normalized_case_and_whitespace():
    a = item("T", "https://example.com/A")
    b = item("T", "  HTTPS://EXAMPLE.COM/A  ")
    assert state.item_id(a) == state.item_id(b)


def test_item_id_falls_back_to_title_when_url_empty():
    a = item("Same Title", "")
    b = item("same title", "")
    assert state.item_id(a) == state.item_id(b)


def test_item_id_is_hex_string():
    iid = state.item_id(item("T", "https://example.com/a"))
    assert isinstance(iid, str) and iid
    int(iid, 16)  # raises if not hex


# ---------------------------------------------------------------------------
# state_exists
# ---------------------------------------------------------------------------
def test_state_exists(tmp_path):
    p = tmp_path / "state.json"
    assert state.state_exists(str(p)) is False
    p.write_text("{}", encoding="utf-8")
    assert state.state_exists(str(p)) is True


# ---------------------------------------------------------------------------
# load_state — robustness
# ---------------------------------------------------------------------------
def test_load_state_missing_returns_fresh(tmp_path):
    p = tmp_path / "does_not_exist.json"
    assert state.load_state(str(p)) == state.fresh_state()


def test_load_state_broken_json_returns_fresh_no_raise(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{ this is not json ]]", encoding="utf-8")
    result = state.load_state(str(p))
    assert result == state.fresh_state()


def test_load_state_missing_keys_returns_fresh(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
    assert state.load_state(str(p)) == state.fresh_state()


def test_load_state_valid_roundtrips_content(tmp_path):
    p = tmp_path / "state.json"
    data = {"version": 1, "seen": {"abc": {"url": "u", "title": "t", "first_seen": "2026-01-01T00:00:00+00:00"}}}
    p.write_text(json.dumps(data), encoding="utf-8")
    assert state.load_state(str(p)) == data


# ---------------------------------------------------------------------------
# save_state — atomic write + round-trip
# ---------------------------------------------------------------------------
def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    st = state.fresh_state()
    st["seen"]["id1"] = {"url": "https://example.com/a", "title": "A", "first_seen": "2026-01-01T00:00:00+00:00"}
    state.save_state(str(p), st)
    assert os.path.exists(str(p))
    assert state.load_state(str(p)) == st


def test_save_state_creates_parent_dir(tmp_path):
    p = tmp_path / "nested" / "deeper" / "state.json"
    st = state.fresh_state()
    state.save_state(str(p), st)
    assert os.path.exists(str(p))
    assert state.load_state(str(p)) == st


def test_save_state_leaves_no_temp_files(tmp_path):
    p = tmp_path / "state.json"
    state.save_state(str(p), state.fresh_state())
    names = [n for n in os.listdir(str(tmp_path))]
    assert names == ["state.json"]


# ---------------------------------------------------------------------------
# new_items
# ---------------------------------------------------------------------------
def test_new_items_filters_seen_preserving_order():
    a = item("A", "https://example.com/a")
    b = item("B", "https://example.com/b")
    c = item("C", "https://example.com/c")
    st = state.fresh_state()
    st["seen"][state.item_id(b)] = {"url": "https://example.com/b", "title": "B", "first_seen": "x"}
    result = state.new_items([a, b, c], st)
    assert result == [a, c]


def test_new_items_all_new_on_fresh_state():
    a = item("A", "https://example.com/a")
    b = item("B", "https://example.com/b")
    assert state.new_items([a, b], state.fresh_state()) == [a, b]


def test_new_items_empty():
    assert state.new_items([], state.fresh_state()) == []


# ---------------------------------------------------------------------------
# record_items
# ---------------------------------------------------------------------------
def test_record_items_adds_ids_to_seen():
    a = item("A", "https://example.com/a")
    st = state.record_items(state.fresh_state(), [a], now="2026-01-01T00:00:00+00:00")
    iid = state.item_id(a)
    assert iid in st["seen"]
    assert st["seen"][iid]["url"] == "https://example.com/a"
    assert st["seen"][iid]["title"] == "A"
    assert st["seen"][iid]["first_seen"] == "2026-01-01T00:00:00+00:00"


def test_record_items_preserves_existing_first_seen():
    a = item("A", "https://example.com/a")
    st = state.record_items(state.fresh_state(), [a], now="2026-01-01T00:00:00+00:00")
    st2 = state.record_items(st, [a], now="2099-12-31T23:59:59+00:00")
    iid = state.item_id(a)
    assert st2["seen"][iid]["first_seen"] == "2026-01-01T00:00:00+00:00"


def test_record_items_default_now_is_iso8601_string():
    a = item("A", "https://example.com/a")
    st = state.record_items(state.fresh_state(), [a])
    iid = state.item_id(a)
    fs = st["seen"][iid]["first_seen"]
    assert isinstance(fs, str) and fs
    # Must be parseable as an ISO8601 datetime.
    from datetime import datetime
    datetime.fromisoformat(fs)


def test_record_items_multiple():
    a = item("A", "https://example.com/a")
    b = item("B", "https://example.com/b")
    st = state.record_items(state.fresh_state(), [a, b], now="2026-01-01T00:00:00+00:00")
    assert state.item_id(a) in st["seen"]
    assert state.item_id(b) in st["seen"]
    assert len(st["seen"]) == 2


# ---------------------------------------------------------------------------
# state_status — distinguishes missing / valid / corrupt so the watcher can
# re-baseline on corruption instead of mass-posting.
# ---------------------------------------------------------------------------
def test_state_status_missing(tmp_path):
    assert state.state_status(str(tmp_path / "nope.json")) == "missing"


def test_state_status_valid(tmp_path):
    p = tmp_path / "state.json"
    state.save_state(str(p), state.fresh_state())
    assert state.state_status(str(p)) == "valid"


def test_state_status_corrupt_json(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{ not valid json ]]", encoding="utf-8")
    assert state.state_status(str(p)) == "corrupt"


def test_state_status_wrong_schema(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert state.state_status(str(p)) == "corrupt"
