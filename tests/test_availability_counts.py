"""Correct product counts and honest availability classification.

Covers the reported Discord contradiction: the heartbeat reported
``available: 16`` while the status report listed only 8 available items. The
watcher fetches two Riftbound category targets that serve identical product
data; nothing deduped them, so every product was counted twice.
"""
import fetch
import notify
import watcher


CATEGORY = "https://merch.riotgames.com/de-de/category/riftbound/"
CATEGORY_SORTED = "https://merch.riotgames.com/de-de/category/riftbound/?page=1&sort=dateDesc"


def _product(slug, title=None, text="Riftbound"):
    return {
        "title": title or slug.replace("-", " ").title(),
        "url": "https://merch.riotgames.com/de-de/product/" + slug,
        "source": CATEGORY,
        "text": text,
    }


def _available(slug, title=None):
    return _product(slug, title, "available Riftbound")


def _sold_out(slug, title=None):
    return _product(slug, title, "sold out Riftbound")


def _preorder(slug, title=None):
    return _product(slug, title, "pre-order Riftbound")


def _unknown(slug, title=None):
    return _product(slug, title, "Riftbound")


def fetch_fn_factory(items):
    def _fetch(targets=None):
        return list(items)

    return _fetch


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, webhook_url, content):
        self.calls.append((webhook_url, content))
        return True


def _sp(tmp_path):
    return str(tmp_path / "state.json")


# --- 1-8: availability parsing ----------------------------------------------

def test_availability_text_plain_strings():
    assert fetch._availability_text('"inStock"') == "available"
    assert fetch._availability_text('"outOfStock"') == "sold out"
    assert fetch._availability_text('"available"') == "available"
    assert fetch._availability_text('"preorder"') == "pre-order"
    assert fetch._availability_text('"in_stock"') == "available"
    assert fetch._availability_text('"comingSoon"') == "coming soon"


def test_availability_text_unavailable_is_never_available():
    """Regression: 'unavailable' contains the substring 'available'."""
    assert fetch._availability_text('"unavailable"') == "sold out"
    assert fetch._availability_text('"notAvailable"') == "sold out"
    assert fetch._availability_text('"not_available"') == "sold out"
    assert fetch._availability_text('"ausverkauft"') == "sold out"


def test_availability_text_object_with_boolean_false_is_sold_out():
    """Regression: {"available":false} used to classify as available."""
    assert fetch._availability_text('{"available":false}') == "sold out"
    assert fetch._availability_text('{"available": false}') == "sold out"
    assert fetch._availability_text('{"availableForSale":false}') == "sold out"
    assert fetch._availability_text('{"isAvailable":false}') == "sold out"


def test_availability_text_object_with_boolean_true_is_available():
    assert fetch._availability_text('{"available":true}') == "available"
    assert fetch._availability_text('{"availableForSale": true}') == "available"
    assert fetch._availability_text('{"outOfStock":false}') == "available"
    assert fetch._availability_text('{"outOfStock":true}') == "sold out"


def test_availability_text_bare_booleans_and_null():
    assert fetch._availability_text("true") == "available"
    assert fetch._availability_text("false") == "sold out"
    assert fetch._availability_text("null") == ""
    assert fetch._availability_text("") == ""


def test_availability_text_variants_any_available_wins():
    raw = '[{"availability":"outOfStock"},{"availability":"inStock"}]'
    assert fetch._availability_text(raw) == "available"


def test_availability_text_variants_all_unavailable_is_sold_out():
    raw = '[{"availability":"outOfStock"},{"availability":"outOfStock"}]'
    assert fetch._availability_text(raw) == "sold out"


def test_availability_text_variants_only_preorder_is_preorder():
    raw = '[{"availability":"preorder"},{"availability":"preorder"}]'
    assert fetch._availability_text(raw) == "pre-order"


def test_availability_text_unrecognised_is_unknown():
    assert fetch._availability_text('"someNewRiotState"') == ""


def test_availability_status_end_to_end_for_each_bucket():
    assert notify.availability_status(_available("a")) == "available"
    assert notify.availability_status(_sold_out("b")) == "sold_out"
    assert notify.availability_status(_preorder("c")) == "preorder"
    assert notify.availability_status(_unknown("d")) == "unknown"


# --- 9-12: extraction / dedupe ----------------------------------------------

def _embedded(slug, title, availability):
    return (
        '{\\"title\\":\\"%s\\",\\"slug\\":\\"%s\\",\\"ip\\":{\\"label\\":\\"Riftbound\\"},'
        '\\"contentType\\":\\"product\\",\\"availability\\":\\"%s\\"}' % (title, slug, availability)
    )


