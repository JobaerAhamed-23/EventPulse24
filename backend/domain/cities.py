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


def mint_city_slug(key: str, region: str = "", country_code: str = "") -> str:
    """`brooklyn`, `brooklyn-ny`, `brooklyn-ny-us` — the FR-27 URL segment.

    Minted once and never re-minted, like `mint_slug` for events: a city page that has been
    indexed must not move. The caller escalates through the longer forms when the unique
    constraint trips.
    """
    parts = [p for p in (key.replace(" ", "-"), region, country_code.lower()) if p]
    return "-".join(parts)[:SLUG_MAX].strip("-")


__all__ = [
    "CityIdentity",
    "city_identity",
    "display_name",
    "mint_city_slug",
    "normalize_city",
    "split_region",
]
