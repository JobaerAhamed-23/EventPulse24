"""Event Identity (FR-15, AD-4): fingerprints, URLs, rules (a)/(b)/(c), resolution, locks.

Golden values pin fingerprint version v1: if one of them changes, identity changed. Bump the
version instead of editing these.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from domain.dedup import (
    Ambiguous,
    Candidate,
    LiveEvent,
    Matched,
    New,
    Rule,
    canonical_url,
    ics_item_id,
    identity_lock_keys,
    jaccard,
    match,
    resolve,
    title_fingerprint,
    tokens,
    venue_fingerprint,
)

SOURCE_A, SOURCE_B = UUID(int=1), UUID(int=2)
EVENT_1, EVENT_2, EVENT_3 = UUID(int=101), UUID(int=102), UUID(int=103)
START = datetime(2026, 11, 6, 0, 30, tzinfo=UTC)
VENUE = venue_fingerprint("Bowery Ballroom", "New York", "US")
TITLE = title_fingerprint("Japanese Breakfast with Special Guests")
URL = canonical_url("https://tickets.example.test/e/123")

# --- Title fingerprint -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "fingerprint"),
    [
        ("Café Tacvba LIVE!", "v1:cafe live tacvba|"),
        ("Straße ﬁnale", "v1:finale strasse|"),  # ß casefolds to ss; the ﬁ ligature splits
        ("ドラゴン祭り", "v1:ゴン ドラ ラゴ ン祭 祭り|"),  # ド keeps its dakuten; bigrams
        ("東京音楽祭", "v1:京音 東京 楽祭 音楽|"),
        ("नमस्ते दुनिया", "v1:दुनिया नमस्ते|"),  # Devanagari marks stay inside the word
        ("The The", "v1:|the"),
        ("Night at the Museum", "v1:museum night|at the"),
        ("Rock&Roll 2026", "v1:2026 rock roll|"),
        ("", "v1:|"),
        (None, "v1:|"),
    ],
)
def test_title_fingerprint_golden(title, fingerprint):
    assert title_fingerprint(title) == fingerprint


def test_title_fingerprint_ignores_case_punctuation_order_and_repeats():
    assert title_fingerprint("ROCK, rock & Roll!!") == title_fingerprint("roll rock")


def test_title_fingerprint_folds_latin_accents_but_not_kana_marks():
    assert title_fingerprint("Café Noël") == title_fingerprint("Cafe Noel")
    assert title_fingerprint("ドラゴン") != title_fingerprint("トラコン")


def test_title_fingerprint_is_capped_at_512_on_a_token_boundary():
    title = " ".join(f"word{n:03d}" for n in range(120))  # ~960 characters

    fingerprint = title_fingerprint(title)

    assert len(fingerprint) <= 512
    assert all(token.startswith("word") and len(token) == 7 for token in fingerprint[3:-1].split())


def test_title_fingerprint_truncates_absurd_tokens():
    assert tokens("x" * 600) == ["x" * 64]


def test_night_at_and_night_of_the_museum_are_the_same_title():
    # Intended: only stop words differ. Rule (b) still needs the same venue and instant.
    assert jaccard(
        title_fingerprint("Night at the Museum"), title_fingerprint("Night of the Museum")
    ) == Fraction(1)


# --- Jaccard -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        # Letters that aren't stop words ("a" is one).
        ("k l m n p", "k l m n p q", Fraction(5, 6)),
        ("k l m n", "k l m n p", Fraction(4, 5)),  # exactly the threshold
        ("k l m", "k l m n", Fraction(3, 4)),  # just below it
        ("k l", "m n", Fraction(0)),
    ],
)
def test_jaccard_exact(a, b, expected):
    assert jaccard(title_fingerprint(a), title_fingerprint(b)) == expected


def test_jaccard_all_stop_word_title_compares_every_token_symmetrically():
    a, b = title_fingerprint("The The"), title_fingerprint("The The Live")

    assert jaccard(a, b) == jaccard(b, a) == Fraction(1, 2)


@pytest.mark.parametrize(
    ("a", "b"),
    [("v1:|", "v1:|"), ("v1:x|", "v2:x|"), ("garbage", "v1:x|"), ("v1:x", "v1:x|")],
    ids=["both-empty", "version-mismatch", "malformed", "missing-separator"],
)
def test_jaccard_zero_cases(a, b):
    assert jaccard(a, b) == 0


# --- Venue fingerprint -----------------------------------------------------------------------


def test_venue_fingerprint_golden():
    assert venue_fingerprint("Bowery Ballroom", "New York", "US") == (
        "v1:720a236e60a98c1944dec6e721fd1e34e9152e23cc10c6f0f6eaf4ef3de67be8"
    )


def test_venue_fingerprint_normalizes_case_stop_words_and_country():
    assert venue_fingerprint("The Fillmore", "San Francisco", "us") == venue_fingerprint(
        "Fillmore", "SAN FRANCISCO", " US "
    )


def test_venue_fingerprint_separates_same_name_city_in_other_countries():
    assert venue_fingerprint("Crystal Ballroom", "Portland", "US") != venue_fingerprint(
        "Crystal Ballroom", "Portland", "CA"
    )


@pytest.mark.parametrize("name", ["", None, "  ", "!!!"])
def test_venue_fingerprint_empty_without_a_name(name):
    assert venue_fingerprint(name, "New York", "US") == ""


def test_venue_fingerprint_keeps_a_name_made_only_of_stop_words():
    assert venue_fingerprint("The The", "London", "GB") != ""


# --- Canonical URL ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "canonical"),
    [
        (
            "HTTP://www.Example.COM:80/a/b/?utm_Source=x&b=2&a=&fbclid=1&gclid=2#frag",
            "https://example.com/a/b?a=&b=2",
        ),
        ("https://user:secret@example.com", "https://example.com/"),
        ("https://example.com", "https://example.com/"),
        ("https://example.com:443/x/", "https://example.com/x"),
        ("https://example.com:8443/x", "https://example.com:8443/x"),
        ("https://example.com/#/route/1", "https://example.com/#/route/1"),
        ("https://example.com/#!/route", "https://example.com/#!/route"),
        ("https://example.com/p%2fa", "https://example.com/p%2Fa"),  # / stays escaped
        ("https://example.com/%7Ebob/%41b", "https://example.com/~bob/Ab"),  # unreserved
        ("https://[2001:DB8::1]:8080/x", "https://[2001:db8::1]:8080/x"),
        ("https://[2001:db8::1]/x", "https://[2001:db8::1]/x"),
        ("https://bücher.de/", "https://xn--bcher-kva.de/"),
        ("http://example.com/?b=1&a=2", "https://example.com/?a=2&b=1"),
    ],
)
def test_canonical_url(url, canonical):
    assert canonical_url(url) == canonical


@pytest.mark.parametrize(
    "url",
    [
        "",
        None,
        "   ",
        "ftp://example.com/a",
        "javascript:alert(1)",
        "http://[::1",
        "https:///x",
        "https://a..b/",
        "https://example.com:99999/",
    ],
)
def test_canonical_url_unusable_input_is_empty(url):
    assert canonical_url(url) == ""


def test_canonical_url_ipv6_port_never_merges_into_the_address():
    assert canonical_url("https://[2001:db8::1]:8080/x") != canonical_url(
        "https://[2001:db8::1:8080]/x"
    )


def test_canonical_url_http_and_www_variants_are_one_url():
    assert canonical_url("http://www.example.com/e") == canonical_url("https://example.com/e/")


# --- ICS item ids ------------------------------------------------------------------------------


def test_ics_item_id_plain_and_recurring():
    assert ics_item_id(" uid-1@example ") == "uid-1@example"
    assert ics_item_id("uid-1", START + timedelta(microseconds=5)) == "uid-1#20261106T003000Z"


def test_ics_weekly_instances_sharing_a_uid_stay_distinct():
    weekly = {ics_item_id("meetup@example", START + timedelta(weeks=n)) for n in range(4)}

    assert len(weekly) == 4


@pytest.mark.parametrize("uid", ["", "   ", None])
def test_ics_item_id_requires_a_uid(uid):
    with pytest.raises(ValueError):
        ics_item_id(uid)


# --- Rules (b) and (c) -----------------------------------------------------------------------


def candidate(**changes) -> Candidate:
    base = Candidate(SOURCE_B, "b-1", VENUE, START, TITLE, URL)
    return replace(base, **changes)


def live(event_id=EVENT_1, **changes) -> LiveEvent:
    base = LiveEvent(event_id, VENUE, START, TITLE, URL, frozenset({SOURCE_A}))
    return replace(base, **changes)


def test_match_rule_b_same_venue_instant_and_similar_title():
    other_title = title_fingerprint("Japanese Breakfast w/ Special Guests")  # 4/5 shared

    assert match(candidate(title_fingerprint=other_title, canonical_url=""), live()) is (
        Rule.VENUE_TIME_TITLE
    )


def test_match_rule_b_reported_before_rule_c():
    assert match(candidate(), live()) is Rule.VENUE_TIME_TITLE


def test_match_rule_c_same_url_and_instant():
    assert match(candidate(venue_fingerprint=""), live()) is Rule.CANONICAL_URL


@pytest.mark.parametrize(
    "changes",
    [
        {"start_utc": START + timedelta(seconds=1)},  # P1: never across instants
        {"start_utc": START + timedelta(days=7)},  # a recurring instance sharing the URL
        {"title_fingerprint": title_fingerprint("Mitski"), "canonical_url": ""},
        {"venue_fingerprint": "", "canonical_url": ""},
        {
            "venue_fingerprint": venue_fingerprint("Elsewhere", "Brooklyn", "US"),
            "canonical_url": "",
        },
        {"canonical_url": canonical_url("https://other.example.test/e"), "venue_fingerprint": ""},
    ],
    ids=[
        "one-second-apart",
        "weekly-instance",
        "different-title",
        "nothing-to-compare",
        "different-venue",
        "different-url",
    ],
)
def test_match_none(changes):
    assert match(candidate(**changes), live()) is None


def test_match_compares_whole_seconds():
    assert match(candidate(start_utc=START + timedelta(microseconds=999_999)), live()) is not None


def test_match_same_instant_in_another_zone_matches():
    in_new_york = START.astimezone(ZoneInfo("America/New_York"))

    assert match(candidate(start_utc=in_new_york), live()) is Rule.VENUE_TIME_TITLE


def test_match_never_merges_two_items_of_the_same_source():
    # A venue feed linking every item to one calendar page: two rooms, same time.
    assert (
        match(candidate(source_id=SOURCE_A), live(bound_source_ids=frozenset({SOURCE_A}))) is None
    )


def test_match_ignores_superseded_events():
    assert match(candidate(), live(superseded=True)) is None


# --- resolve() ---------------------------------------------------------------------------------


def test_resolve_bound_item_keeps_its_event_and_reports_others_as_review_signals():
    result = resolve(candidate(), EVENT_3, [live(EVENT_1), live(EVENT_3)])

    assert result == Matched(EVENT_3, Rule.SOURCE_ITEM, frozenset({EVENT_1}))


def test_resolve_bound_item_without_other_matches():
    assert resolve(candidate(), EVENT_3, []) == Matched(EVENT_3, Rule.SOURCE_ITEM)


def test_resolve_new_when_nothing_matches():
    assert resolve(candidate(), None, [live(start_utc=START + timedelta(hours=1))]) == New()


def test_resolve_single_match():
    assert resolve(candidate(), None, [live(EVENT_1), live(EVENT_1)]) == Matched(
        EVENT_1, Rule.VENUE_TIME_TITLE
    )


def test_resolve_two_distinct_matches_is_ambiguous():
    result = resolve(candidate(), None, [live(EVENT_1), live(EVENT_2, venue_fingerprint="")])

    assert result == Ambiguous(frozenset({EVENT_1, EVENT_2}))


def test_resolve_skips_superseded_candidates():
    result = resolve(candidate(), None, [live(EVENT_1, superseded=True), live(EVENT_2)])

    assert result == Matched(EVENT_2, Rule.VENUE_TIME_TITLE)


def test_resolve_reports_rule_by_priority_not_list_order():
    by_url = live(EVENT_1, venue_fingerprint="")

    assert resolve(candidate(), None, [by_url]).rule is Rule.CANONICAL_URL
    assert resolve(candidate(), None, [live(EVENT_1)]).rule is Rule.VENUE_TIME_TITLE


# --- Lock keys ---------------------------------------------------------------------------------


def test_identity_lock_keys_golden_and_sorted():
    keys = identity_lock_keys(
        Candidate(SOURCE_A, "item-1", "v", datetime(2026, 1, 1, tzinfo=UTC), "v1:a|", "")
    )

    assert keys == (-6476308451346063572, 9134818763111587391)


def test_identity_lock_keys_one_per_rule_and_signed_64_bit():
    keys = identity_lock_keys(candidate())

    assert len(keys) == 3
    assert list(keys) == sorted(keys)
    assert all(-(2**63) <= key < 2**63 for key in keys)


def test_identity_lock_keys_skip_empty_parts():
    assert len(identity_lock_keys(candidate(venue_fingerprint="", canonical_url=""))) == 1
    assert (
        identity_lock_keys(candidate(source_event_id="", venue_fingerprint="", canonical_url=""))
        == ()
    )


def test_identity_lock_keys_ignore_sub_second_and_zone_differences():
    shifted = START.astimezone(ZoneInfo("Asia/Tokyo")) + timedelta(microseconds=10)

    assert identity_lock_keys(candidate(start_utc=shifted)) == identity_lock_keys(candidate())


def test_identity_lock_keys_differ_by_instant():
    later = candidate(start_utc=START + timedelta(seconds=1))

    assert set(identity_lock_keys(later)) & set(identity_lock_keys(candidate())) == {
        identity_lock_keys(candidate(venue_fingerprint="", canonical_url=""))[0]
    }
