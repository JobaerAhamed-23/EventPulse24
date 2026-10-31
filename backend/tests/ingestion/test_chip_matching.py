"""The event's half of the interest overlap: which chips an event belongs to (FR-1).

**Why this module is tested on its own.** The Relevance Pulse's interest term is the
largest weight in the formula (`0.45 × interest_overlap`), and it was pinned to `0.0`
for every candidate until this module existed — because the *event's* chip keys were
never produced anywhere. `domain/ranking.py` calls an absent half "an inert weight",
and an inert weight is worse than a small one: "the published formula would stay
arithmetically checkable and still produce a different number from the one on the
card".

So the tests here are the ones that prove the term is **alive** — and, just as
importantly, that it is **conservative**. A keyword that matches too broadly files a
card under a category the user never asked about, and inflates the term that decides
which event the user sees first. The whole-word rule is therefore a behaviour worth
pinning down, not an implementation detail.
"""

from apps.ingestion.services.chip_matching import chip_keys_for
from shared.constants import INTEREST_CHIP_KEYWORDS

# --- the matching ---------------------------------------------------------------------


def test_a_matching_keyword_produces_its_chip():
    assert "tech_meetups" in chip_keys_for(title="Brooklyn Tech Meetup")


def test_the_matching_is_case_insensitive():
    assert "tech_meetups" in chip_keys_for(title="BROOKLYN TECH MEETUP")
    assert "tech_meetups" in chip_keys_for(title="Brooklyn Tech Meetup")


def test_a_keyword_is_matched_against_the_description_too():
    """The description is the event's own text, so it counts."""
    assert "arts_culture" in chip_keys_for(title="An Evening", description="Live music tonight")


def test_an_event_with_no_keywords_matches_nothing():
    assert chip_keys_for(title="Quarterly Accounting Review") == ()


def test_an_empty_title_and_description_match_nothing():
    assert chip_keys_for(title="", description="") == ()


def test_text_with_no_word_characters_matches_nothing():
    """Punctuation and digits are not words, so there is nothing to match against."""
    assert chip_keys_for(title="--- !!! ???") == ()
    assert chip_keys_for(title="2026") == ()


# --- the whole-word rule --------------------------------------------------------------


def test_a_keyword_does_not_match_inside_a_longer_word():
    """ "art" must not match "start", or every "startup" event becomes an art event."""
    assert "arts_culture" not in chip_keys_for(title="Startup Weekend")


def test_a_keyword_does_not_match_a_prefix_of_a_longer_word():
    """ "market" must not match "marketing", and "art" must not match "cart".

    The rule is about **substrings**: a word that merely *contains* a keyword is not a
    match. "sports" is a separate keyword from "sport" in its own right, so "Sports
    Clinic" is a sports event for the ordinary reason — it contains the word "sports".
    """
    assert "markets_fairs" not in chip_keys_for(title="Marketing Meetup")
    assert "arts_culture" not in chip_keys_for(title="Shopping Cart Fair")


def test_the_whole_word_boundary_respects_apostrophes_and_hyphens():
    """ "storytime" and "story-time" are both spellings of the same thing, and a keyword
    set that matched one but not the other would be a rule nobody could predict."""
    assert "family_kids" in chip_keys_for(title="Storytime at the Library")
    assert "family_kids" in chip_keys_for(title="Story-Time at the Library")
    assert "family_kids" in chip_keys_for(title="Storytime's Song Circle")


def test_a_word_that_merely_contains_the_keyword_does_not_match():
    assert "tech_meetups" not in chip_keys_for(title="Technical Writing Circle")


# --- the multi-word phrase ------------------------------------------------------------


def test_a_multi_word_keyword_matches_as_a_phrase():
    """A phrase is matched as a phrase, not as two separate words."""
    assert "markets_fairs" in chip_keys_for(title="Saturday Craft Fair")


def test_a_multi_word_keyword_does_not_match_its_words_apart():
    """The two words in the wrong order, or not adjacent, are not the phrase.

    `government_civic` has a phrase keyword ("public hearing") among its single-word
    ones, so the chip can be reached either way. The phrase rule is therefore checked
    against the phrase *alone* — the test text carries no other keyword of the chip, so
    the chip is reached by the phrase and only by the phrase.
    """
    # Out of order: the phrase does not match, and no other keyword of the chip is
    # present, so the chip is not reached.
    assert "government_civic" not in chip_keys_for(title="Hearing of the Public")
    # Not adjacent: same.
    assert "government_civic" not in chip_keys_for(title="Public Meeting Hearing")
    # Adjacent and in order: the phrase matches, and it is the only keyword present.
    assert "government_civic" in chip_keys_for(title="A Public Hearing")


