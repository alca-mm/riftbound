"""Tests for notify.py — the notify-only Discord sender.

SECURITY IS THE POINT: the webhook URL is a secret and must NEVER appear in
any log line, exception message, traceback, or repr. Every test uses an
obviously-fake placeholder webhook and injects a fake session so that no real
network access happens anywhere.
"""
import logging

import pytest

import notify


# An obviously-fake placeholder. NOT a real webhook. Never use a real one here.
FAKE_WEBHOOK = "https://discord.com/api/webhooks/000000000000000000/FAKE_TOKEN_DO_NOT_USE"
FAKE_TOKEN = "FAKE_TOKEN_DO_NOT_USE"


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------
class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class RecordingSession:
    """Fake requests.Session-like object recording the last .post() call."""

    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self._exc is not None:
            raise self._exc
        return self._response


# ---------------------------------------------------------------------------
# send_discord — happy path
# ---------------------------------------------------------------------------
def test_send_discord_posts_json_and_returns_true_on_200():
    session = RecordingSession(response=FakeResponse(status_code=200))
    result = notify.send_discord(FAKE_WEBHOOK, "hello world", session=session)
    assert result is True
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url == FAKE_WEBHOOK
    assert kwargs["json"] == {"content": "hello world"}


def test_send_discord_returns_true_on_204():
    session = RecordingSession(response=FakeResponse(status_code=204))
    assert notify.send_discord(FAKE_WEBHOOK, "hi", session=session) is True


def test_send_discord_honors_timeout():
    session = RecordingSession(response=FakeResponse(status_code=204))
    notify.send_discord(FAKE_WEBHOOK, "hi", session=session, timeout=15)
    _, kwargs = session.calls[0]
    assert kwargs["timeout"] == 15


# ---------------------------------------------------------------------------
# send_discord — failure paths (must never leak the url)
# ---------------------------------------------------------------------------
def test_send_discord_raises_on_500_without_leaking_url():
    session = RecordingSession(response=FakeResponse(status_code=500))
    with pytest.raises(notify.WebhookError) as excinfo:
        notify.send_discord(FAKE_WEBHOOK, "hi", session=session)
    message = str(excinfo.value)
    assert FAKE_WEBHOOK not in message
    assert FAKE_TOKEN not in message
    # A generic reason (the status code) is fine and useful.
    assert "500" in message


def test_send_discord_single_attempt_on_failure():
    session = RecordingSession(response=FakeResponse(status_code=500))
    with pytest.raises(notify.WebhookError):
        notify.send_discord(FAKE_WEBHOOK, "hi", session=session)
    assert len(session.calls) == 1  # defensive: no retry loop


def test_send_discord_raises_on_network_exception_without_leaking_url():
    # Simulate a network error whose message embeds the url (requests often does
    # this, e.g. "Max retries exceeded with url: ..."). The url must NOT survive
    # into the WebhookError message.
    leaky_exc = RuntimeError("Max retries exceeded with url: " + FAKE_WEBHOOK)
    session = RecordingSession(exc=leaky_exc)
    with pytest.raises(notify.WebhookError) as excinfo:
        notify.send_discord(FAKE_WEBHOOK, "hi", session=session)
    message = str(excinfo.value)
    assert FAKE_WEBHOOK not in message
    assert FAKE_TOKEN not in message


def test_no_secret_leaks_into_logs_or_exception(caplog):
    """SECRET LEAK TEST: capture DEBUG logs while a send fails and assert the
    webhook url (and its token) appear nowhere in the logs or the exception."""
    leaky_exc = RuntimeError("boom while connecting to " + FAKE_WEBHOOK)
    session = RecordingSession(exc=leaky_exc)
    with caplog.at_level(logging.DEBUG, logger="riot.notify"):
        with pytest.raises(notify.WebhookError) as excinfo:
            notify.send_discord(FAKE_WEBHOOK, "hi", session=session)
    assert FAKE_WEBHOOK not in caplog.text
    assert FAKE_TOKEN not in caplog.text
    assert FAKE_WEBHOOK not in str(excinfo.value)
    assert FAKE_TOKEN not in str(excinfo.value)


