"""Tests for relevance.py — the Riftbound x T1 relevance filter.

Pure functions, no I/O. Candidate items are dicts with EXACTLY the keys
{"title", "url", "source", "text"}.
"""
import relevance


def item(title, *, text="", url="", source=""):
    return {"title": title, "text": text, "url": url, "source": source}


# ---------------------------------------------------------------------------
# is_relevant — positive cases
# ---------------------------------------------------------------------------
def test_positive_riftbound_x_t1_collection():
    assert relevance.is_relevant(
        item("Riftbound x T1 Worlds Champion Collection now live")
    ) is True


def test_positive_worlds_champion_collection():
    assert relevance.is_relevant(item("Worlds Champion Collection revealed")) is True


def test_positive_signature_edition():
    assert relevance.is_relevant(item("T1 Signature Edition set details")) is True


def test_positive_player_bundle():
    assert relevance.is_relevant(item("T1 Player Bundle available now")) is True


def test_positive_faker_galio_riftbound():
    assert relevance.is_relevant(
        item("New Faker Galio card revealed for Riftbound")
    ) is True


def test_positive_player_names_and_t1():
    assert relevance.is_relevant(
        item("Gumayusi and Keria featured in the T1 collection")
    ) is True


def test_positive_drawing_registration():
    it = item("Riftbound x T1 Signature Edition drawing registration is open")
    assert relevance.is_relevant(it) is True
    assert "drawing" in relevance.relevance_reasons(it)


def test_positive_in_stock_availability_reason():
    it = item(
        "Riftbound T1 Worlds Champion Collection now in stock at the Riot merch store"
    )
    assert relevance.is_relevant(it) is True
    reasons = relevance.relevance_reasons(it)
    availability = {"in stock", "available", "restock", "sold out", "drop"}
    assert availability & set(reasons)
    assert "in stock" in reasons


# ---------------------------------------------------------------------------
# is_relevant — negative cases
# ---------------------------------------------------------------------------
def test_negative_anti_cheat():
    assert relevance.is_relevant(
        item("Riot Games announces new anti-cheat system for League")
    ) is False


def test_negative_hoodie_merch_context_only():
    # Has merch/availability context but NO focus subject -> must be False.
    assert relevance.is_relevant(
        item("New League of Legends hoodie now in the merch store")
    ) is False


def test_negative_patch_notes():
    assert relevance.is_relevant(
        item("Patch 14.13 balance changes for League of Legends")
    ) is False


def test_negative_t1_not_whole_word():
    # "t100" must NOT trigger the whole-word "t1" focus subject.
    assert relevance.is_relevant(
        item("the t100 keyboard is on sale")
    ) is False


# ---------------------------------------------------------------------------
# t1 whole-word matching
# ---------------------------------------------------------------------------
def test_t1_whole_word_matches_alone():
    assert relevance.is_relevant(item("The T1 roster looks strong")) is True


def test_t1_appears_in_reasons_when_present():
    reasons = relevance.relevance_reasons(item("T1 Player Bundle available now"))
    assert "t1" in reasons


def test_t1100_does_not_appear_in_reasons():
    reasons = relevance.relevance_reasons(item("the t100 keyboard is on sale"))
    assert "t1" not in reasons


# ---------------------------------------------------------------------------
# relevance_reasons — deterministic + combined text (title+text+url)
# ---------------------------------------------------------------------------
def test_reasons_are_deterministic_sorted():
    it = item("Riftbound x T1 Signature Edition drawing registration is open")
    assert relevance.relevance_reasons(it) == sorted(relevance.relevance_reasons(it))


def test_reasons_empty_for_irrelevant():
    assert relevance.relevance_reasons(
        item("Patch 14.13 balance changes for League of Legends")
    ) == []


def test_reasons_consider_url_and_text():
    it = item("Cool item", text="", url="https://merch.riotgames.com/riftbound-set")
    assert "riftbound" in relevance.relevance_reasons(it)
    assert relevance.is_relevant(it) is True


def test_reasons_include_multiple_focus_and_context():
    it = item("Riftbound x T1 drop")
    reasons = relevance.relevance_reasons(it)
    assert "riftbound" in reasons
    assert "t1" in reasons
    assert "drop" in reasons


