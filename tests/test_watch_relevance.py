"""Watch-relevance: ALL new Riot-merch Riftbound shop products are reported.

T1 / Worlds Champion Collection / Signature Edition / Player Bundle / Faker /
Galio are a HIGHLIGHT, never a precondition. General Riftbound articles
(get-started, how-to-play, newsletter, top decks) stay excluded by the shop gate.
"""
import notify
import relevance
import watcher


CATEGORY = "https://merch.riotgames.com/de-de/category/riftbound/"
CATEGORY_SORTED = "https://merch.riotgames.com/de-de/category/riftbound/?page=1&sort=dateDesc"
MERCH_HOME = "https://merch.riotgames.com/"


# --- fixtures ---------------------------------------------------------------

# A plain Riftbound shop product: no T1 anywhere.
GENERIC_PRODUCT = {
    "title": "Riftbound: Origins Champion Deck - Jinx",
    "url": "https://merch.riotgames.com/de-de/product/riftbound-origins-champion-deck-jinx",
    "source": CATEGORY,
    "text": "available Riftbound",
}

# Same product, but neither the title, the slug nor the text spell out
# "Riftbound" — only the merch Riftbound CATEGORY source does. This is the case
# the old title+text+url relevance filter dropped on the floor.
CATEGORY_ONLY_PRODUCT = {
    "title": "Champion Deck - Jinx",
    "url": "https://merch.riotgames.com/de-de/product/champion-deck-jinx",
    "source": CATEGORY,
    "text": "available",
}

# A T1 / Worlds product: relevant AND special.
T1_PRODUCT = {
    "title": "Riftbound x T1 Worlds Champion Collection",
    "url": "https://merch.riotgames.com/de-de/product/riftbound-t1-worlds-champion-collection",
    "source": CATEGORY,
    "text": "available Riftbound",
}

# Negatives: general Riftbound content, not shop products.
GET_STARTED = {
    "title": "HOW TO PLAY Riftbound",
    "url": "https://riftbound.com/get-started",
    "source": "https://riftbound.com/",
    "text": "Riftbound how to play",
}
NEWSLETTER = {
    "title": "Riftbound Newsletter",
    "url": "https://riftbound.com/newsletter",
    "source": "https://riftbound.com/",
    "text": "Riftbound newsletter signup",
}
TOP_DECKS = {
    "title": "Riftbound Top Decks",
    "url": "https://riftbound.com/top-decks",
    "source": "https://riftbound.com/",
    "text": "Riftbound top decks",
}

# Negative guard: a merch product that is NOT Riftbound must stay excluded.
LOL_HOODIE = {
    "title": "New League of Legends hoodie",
    "url": "https://merch.riotgames.com/de-de/product/lol-hoodie",
    "source": MERCH_HOME,
    "text": "available",
}


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


# --- 1-2: shop relevance without any T1 token -------------------------------

def test_general_riftbound_product_is_watch_relevant():
    assert relevance.is_riftbound_merch_relevant(GENERIC_PRODUCT) is True
    assert watcher.is_watch_relevant_item(GENERIC_PRODUCT) is True


def test_product_relevant_via_riftbound_category_source_only():
    """Title, slug and text carry no 'Riftbound' token — the merch Riftbound
    category source alone must make it watch-relevant."""
    combined = " ".join(
        (CATEGORY_ONLY_PRODUCT["title"], CATEGORY_ONLY_PRODUCT["text"], CATEGORY_ONLY_PRODUCT["url"])
    ).lower()
    assert "riftbound" not in combined  # guards the premise of this test

    assert relevance.is_riftbound_merch_relevant(CATEGORY_ONLY_PRODUCT) is True
    assert watcher.is_watch_relevant_item(CATEGORY_ONLY_PRODUCT) is True


def test_category_source_works_for_sorted_variant():
    item = dict(CATEGORY_ONLY_PRODUCT, source=CATEGORY_SORTED)
    assert watcher.is_watch_relevant_item(item) is True


# --- 3: special focus is a marker, not a gate -------------------------------

def test_general_riftbound_product_is_not_special_focus():
    assert relevance.is_special_focus(GENERIC_PRODUCT) is False
    assert relevance.special_reasons(GENERIC_PRODUCT) == []