def test_extract_products_json_extracts_every_product_object():
    html = "".join(
        _embedded("riftbound-item-%02d" % i, "Riftbound Item %02d" % i,
                  "inStock" if i < 8 else "outOfStock")
        for i in range(23)
    )
    items = fetch.extract_products_json(CATEGORY, html)
    assert len(items) == 23
    counts = {}
    for it in items:
        counts[notify.availability_status(it)] = counts.get(notify.availability_status(it), 0) + 1
    assert counts == {"available": 8, "sold_out": 15}


def test_extract_products_json_keeps_similar_titles_separate():
    """Two distinct products may share a title; the slug/URL keeps them apart."""
    html = _embedded("riftbound-playmat-vi", "Riftbound Playmat", "inStock") + _embedded(
        "riftbound-playmat-poppy", "Riftbound Playmat", "inStock"
    )
    items = fetch.extract_products_json(CATEGORY, html)
    assert len(items) == 2
    assert {i["url"] for i in items} == {
        "https://merch.riotgames.com/de-de/product/riftbound-playmat-vi",
        "https://merch.riotgames.com/de-de/product/riftbound-playmat-poppy",
    }


def test_dedupe_items_by_url_not_title():
    same_title_different_url = [_available("slug-a", "Same Title"), _available("slug-b", "Same Title")]
    assert len(notify.dedupe_items(same_title_different_url)) == 2

    same_url_twice = [_available("slug-a"), _available("slug-a")]
    assert len(notify.dedupe_items(same_url_twice)) == 1


def test_dedupe_items_falls_back_to_title_when_url_empty():
    items = [
        {"title": "Riftbound A", "url": "", "source": "", "text": ""},
        {"title": "riftbound a", "url": "", "source": "", "text": ""},
        {"title": "Riftbound B", "url": "", "source": "", "text": ""},
    ]
    assert len(notify.dedupe_items(items)) == 2


def test_dedupe_items_preserves_input_order_newest_first():
    items = [_available("newest"), _available("middle"), _available("oldest"), _available("newest")]
    out = notify.dedupe_items(items)
    assert [i["url"].rsplit("/", 1)[1] for i in out] == ["newest", "middle", "oldest"]


# --- the reported bug: identical targets must not double-count ---------------

def test_two_identical_category_targets_do_not_double_count(tmp_path):
    """The exact reported contradiction: heartbeat said available: 16 while the
    status report listed 8. Both targets serve the same 16 products."""
    products = [_available("a%d" % i) for i in range(8)] + [_sold_out("s%d" % i) for i in range(8)]
    from_target_1 = products
    from_target_2 = [dict(p, source=CATEGORY_SORTED) for p in products]

    send = Recorder()
    summary = watcher.run(
        watcher.MODE_HEARTBEAT,
        state_path=_sp(tmp_path),
        webhook_url="https://example.invalid/hook",
        fetch_fn=fetch_fn_factory(from_target_1 + from_target_2),
        send_fn=send,
    )
    assert summary["relevant"] == 16
    content = send.calls[0][1]
    assert "total: 16" in content
    assert "available: 8" in content
    assert "unavailable: 8" in content


def test_duplicate_urls_in_one_pass_send_only_one_message(tmp_path):
    sp = _sp(tmp_path)
    hook = "https://example.invalid/hook"
    watcher.run(watcher.MODE_NORMAL, state_path=sp, webhook_url=hook,
                fetch_fn=fetch_fn_factory([_available("baseline")]), send_fn=Recorder())

    dup = _available("brand-new")
    send = Recorder()
    summary = watcher.run(
        watcher.MODE_NORMAL, state_path=sp, webhook_url=hook,
        fetch_fn=fetch_fn_factory([_available("baseline"), dup, dict(dup, source=CATEGORY_SORTED)]),
        send_fn=send,
    )
    assert summary["new"] == 1
    assert len(send.calls) == 1


# --- 14-20: status report ---------------------------------------------------

def _mixed_23():
    """8 available + 15 sold out = 23 distinct products."""
    return [_available("av-%02d" % i, "Riftbound Available %02d" % i) for i in range(8)] + [
        _sold_out("so-%02d" % i, "Riftbound SoldOut %02d" % i) for i in range(15)
    ]


def test_status_report_shows_total_and_all_status_counts():
    msg = notify.format_status_report(_mixed_23())
    assert "Detected Riftbound merch items: 23" in msg
    assert "Available: 8" in msg
    assert "Unavailable / sold out: 15" in msg
    assert "Preorder: 0" in msg
    assert "Unknown: 0" in msg


