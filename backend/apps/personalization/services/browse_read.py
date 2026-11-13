"""The Browse surface's read: one ranked pool of the user's city, this week (FR-26, FR-48).

**Browse ranks with the Relevance Pulse, never the Event Fit.** AD-10 names two explanations
and forbids substituting one for the other: the **Event Fit** is per `(event, city)`, lives on
`catalog`, and is computed blind to who is looking — the explanation for a stranger. The
**Relevance Pulse** is per user. Browse is an authed surface whose first section head reads
*"3 worth your attention today"* — *your* — so its cards carry the personal explanation. A
card ranked by Event Fit under that heading would be a stranger's score wearing the personal
one's clothes, one click from the Digest that shows the real thing in the same card
vocabulary. That is the trust-collapse AD-10 calls company-ending, and the import contract
("personalization never reaches the Event Fit") rejects the code before it can ship.

**The wall (AD-3).** Two reads against two aliases, joined here in Python. The public facts
arrive from `apps.ingestion.services.catalog_read` as frozen dataclasses, so no model
reference crosses; the saved rows are read from `personal`. Nothing joins the two in SQL and
no transaction spans them — the same shape `digest_candidates.py` documents.

**One pool, ranked once, sliced per request.** `list_public_candidates` applies FR-14's
staleness bound *in Python*, after the SQL has narrowed the set, because the bound is
per-source and a database cannot compare a column against another column times a multiplier.
That makes SQL `OFFSET` unsound here: a second page would re-run the fetch, drop a different
set of stale rows, and could show an event already seen or skip one entirely. So Browse
fetches one bounded pool, ranks it, and slices *that* — sound by construction, because there
is one list in one order.

**The pool is capped at `MAX_CANDIDATE_POOL_SIZE` (200), and that is a real limit.** A city
with more than 200 eligible events in its seven-day window will report 200 and page to 200.
The design's own mockup shows 147 in a week, so there is room — but if this ever binds, the
answer is a decision about what Browse is for, not a bigger constant. `total` is the size of
this pool and nothing else: it is exactly what the user can reach. A `COUNT(*)` would count
rows the staleness filter then drops, advertising a number no amount of scrolling arrives at.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from apps.ingestion.services.catalog_read import (
    MAX_CANDIDATE_POOL_SIZE,
    PublicEventCandidate,
    list_public_candidates,
)
from apps.personalization.models import DigestPreference, Interest, SavedEvent
from apps.personalization.services.save_cap import SaveQuota, read_save_quota
from domain.lifecycle import EventStatus
from domain.ranking import (
    RankingInputs,
    apply_hysteresis,
    city_band,
    interest_overlap,
    recency_band,
    relevance_score,
    why_this_tags,
)
from shared.db import PERSONAL

#: How many days past today the window reaches. "Tonight + 7 days" (`EXPERIENCE.md` §336).
BROWSE_WINDOW_DAYS = 7

#: How many cards the first, attention-tier section holds. The section head says "3 worth
#: your attention today" and the number is in the copy, so it is a constant and not a
#: parameter — a tier of four would make the heading false.
BROWSE_TIER_1_SIZE = 3

#: The soft cap per page (`EXPERIENCE.md` §356). Past it the surface loads the next chunk in
#: place; there is no pagination chrome.
BROWSE_PAGE_SIZE = 24


@dataclass(frozen=True)
class BrowseCard:
    """One Browse card: the public facts, the personal explanation, and the save state."""

    event_id: UUID
    slug: str
    title: str
    canonical_url: str
    start_time_utc: datetime
    start_time_tz: str
    end_time_utc: datetime | None
    venue_name: str | None
    venue_city: str | None
    status: str
    source_badge: str
    tz_review_pending: bool
    #: The Why-this Tags — the **personal** explanation, from the same inputs the score used.
    tags: tuple[str, ...]
    #: The Confidence Pulse bucket (FR-22), 1-3.
    confidence: int
    #: `"must_know"` on at most one card per response; `"public"` on the rest.
    stripe: str
    is_saved: bool


@dataclass(frozen=True)
class BrowsePage:
    """One page of Browse, plus everything the surface's chrome needs to render itself."""

    city: str
    timezone: str
    window_from: datetime
    window_to: datetime
    #: The size of the ranked pool — what the user can actually page to, not a `COUNT(*)`.
    total: int
    #: The index at which tier 2 ("More this week") begins. The **server** names the tiers so
    #: the rule lives in one place and cannot drift from the Digest's idea of "worth your
    #: attention".
    tier_2_starts_at: int
    quota: SaveQuota
    cards: tuple[BrowseCard, ...]
    has_more: bool
    #: True when the user has no city set. The surface shows the same quiet empty state it
    #: shows for a city with nothing on — with "Change city" as the way out — rather than an
    #: error, and rather than guessing a city the user never chose.
    city_missing: bool = False