def test_t1_product_is_watch_relevant_and_special():
    assert watcher.is_watch_relevant_item(T1_PRODUCT) is True
    assert relevance.is_special_focus(T1_PRODUCT) is True
    reasons = relevance.special_reasons(T1_PRODUCT)
    assert "t1" in reasons
    assert "worlds champion collection" in reasons
    # "riftbound" is the scope, not a special reason.
    assert "riftbound" not in reasons


def test_signature_edition_and_faker_galio_are_special():
    sig = dict(GENERIC_PRODUCT, title="Riftbound Faker Galio Signature Edition")
    assert relevance.is_special_focus(sig) is True
    reasons = relevance.special_reasons(sig)
    assert "signature edition" in reasons
    assert "faker" in reasons
    assert "galio" in reasons


def test_player_bundle_is_special():
    pb = dict(GENERIC_PRODUCT, title="Riftbound T1 Player Bundle")
    assert relevance.is_special_focus(pb) is True
    assert "player bundle" in relevance.special_reasons(pb)


def test_special_reasons_exclude_availability_which_has_its_own_status_line():
    """`Status:` already reports availability; it must not be repeated as a
    highlight reason in the `Match:` line."""
    reasons = relevance.special_reasons(T1_PRODUCT)  # text = "available Riftbound"
    assert "available" not in reasons
    assert "in stock" not in reasons
    assert "sold out" not in reasons


def test_special_reasons_keep_drawing_and_lottery_signals():
    """Drawing / lottery for a T1-related collection stays a highlight reason."""
    item = dict(T1_PRODUCT, text="Riftbound drawing lottery for the collection")
    reasons = relevance.special_reasons(item)
    assert "drawing" in reasons
    assert "lottery" in reasons
    assert "t1" in reasons


# --- 4-5: general articles stay excluded ------------------------------------

def test_get_started_is_not_watch_relevant():
    assert watcher.is_watch_relevant_item(GET_STARTED) is False


def test_newsletter_is_not_watch_relevant():
    assert watcher.is_watch_relevant_item(NEWSLETTER) is False


def test_top_decks_is_not_watch_relevant():
    assert watcher.is_watch_relevant_item(TOP_DECKS) is False


def test_non_riftbound_merch_product_is_not_watch_relevant():
    """Widening must not turn the whole merch store into a watch target."""
    assert relevance.is_riftbound_merch_relevant(LOL_HOODIE) is False
    assert watcher.is_watch_relevant_item(LOL_HOODIE) is False


# --- message format ---------------------------------------------------------

def test_new_item_message_for_general_product_has_link_and_no_t1_marker():
    content = notify.format_new_item_message(GENERIC_PRODUCT, [])
    assert content.startswith(notify.NEW_ITEM_HEADER)
    assert "Riftbound: Origins Champion Deck - Jinx" in content
    assert GENERIC_PRODUCT["url"] in content
    assert "Status: available" in content
    assert "Match:" not in content
    assert "🔥" not in content


def test_new_item_message_for_special_product_is_highlighted():
    content = notify.format_new_item_message(T1_PRODUCT, relevance.special_reasons(T1_PRODUCT))
    assert content.startswith(notify.HIGHLIGHT_ITEM_HEADER)
    assert "🔥" in content
    assert T1_PRODUCT["url"] in content
    assert "Match:" in content
    assert "t1" in content
    assert "Status: available" in content


def test_new_item_message_omits_status_line_never_and_survives_missing_url():
    item = {"title": "Riftbound Thing", "url": "", "source": "", "text": ""}
    content = notify.format_new_item_message(item, [])
    assert "Status: unknown" in content
    assert "http" not in content


def test_new_item_message_stays_within_discord_limit():
    item = dict(GENERIC_PRODUCT, title="R" * 5000)
    content = notify.format_new_item_message(item, ["t1"])
    assert len(content) <= notify.MAX_CONTENT
    assert GENERIC_PRODUCT["url"] in content
    assert "Status: available" in content


# --- 6-9: normal mode end to end --------------------------------------------

