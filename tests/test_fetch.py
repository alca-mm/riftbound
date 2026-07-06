"""Tests for fetch.py — the notify-only page watcher.

No real network access anywhere: every test injects a fake session or
monkeypatches module functions.
"""
import json
import sys

import fetch
import notify


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------
class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class RecordingSession:
    """Fake requests.Session-like object recording the last .get() call."""

    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self._exc is not None:
            raise self._exc
        return self._response


# ---------------------------------------------------------------------------
# extract_items
# ---------------------------------------------------------------------------
def test_extract_items_returns_candidate_dicts_with_four_keys():
    html = '<html><body><a href="https://example.com/item">Cool Item</a></body></html>'
    items = fetch.extract_items("https://merch.riotgames.com/", html)
    assert len(items) == 1
    item = items[0]
    assert set(item.keys()) == {"title", "url", "source", "text"}
    assert all(isinstance(item[k], str) for k in ("title", "url", "source", "text"))
    assert item["title"] == "Cool Item"
    assert item["url"] == "https://example.com/item"
    assert item["source"] == "https://merch.riotgames.com/"


def test_extract_items_resolves_relative_url_to_absolute():
    html = '<a href="/riftbound/t1-item">Riftbound Item</a>'
    items = fetch.extract_items("https://merch.riotgames.com/shop/", html)
    assert len(items) == 1
    assert items[0]["url"] == "https://merch.riotgames.com/riftbound/t1-item"
    assert items[0]["source"] == "https://merch.riotgames.com/shop/"


def test_extract_items_skips_empty_and_hash_anchors():
    html = (
        '<a href="#">nope</a>'
        '<a href="">empty</a>'
        '<a href="   ">whitespace</a>'
        '<a href="https://example.com/real">real</a>'
    )
    items = fetch.extract_items("https://merch.riotgames.com/", html)
    urls = [i["url"] for i in items]
    assert "https://example.com/real" in urls
    assert len(items) == 1


def test_extract_items_empty_html_returns_empty_list():
    assert fetch.extract_items("https://merch.riotgames.com/", "") == []


# ---------------------------------------------------------------------------
# fetch_page
# ---------------------------------------------------------------------------
def test_fetch_page_returns_none_on_exception():
    session = RecordingSession(exc=RuntimeError("boom"))
    result = fetch.fetch_page("https://merch.riotgames.com/", session=session)
    assert result is None


def test_fetch_page_returns_none_on_non_200():
    session = RecordingSession(response=FakeResponse(status_code=404, text="nope"))
    result = fetch.fetch_page("https://merch.riotgames.com/", session=session)
    assert result is None


def test_fetch_page_returns_text_on_200():
    session = RecordingSession(response=FakeResponse(status_code=200, text="<html>ok</html>"))
    result = fetch.fetch_page("https://merch.riotgames.com/", session=session)
    assert result == "<html>ok</html>"


def test_fetch_page_passes_user_agent_and_timeout():
    session = RecordingSession(response=FakeResponse(status_code=200, text="ok"))
    fetch.fetch_page("https://merch.riotgames.com/", session=session, timeout=15)
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url == "https://merch.riotgames.com/"
    assert kwargs["timeout"] == 15
    headers = kwargs["headers"]
    assert headers["User-Agent"] == fetch.USER_AGENT


def test_fetch_page_makes_only_one_attempt():
    session = RecordingSession(exc=RuntimeError("boom"))
    fetch.fetch_page("https://merch.riotgames.com/", session=session)
    assert len(session.calls) == 1


# ---------------------------------------------------------------------------
# fetch_targets
# ---------------------------------------------------------------------------
def test_fetch_targets_combines_items_and_skips_none(monkeypatch):
    pages = {
        "https://a.example/": '<a href="https://a.example/one">One</a>',
        "https://b.example/": None,  # simulate failed fetch
        "https://c.example/": '<a href="https://c.example/two">Two</a>',
    }

    def fake_fetch_page(url, *, session=None, timeout=fetch.DEFAULT_TIMEOUT):
        return pages[url]

    monkeypatch.setattr(fetch, "fetch_page", fake_fetch_page)

    items = fetch.fetch_targets(list(pages.keys()))
    urls = [i["url"] for i in items]
    assert "https://a.example/one" in urls
    assert "https://c.example/two" in urls
    assert len(items) == 2