# ---------------------------------------------------------------------------
# redact_secrets
# ---------------------------------------------------------------------------
def test_redact_secrets_replaces_every_occurrence():
    text = "token is SECRET123 and again SECRET123"
    out = notify.redact_secrets(text, ["SECRET123"])
    assert "SECRET123" not in out
    assert out == "token is *** and again ***"


def test_redact_secrets_tolerates_none_and_empty_entries():
    out = notify.redact_secrets("keep SECRET123 safe", [None, "", "SECRET123"])
    assert out == "keep *** safe"


def test_redact_secrets_no_secrets_returns_text_unchanged():
    assert notify.redact_secrets("nothing here", []) == "nothing here"
    assert notify.redact_secrets("still here", [None, ""]) == "still here"


def test_redact_secrets_redacts_full_webhook_url():
    out = notify.redact_secrets("posting to " + FAKE_WEBHOOK + " now", [FAKE_WEBHOOK])
    assert FAKE_WEBHOOK not in out
    assert FAKE_TOKEN not in out
    assert "***" in out


# ---------------------------------------------------------------------------
# format_message
# ---------------------------------------------------------------------------
def test_format_message_includes_title_and_url():
    item = {
        "title": "Riftbound T1 Deck Box",
        "url": "https://merch.riotgames.com/item/123",
        "source": "https://merch.riotgames.com/",
        "text": "in stock",
    }
    msg = notify.format_message(item)
    assert "Riftbound T1 Deck Box" in msg
    assert "https://merch.riotgames.com/item/123" in msg


def test_format_message_includes_match_line_when_reasons_given():
    item = {"title": "T1 Jersey", "url": "https://example.com/j", "source": "s", "text": "t"}
    msg = notify.format_message(item, reasons=["riftbound", "t1"])
    assert "Match:" in msg
    assert "riftbound" in msg
    assert "t1" in msg


def test_format_message_no_match_line_when_reasons_empty_or_none():
    item = {"title": "X", "url": "https://example.com/x", "source": "s", "text": "t"}
    assert "Match:" not in notify.format_message(item)
    assert "Match:" not in notify.format_message(item, reasons=[])
    assert "Match:" not in notify.format_message(item, reasons=None)


def test_format_message_truncates_huge_title_but_keeps_url():
    item = {
        "title": "A" * 5000,
        "url": "https://example.com/item",
        "source": "s",
        "text": "t",
    }
    msg = notify.format_message(item)
    assert len(msg) <= 2000  # well under Discord's 2000-char content limit
    assert "https://example.com/item" in msg


# ---------------------------------------------------------------------------
# best_item_url — pure/offline link selection (NO network requests)
# ---------------------------------------------------------------------------
def test_best_item_url_prefers_specific_product_over_source():
    item = {
        "title": "Riftbound T1 WCC",
        "url": "https://merch.riotgames.com/products/riftbound-t1-wcc",
        "source": "https://merch.riotgames.com/",
        "text": "in stock",
    }
    assert (
        notify.best_item_url(item)
        == "https://merch.riotgames.com/products/riftbound-t1-wcc"
    )


def test_best_item_url_returns_url_when_only_url_valid():
    item = {"title": "T", "url": "https://example.com/thing", "source": ""}
    assert notify.best_item_url(item) == "https://example.com/thing"


def test_best_item_url_returns_url_when_source_key_missing():
    item = {"title": "T", "url": "https://example.com/thing"}
    assert notify.best_item_url(item) == "https://example.com/thing"


def test_best_item_url_resolves_relative_against_source():
    item = {
        "title": "T",
        "url": "/riftbound/t1-item",
        "source": "https://merch.riotgames.com/shop/",
    }
    assert (
        notify.best_item_url(item)
        == "https://merch.riotgames.com/riftbound/t1-item"
    )