def test_first_run_with_general_products_is_baseline_and_sends_nothing(tmp_path):
    send = Recorder()
    summary = watcher.run(
        watcher.MODE_NORMAL,
        state_path=_sp(tmp_path),
        webhook_url="https://example.invalid/hook",
        fetch_fn=fetch_fn_factory([GENERIC_PRODUCT, CATEGORY_ONLY_PRODUCT]),
        send_fn=send,
    )
    assert summary["relevant"] == 2
    assert summary["posted"] == 0
    assert send.calls == []
    assert summary["state_written"] is True


def test_second_run_posts_new_general_product_with_link_and_no_t1_marker(tmp_path):
    sp = _sp(tmp_path)
    hook = "https://example.invalid/hook"

    watcher.run(
        watcher.MODE_NORMAL, state_path=sp, webhook_url=hook,
        fetch_fn=fetch_fn_factory([GENERIC_PRODUCT]), send_fn=Recorder(),
    )

    send = Recorder()
    summary = watcher.run(
        watcher.MODE_NORMAL, state_path=sp, webhook_url=hook,
        fetch_fn=fetch_fn_factory([GENERIC_PRODUCT, CATEGORY_ONLY_PRODUCT]), send_fn=send,
    )

    assert summary["new"] == 1
    assert summary["posted"] == 1
    assert len(send.calls) == 1
    content = send.calls[0][1]
    assert CATEGORY_ONLY_PRODUCT["url"] in content
    assert content.startswith(notify.NEW_ITEM_HEADER)
    assert "🔥" not in content
    assert "Match:" not in content


def test_second_run_posts_new_t1_product_with_highlight_marker(tmp_path):
    sp = _sp(tmp_path)
    hook = "https://example.invalid/hook"

    watcher.run(
        watcher.MODE_NORMAL, state_path=sp, webhook_url=hook,
        fetch_fn=fetch_fn_factory([GENERIC_PRODUCT]), send_fn=Recorder(),
    )

    send = Recorder()
    summary = watcher.run(
        watcher.MODE_NORMAL, state_path=sp, webhook_url=hook,
        fetch_fn=fetch_fn_factory([GENERIC_PRODUCT, T1_PRODUCT]), send_fn=send,
    )

    assert summary["posted"] == 1
    content = send.calls[0][1]
    assert T1_PRODUCT["url"] in content
    assert content.startswith(notify.HIGHLIGHT_ITEM_HEADER)
    assert "Match:" in content


def test_no_duplicate_messages_for_already_seen_products(tmp_path):
    sp = _sp(tmp_path)
    hook = "https://example.invalid/hook"
    items = [GENERIC_PRODUCT, CATEGORY_ONLY_PRODUCT, T1_PRODUCT]

    watcher.run(
        watcher.MODE_NORMAL, state_path=sp, webhook_url=hook,
        fetch_fn=fetch_fn_factory([GENERIC_PRODUCT]), send_fn=Recorder(),
    )

    send1 = Recorder()
    watcher.run(
        watcher.MODE_NORMAL, state_path=sp, webhook_url=hook,
        fetch_fn=fetch_fn_factory(items), send_fn=send1,
    )
    assert len(send1.calls) == 2

    send2 = Recorder()
    summary = watcher.run(
        watcher.MODE_NORMAL, state_path=sp, webhook_url=hook,
        fetch_fn=fetch_fn_factory(items), send_fn=send2,
    )
    assert summary["new"] == 0
    assert send2.calls == []


def test_normal_run_never_posts_get_started_or_newsletter(tmp_path):
    sp = _sp(tmp_path)
    hook = "https://example.invalid/hook"

    watcher.run(
        watcher.MODE_NORMAL, state_path=sp, webhook_url=hook,
        fetch_fn=fetch_fn_factory([GENERIC_PRODUCT]), send_fn=Recorder(),
    )

    send = Recorder()
    summary = watcher.run(
        watcher.MODE_NORMAL, state_path=sp, webhook_url=hook,
        fetch_fn=fetch_fn_factory([GENERIC_PRODUCT, GET_STARTED, NEWSLETTER, TOP_DECKS]),
        send_fn=send,
    )
    assert summary["posted"] == 0
    assert send.calls == []


# --- 10-12: test-webhook ----------------------------------------------------

