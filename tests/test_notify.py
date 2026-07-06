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