def test_fetch_targets_defaults_to_default_targets(monkeypatch):
    seen = []

    def fake_fetch_page(url, *, session=None, timeout=fetch.DEFAULT_TIMEOUT):
        seen.append(url)
        return None  # skip everything, we only care which URLs were visited

    monkeypatch.setattr(fetch, "fetch_page", fake_fetch_page)

    result = fetch.fetch_targets()
    assert result == []
    assert seen == fetch.DEFAULT_TARGETS
    assert len(fetch.DEFAULT_TARGETS) >= 3


# ---------------------------------------------------------------------------
# module-level public API sanity
# ---------------------------------------------------------------------------
def test_public_api_constants():
    assert isinstance(fetch.USER_AGENT, str) and fetch.USER_AGENT
    assert isinstance(fetch.DEFAULT_TIMEOUT, int)
    assert isinstance(fetch.DEFAULT_TARGETS, list)
    assert all(isinstance(t, str) for t in fetch.DEFAULT_TARGETS)


def test_default_targets_primary_is_merch_riftbound_category():
    # The Riot merch Riftbound category page is the PRIMARY target.
    assert (
        fetch.DEFAULT_TARGETS[0]
        == "https://merch.riotgames.com/de-de/category/riftbound/"
    )
    # The newest-first sorted variant is also present among the targets.
    assert (
        "https://merch.riotgames.com/de-de/category/riftbound/?page=1&sort=dateDesc"
        in fetch.DEFAULT_TARGETS
    )


def test_default_targets_are_all_http_urls_with_merch():
    for target in fetch.DEFAULT_TARGETS:
        assert target.startswith(("http://", "https://"))
    assert any("merch.riotgames.com" in target for target in fetch.DEFAULT_TARGETS)


# ---------------------------------------------------------------------------
# Session lifecycle: a self-created requests.Session must be reused across
# targets and closed afterwards (no per-URL session leak).
# ---------------------------------------------------------------------------
class _FakeSession:
    instances = []

    def __init__(self):
        self.closed = False
        _FakeSession.instances.append(self)

    def get(self, url, headers=None, timeout=None):
        return FakeResponse(status_code=200, text='<a href="https://x.example/y">y</a>')

    def close(self):
        self.closed = True


def _fake_requests_module():
    import types

    return types.SimpleNamespace(Session=_FakeSession)


def test_fetch_targets_uses_single_session_and_closes_it(monkeypatch):
    _FakeSession.instances = []
    monkeypatch.setitem(sys.modules, "requests", _fake_requests_module())
    items = fetch.fetch_targets(
        ["https://a.example/", "https://b.example/", "https://c.example/"]
    )
    assert len(_FakeSession.instances) == 1           # ONE session for all targets
    assert _FakeSession.instances[0].closed is True   # and it was closed
    assert len(items) == 3                             # still extracted every page


def test_fetch_page_closes_session_it_created(monkeypatch):
    _FakeSession.instances = []
    monkeypatch.setitem(sys.modules, "requests", _fake_requests_module())
    result = fetch.fetch_page("https://a.example/")
    assert result is not None
    assert len(_FakeSession.instances) == 1
    assert _FakeSession.instances[0].closed is True


# ---------------------------------------------------------------------------
# extract_products_json — parse products embedded as (escaped) JSON in the page
# ---------------------------------------------------------------------------
def _escaped(obj):
    """Mimic the merch store's backslash-escaped embedded JSON (" -> \\")."""
    return json.dumps(obj, separators=(",", ":")).replace('"', '\\"')


