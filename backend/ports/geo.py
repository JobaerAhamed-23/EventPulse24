"""Geo port (FR-2): where the caller is, as far as the edge says.

The Pulse Preview is the first thing a visitor sees, and it is local: "three events in
the user's inferred city" (FR-2). The only source of that location is the **edge's geo
header** — the hosting platform already knows where the request came from and says so
in a header.

**The port's input is a bag of headers, not a request.** That is the whole design in one
sentence, and everything else follows from it:

- The adapter can do **nothing but read a header**. No database lookup, no vendor call,
  no `request` object to poke at. The work item says exactly this: "The real adapter
  only reads a header. It does no database lookup and calls no vendor."
- The code **does not depend on the host** (AD-1). A `request` carries the host's
  session machinery, the host's middleware and the host's opinions; a mapping of
  headers carries none of that.
- Deciding whether a city is *supported* is **not the port's job**. The adapter does not
  know what the catalog covers — only the application layer does.

Like every other port here, this is an ABC that imports no Django. There is no
dataclass on this one: a city name is a `str`, and there is nothing else to carry.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping


class GeoPort(ABC):
    """Turns a request's headers into a city name, or nothing."""

    @abstractmethod
    def resolve_city(self, headers: Mapping[str, str]) -> str | None:
        """The city the edge says this request came from, or `None`.

        `None` means "the edge did not say" — not "the caller is nowhere". The two are
        the same to the caller, and the difference is not one the port can see.

        The returned city is **untrusted**: it came from a header the caller could have
        written. It is safe to use as a lookup key against a known set of cities; it is
        not safe to interpolate into SQL, into a path, or into a log line.
        """
        ...


__all__ = ["GeoPort"]