def test_best_item_url_returns_none_when_no_valid_link():
    item = {"title": "T", "url": "#", "source": ""}
    assert notify.best_item_url(item) is None


def test_best_item_url_rejects_non_http_schemes():
    assert notify.best_item_url({"url": "javascript:void(0)", "source": ""}) is None
    assert (
        notify.best_item_url({"url": "mailto:someone@example.com", "source": ""})
        is None
    )


def test_best_item_url_prefers_url_over_source_on_tie():
    # Identical score for both merch product links; url must win the tie-break.
    item = {
        "url": "https://merch.riotgames.com/products/a",
        "source": "https://merch.riotgames.com/products/b",
    }
    assert notify.best_item_url(item) == "https://merch.riotgames.com/products/a"


def test_best_item_url_falls_back_to_source_when_url_invalid():
    item = {
        "url": "#",
        "source": "https://merch.riotgames.com/collections/riftbound",
    }
    assert (
        notify.best_item_url(item)
        == "https://merch.riotgames.com/collections/riftbound"
    )


# ---------------------------------------------------------------------------
# is_shop_candidate — pure/offline shop-vs-article classification (NO network)
# ---------------------------------------------------------------------------
def test_is_shop_candidate_true_for_merch_product_url():
    item = {
        "title": "Some product",
        "url": "https://merch.riotgames.com/de-de/category/riftbound/some-product",
        "source": "https://merch.riotgames.com/de-de/category/riftbound/",
        "text": "",
    }
    assert notify.is_shop_candidate(item) is True


def test_is_shop_candidate_true_for_merch_category_url():
    item = {
        "title": "Riftbound",
        "url": "https://merch.riotgames.com/de-de/category/riftbound/",
        "source": "https://merch.riotgames.com/",
        "text": "",
    }
    assert notify.is_shop_candidate(item) is True


def test_is_shop_candidate_true_for_signature_edition_title():
    item = {"title": "T1 Signature Edition", "url": "", "source": "", "text": ""}
    assert notify.is_shop_candidate(item) is True


def test_is_shop_candidate_true_for_worlds_champion_collection_title():
    item = {"title": "Worlds Champion Collection", "url": "", "source": "", "text": ""}
    assert notify.is_shop_candidate(item) is True


def test_is_shop_candidate_true_for_player_bundle_title():
    item = {"title": "T1 Player Bundle", "url": "", "source": "", "text": ""}
    assert notify.is_shop_candidate(item) is True


def test_is_shop_candidate_false_for_reported_how_to_play_get_started():
    # The exact case that was wrongly notified in the live test.
    item = {
        "title": "HOW TO PLAY",
        "url": "https://www.riftbound.com/en-us/get-started/",
        "source": "https://www.riftbound.com/",
        "text": "",
    }
    assert notify.is_shop_candidate(item) is False


def test_is_shop_candidate_false_for_top_decks_article():
    item = {
        "title": "Top decks",
        "url": "https://www.riftbound.com/en-us/top-decks/",
        "source": "https://www.riftbound.com/",
        "text": "",
    }
    assert notify.is_shop_candidate(item) is False


def test_is_shop_candidate_false_for_newsletter_signup():
    item = {
        "title": "Newsletter sign-up",
        "url": "https://www.riftbound.com/en-us/newsletter/",
        "source": "https://www.riftbound.com/",
        "text": "",
    }
    assert notify.is_shop_candidate(item) is False


def test_is_shop_candidate_false_for_generic_news_article_without_shop_keyword():
    item = {
        "title": "Whatever happened this week",
        "url": "https://www.riftbound.com/en-us/news/whatever",
        "source": "https://www.riftbound.com/",
        "text": "",
    }
    assert notify.is_shop_candidate(item) is False