def test_test_webhook_sends_general_riftbound_product_without_t1(tmp_path):
    send = Recorder()
    summary = watcher.run(
        watcher.MODE_TEST_WEBHOOK,
        state_path=_sp(tmp_path),
        webhook_url="https://example.invalid/hook",
        fetch_fn=fetch_fn_factory([GENERIC_PRODUCT]),
        send_fn=send,
        rng=type("R", (), {"choice": staticmethod(lambda seq: seq[0])})(),
    )
    assert summary["posted"] == 1
    content = send.calls[0][1]
    assert GENERIC_PRODUCT["url"] in content
    assert summary["state_written"] is False


def test_test_webhook_never_sends_get_started(tmp_path):
    send = Recorder()
    summary = watcher.run(
        watcher.MODE_TEST_WEBHOOK,
        state_path=_sp(tmp_path),
        webhook_url="https://example.invalid/hook",
        fetch_fn=fetch_fn_factory([GET_STARTED]),
        send_fn=send,
        rng=type("R", (), {"choice": staticmethod(lambda seq: seq[0])})(),
    )
    assert summary["posted"] == 0
    assert send.calls == []


# --- 13-15: heartbeat / status ----------------------------------------------

def test_heartbeat_counts_general_riftbound_products_not_only_t1(tmp_path):
    send = Recorder()
    preorder = dict(CATEGORY_ONLY_PRODUCT, title="Origins Booster Box", text="pre-order",
                    url="https://merch.riotgames.com/de-de/product/origins-booster-box")
    summary = watcher.run(
        watcher.MODE_HEARTBEAT,
        state_path=_sp(tmp_path),
        webhook_url="https://example.invalid/hook",
        fetch_fn=fetch_fn_factory([GENERIC_PRODUCT, CATEGORY_ONLY_PRODUCT, preorder]),
        send_fn=send,
    )
    assert summary["relevant"] == 3
    content = send.calls[0][1]
    assert "available: 2" in content
    assert "preorder: 1" in content


def test_heartbeat_contains_no_links(tmp_path):
    send = Recorder()
    watcher.run(
        watcher.MODE_HEARTBEAT,
        state_path=_sp(tmp_path),
        webhook_url="https://example.invalid/hook",
        fetch_fn=fetch_fn_factory([GENERIC_PRODUCT, T1_PRODUCT]),
        send_fn=send,
    )
    content = send.calls[0][1]
    assert "http" not in content
    assert "merch.riotgames.com" not in content


def test_status_report_lists_general_available_riftbound_products(tmp_path):
    send = Recorder()
    watcher.run(
        watcher.MODE_STATUS,
        state_path=_sp(tmp_path),
        webhook_url="https://example.invalid/hook",
        fetch_fn=fetch_fn_factory([GENERIC_PRODUCT, CATEGORY_ONLY_PRODUCT]),
        send_fn=send,
    )
    content = send.calls[0][1]
    assert "Riftbound: Origins Champion Deck - Jinx" in content
    assert "Champion Deck - Jinx" in content
    assert "http" not in content


def test_state_is_untouched_by_heartbeat_and_status(tmp_path):
    sp = _sp(tmp_path)
    for mode in (watcher.MODE_HEARTBEAT, watcher.MODE_STATUS):
        summary = watcher.run(
            mode, state_path=sp, webhook_url="https://example.invalid/hook",
            fetch_fn=fetch_fn_factory([GENERIC_PRODUCT]), send_fn=Recorder(),
        )
        assert summary["state_written"] is False


# --- fetch integration: embedded product JSON stays watch-relevant ----------

def test_products_from_embedded_json_are_watch_relevant():
    """A product parsed out of the merch category page must survive the gate even
    when its ip.label is not 'Riftbound'."""
    import fetch

    html = (
        '{\\"title\\":\\"Champion Deck - Jinx\\",'
        '\\"slug\\":\\"champion-deck-jinx\\",\\"ip\\":{\\"label\\":\\"League of Legends\\"},'
        '\\"availability\\":\\"in_stock\\"}'
    )
    items = fetch.extract_products_json(CATEGORY, html)
    assert len(items) == 1
    product = items[0]
    # Premise: the token only lives in `source`, which the old filter ignored.
    combined = " ".join((product["title"], product["text"], product["url"])).lower()
    assert "riftbound" not in combined
    assert "riftbound" in product["source"].lower()
    assert watcher.is_watch_relevant_item(product) is True
