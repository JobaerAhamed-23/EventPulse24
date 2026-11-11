"""The editorial queue's **read** side (FR-57, AD-14): the facts a reviewer needs.

`review_queue.py` owns the queue's writes and `editorial_review.py` owns the verdicts.
This module owns neither. It is the read an editor's screen is built from, and it hands
over **plain data** — frozen dataclasses, never a model instance — so the surface that
renders it (Django admin) holds no reference to `apps.ingestion.models` and the
`models-ingestion` contract holds without either side knowing about the other's models.

That is the same shape `catalog_read.py` established, and for the same reason: a read that
hands over a row makes every caller a model holder.

---

## Why the queue's metrics are computed here and not in the template

The AC asks for three numbers at the top of the queue — its size, the age of its oldest
open item, and how many items have missed their SLA — and says they are *"the FR-57 metrics
that FR-29's dashboard will later read, computed by an `ingestion` read service, not in the
template"*.

A template cannot compute them. It has no clock and no query. So they live here, and FR-29's
dashboard calls the same function later. **One implementation, two readers** — which is the
whole point of naming a read service instead of computing twice.

---

## The ordering, and where "priority" comes from

The queue is ordered **open items first**, then by **priority**, then by **`due_at`**.

`ReviewItem` has **no priority column**, and that was a decision, not an oversight:
`review-queue-model` did not add one, and `review-intake-and-backfill` D1 explicitly
declined to, because a low-priority item would dilute the very metrics this module
computes. So priority is **derived from the reason** — the one thing every item already
carries — through `shared.constants.REVIEW_PRIORITY`:

| Reason | Priority | Why |
|---|---|---|
| `user_reported` | 0 | A person says something is wrong, and FR-59's 24h SLA is running |
| `source_reliability` | 1 | FR-16's escalation: this source keeps being wrong |
| `in_review` | 2 | The gate caught it; nobody has complained yet |

The derivation happens in the **database**, as a `Case/When`, so the whole queue is one
query rather than one per row.

`due_at` is null for every reason except `user_reported` (the D8 check), so nulls sort
**last** within a priority band. Sorting nulls first would put the items with no deadline
ahead of the ones with one, which is the opposite of what the ordering is for.

---

## What the queue deliberately does not carry

**No reporter identities, and not by policy — by shape.** A `ReviewItem` row has no user
column at all (D4 of `review-queue-model`): a report arrives as a category tally, and the
reporter lives in `personal.EventReport`. So this module *cannot* hand a reviewer a
reporter's id even by accident. There is nothing to hand over.

**No recomputed score here.** FR-16's score is computed and stored by
`reliability-recompute-and-escalation`, in `apps/ingestion/services/reliability.py`. A
source item therefore shows the **observations the score is computed from** — the
`SourceObservation` history — labelled as exactly that. Computing a live score here would
be a second implementation of another work item's job, and two implementations of one score
are two truths. The *stored* score is read from `Source.reliability_score`, which the
recompute writes in the same transaction as the row it computed.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from django.db.models import Case, Count, F, IntegerField, QuerySet, Value, When

from apps.ingestion.models import ReviewItem, Source, SourceObservation
from apps.ingestion.services.source_badges import source_badge_for_type
from shared.constants import REVIEW_PRIORITY
from shared.db import CATALOG


@dataclass(frozen=True)
class ReportTally:
    """One report category's count. **A count, never a list of people.**"""

    category: str
    count: int


@dataclass(frozen=True)
class ReviewItemRow:
    """One queue entry, as plain data.

    Deliberately not the model: the surface that renders this holds no reference to
    `apps.ingestion.models`, and the `models-ingestion` contract holds without either side
    importing the other.
    """

    id: UUID
    reason: str
    status: str
    resolution: str
    #: The derived priority (see the module docstring). Lower is more urgent.
    priority: int
    raised_at: datetime
    last_raised_at: datetime
    #: The FR-59 deadline, for a `user_reported` item. None otherwise.
    due_at: datetime | None
    #: Whether this item is past its deadline. **False for a non-report item**, which has
    #: no deadline at all — "overdue" is not a thing that can be true of it.
    sla_breached: bool
    #: The four report tallies, in a fixed order. Empty for a non-report item.
    tallies: tuple[ReportTally, ...]
    #: The total of the tallies — the number of people who reported this.
    report_count: int
    #: The event this is about, or None for a source item.
    event_id: UUID | None
    event_title: str | None
    event_start_time_utc: datetime | None
    event_version: int | None
    #: The source this is about — always present, for both kinds of item.
    source_id: UUID | None
    source_name: str | None
    #: The Source Badge type (EXPERIENCE.md §4). The server names the type.
    source_badge: str | None