# ---------------------------------------------------------------------------
# format_message — header + bare clickable link line
# ---------------------------------------------------------------------------
def test_format_message_contains_header_title_and_best_link():
    item = {
        "title": "Riftbound x T1 Deck Box",
        "url": "https://merch.riotgames.com/products/riftbound-t1-deck",
        "source": "https://merch.riotgames.com/",
    }
    msg = notify.format_message(item)
    assert notify.MESSAGE_HEADER in msg
    # Stable ASCII substrings of the header (avoid asserting the × glyph).
    assert "New Riftbound" in msg
    assert "match found" in msg
    assert "Riftbound x T1 Deck Box" in msg
    assert "https://merch.riotgames.com/products/riftbound-t1-deck" in msg
    # The link sits on its own bare line so Discord renders it clickable.
    assert "\nhttps://merch.riotgames.com/products/riftbound-t1-deck" in msg


def test_format_message_linkless_item_has_no_none_or_empty_link():
    item = {"title": "Some title", "url": "#", "source": ""}
    msg = notify.format_message(item)
    assert notify.MESSAGE_HEADER in msg
    assert "Some title" in msg
    assert "None" not in msg  # never emit the literal None
    assert "\n\n" not in msg  # no dangling empty line where the link would go
    assert "http" not in msg  # no broken/partial link


def test_format_message_keeps_link_and_match_when_truncating_long_title():
    item = {
        "title": "A" * 5000,
        "url": "https://merch.riotgames.com/products/riftbound-t1",
        "source": "https://merch.riotgames.com/",
    }
    msg = notify.format_message(item, reasons=["riftbound", "t1"])
    assert len(msg) <= 2000
    assert notify.MESSAGE_HEADER in msg
    assert "https://merch.riotgames.com/products/riftbound-t1" in msg
    assert "Match: riftbound, t1" in msg


# ---------------------------------------------------------------------------
# Secret-leak regression: real requests exceptions split the URL across their
# message (host separate from path), so redacting the full URL string is not
# enough. The token must never reach the logs, the exception, or __context__.
# ---------------------------------------------------------------------------
def test_split_url_network_exception_does_not_leak_token(caplog):
    # Only the path (with the token) appears — the FULL url is NOT a substring,
    # so a naive full-url replace would miss the bare token.
    leaky = RuntimeError(
        "HTTPSConnectionPool(host='discord.com', port=443): Max retries exceeded "
        "with url: /api/webhooks/000000000000000000/FAKE_TOKEN_DO_NOT_USE "
        "(Caused by NewConnectionError('boom'))"
    )
    session = RecordingSession(exc=leaky)
    with caplog.at_level(logging.DEBUG, logger="riot.notify"):
        with pytest.raises(notify.WebhookError) as excinfo:
            notify.send_discord(FAKE_WEBHOOK, "hi", session=session)
    assert FAKE_TOKEN not in caplog.text
    assert FAKE_TOKEN not in str(excinfo.value)


def test_network_failure_has_no_leaky_exception_context():
    leaky = RuntimeError("connect failed to /api/webhooks/000/FAKE_TOKEN_DO_NOT_USE")
    session = RecordingSession(exc=leaky)
    with pytest.raises(notify.WebhookError) as excinfo:
        notify.send_discord(FAKE_WEBHOOK, "hi", session=session)
    # The original (url-bearing) exception must not be chained onto WebhookError.
    assert excinfo.value.__context__ is None
    assert excinfo.value.__cause__ is None


# ---------------------------------------------------------------------------
# availability_status / availability_score — pure/offline availability detection
# (derive availability from the item's OWN text fields; NO network requests)
# ---------------------------------------------------------------------------
def _item(text="", title="", url="", source=""):
    return {"title": title, "text": text, "url": url, "source": source}


@pytest.mark.parametrize(
    "text",
    ["available", "in stock", "in-stock", "lieferbar", "verfügbar", "auf lager"],
)
def test_availability_status_available(text):
    assert notify.availability_status(_item(text=text)) == "available"