def test_status_report_counts_add_up_to_total():
    items = [_available("a"), _sold_out("s"), _preorder("p"), _unknown("u")]
    msg = notify.format_status_report(items)
    assert "Detected Riftbound merch items: 4" in msg
    assert "Available: 1" in msg
    assert "Unavailable / sold out: 1" in msg
    assert "Preorder: 1" in msg
    assert "Unknown: 1" in msg


def test_status_report_lists_unavailable_items_in_their_own_section():
    msg = notify.format_status_report(_mixed_23())
    assert notify.UNAVAILABLE_HEADER in msg
    after = msg.split(notify.UNAVAILABLE_HEADER)[1]
    assert "Riftbound SoldOut 00" in after
    # available items stay in the available section, above the unavailable one
    assert msg.index("Riftbound Available 00") < msg.index(notify.UNAVAILABLE_HEADER)


def test_status_report_caps_both_sections_and_reports_the_remainder():
    msg = notify.format_status_report(_mixed_23(), max_items=10)
    assert "...and 5 more unavailable item(s)." in msg
    # 8 available items fit under the cap of 10, so no available tail
    assert "more available item(s)." not in msg


def test_status_report_zero_unavailable_still_reports_the_count():
    msg = notify.format_status_report([_available("a")])
    assert "Unavailable / sold out: 0" in msg
    assert notify.UNAVAILABLE_HEADER not in msg


def test_status_report_has_no_links_and_stays_under_discord_limit():
    long_title = "Riftbound: League of Legends TCG " + "X" * 90
    items = [_available("av-%02d" % i, long_title + " A%02d" % i) for i in range(12)] + [
        _sold_out("so-%02d" % i, long_title + " S%02d" % i) for i in range(12)
    ]
    msg = notify.format_status_report(items)
    assert "http" not in msg
    assert len(msg) <= notify.MAX_CONTENT


def test_status_report_dedupes_by_url_so_duplicate_targets_do_not_inflate():
    products = [_available("a%d" % i) for i in range(8)]
    dup = products + [dict(p, source=CATEGORY_SORTED) for p in products]
    msg = notify.format_status_report(dup)
    assert "Detected Riftbound merch items: 8" in msg
    assert "Available: 8" in msg


def test_status_report_preserves_newest_first_order():
    items = [_available("newest", "Riftbound Newest"), _available("older", "Riftbound Older")]
    msg = notify.format_status_report(items)
    assert msg.index("1. Riftbound Newest") < msg.index("2. Riftbound Older")


def test_status_report_counts_coming_soon_only_when_present():
    plain = notify.format_status_report([_available("a")])
    assert "Coming soon:" not in plain

    soon = notify.format_status_report([_available("a"), _product("b", text="coming soon Riftbound")])
    assert "Coming soon: 1" in soon


# --- 21-25: heartbeat --------------------------------------------------------

def test_heartbeat_reports_total_and_every_bucket():
    items = [_available("a"), _available("a2"), _sold_out("s"), _preorder("p"), _unknown("u")]
    msg = notify.format_heartbeat(items)
    assert "total: 5" in msg
    assert "available: 2" in msg
    assert "unavailable: 1" in msg
    assert "preorder: 1" in msg
    assert "unknown: 1" in msg


def test_heartbeat_available_count_excludes_sold_out():
    items = [_available("a")] + [_sold_out("s%d" % i) for i in range(15)]
    msg = notify.format_heartbeat(items)
    assert "total: 16" in msg
    assert "unavailable: 15" in msg
    # the true available count is 1 and must not be inflated to 16
    assert "— total: 16, available: 1," in msg


def test_heartbeat_has_no_links_and_no_product_list():
    items = [_available("a", "Riftbound Secret Vault Title"), _sold_out("s", "Riftbound Hidden Hoodie")]
    msg = notify.format_heartbeat(items)
    assert "http" not in msg
    assert "Riftbound Secret Vault Title" not in msg
    assert "Riftbound Hidden Hoodie" not in msg


def test_heartbeat_dedupes_by_url():
    products = [_available("a%d" % i) for i in range(8)]
    msg = notify.format_heartbeat(products + [dict(p, source=CATEGORY_SORTED) for p in products])
    assert "total: 8" in msg
    assert "— total: 8, available: 8," in msg


def test_heartbeat_empty_list_reports_zeros():
    msg = notify.format_heartbeat([])
    assert "total: 0" in msg
    assert "available: 0" in msg
    assert "unavailable: 0" in msg