def _merch_category_html(locale="de-de"):
    # Product objects keep "slug" immediately before "ip" (as the real page does),
    # plus a nav item that must NOT be treated as a product.
    products = [
        {"id": "111", "title": "Riftbound Unleashed Vault", "trackingTitle": "x",
         "sku": "111", "productType": "simple", "slug": "riftbound-unleashed-vault",
         "ip": {"label": "Riftbound", "slug": "riftbound"},
         "assets": [{"src": "https://cdn/x.png"}],
         "price": {"amount": 49.99, "currencyCode": "EUR"},
         "contentType": "product", "availability": "available"},
        {"id": "222", "title": "Riftbound Worlds Bundle 2025", "sku": "222",
         "slug": "riftbound-worlds-bundle-2025",
         "ip": {"label": "Riftbound", "slug": "riftbound"},
         "price": {"amount": 99.0, "currencyCode": "EUR"},
         "contentType": "product", "availability": "preorder"},
        {"id": "333", "title": "Riftbound Poppy Playmat", "sku": "333",
         "slug": "riftbound-unleashed-poppy-playmat",
         "ip": {"label": "Riftbound", "slug": "riftbound"},
         "contentType": "product"},
    ]
    nav = {"_type": None, "slug": "/faqs", "title": "FAQs"}
    blob = _escaped(products) + _escaped(nav)
    return (
        "<html><head><title>Riftbound | Riot Games Store</title></head><body>"
        '<a href="/%s/faqs/">FAQs</a>' % locale
        + '<script>self.__next_f.push([1,"' + blob + '"])</script>'
        + "</body></html>"
    )


CATEGORY_SRC = "https://merch.riotgames.com/de-de/category/riftbound/"


def test_extract_products_json_finds_embedded_products():
    prods = fetch.extract_products_json(CATEGORY_SRC, _merch_category_html())
    assert len(prods) == 3
    by_url = {p["url"]: p for p in prods}
    vault = "https://merch.riotgames.com/de-de/product/riftbound-unleashed-vault"
    assert vault in by_url
    p = by_url[vault]
    assert p["title"] == "Riftbound Unleashed Vault"
    assert p["source"] == CATEGORY_SRC
    assert set(p.keys()) == {"title", "url", "source", "text"}
    assert all(isinstance(p[k], str) for k in p)


def test_extract_products_json_availability_detected():
    prods = {p["url"].rsplit("/", 1)[-1]: p for p in
             fetch.extract_products_json(CATEGORY_SRC, _merch_category_html())}
    assert notify.availability_status(prods["riftbound-unleashed-vault"]) == "available"
    assert notify.availability_status(prods["riftbound-worlds-bundle-2025"]) == "preorder"
    # No availability field -> honest unknown (still carries the IP label).
    assert notify.availability_status(prods["riftbound-unleashed-poppy-playmat"]) == "unknown"


def test_extract_products_json_ignores_nav_and_uses_locale():
    prods = fetch.extract_products_json(
        "https://merch.riotgames.com/en-us/category/riftbound/",
        _merch_category_html(locale="en-us"),
    )
    urls = [p["url"] for p in prods]
    assert all("/faqs" not in u for u in urls)          # nav item excluded
    assert all("/en-us/product/" in u for u in urls)    # locale from source


def test_extract_products_json_empty_and_garbage():
    assert fetch.extract_products_json(CATEGORY_SRC, "") == []
    assert fetch.extract_products_json(CATEGORY_SRC, "<html>no product data here</html>") == []
    # Malformed embedded data must not crash.
    assert isinstance(fetch.extract_products_json(CATEGORY_SRC, '<script>\\"slug\\":\\"'), list)


def test_extract_items_includes_embedded_products():
    items = fetch.extract_items(CATEGORY_SRC, _merch_category_html())
    urls = [it["url"] for it in items]
    assert "https://merch.riotgames.com/de-de/product/riftbound-unleashed-vault" in urls
    assert "https://merch.riotgames.com/de-de/faqs/" in urls   # the plain anchor too
    # No duplicates by URL.
    assert len(urls) == len(set(urls))


def test_extracted_products_pass_downstream_filters():
    import relevance
    prods = fetch.extract_products_json(CATEGORY_SRC, _merch_category_html())
    for p in prods:
        assert relevance.is_relevant(p) is True
        assert relevance.is_riftbound(p) is True
        assert notify.is_shop_candidate(p) is True
        assert notify.best_item_url(p)