@pytest.mark.parametrize(
    "text",
    ["pre-order", "preorder", "pre order", "vorbestellbar", "vorbestellung"],
)
def test_availability_status_preorder(text):
    assert notify.availability_status(_item(text=text)) == "preorder"


@pytest.mark.parametrize(
    "text",
    ["sold out", "sold-out", "soldout", "ausverkauft", "out of stock", "out-of-stock"],
)
def test_availability_status_sold_out(text):
    assert notify.availability_status(_item(text=text)) == "sold_out"


@pytest.mark.parametrize(
    "text",
    ["not available", "unavailable", "nicht verfügbar", "nicht lieferbar"],
)
def test_availability_status_negatives_are_sold_out_not_available(text):
    # These CONTAIN the positive substrings "available"/"verfügbar"/"lieferbar",
    # so they must be checked first and classified as sold_out, NOT available.
    assert notify.availability_status(_item(text=text)) == "sold_out"


@pytest.mark.parametrize("text", ["coming soon", "coming-soon"])
def test_availability_status_coming_soon(text):
    assert notify.availability_status(_item(text=text)) == "coming_soon"


def test_availability_status_unknown_when_no_signal():
    # A plain merch product title with empty text gives no availability signal.
    item = {
        "title": "Riftbound T1 Deck Box",
        "text": "",
        "url": "https://merch.riotgames.com/products/riftbound-t1-deck",
        "source": "https://merch.riotgames.com/",
    }
    assert notify.availability_status(item) == "unknown"


def test_availability_status_signal_may_come_from_any_field():
    # The signal is derived from title + text + url + source combined.
    assert notify.availability_status(_item(title="Sold Out")) == "sold_out"
    assert notify.availability_status(_item(url="https://merch.riotgames.com/preorder/x")) == "preorder"
    assert notify.availability_status(_item(source="https://x/in-stock/")) == "available"


def test_availability_status_handles_none_item():
    assert notify.availability_status(None) == "unknown"


def test_availability_score_matches_rank_table():
    assert notify.availability_score(_item(text="in stock")) == notify.AVAILABILITY_RANK["available"]
    assert notify.availability_score(_item(text="preorder")) == notify.AVAILABILITY_RANK["preorder"]
    assert notify.availability_score(_item(text="")) == notify.AVAILABILITY_RANK["unknown"]
    assert notify.availability_score(_item(text="coming soon")) == notify.AVAILABILITY_RANK["coming_soon"]
    assert notify.availability_score(_item(text="sold out")) == notify.AVAILABILITY_RANK["sold_out"]


def test_availability_score_orders_available_over_preorder_over_unknown_over_coming_soon_over_sold_out():
    available = notify.availability_score(_item(text="available"))
    preorder = notify.availability_score(_item(text="pre-order"))
    unknown = notify.availability_score(_item(text=""))
    coming_soon = notify.availability_score(_item(text="coming soon"))
    sold_out = notify.availability_score(_item(text="sold out"))
    assert available > preorder > unknown > coming_soon > sold_out


# ---------------------------------------------------------------------------
# format_status_report — periodic heartbeat listing AVAILABLE merch, NO links
# (pure/offline; splits already-relevant items by availability and formats them)
# ---------------------------------------------------------------------------
# Exact status lines. × is the × glyph — spell it out so the assertion is
# byte-for-byte exact without embedding the raw glyph in the test source.
_NO_T1_LINE = "No new Riftbound × T1 / Worlds Champion Collection hits found."
_AVAIL_HEADER = "Available Riftbound merch items:"
_PREORDER_HEADER = "Preorder Riftbound merch items:"
_NO_AVAIL_LINE = "No available Riftbound merch items detected in the static product data."


def _merch(title, *, text="", url="", source=""):
    """A fake already-relevant shop/merch item dict (title/url/source/text)."""
    return {"title": title, "text": text, "url": url, "source": source}