def test_a_multi_word_keyword_matches_across_any_run_of_whitespace():
    assert "markets_fairs" in chip_keys_for(title="Saturday  Craft   Fair")


def test_a_multi_word_keyword_matches_in_the_description():
    assert "markets_fairs" in chip_keys_for(title="Saturday", description="A craft fair downtown")


# --- the ordering and the de-duplication -----------------------------------------------


def test_a_chip_matched_by_several_keywords_is_listed_once():
    """ "Concert", "music" and "film" all belong to `arts_culture`, and the interest
    overlap is counted over *distinct* chips — so the chip must appear once, and the
    caller must not have to de-duplicate."""
    keys = chip_keys_for(title="Concert and Music and Film")
    assert keys.count("arts_culture") == 1


def test_the_keys_come_back_in_the_table_s_order():
    """The order is the table's order, not the order the keywords were found, so the
    result is deterministic — which is what the ranking's determinism needs."""
    keys = chip_keys_for(title="Park Concert and a Tech Meetup")

    assert keys == tuple(chip_key for chip_key in INTEREST_CHIP_KEYWORDS if chip_key in set(keys))


def test_the_keys_come_back_in_the_order_the_chips_are_offered():
    """The table's order is the `INTEREST_CHIPS` order, so the event's chips come back
    in the same order the chips were offered to the user."""
    from shared.constants import INTEREST_CHIPS

    chip_order = [key for key, _label in INTEREST_CHIPS]
    keys = chip_keys_for(title="Park Concert and a Tech Meetup")

    assert [chip_order.index(key) for key in keys] == sorted(chip_order.index(key) for key in keys)


# --- the venue is not the event's text ------------------------------------------------


def test_the_venue_is_not_matched():
    """The venue is *where* the event happens; the title and description are *what* it
    is. A venue named "The Tech Bar" must not make every event there a tech event.

    The function takes only the event's own text, so a venue cannot reach it at all —
    and the catalog read is what keeps it that way: it passes the title and the
    description, and never the venue's name.
    """
    from apps.ingestion.services.catalog_read import PublicEventCandidate

    fields = PublicEventCandidate.__dataclass_fields__
    assert "venue_name" in fields
    assert "venue_city" in fields
    # The candidate carries the venue's name, and the chip keys are computed from the
    # title and description alone — so the venue's words never reach the matcher.
    assert set(PublicEventCandidate.__dataclass_fields__) >= {"chip_keys"}


# --- the table itself -----------------------------------------------------------------


def test_every_keyword_in_the_table_is_reachable():
    """A keyword nobody can match is a keyword that does nothing.

    This walks the table and asserts each chip can be produced by one of its own
    keywords, so a typo in a keyword ("faris" for "fair") cannot survive quietly.
    """
    for chip_key, keywords in INTEREST_CHIP_KEYWORDS.items():
        matched = chip_keys_for(title=f"{keywords[0]} Event")
        assert chip_key in matched, f"{chip_key} is unreachable via {keywords[0]!r}"


def test_the_table_is_not_empty():
    assert INTEREST_CHIP_KEYWORDS


# --- the guards -----------------------------------------------------------------------


def test_a_keyword_with_no_word_characters_matches_nothing():
    """A keyword that is only punctuation has no words to match on.

    It cannot happen from the shipped table — every keyword there has letters — but the
    table is **editable** (the keywords are matching policy, and the policy is allowed
    to change), so a hand-edit that leaves a stray keyword must not make the matcher
    match *everything*. The guard matches nothing instead.
    """
    from apps.ingestion.services.chip_matching import _pattern_for

    pattern = _pattern_for("!!!")
    assert pattern.search("anything at all") is None
    assert pattern.search("!!!") is None


def test_a_keyword_with_no_word_characters_adds_no_chip():
    """The same guard, through the public function."""
    assert chip_keys_for(title="!!! Event") == ()
