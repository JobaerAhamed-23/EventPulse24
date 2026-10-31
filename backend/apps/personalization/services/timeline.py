"""The Timeline week read — one week, day by day, conflicts decided (FR-32, FR-33).

`GET /api/personal/timeline?week=YYYY-MM-DD` returns one Mon–Sun week in the **user's
timezone**, as seven days, each a time-ordered list of blocks: the user's personal events
and their saved public events, merged, with the conflict indicator already decided.

**The screen draws what it is given.** The per-day bucketing across timezones, the
cross-midnight placement, and the indicator projection are logic, and logic belongs on the
server where it is tested once. The frontend never decides which day an event belongs to —
that is the rule that has to be right across a DST boundary, and a client that guesses it
is a client that guesses it twice.

**The week is a *local* week.** A week is not seven times 24 hours: it is cut at local
midnight in the user's zone, so it is 167 hours across a spring-forward and 169 across a
fall-back. The arithmetic lives in `timeline_days.py`, which is pure — no database, no
clock — so a DST week is testable without a fixture that has to be right twice a year.

**The zone is the digest preference's, falling back to UTC.** The user's calendar is cut
in the zone they told us their days are in. There is no second notion of "the user's
timezone" in this codebase, so the timeline reads the one that exists.

**The query count is constant — five, whatever the number of events.** A read that cost
one query per event would be a read that gets slower exactly when the user's calendar gets
busy. The five are:

1. the user's digest preference (the zone);
2. the user's personal events overlapping the week;
3. the user's saved events overlapping the week;
4. the user's conflict pairs (active + `keep_both`-resolved);
5. the catalog titles and zones for the week's saves — **one batched read**.

**The catalog is read through its published interface** (`get_public_events`), never by a
cross-schema query (AD-2 / AD-3). A user with five saved events costs one round-trip to
the catalog, not five.

**A save whose catalog event has disappeared is still shown.** The save is the user's own
record and its snapshot still has a time, so the block appears — with the snapshot's times
and the user's zone, but **no title**. There is no name to give, so the name is `None` and
the client says "event no longer available" rather than drawing a blank.

**The indicator is decided here, once, in one place.** A block carries the indicator when
it is a side of an **active** pair, or of a pair **resolved with `keep_both`** — because
FR-58 says "Keep both" leaves a permanent, calm reminder on both events. Every other
resolution removes it: the conflict the user was reminded about is gone. A pair closed as
`cleared_by_state_change` never carries it — nobody answered, and the side that caused it
went away.

**The indicator is per day-cell, and it follows the pair's overlap.** The acceptance
criteria say the indicator "fires on the day-cell whose interval contains the overlap" —
and the overlap is between the two *conflicting* events, not the block's own span. So an
event running from Friday 22:00 to Saturday 02:00 that clashes with something on Friday
lights Friday's cell only, while a clash that itself straddles midnight lights both of
its days. The block's own span decides which cells the block appears on; the pair's
overlap decides which of them carry the flag.

**This is a read.** It opens no transaction, writes no audit row, and touches no model
attribute. Every query is scoped to the caller's `user_id`.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID

from django.db.models import Q

from apps.ingestion.services.catalog_read import get_public_events
from apps.personalization.models import ConflictPair, DigestPreference
from apps.personalization.services.personal_events import (
    PersonalEventSnapshot,
    list_personal_events,
)
from apps.personalization.services.saved_events import SavedEventSnapshot, list_saved_events
from apps.personalization.services.timeline_days import (
    DAYS_IN_WEEK,
    days_covered,
    local_date_at,
    overlaps_day,
    week_bounds,
    week_days,
    week_start_for,
)
from shared.constants import DEFAULT_DIGEST_TIMEZONE
from shared.db import PERSONAL


class TimelineBlockKind:
    """The two kinds of thing the Timeline draws.

    **This is a new vocabulary, not `ConflictPair.SideKind`.** The pair's side kinds are
    `personal_event` / `saved_event` — they name *a side of a conflict pair*, and they say
    which table the id points at. A timeline block's kind says *what the block is*, and the
    block a saved event produces is a **public** block: it carries the catalog event's id,
    because that is the id the screen routes to (`/events/:id`), and it is labelled
    "Public event" on screen.

    The two sets answer different questions, so they stay separate. Conflating them would
    put a pair-side name on a block the screen renders.
    """

    PERSONAL = "personal"
    PUBLIC = "public"


@dataclass(frozen=True)
class TimelineBlock:
    """One block on one day of the Timeline.

    `id` is the id the screen acts on: the personal event's id for a personal block, and
    the **catalog** event's id for a public one — so the screen can route to
    `/events/:id` without knowing which table the id came from.

    `name` is None when the catalog no longer holds a saved event. The block is still
    shown (the save is the user's own record, and its snapshot still has a time), but
    there is no title to show.

    `start_time_tz` is the **event's own zone** — the personal event's, or the catalog
    event's for a public block. That is not the same as the zone the days are cut in: a
    public event in Berlin, shown to a user in Los Angeles, is on a different Los Angeles
    day than its own clock suggests. The block carries both, so the screen can label it
    either way.
    """

    kind: str
    id: UUID
    name: str | None
    start_time_utc: datetime
    end_time_utc: datetime | None
    start_time_tz: str
    conflict: bool


@dataclass(frozen=True)
class TimelineDay:
    """One local day, with its blocks in time order."""

    date: date
    blocks: tuple[TimelineBlock, ...]


@dataclass(frozen=True)
class TimelineWeek:
    """One Mon–Sun week, in the user's timezone."""

    week_start: date
    week_end: date
    timezone: str
    days: tuple[TimelineDay, ...]


def _read_zone(user_id: UUID) -> str:
    """The user's timezone: the digest preference's, or UTC.

    **The same rule the digest read and the composition use**, in one place for the
    Timeline. Three services each inline the same two-line idiom; the *rule* ("the
    preference's zone, else UTC") is what has to be stated once, and this is that
    statement. The other three copies are left alone — refactoring them is not this work
    item's job, and they are readers of one rule rather than three rules.

    An unknown zone name is not rejected here: `timeline_days._zone` falls back to UTC
    rather than raising, because the zone is validated at write time by onboarding, and a
    hand-edited name must not take the user's timeline away.
    """
    preference = (
        DigestPreference.objects.using(PERSONAL).filter(user_id=user_id).order_by("id").last()
    )
    return preference.timezone if preference else DEFAULT_DIGEST_TIMEZONE


@dataclass(frozen=True)
class _ConflictWindow:
    """The window a conflict pair occupies — the overlap of its two sides.

    **This is the pair's overlap, not the event's own span.** The AC says the indicator
    "fires on the day-cell whose interval contains the overlap" — and the overlap is
    between the two *conflicting* events. An event that runs Friday 22:00 to Saturday 02:00
    but clashes with something on Friday and nothing on Saturday lights Friday's cell
    only.

    The window is the intersection of the two sides' intervals:
    `[max(start_a, start_b), min(end_a, end_b))`. An open-ended side has no end, so the
    window's end is the other side's end — or unbounded, if both are open-ended.

    **A duplicate pair has no time overlap.** Its two sides are the *same event* twice —
    the same name, with starts within 24 hours. The window is then the span of the two
    sides together, so the indicator lands on the day the duplicate actually sits rather
    than on a day neither side touches.
    """

    start_utc: datetime
    end_utc: datetime | None


def _side_window(
    *,
    start_utc: datetime,
    end_utc: datetime | None,
    other_start_utc: datetime,
    other_end_utc: datetime | None,
    kind: str,
) -> _ConflictWindow:
    """The window a pair occupies, from the two sides' times.

    A **time** pair's window is the intersection of the two intervals — the time they
    genuinely share.

    A **duplicate** pair's sides are the same event twice, so there is nothing to
    intersect: the window is the span from the earlier start to the later end, which is
    where the duplicate sits on the calendar.
    """
    if kind == ConflictPair.Kind.TIME:
        start = max(start_utc, other_start_utc)
        ends = [end for end in (end_utc, other_end_utc) if end is not None]
        end = min(ends) if ends else None
    else:
        start = min(start_utc, other_start_utc)
        ends = [end for end in (end_utc, other_end_utc) if end is not None]
        end = max(ends) if ends else None
    return _ConflictWindow(start_utc=start, end_utc=end)


def _conflicted_sides(
    *,
    user_id: UUID,
    personal_events: list[PersonalEventSnapshot],
    saved_events: list[SavedEventSnapshot],
) -> tuple[dict[UUID, _ConflictWindow], dict[UUID, _ConflictWindow]]:
    """The conflicted sides and the window each pair occupies, in one query.

    Two maps, keyed by the side's own id: the personal event's id on one, and the **save
    row's** id on the other. The block a save produces carries the *catalog* event's id, so
    the bridge between the two is the save row — and it is built below, where the week's
    saves are in hand.

    **The rule, in one place.** A side carries the indicator when its pair is **active**,
    or when the pair was **resolved with `keep_both`**. Every other resolution removes it
    — `edit_new`, `delete_new`, `update_existing` and `skip_public` each mean the
    conflict is dealt with, so the reminder goes. `cleared_by_state_change` never carries
    it: nobody answered, and the side that caused it went away.

    The two existing projections — `digest_read._conflicted_card_ids` and
    `digest_candidates.list_conflict_pairs` — are **active-only**, which is correct for a
    digest card (a card shows *open* conflicts) but wrong here: FR-58 says "Keep both"
    leaves a permanent reminder. So the Timeline has its own projection, and this docstring
    is where its rule lives.

    **The sides' times come from the week's own reads.** The week already holds every
    personal event and every save that could put a block on a cell, and the side lookup
    reuses those lists rather than reading the tables again — so the query count does not
    grow with the number of pairs.

    A pair whose side is **not** in the week has no block on any of the week's cells, so
    its window is not computed: a conflict entirely outside the week cannot light a cell
    inside it. And a pair whose other side has gone is not the user's standing reminder
    either, so it is skipped as well.
    """
    personal_windows: dict[UUID, _ConflictWindow] = {}
    saved_windows: dict[UUID, _ConflictWindow] = {}

    pairs = (
        ConflictPair.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .filter(
            # An active pair carries the indicator on both sides.
            Q(status=ConflictPair.Status.ACTIVE)
            # A pair resolved with `keep_both` does too — the permanent reminder.
            | Q(
                status=ConflictPair.Status.RESOLVED,
                resolution=ConflictPair.Resolution.KEEP_BOTH,
            )
        )
    )

    personal_times = {event.id: (event.start_utc, event.end_utc) for event in personal_events}
    saved_times = {saved.id: (saved.start_utc, saved.end_utc) for saved in saved_events}

    def times_for(side_kind: str, side_id: UUID) -> tuple[datetime, datetime | None] | None:
        """The side's own times, or None when the side is not on this week."""
        if side_kind == ConflictPair.SideKind.PERSONAL_EVENT:
            return personal_times.get(side_id)
        return saved_times.get(side_id)

    for pair in pairs:
        sides = (
            (pair.left_kind, pair.left_id),
            (pair.right_kind, pair.right_id),
        )
        left_times = times_for(*sides[0])
        right_times = times_for(*sides[1])
        if left_times is None or right_times is None:
            # One of the sides is not on this week. There is no window to place, and the
            # side that is here is not flagged — a pair whose other side is gone (or is
            # outside the week) is not the user's standing reminder on this week's cells.
            continue

        window = _side_window(
            start_utc=left_times[0],
            end_utc=left_times[1],
            other_start_utc=right_times[0],
            other_end_utc=right_times[1],
            kind=pair.kind,
        )
        for side_kind, side_id in sides:
            if side_kind == ConflictPair.SideKind.PERSONAL_EVENT:
                personal_windows[side_id] = window
            else:
                saved_windows[side_id] = window

    return personal_windows, saved_windows


def _block_sort_key(block: TimelineBlock) -> tuple[datetime, str]:
    """Blocks are ordered by start, then by id.

    The id breaks a tie, so the order is total: two blocks starting at the same instant
    always come out in the same order, and the client does not have to sort them itself.
    """
    return (block.start_time_utc, str(block.id))


def read_timeline_week(
    *,
    user_id: UUID,
    day: date | None = None,
    now: datetime,
) -> TimelineWeek:
    """The user's week, as seven days of blocks.

    `day` selects the week: any date in the wanted week names it, and the response names
    that week's Monday and Sunday. With no `day`, the week is the **current** week in the
    user's own zone — not the server's, which is the whole point of a local week.

    **Seven days, always.** Even an empty week returns seven day cells with empty block
    lists: the screen draws seven columns, and it should not have to know whether the week
    has anything in it.

    **An event is placed on the day its local start falls on, and on every later day it
    covers.** A block running from Friday 22:00 to Saturday 02:00 appears on Friday *and*
    Saturday. The same rule decides the indicator: it is tested against **each day's own
    interval**, so a conflict that falls on Tuesday lights Tuesday's cell even if the event
    also spans Wednesday.

    The blocks are the user's personal events and their saved public events, merged. The
    query count is constant — five, whatever the number of events.
    """
    zone_name = _read_zone(user_id)

    if day is None:
        # The current week, in the user's zone. The server's date is not the user's date,
        # and which Monday is "this week" depends on the zone.
        day = local_date_at(instant=now, zone_name=zone_name)

    monday = week_start_for(day=day, zone_name=zone_name)
    sunday = monday + timedelta(days=DAYS_IN_WEEK - 1)
    window_start, window_end = week_bounds(day=day, zone_name=zone_name)

    # --- the reads (four queries; the fifth is the catalog batch below) -------------
    personal_events = list_personal_events(
        user_id=user_id,
        overlaps_after=window_start,
        overlaps_before=window_end,
    )
    saved_events = list_saved_events(
        user_id=user_id,
        overlaps_after=window_start,
        overlaps_before=window_end,
    )
    conflicted_personal, conflicted_saved = _conflicted_sides(
        user_id=user_id,
        personal_events=personal_events,
        saved_events=saved_events,
    )

    # One batched catalog read for every save in the week. The ids are the catalog's; the
    # query runs against the `catalog` alias and hands back plain data, so the wall holds.
    catalog_event_ids = {saved.event_id for saved in saved_events}
    public_events = get_public_events(event_ids=catalog_event_ids)

    days = week_days(day=day, zone_name=zone_name)

    blocks_by_day: dict[date, list[TimelineBlock]] = {local_day: [] for local_day in days}

    def add_block(
        block: TimelineBlock,
        *,
        conflict_window: _ConflictWindow | None,
    ) -> None:
        """Place a block on every local day it covers, with the day's own indicator.

        **The block's days come from the block's own span.** A block running from Friday
        22:00 to Saturday 02:00 appears on Friday *and* Saturday — the FR-33 (e) rule, and
        the screen's own shape.

        **The indicator comes from the pair's overlap.** The AC says the indicator "fires
        on the day-cell whose interval contains the overlap" — and the overlap is between
        the two *conflicting* events, not the block's own span. So a block that spans
        Friday and Saturday but clashes only on Saturday lights Saturday's cell, and a
        clash that itself straddles midnight lights both of its days.
        """
        covered = days_covered(
            start_utc=block.start_time_utc,
            end_utc=block.end_time_utc,
            zone_name=zone_name,
            limit=sunday,
        )
        for covered_day in covered:
            if covered_day not in blocks_by_day:
                continue
            # The overlap is tested against **this day's** interval. A clash that falls
            # inside the day lights that day, and a clash that runs across midnight
            # lights both days it runs across.
            lights = conflict_window is not None and overlaps_day(
                start_utc=conflict_window.start_utc,
                end_utc=conflict_window.end_utc,
                local_date=covered_day,
                zone_name=zone_name,
            )
            blocks_by_day[covered_day].append(
                TimelineBlock(
                    kind=block.kind,
                    id=block.id,
                    name=block.name,
                    start_time_utc=block.start_time_utc,
                    end_time_utc=block.end_time_utc,
                    start_time_tz=block.start_time_tz,
                    conflict=lights,
                )
            )

    for event in personal_events:
        add_block(
            TimelineBlock(
                kind=TimelineBlockKind.PERSONAL,
                id=event.id,
                name=event.name,
                start_time_utc=event.start_utc,
                end_time_utc=event.end_utc,
                start_time_tz=event.start_time_tz,
                conflict=False,
            ),
            conflict_window=conflicted_personal.get(event.id),
        )

    for saved in saved_events:
        public = public_events.get(saved.event_id)
        add_block(
            TimelineBlock(
                kind=TimelineBlockKind.PUBLIC,
                # The **catalog** event's id, so the screen routes to `/events/:id`.
                id=saved.event_id,
                # No title when the catalog no longer holds the event. The save is still
                # the user's, and its snapshot still has a time, so the block is still shown.
                name=public.title if public else None,
                start_time_utc=saved.start_utc,
                end_time_utc=saved.end_utc,
                # The catalog event's own zone when it is still there; the user's zone
                # otherwise, because the snapshot's display zone is then unknown.
                start_time_tz=public.start_time_tz if public else zone_name,
                conflict=False,
            ),
            conflict_window=conflicted_saved.get(saved.id),
        )

    return TimelineWeek(
        week_start=monday,
        week_end=sunday,
        timezone=zone_name,
        days=tuple(
            TimelineDay(
                date=local_day,
                blocks=tuple(sorted(blocks_by_day[local_day], key=_block_sort_key)),
            )
            for local_day in days
        ),
    )


__all__ = [
    "TimelineBlock",
    "TimelineBlockKind",
    "TimelineDay",
    "TimelineWeek",
    "read_timeline_week",
]