def _no_links(msg):
    return "http://" not in msg and "https://" not in msg and "http" not in msg


def test_status_report_has_header_lists_available_in_input_order_no_links():
    items = [
        _merch("Riftbound Newest Poster", text="available",
               url="https://merch.riotgames.com/products/newest"),
        _merch("Riftbound Older Deck Box", text="in stock",
               url="https://merch.riotgames.com/products/older"),
        _merch("Riftbound Oldest Playmat", text="auf lager",
               url="https://merch.riotgames.com/products/oldest"),
    ]
    msg = notify.format_status_report(items)
    assert notify.STATUS_HEADER in msg
    assert "[STATUS]" in msg
    assert _AVAIL_HEADER in msg
    # Numbered top-to-bottom in INPUT ORDER (source is date-desc, newest first).
    assert "1. Riftbound Newest Poster" in msg
    assert "2. Riftbound Older Deck Box" in msg
    assert "3. Riftbound Oldest Playmat" in msg
    assert msg.index("1. Riftbound Newest Poster") < msg.index("2. Riftbound Older Deck Box")
    assert msg.index("2. Riftbound Older Deck Box") < msg.index("3. Riftbound Oldest Playmat")
    # NO links, even though every item carries a product URL in its url field.
    assert _no_links(msg)


def test_status_report_available_only_excludes_sold_out_and_unknown():
    items = [
        _merch("Riftbound Available Mug", text="available"),
        _merch("Riftbound Sold Out Hoodie", text="sold out"),
        _merch("Riftbound Mystery Item", text=""),  # unknown
    ]
    msg = notify.format_status_report(items)
    assert "Riftbound Available Mug" in msg
    # The sold-out and unknown items must NOT appear in the available list.
    assert "Riftbound Sold Out Hoodie" not in msg
    assert "Riftbound Mystery Item" not in msg


def test_status_report_preorder_items_in_separate_section_not_available_list():
    items = [
        _merch("Riftbound Available Cap", text="available"),
        _merch("Riftbound Preorder Statue", text="preorder"),
    ]
    msg = notify.format_status_report(items)
    assert _AVAIL_HEADER in msg
    assert _PREORDER_HEADER in msg
    # The preorder item is listed under the preorder section, AFTER the available
    # header, and is not part of the available list.
    assert "Riftbound Preorder Statue" in msg
    assert msg.index(_AVAIL_HEADER) < msg.index(_PREORDER_HEADER)
    assert msg.index("Riftbound Available Cap") < msg.index(_PREORDER_HEADER)
    assert msg.index("Riftbound Preorder Statue") > msg.index(_PREORDER_HEADER)
    assert _no_links(msg)


def test_status_report_no_available_items_reports_static_line_no_crash_no_links():
    items = [
        _merch("Riftbound Sold Out Tee", text="sold out"),
        _merch("Riftbound Coming Soon Box", text="coming soon"),
    ]
    msg = notify.format_status_report(items)
    assert _NO_AVAIL_LINE in msg
    assert _AVAIL_HEADER not in msg
    assert notify.STATUS_HEADER in msg
    assert _no_links(msg)


def test_status_report_no_available_items_at_all_empty_list():
    msg = notify.format_status_report([])
    assert _NO_AVAIL_LINE in msg
    assert notify.STATUS_HEADER in msg
    assert _no_links(msg)


def test_status_report_no_t1_items_uses_exact_no_hits_line():
    items = [
        _merch("Riftbound Generic Poster", text="available"),
        _merch("Riftbound Enamel Pin", text="in stock"),
    ]
    msg = notify.format_status_report(items)
    assert _NO_T1_LINE in msg
    # These available items are still listed.
    assert "Riftbound Generic Poster" in msg
    assert "Riftbound Enamel Pin" in msg


