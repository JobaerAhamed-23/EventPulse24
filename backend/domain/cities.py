"""Canonical cities (FR-27). Stdlib only, plus `domain.dedup`'s tokenizer.

A city reaches us as free text on a venue — "Brooklyn", "brooklyn ", "Brooklyn, NY" — and
FR-27 needs one page per city, at one stable URL. This module turns that text into a
canonical key, and that key into a slug.

**The trailing region qualifier is kept, never dropped.** Dropping a final "NY" would read
nicely on Brooklyn and would also map `Portland, OR` and `Portland, ME` onto one key —
`dedup.venue_fingerprint` warns about exactly that pair ("The country keeps Portland, Oregon
apart from Portland, Maine"), and `country_code` cannot separate two cities in one country.
So a qualifier becomes its own value, part of the identity rather than noise removed from it.
The cost is accepted and known: "Brooklyn" and "Brooklyn, NY" are two cities here, and FR-27's
">5 events" threshold is what keeps the thinner one off the web.

What is folded is only what is certainly the same place: case, surrounding and internal
whitespace, punctuation, and accents on Latin/Greek/Cyrillic. That folding is
`dedup.tokens`, reused rather than reimplemented so that city identity and venue identity
never disagree about where one word ends and the next begins. This module only reads it —
`venue_fingerprint` is computed from the raw string and is not this module's business.
"""

from collections.abc import Iterable
from typing import NamedTuple

from domain.dedup import tokens

# A trailing qualifier is a short alphabetic run after at least one other word: the "NY" in
# "Brooklyn, NY". Two or three characters covers state and province codes (NY, CA, BC) and
# ISO country codes (US, GB); longer runs are words, and a city is allowed to end in a word.
REGION_MAX = 3
SLUG_MAX = 120
NAME_MAX = 100
KEY_MAX = 100


def split_region(city: str | None) -> tuple[str, str]:
    """`("brooklyn", "ny")` for "Brooklyn, NY"; `("brooklyn", "")` for "Brooklyn".

    The qualifier is only split off when something precedes it, so a city whose whole name is
    short ("Ur", "Ho") keeps its name and gets no region.
    """
    parts = tokens(city)
    if len(parts) > 1 and len(parts[-1]) <= REGION_MAX and parts[-1].isalpha():
        return " ".join(parts[:-1])[:KEY_MAX], parts[-1][:REGION_MAX]
    return " ".join(parts)[:KEY_MAX], ""


class CityIdentity(NamedTuple):
    """What makes one city one city. All three parts, or none of them.

    The key alone is **not** an identity: `Portland, OR` and `Portland, ME` share the key
    `portland` and are different places. Callers resolve on the whole tuple, which is why
    this exists rather than leaving three values for each caller to remember to carry.
    """

    key: str
    region: str
    country_code: str

    def __bool__(self) -> bool:
        """Falsy when there is no city to speak of, so `if identity:` reads correctly."""
        return bool(self.key)


def city_identity(city: str | None, country_code: str | None = None) -> CityIdentity:
    """The resolution key for a free-text city. Falsy when there is nothing to key on.

    An empty identity is a real answer, not a failure: a venue with no city gets no City,
    the same rule Event Fit already follows rather than guessing one.
    """
    key, region = split_region(city)
    return CityIdentity(key, region, (country_code or "").strip().upper())


def normalize_city(city: str | None) -> str:
    """Just the key part. **Not an identity on its own** — see `city_identity`."""
    return split_region(city)[0]


def display_name(city: str | None) -> str:
    """The name as written, trimmed to the column. Never re-cased.

    Title-casing mangles NYC, São Paulo and 's-Hertogenbosch, and a wrong display name is
    visible on the page itself. The first writer's spelling stands until editorial says
    otherwise.
    """
    return " ".join((city or "").split())[:NAME_MAX]