def _read_preference(user_id: UUID) -> DigestPreference | None:
    """The user's digest preference, if they have one.

    The same read `digest_composition.py` makes, and for the same reason: Browse needs the
    city and the zone, and `digest_preferences.py` is a command module whose own reader is
    private to it. **This is deliberately the digest's city** — one meaning of "your city"
    across both surfaces, which is why the design routes "Change city" to the one place that
    sets it.
    """
    return DigestPreference.objects.using(PERSONAL).filter(user_id=user_id).order_by("id").last()


def _read_interest_keys(user_id: UUID) -> tuple[str, ...]:
    """The chips the user picked at onboarding, in the order they picked them.

    Ordered by `id`, a UUIDv7, so the id **is** the creation time.
    """
    rows = (
        Interest.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .order_by("id")
        .values_list("chip_key", flat=True)
    )
    return tuple(rows)


def _inputs_for(
    *,
    candidate: PublicEventCandidate,
    user_chip_keys: tuple[str, ...],
    user_city: str,
    now: datetime,
) -> RankingInputs:
    """The five Relevance Pulse inputs for one public candidate.

    **Built the same way `digest_composition._inputs_for_public` builds them**, from the same
    public `domain.ranking` functions. `tests/personalization/test_browse_read.py` pins that
    the two agree for the same candidate: if they ever diverge, the Digest and Browse would
    explain the same event differently, which is the drift AD-10 exists to prevent.

    **The user's country is empty**, as it is for the digest: `DigestPreference` holds a city
    and a zone and no country, and the country band is a half-credit consolation for
    "different city, same country".
    """
    return RankingInputs(
        interest_overlap=interest_overlap(
            event_chip_keys=candidate.chip_keys,
            user_chip_keys=user_chip_keys,
        ),
        recency=recency_band(start_time_utc=candidate.start_time_utc, now=now),
        city_match=city_band(
            event_city=candidate.venue_city or "",
            event_country=candidate.venue_country_code or "",
            user_city=user_city,
            user_country="",
        ),
        confidence=candidate.extraction_confidence,
        source_reliability=candidate.source_reliability,
    )


def _window(*, now: datetime, zone: str) -> tuple[datetime, datetime]:
    """Tonight through +7 days, cut in the **user's** zone and returned as instants.

    The window is a local idea — "this week" means the user's week — so the far edge is the
    end of the seventh local day, not `now + 168h`. Cutting it in UTC would move the boundary
    by the user's offset and put a late event on the wrong side of it.
    """
    zoneinfo = ZoneInfo(zone)
    local_now = now.astimezone(zoneinfo)
    last_day = (local_now + timedelta(days=BROWSE_WINDOW_DAYS)).date()
    # Midnight after the last day, in the user's zone: an 11pm event on day 7 is in, and a
    # 1am event on day 8 is out.
    local_end = datetime.combine(
        last_day + timedelta(days=1),
        datetime.min.time(),
        tzinfo=zoneinfo,
    )
    return now, local_end.astimezone(now.tzinfo)


def _saved_event_ids(*, user_id: UUID, event_ids: list[UUID]) -> set[UUID]:
    """Which of these events this user has already saved — **one** query.

    An `IN` clause rather than one lookup per card, for the reason `get_public_events` gives
    about the same shape: a page of 24 cards would otherwise cost 24 round-trips, times every
    user, on a surface people open repeatedly.
    """
    if not event_ids:
        return set()
    rows = (
        SavedEvent.objects.using(PERSONAL)
        .filter(user_id=user_id, event_id__in=event_ids)
        .values_list("event_id", flat=True)
    )
    return set(rows)


def _stripe_for(*, candidate: PublicEventCandidate) -> str:
    """Whether this card earns the amber must-know stripe before the per-page cap is applied.

    A cancelled or postponed event is the must-know case: it is still in the user's city and
    still on their list of things to know about, and hiding it would conceal the change
    rather than report it. Everything else is the slate public stripe. **Two colours only** —
    Amendment A-12 drops the discovery stripe, because three would be the category-colour
    flood the anti-pattern list bans.
    """
    if candidate.status in (EventStatus.CANCELLED.value, EventStatus.POSTPONED.value):
        return "must_know"
    return "public"