@dataclass(frozen=True)
class QueueSummary:
    """The three FR-57 numbers, read at one instant.

    **These are the metrics FR-29's dashboard will read.** It calls `queue_summary` rather
    than computing its own, so the dashboard and this queue can never disagree about how
    big the queue is.
    """

    #: How many items are open. Resolved items are history and are not counted.
    queue_size: int
    #: How long the oldest open item has been waiting. None when the queue is empty.
    oldest_open_age: timedelta | None
    #: How many open items are past their deadline. Only a `user_reported` item has one.
    sla_breaches: int

    def oldest_open_age_parts(self) -> tuple[int, int, int] | None:
        """The oldest open item's age as (days, hours, minutes), or None for an empty queue.

        **The formatting lives here, not in the template.** A Django template has no
        arithmetic — `{{ age.seconds // 3600 }}` is a syntax error — so a template that
        wanted to render the age would have to be handed the parts. Reading them from the
        service keeps one implementation for the admin's page and FR-29's dashboard.
        """
        if self.oldest_open_age is None:
            return None
        total = int(self.oldest_open_age.total_seconds())
        return total // 86400, (total % 86400) // 3600, (total % 3600) // 60


@dataclass(frozen=True)
class SourceObservationRow:
    """One verdict in a source's history.

    **The input side of FR-16's score, not the score.** `reliability-recompute-and-escalation`
    reads these to compute it; until it ships, the reviewer sees the facts and the score is
    simply not there yet.
    """

    kind: str
    occurred_at: datetime
    #: The event the verdict was about, when there was one.
    event_id: UUID | None
    event_title: str | None


@dataclass(frozen=True)
class ReviewItemDetail:
    """Everything one item's page shows.

    **For an event item**, the event's current facts — the things an editor decides on.
    **For a source item**, the source's facts and its verdict history, in place of an
    event's.
    """

    id: UUID
    reason: str
    status: str
    resolution: str
    raised_at: datetime
    last_raised_at: datetime
    due_at: datetime | None
    sla_breached: bool
    tallies: tuple[ReportTally, ...]
    report_count: int
    resolved_at: datetime | None
    resolved_by_kind: str
    resolved_by_label: str
    # The event's facts, for an event item.
    event_id: UUID | None
    event_title: str | None
    event_start_time_utc: datetime | None
    event_end_time_utc: datetime | None
    event_start_time_tz: str | None
    event_status: str | None
    event_publication_status: str | None
    event_venue_name: str | None
    event_version: int | None
    # The source's facts, for both kinds of item.
    source_id: UUID | None
    source_name: str | None
    source_type: str | None
    source_badge: str | None
    source_acquisition_method: str | None
    source_status: str | None
    source_url: str | None
    source_city: str | None
    #: The source's verdict history. Empty for an event item.
    observations: tuple[SourceObservationRow, ...]


def priority_expression() -> Case:
    """The reason → priority mapping, as one SQL expression.

    **Public, because the admin's own ordering needs it.** The admin's `get_queryset`
    sorts by the same priority the read service sorts by — two orderings that disagreed
    would put the rows in one order and the summary in another, and the page would then
    describe a queue that does not exist.

    The `default` gives an unknown reason the **lowest** priority, so a reason added later
    without a `REVIEW_PRIORITY` entry sorts last among the open items rather than first.
    A new kind of review should be looked at, but not before the three the team already
    knows about — and the safe default for an unranked thing is "not the most urgent".
    """
    whens = [
        When(reason=reason, then=Value(priority))
        for reason, priority in sorted(REVIEW_PRIORITY.items(), key=lambda pair: pair[1])
    ]
    return Case(*whens, default=Value(len(REVIEW_PRIORITY)), output_field=IntegerField())


def ordered(queryset: QuerySet) -> QuerySet:
    """Open first, then priority, then the deadline, then the oldest.

    **`due_at` ascending with nulls last.** Only `user_reported` carries a deadline (D8),
    so a null is "no deadline" rather than "the most urgent deadline".

    **Public, because the admin's own list needs it.** The admin's changelist sorts by
    the same rule this service does, and it sorts by it *here* rather than by writing the
    same four `order_by` terms a second time. Two orderings that drifted apart would put
    the rows in one order and the summary in another, and the page would then describe a
    queue that does not exist.
    """
    return queryset.order_by(
        F("status").asc(nulls_last=True),  # "open" < "resolved" by value; explicit anyway
        priority_expression().asc(),
        F("due_at").asc(nulls_last=True),
        F("raised_at").asc(),
    )