# ---------------------------------------------------------------------------
# filter_relevant
# ---------------------------------------------------------------------------
def test_filter_relevant_preserves_order_and_filters():
    items = [
        item("Riftbound x T1 Worlds Champion Collection now live"),
        item("Patch 14.13 balance changes for League of Legends"),
        item("Worlds Champion Collection revealed"),
        item("New League of Legends hoodie now in the merch store"),
    ]
    result = relevance.filter_relevant(items)
    titles = [i["title"] for i in result]
    assert titles == [
        "Riftbound x T1 Worlds Champion Collection now live",
        "Worlds Champion Collection revealed",
    ]


def test_filter_relevant_empty():
    assert relevance.filter_relevant([]) == []


# ---------------------------------------------------------------------------
# is_riftbound
# ---------------------------------------------------------------------------
def test_is_riftbound_true():
    assert relevance.is_riftbound(
        item("Riftbound x T1 Worlds Champion Collection now live")
    ) is True


def test_is_riftbound_false():
    # "T1 Player Bundle available now" has no 'riftbound'.
    assert relevance.is_riftbound(item("T1 Player Bundle available now")) is False


def test_is_riftbound_considers_url():
    assert relevance.is_riftbound(
        item("Cool item", url="https://merch.riotgames.com/riftbound-set")
    ) is True


# ---------------------------------------------------------------------------
# public API sanity
# ---------------------------------------------------------------------------
def test_focus_subjects_present():
    subjects = {s.lower() for s in relevance.FOCUS_SUBJECTS}
    for required in (
        "riftbound",
        "worlds champion collection",
        "signature edition",
        "player bundle",
        "faker",
        "galio",
        "t1",
        "gumayusi",
        "keria",
        "oner",
        "zeus",
        "doran",
    ):
        assert required in subjects


def test_context_signals_present():
    signals = {s.lower() for s in relevance.CONTEXT_SIGNALS}
    for required in (
        "drawing",
        "lottery",
        "raffle",
        "sweepstakes",
        "in stock",
        "available",
        "restock",
        "sold out",
        "drop",
    ):
        assert required in signals


# ---------------------------------------------------------------------------
# Over-breadth regression: bare champion/player tokens must NOT flag generic
# League news on their own — only together with a Riftbound/T1 anchor.
# ---------------------------------------------------------------------------
def test_negative_bare_doran_generic_league():
    assert relevance.is_relevant(
        item("Doran's Blade build guide for League patch 14.13")
    ) is False


def test_negative_bare_galio_generic_patch():
    assert relevance.is_relevant(
        item("Galio gets a mid-scope update in patch 14.13")
    ) is False


def test_negative_bare_zeus_streamer():
    assert relevance.is_relevant(item("Zeus streams solo queue tonight")) is False


def test_negative_oner_substring_not_matched():
    # "commissioner" / "toner" contain the substring "oner" but must NOT match.
    assert relevance.is_relevant(item("The new commissioner of the league")) is False
    assert "oner" not in relevance.relevance_reasons(item("A toner cartridge review"))


def test_conditional_token_relevant_with_riftbound_anchor():
    it = item("Riftbound Galio collector card")
    assert relevance.is_relevant(it) is True
    assert "galio" in relevance.relevance_reasons(it)


def test_conditional_token_relevant_with_t1_anchor():
    it = item("T1 Doran signature card in the collection")
    assert relevance.is_relevant(it) is True
    assert "doran" in relevance.relevance_reasons(it)


# ---------------------------------------------------------------------------
# Newsletter / top-deck / article noise: generic content with NO Riftbound/T1
# collection signal must stay rejected. These are regression guards proving the
# filter is not too broad — they must pass WITHOUT modifying relevance.py.
# ---------------------------------------------------------------------------
def test_negative_weekly_newsletter_top_decks():
    assert relevance.is_relevant(
        item("Weekly newsletter: top decks and patch highlights")
    ) is False


def test_negative_top_5_decks_to_climb():
    assert relevance.is_relevant(
        item("Top 5 decks to climb this week")
    ) is False


def test_negative_riot_games_newsletter_signup():
    assert relevance.is_relevant(
        item("Riot Games newsletter sign-up")
    ) is False


def test_negative_best_budget_decks_this_patch():
    assert relevance.is_relevant(
        item("Best budget decks this patch")
    ) is False


def test_positive_control_merch_riftbound_still_relevant():
    # Positive control: a real merch item must still pass while the noise above
    # is rejected — proof the filter stays correctly scoped, not merely narrow.
    it = item(
        "Riftbound x T1 Worlds Champion Collection",
        url="https://merch.riotgames.com/de-de/category/riftbound/",
    )
    assert relevance.is_relevant(it) is True