def read_browse_page(
    *,
    user_id: UUID,
    now: datetime,
    offset: int = 0,
    limit: int = BROWSE_PAGE_SIZE,
) -> BrowsePage:
    """One page of Browse for this user.

    Raises nothing for an empty result: a user with no city, a city with nothing on, and an
    offset past the end are all **answers**, not errors. The surface tells them apart by
    `city_missing` and `total`, and distinguishes all three from a failure by the fact that a
    failure is not a 200 at all.
    """
    offset = max(0, offset)
    limit = max(1, min(limit, BROWSE_PAGE_SIZE))

    preference = _read_preference(user_id)
    city = (preference.city or "").strip() if preference else ""
    zone = (preference.timezone if preference and preference.timezone else "UTC") or "UTC"
    quota = read_save_quota(user_id=user_id)

    window_from, window_to = _window(now=now, zone=zone)

    if not city:
        # Onboarding can be skipped, so a user may genuinely have no city. Browse shows the
        # designed quiet empty state with "Change city" rather than guessing one from geo-IP:
        # a city the user never chose is a worse answer than no city, because "Change city"
        # would then be correcting our guess instead of setting their preference.
        return BrowsePage(
            city="",
            timezone=zone,
            window_from=window_from,
            window_to=window_to,
            total=0,
            tier_2_starts_at=0,
            quota=quota,
            cards=(),
            has_more=False,
            city_missing=True,
        )

    candidates = list_public_candidates(
        now=now,
        city=city,
        limit=MAX_CANDIDATE_POOL_SIZE,
        starts_before=window_to,
    )
    user_chip_keys = _read_interest_keys(user_id)
    saved_ids = _saved_event_ids(
        user_id=user_id,
        event_ids=[candidate.id for candidate in candidates],
    )

    scored: list[tuple[Decimal, datetime, UUID, PublicEventCandidate, RankingInputs]] = []
    for candidate in candidates:
        inputs = _inputs_for(
            candidate=candidate,
            user_chip_keys=user_chip_keys,
            user_city=city,
            now=now,
        )
        scored.append(
            (relevance_score(inputs), candidate.start_time_utc, candidate.id, candidate, inputs)
        )

    # **A total order, or paging lies.** Score descending, then the sooner event, then the id.
    # Without the id the order is only partial, and two events with the same score and start
    # could swap places between one page and the next — showing one twice and losing the other.
    scored.sort(key=lambda row: (-row[0], row[1], row[2]))

    total = len(scored)
    page = scored[offset : offset + limit]

    # **At most one must-know card per response.** The <10% rule is enforced here rather than
    # in the client because a client cap is per page: two pages would each show "their one",
    # and the surface as a whole would flood.
    must_know_used = False
    cards: list[BrowseCard] = []
    for score, _start, _id, candidate, inputs in page:
        stripe = _stripe_for(candidate=candidate)
        if stripe == "must_know":
            if must_know_used:
                stripe = "public"
            else:
                must_know_used = True
        is_saved = candidate.id in saved_ids
        cards.append(
            BrowseCard(
                event_id=candidate.id,
                slug=candidate.slug,
                title=candidate.title,
                canonical_url=candidate.canonical_url,
                start_time_utc=candidate.start_time_utc,
                start_time_tz=candidate.start_time_tz,
                end_time_utc=candidate.end_time_utc,
                venue_name=candidate.venue_name,
                venue_city=candidate.venue_city,
                status=candidate.status,
                source_badge=candidate.source_badge,
                tz_review_pending=candidate.tz_review_pending,
                tags=why_this_tags(
                    inputs=inputs,
                    event_chip_keys=candidate.chip_keys,
                    user_chip_keys=user_chip_keys,
                    start_time_utc=candidate.start_time_utc,
                    start_time_tz=candidate.start_time_tz,
                    now=now,
                    is_saved=is_saved,
                ),
                # No previous bucket: Browse has no yesterday to compare against, and
                # `apply_hysteresis` with nothing to compare *is* `score_bucket`. The same
                # call the digest makes, for the same stated reason.
                confidence=apply_hysteresis(
                    previous_bucket=None,
                    previous_score=None,
                    new_score=score,
                ),
                stripe=stripe,
                is_saved=is_saved,
            )
        )

    return BrowsePage(
        city=city,
        timezone=zone,
        window_from=window_from,
        window_to=window_to,
        total=total,
        # Tier 1 is the top three of the **pool**, so it appears only on the first page. A
        # later page is all "More this week", and its boundary is zero.
        tier_2_starts_at=max(0, min(BROWSE_TIER_1_SIZE - offset, len(cards))),
        quota=quota,
        cards=tuple(cards),
        has_more=offset + len(cards) < total,
    )


__all__ = [
    "BROWSE_PAGE_SIZE",
    "BROWSE_TIER_1_SIZE",
    "BROWSE_WINDOW_DAYS",
    "BrowseCard",
    "BrowsePage",
    "read_browse_page",
]