def test_heartbeat_coming_soon_only_when_present():
    assert "coming soon:" not in notify.format_heartbeat([_available("a")])
    soon = notify.format_heartbeat([_product("b", text="coming soon Riftbound")])
    assert "coming soon: 1" in soon


def test_heartbeat_writes_no_state(tmp_path):
    summary = watcher.run(
        watcher.MODE_HEARTBEAT, state_path=_sp(tmp_path),
        webhook_url="https://example.invalid/hook",
        fetch_fn=fetch_fn_factory([_available("a")]), send_fn=Recorder(),
    )
    assert summary["state_written"] is False


# --- 26-32: watch regression -------------------------------------------------

def _second_run_content(tmp_path, new_item):
    sp = _sp(tmp_path)
    hook = "https://example.invalid/hook"
    watcher.run(watcher.MODE_NORMAL, state_path=sp, webhook_url=hook,
                fetch_fn=fetch_fn_factory([_available("baseline")]), send_fn=Recorder())
    send = Recorder()
    watcher.run(watcher.MODE_NORMAL, state_path=sp, webhook_url=hook,
                fetch_fn=fetch_fn_factory([_available("baseline"), new_item]), send_fn=send)
    assert len(send.calls) == 1
    return send.calls[0][1]


def test_new_available_item_posts_status_available(tmp_path):
    assert "Status: available" in _second_run_content(tmp_path, _available("new-av"))


def test_new_sold_out_item_is_posted_with_status_sold_out(tmp_path):
    content = _second_run_content(tmp_path, _sold_out("new-so"))
    assert "Status: sold_out" in content
    assert "new-so" in content  # still carries the clickable product link


def test_new_preorder_item_posts_status_preorder(tmp_path):
    assert "Status: preorder" in _second_run_content(tmp_path, _preorder("new-pre"))


def test_new_unknown_item_posts_status_unknown(tmp_path):
    assert "Status: unknown" in _second_run_content(tmp_path, _unknown("new-unk"))


def test_first_run_is_baseline_and_sends_nothing(tmp_path):
    send = Recorder()
    summary = watcher.run(
        watcher.MODE_NORMAL, state_path=_sp(tmp_path), webhook_url="https://example.invalid/hook",
        fetch_fn=fetch_fn_factory(_mixed_23()), send_fn=send,
    )
    assert summary["relevant"] == 23
    assert send.calls == []


def test_t1_highlight_survives_for_sold_out_item(tmp_path):
    t1 = _sold_out("riftbound-t1-worlds-champion-collection",
                   "Riftbound x T1 Worlds Champion Collection")
    content = _second_run_content(tmp_path, t1)
    assert content.startswith(notify.HIGHLIGHT_ITEM_HEADER)
    assert "Match:" in content
    assert "Status: sold_out" in content


def test_general_articles_stay_excluded(tmp_path):
    sp = _sp(tmp_path)
    hook = "https://example.invalid/hook"
    watcher.run(watcher.MODE_NORMAL, state_path=sp, webhook_url=hook,
                fetch_fn=fetch_fn_factory([_available("baseline")]), send_fn=Recorder())
    articles = [
        {"title": "HOW TO PLAY", "url": "https://riftbound.com/get-started",
         "source": "https://riftbound.com/", "text": "Riftbound how to play"},
        {"title": "Riftbound Newsletter", "url": "https://riftbound.com/newsletter",
         "source": "https://riftbound.com/", "text": "Riftbound newsletter"},
        {"title": "Riftbound Top Decks", "url": "https://riftbound.com/top-decks",
         "source": "https://riftbound.com/", "text": "Riftbound top decks"},
    ]
    send = Recorder()
    summary = watcher.run(watcher.MODE_NORMAL, state_path=sp, webhook_url=hook,
                          fetch_fn=fetch_fn_factory([_available("baseline")] + articles), send_fn=send)
    assert summary["posted"] == 0
    assert send.calls == []


# --- remainingSKUs: honest reporting of products the page does not embed -----

def test_extract_remaining_sku_count_reads_the_lazy_loaded_remainder():
    html = '\\"remainingSKUs\\":[\\"810155273583\\",\\"RB3416-00-00\\",\\"810155273248\\"]'
    assert fetch.extract_remaining_sku_count(html) == 3


def test_extract_remaining_sku_count_zero_when_absent_or_empty():
    assert fetch.extract_remaining_sku_count("") == 0
    assert fetch.extract_remaining_sku_count("<html>nothing</html>") == 0
    assert fetch.extract_remaining_sku_count('\\"remainingSKUs\\":[]') == 0