def test_status_report_t1_signature_edition_reports_count():
    items = [
        _merch("T1 Signature Edition", text="available"),
        _merch("Riftbound Generic Poster", text="in stock"),
    ]
    msg = notify.format_status_report(items)
    assert _NO_T1_LINE not in msg
    # Status line mentions items available with the highlight count.
    assert "items available: 1" in msg
    assert "Worlds Champion Collection items available" in msg


def test_status_report_max_items_caps_available_list_and_stays_under_limit():
    items = [_merch("Riftbound Item %02d" % i, text="available") for i in range(20)]
    msg = notify.format_status_report(items, max_items=5)
    # Exactly 5 numbered available lines, then a "...and 15 more" summary.
    assert "1. Riftbound Item 00" in msg
    assert "5. Riftbound Item 04" in msg
    assert "6. Riftbound Item 05" not in msg
    assert "...and 15 more available item(s)." in msg
    assert len(msg) <= 2000


def test_status_report_dedupes_by_title_case_insensitive_preserving_order():
    items = [
        _merch("Riftbound Deck Box", text="available"),
        _merch("RIFTBOUND DECK BOX", text="available"),  # dup of #1 (case-insensitive)
        _merch("Riftbound Playmat", text="available"),
        _merch("", text="available"),  # empty title skipped
    ]
    msg = notify.format_status_report(items)
    assert "1. Riftbound Deck Box" in msg
    assert "2. Riftbound Playmat" in msg
    assert "3." not in msg  # only two distinct, non-empty titles survive


def test_status_report_sanitizes_url_in_title_no_http_leaks():
    items = [
        _merch("Riftbound Poster https://merch.riotgames.com/products/x see link",
               text="available",
               url="https://merch.riotgames.com/products/x"),
    ]
    msg = notify.format_status_report(items)
    assert "Riftbound Poster" in msg
    assert "http" not in msg  # the URL embedded in the title is stripped out
    assert _no_links(msg)


def test_status_report_preorder_section_absent_when_no_preorders():
    items = [_merch("Riftbound Available Thing", text="available")]
    msg = notify.format_status_report(items)
    assert _PREORDER_HEADER not in msg


def test_status_report_t1_whole_word_only_not_substring():
    # "t1" as a whole word triggers the highlight; a substring like "att1c" does not.
    hit = notify.format_status_report([_merch("Riftbound T1 Jersey", text="available")])
    assert _NO_T1_LINE not in hit
    miss = notify.format_status_report([_merch("Riftbound Battle Poster", text="available")])
    assert _NO_T1_LINE in miss


# ---------------------------------------------------------------------------
# format_heartbeat — SHORT daily heartbeat: counts only, NO links, NO titles,
# never touches state (pure/offline; counts already-relevant items)
# ---------------------------------------------------------------------------
def test_heartbeat_has_status_header_running_and_no_links():
    msg = notify.format_heartbeat([_merch("Riftbound Poster", text="available")])
    assert "[STATUS]" in msg
    assert "heartbeat" in msg.lower()
    assert "running" in msg.lower()
    assert _no_links(msg)


def test_heartbeat_reports_availability_counts():
    items = [
        _merch("Riftbound A", text="available"),
        _merch("Riftbound B", text="available"),
        _merch("Riftbound C", text="preorder"),
        _merch("Riftbound D", text=""),  # unknown
    ]
    msg = notify.format_heartbeat(items)
    assert "available: 2" in msg
    assert "preorder: 1" in msg
    assert "unknown: 1" in msg


def test_heartbeat_omits_item_titles():
    msg = notify.format_heartbeat(
        [_merch("Riftbound Secret Vault Title", text="available")]
    )
    # Counts only — never a product list.
    assert "Riftbound Secret Vault Title" not in msg
    assert "available: 1" in msg


def test_heartbeat_empty_list_no_crash_no_links():
    msg = notify.format_heartbeat([])
    assert notify.HEARTBEAT_HEADER in msg
    assert "available: 0" in msg
    assert _no_links(msg)
