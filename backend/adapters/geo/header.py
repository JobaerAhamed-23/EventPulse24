"""The real geo adapter: reads the edge's geo header and does nothing else (FR-2).

**This adapter does no database lookup and calls no vendor.** It reads one header, and
that is the whole of it. The edge already knows where the request came from; asking a
geo-IP service would mean sending the caller's address to a third party on every page
load, which PRD §10.2 and FR-2's consent banner are both about.

**The header is untrusted input.** It came from the caller — or from the edge, which the
caller could have spoofed if the edge did not overwrite it. Three things happen to it
before it is allowed near anything:

1. **It is length-bounded.** A header value can be 8 KB, and a city name is not. Past
   `GEO_CITY_MAX_LENGTH` the value is refused outright: a 10 KB "city" is not a city,
   it is an attempt to put a value somewhere it should not go.

2. **It is URL-decoded exactly once.** The edge encodes the city, because a raw header
   value cannot contain every character (`Brooklyn%2CNY`). **Once.** Decoding twice is
   how `%252e%252e%252f` becomes `../`: the first decode turns it into `%2e%2e%2f`,
   which looks encoded and innocent, and the second decode turns it into a path
   traversal. One decode, and then it is never decoded again.

3. **It is normalized into a city shape.** Collapsed whitespace, stripped, and reduced
   to letters, digits, spaces, hyphens and apostrophes. The result is used as a
   **lookup key** against the supported-cities set, never interpolated into SQL or into a
   path — but it is still attacker-controlled, and the normalization is the last line
   rather than the only one.

**Header lookup is case-insensitive.** HTTP header names are case-insensitive, and
Django's `request.headers` already folds them — but the port takes a plain mapping, so
the adapter does the folding itself rather than assuming the caller's mapping is a
Django one.
"""

from collections.abc import Mapping
from urllib.parse import unquote

from ports.geo import GeoPort
from shared.constants import GEO_CITY_MAX_LENGTH, GEO_HEADER_NAME

#: The characters a city name may contain once it has been normalized.
#:
#: Letters, digits, spaces, hyphens and apostrophes — which is enough for "New York
#: City", "St. John's", "Saint-Denis" and "Côte-d'Or", and not enough for a path
#: separator, a quote or a control character.
_ALLOWED_CITY_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -'")


class HeaderGeoAdapter(GeoPort):
    """Reads the edge's geo header. No lookup, no vendor call, no clock."""

    def resolve_city(self, headers: Mapping[str, str]) -> str | None:
        """The city in the geo header, or `None` when there isn't a usable one."""
        raw = _header_value(headers, GEO_HEADER_NAME)
        if raw is None:
            return None

        # Bound it BEFORE decoding: the *encoded* value is what arrived, and a value
        # that is already over the bound is refused without being expanded. Decoding
        # only ever *shortens* a value — each `%XX` escape becomes one character — so
        # a bound checked here is a bound on the decoded value too, and there is no
        # second check to add. An earlier version had one, and it could never fire:
        # unreachable code is not a safety net, it is a claim the code does not make.
        if len(raw) > GEO_CITY_MAX_LENGTH:
            return None

        # Decode exactly once. `unquote` on a value with no escapes is the identity, so
        # an already-plain city passes through unchanged.
        decoded = unquote(raw)

        return normalize_city(decoded)


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    """The header's value, looked up case-insensitively.

    `request.headers` folds header names for Django; a plain mapping might not. The
    port's contract is a mapping, so the adapter cannot assume the caller's mapping
    folds anything.
    """
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return None


def normalize_city(value: str) -> str | None:
    """Reduce a raw header value to a city name, or `None` if nothing usable is left.

    * Whitespace is collapsed and trimmed, so `"  Brooklyn  "` is `"Brooklyn"`.
    * Characters outside the allowed set are **dropped**, not replaced — so
      `"Brooklyn/NY"` becomes `"BrooklynNY"` rather than something with a separator in
      it. Dropping rather than substituting keeps the output inside the allowed set by
      construction.
    * An empty result is `None`: the edge said something, and it said nothing usable.
    """
    collapsed = " ".join(value.split())
    if not collapsed:
        return None
    kept = "".join(ch for ch in collapsed if ch in _ALLOWED_CITY_CHARS)
    kept = " ".join(kept.split())
    if not kept:
        return None
    return kept


__all__ = ["GEO_HEADER_NAME", "HeaderGeoAdapter", "normalize_city"]