#: Written forms that name the same city, grouped. Curated by hand, deliberately.
#:
#: **This is not a relaxation of the identity rule above.** `city_identity` still keys
#: `Portland, OR` and `Portland, ME` apart, and an `ItemList` of free text still produces
#: one `City` row per distinct identity — that is FR-27's accepted cost and it stands.
#: What this table does is narrower: it lets a *reader* that was given one spelling also
#: find events filed under another spelling of the same place.
#:
#: **Why a curated tuple and not a database table.** An alias is a factual claim that two
#: names are one place, and a wrong one silently merges two cities' events — the kind of
#: claim that should go through code review rather than a form. The list is small by
#: nature: it earns a row only when a real source is seen writing a city two ways.
#:
#: **Only alternate spellings and scripts belong here — never a neighbourhood.** Folding
#: "Mohammadpur" into Dhaka would be a different claim ("this district is inside that
#: city"), it would be unbounded, and it would make a reader who asked for one place
#: silently receive another. `domain.dedup` draws the same line for venues.
#:
#: **A group must be unambiguous across countries**, because the lookup is not scoped by
#: one: the caller that needs this most (Browse) carries no country for the user. So a
#: spelling that names different places in different countries does not go in this table.
CITY_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    # Bangladesh's capital. Eventbrite's Dhaka listings write the city in Latin script on
    # some venues and Bengali on others, so a reader whose city is "Dhaka" would otherwise
    # never be shown an event at a venue filed under "ঢাকা".
    ("Dhaka", "ঢাকা"),
)


def _alias_index() -> dict[str, tuple[str, ...]]:
    """Every alias key mapped to its group's written forms. Built once, at import."""
    index: dict[str, tuple[str, ...]] = {}
    for group in CITY_ALIAS_GROUPS:
        for form in group:
            index[normalize_city(form)] = group
    return index


_ALIAS_INDEX = _alias_index()


def city_spellings(city: str | None) -> tuple[str, ...]:
    """Every written form that names the same city as `city`, including `city` itself.

    A city with no known alias returns just itself, so a caller can always filter on the
    result rather than branching on whether an alias happened to exist. Empty text returns
    nothing at all — the same "no city is a real answer" rule `city_identity` follows.

    The match is on the normalized key, so the caller's spacing and casing do not matter:
    "  dhaka " finds the group that "Dhaka" is in.
    """
    written = display_name(city)
    if not written:
        return ()
    group = _ALIAS_INDEX.get(normalize_city(city))
    if group is None:
        return (written,)
    # The caller's own spelling first, and never twice: a form that only differs by case or
    # spacing is already covered by the case-insensitive comparison the caller makes.
    key = normalize_city(written)
    return (written, *(form for form in group if normalize_city(form) != key))


def canonical_spelling(city: str | None) -> str:
    """The form a city is *shown* as: its group's first entry, or the city as written.

    **The group's first entry is the one the picker offers**, so a city that the catalog
    files under two scripts still appears once, under one name, however the venues that
    happen to exist today are spelled. A label that changed with the catalog's contents
    would move under the reader between visits.
    """
    written = display_name(city)
    if not written:
        return ""
    group = _ALIAS_INDEX.get(normalize_city(written))
    return display_name(group[0]) if group is not None else written


def collapse_aliases(cities: Iterable[str]) -> tuple[str, ...]:
    """The cities, with each alias group reduced to one entry, order preserved.

    **For a picker, not for a filter.** Two spellings of one city are one choice, and
    offering both asks the reader a question with no answer — either picks the same
    events, because the reads expand a city into every spelling in its group. A filter
    must still use `city_spellings`; this is only about what is *offered*.
    """
    seen: set[str] = set()
    collapsed: list[str] = []
    for city in cities:
        shown = canonical_spelling(city)
        key = normalize_city(shown)
        if not key or key in seen:
            continue
        seen.add(key)
        collapsed.append(shown)
    return tuple(collapsed)


def mint_city_slug(key: str, region: str = "", country_code: str = "") -> str:
    """`brooklyn`, `brooklyn-ny`, `brooklyn-ny-us` — the FR-27 URL segment.

    Minted once and never re-minted, like `mint_slug` for events: a city page that has been
    indexed must not move. The caller escalates through the longer forms when the unique
    constraint trips.
    """
    parts = [p for p in (key.replace(" ", "-"), region, country_code.lower()) if p]
    return "-".join(parts)[:SLUG_MAX].strip("-")


__all__ = [
    "CITY_ALIAS_GROUPS",
    "CityIdentity",
    "canonical_spelling",
    "city_identity",
    "city_spellings",
    "collapse_aliases",
    "display_name",
    "mint_city_slug",
    "normalize_city",
    "split_region",
]
