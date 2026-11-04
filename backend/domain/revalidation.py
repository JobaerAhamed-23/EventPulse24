"""Which public pages a change to an Event makes stale (FR-27, FR-28). Stdlib only.

The signal already exists: `Event.LIFECYCLE_FIELDS` names the columns whose change means "the
public page's facts moved", and `catalog.guard_event_write` requires `event_version + 1` on
every change to them. This module turns such a change into **the concrete list of paths that
must be rebuilt**.

**The rules live here, and only here.** The backend computes the paths and delivers them; the
frontend revalidates what it is given and infers nothing. A rule that existed on both sides
would be two rules, and one of them would eventually be the stale one.

**The paths are the deliverable, so they are computed once, at enqueue time.** By the time a
signal reaches the frontend it is already a list of strings, and the frontend's route handler
does no lookup and draws no conclusion. A stale path computed at delivery time is computed from
a row that has since moved again; a path computed at enqueue time names the page that was
stale when the change happened, which is the page that must be rebuilt.

**An event's own page is `/events/<slug>`; a city's page is `/events-in-<city-slug>`.** These
are the conventions the public-page work items build against. They are named here, in one
place, because a URL convention that exists in two places is one that will differ in two places.
"""

from dataclasses import dataclass

# The public page of one event.
EVENT_PATH_PREFIX = "/events/"
# The public page of one city (FR-27: `/events-in-{city-slug}`).
CITY_PATH_PREFIX = "/events-in-"


@dataclass(frozen=True)
class EventPaths:
    """What the signal needs to know about one event to name its pages.

    **The three cities are not the same kind of thing, and the difference is the whole
    point of the cascade.** `city_slug` is where the event is *now*. `previous_city_slug` is
    where it *was*, and it is only knowable from the state change's `before` facts — a
    venue fingerprint is a hash and cannot be reversed to a city. An event that moved from
    Brooklyn to Queens must revalidate **both** city pages: the new one's listing has gained
    it, and the old one's has lost it. Revalidating only the new one leaves a listing that
    still shows an event in a city it is no longer in.
    """

    slug: str
    city_slug: str = ""
    previous_city_slug: str = ""
    #: True while the event is publicly listed (published, and not superseded).
    is_public: bool = True
    #: True once the event has been superseded — its page must stop serving.
    is_superseded: bool = False

    @property
    def event_path(self) -> str:
        """The event's own page."""
        return f"{EVENT_PATH_PREFIX}{self.slug}"

    def city_paths(self) -> tuple[str, ...]:
        """Every city page this event's change touches, in a stable order.

        **The previous city comes first**, so a list built from two events' paths has a
        deterministic order. Deduplicated, because an event that moved within the same city
        names the same city twice and a path repeated in the payload is a path rebuilt twice.
        """
        seen: list[str] = []
        for slug in (self.previous_city_slug, self.city_slug):
            if not slug:
                continue
            path = f"{CITY_PATH_PREFIX}{slug}"
            if path not in seen:
                seen.append(path)
        return tuple(seen)


def paths_for_event(
    *,
    slug: str,
    city_slug: str = "",
    previous_city_slug: str = "",
    is_public: bool = True,
    is_superseded: bool = False,
) -> tuple[str, ...]:
    """Every path whose cached copy may now be wrong, for one changed event.

    **The event's own page is always in the list**, whether the event is public or not. A
    published event that has just been unpublished still has a cached page, and that cached
    page is now serving content that is no longer public — so the path must be rebuilt, and
    the rebuild reads the event's own public read, which refuses it. The result is a 404
    where a 200 was cached, which is the correct outcome. **Removing the path from the
    signal would leave the stale page live**, and that is the failure this whole item
    exists to prevent.

    **A city page is in the list when the event is or was listed in it.** The city listing
    shows published, non-superseded events, so an event that has just become non-public
    must leave the listing — and the city page is the page that lists it.

    **The superseded case.** A superseded event's page must stop serving, so its own path
    is revalidated like any other. The successor has its own slug and its own page, which
    has never been built and so has nothing stale to fix.
    """
    facts = EventPaths(
        slug=slug,
        city_slug=city_slug,
        previous_city_slug=previous_city_slug,
        is_public=is_public,
        is_superseded=is_superseded,
    )
    paths = [facts.event_path]
    if facts.is_public or facts.is_superseded:
        paths.extend(facts.city_paths())
    return tuple(paths)


__all__ = [
    "CITY_PATH_PREFIX",
    "EVENT_PATH_PREFIX",
    "EventPaths",
    "paths_for_event",
]