def _tallies(item: ReviewItem) -> tuple[ReportTally, ...]:
    """The four report tallies, in the model's own order.

    **Counts only.** The `ReviewItem` row holds no user column (D4), so there is no
    reporter to expose here even in principle.
    """
    return tuple(
        ReportTally(category=category, count=getattr(item, column))
        for category, column in ReviewItem.REPORT_FIELDS.items()
    )


def _sla_breached(item: ReviewItem, now: datetime) -> bool:
    """Whether this item is past its deadline.

    **Only a `user_reported` item can be overdue.** The other reasons carry no deadline
    (D8), and "overdue" is not a thing that can be true of an item that was never due.
    """
    if item.reason != ReviewItem.Reason.USER_REPORTED or item.due_at is None:
        return False
    return item.due_at < now


def item_is_past_its_sla(item: ReviewItem, *, now: datetime | None = None) -> bool:
    """Whether one item is past its deadline — **the rule, once, for everyone**.

    **Public because the admin's list column needs it.** The summary's `sla_breaches`
    count and the list's per-row mark are two readings of one fact, so they must come
    from one implementation. A copy of this rule in the admin could disagree with the
    count — an item marked overdue on its row and missing from the total — and the page
    would then contradict itself.

    `now` defaults to the current instant, so a caller that does not care which instant
    it reads at does not have to say.
    """
    return _sla_breached(item, now or datetime.now(UTC))


def _source_of(item: ReviewItem) -> Source | None:
    """The source an item is about: its own, or its event's.

    **D1: a target is an Event *or* a Source, never both.** An event item leaves `source`
    null — the item names the event, and the event names the source the listing came
    from. So the source an editor is shown for a reported listing is one hop away, and
    reading it from `item.source` alone would show nothing.
    """
    if item.source is not None:
        return item.source
    if item.event is not None:
        return item.event.source
    return None


def _to_row(item: ReviewItem, now: datetime) -> ReviewItemRow:
    source = _source_of(item)
    event = item.event
    return ReviewItemRow(
        id=item.id,
        reason=item.reason,
        status=item.status,
        resolution=item.resolution,
        priority=REVIEW_PRIORITY.get(item.reason, len(REVIEW_PRIORITY)),
        raised_at=item.raised_at,
        last_raised_at=item.last_raised_at,
        due_at=item.due_at,
        sla_breached=_sla_breached(item, now),
        tallies=_tallies(item),
        report_count=item.report_count,
        event_id=item.event_id,
        event_title=event.title if event else None,
        event_start_time_utc=event.start_time_utc if event else None,
        event_version=event.event_version if event else None,
        source_id=source.pk if source else None,
        source_name=source.name if source else None,
        source_badge=(
            source_badge_for_type(
                source_type=source.source_type,
                acquisition_method=source.acquisition_method,
            )
            if source
            else None
        ),
    )


def list_review_items(
    *,
    now: datetime,
    status: str | None = None,
    reason: str | None = None,
    source_id: UUID | None = None,
) -> list[ReviewItemRow]:
    """The queue, in the order an editor should work it.

    **Open items first, then priority, then the deadline, then the oldest.** See the module
    docstring for where priority comes from and why nulls sort last.

    The filters are the three the AC names — reason, status and source — and each one
    narrows the same single query. `status` defaults to *no filter*, so the queue opens on
    everything; the admin's own "open only" view is the one that pins it.
    """
    queryset = ReviewItem.objects.using(CATALOG).select_related("event", "event__source", "source")
    if status:
        queryset = queryset.filter(status=status)
    if reason:
        queryset = queryset.filter(reason=reason)
    if source_id:
        queryset = queryset.filter(source_id=source_id)

    return [_to_row(item, now) for item in ordered(queryset)]


def queue_summary(*, now: datetime) -> QueueSummary:
    """The three FR-57 numbers, at one instant.

    **`queue_size` counts open items only.** A resolved item is history: it was decided,
    the decision is recorded, and counting it would make the queue look bigger than the
    work in it.

    **`oldest_open_age` is the age of the oldest *open* item**, measured from when it was
    first raised. It is None for an empty queue rather than a zero timedelta, because "no
    items" and "an item raised just now" are different facts and the second one is a lie
    about the first.

    **`sla_breaches` counts open reports past their deadline.** Only a `user_reported` item
    has a deadline, so the other reasons can never breach one.
    """
    open_items = ReviewItem.objects.using(CATALOG).filter(status=ReviewItem.Status.OPEN)
    queue_size = open_items.count()

    oldest_raised_at = open_items.order_by("raised_at").values_list("raised_at", flat=True).first()
    oldest_open_age = None if oldest_raised_at is None else now - oldest_raised_at

    sla_breaches = open_items.filter(reason=ReviewItem.Reason.USER_REPORTED, due_at__lt=now).count()

    return QueueSummary(
        queue_size=queue_size,
        oldest_open_age=oldest_open_age,
        sla_breaches=sla_breaches,
    )


def list_source_observations(*, source_id: UUID) -> list[SourceObservationRow]:
    """One source's verdict history, newest first.

    **These are the facts FR-16's score is computed from, and not the score.** The score is
    computed and stored by `reliability-recompute-and-escalation`; until that ships there is
    nothing to show, and a live computation here would be a second implementation of
    another work item's job.
    """
    rows = (
        SourceObservation.objects.using(CATALOG)
        .filter(source_id=source_id)
        .select_related("event")
        .order_by("-occurred_at")
    )
    return [
        SourceObservationRow(
            kind=observation.kind,
            occurred_at=observation.occurred_at,
            event_id=observation.event_id,
            event_title=observation.event.title if observation.event else None,
        )
        for observation in rows
    ]


def get_review_item_detail(*, item_id: UUID, now: datetime) -> ReviewItemDetail | None:
    """One item's page facts, or None if there is no such item.

    **An event item shows the event's current facts; a source item shows the source's
    facts and its verdict history.** The two are different pages because they answer
    different questions: "is this listing right?" and "is this source worth trusting?".

    The facts are the *current* ones, not the ones the item was raised with. An editor
    decides on what is true now, and the `event_version` carried here is the staleness
    token the verdicts take.
    """
    item = (
        ReviewItem.objects.using(CATALOG)
        .select_related("event", "event__venue", "event__source", "source")
        .filter(pk=item_id)
        .first()
    )
    if item is None:
        return None

    event = item.event
    source = _source_of(item)
    observations = tuple(list_source_observations(source_id=source.pk)) if source else ()

    return ReviewItemDetail(
        id=item.id,
        reason=item.reason,
        status=item.status,
        resolution=item.resolution,
        raised_at=item.raised_at,
        last_raised_at=item.last_raised_at,
        due_at=item.due_at,
        sla_breached=_sla_breached(item, now),
        tallies=_tallies(item),
        report_count=item.report_count,
        resolved_at=item.resolved_at,
        resolved_by_kind=item.resolved_by_kind,
        resolved_by_label=item.resolved_by_label,
        event_id=item.event_id,
        event_title=event.title if event else None,
        event_start_time_utc=event.start_time_utc if event else None,
        event_end_time_utc=event.end_time_utc if event else None,
        event_start_time_tz=event.start_time_tz if event else None,
        event_status=event.status if event else None,
        event_publication_status=event.publication_status if event else None,
        event_venue_name=event.venue.name if event and event.venue else None,
        event_version=event.event_version if event else None,
        source_id=item.source_id,
        source_name=source.name if source else None,
        source_type=source.source_type if source else None,
        source_badge=(
            source_badge_for_type(
                source_type=source.source_type,
                acquisition_method=source.acquisition_method,
            )
            if source
            else None
        ),
        source_acquisition_method=source.acquisition_method if source else None,
        source_status=source.status if source else None,
        source_url=source.url if source else None,
        source_city=source.city if source else None,
        observations=observations,
    )


def open_item_count_by_reason(*, now: datetime | None = None) -> dict[str, int]:
    """How many open items each reason has.

    A read that exists so the admin can say "user reports (7)" rather than "user reports",
    which tells a reviewer whether the filter is worth clicking.

    **`now` is accepted so every read in this module has the same shape**, and so the
    admin can hand one instant to this and to `queue_summary` together. It is not used:
    a count of open items does not depend on the instant it is taken at, because "open"
    is a status rather than a deadline.
    """
    rows = (
        ReviewItem.objects.using(CATALOG)
        .filter(status=ReviewItem.Status.OPEN)
        .values("reason")
        .annotate(total=Count("id"))
    )
    return {row["reason"]: row["total"] for row in rows}


def source_badge_for(*, source_type: str | None, acquisition_method: str | None) -> str | None:
    """The Source Badge type for a source (EXPERIENCE.md §4).

    **Re-exported, not reimplemented.** The badge rule lives in
    `services.source_badges`; this wrapper exists so the admin and the read service
    share one name for it rather than each importing the badge module by its own path.
    """
    return source_badge_for_type(source_type=source_type, acquisition_method=acquisition_method)


__all__ = [
    "QueueSummary",
    "ReportTally",
    "ReviewItemDetail",
    "ReviewItemRow",
    "SourceObservationRow",
    "get_review_item_detail",
    "item_is_past_its_sla",
    "list_review_items",
    "list_source_observations",
    "open_item_count_by_reason",
    "ordered",
    "priority_expression",
    "queue_summary",
    "source_badge_for",
]
