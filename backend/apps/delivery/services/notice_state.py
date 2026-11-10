"""One event's notice and mute facts, read together (FR-54, FR-55).

The Detail Screen needs **two** things about one event — whether the user has silenced its
notices, and what the newest notice about it says — and it needs them **in one round trip**,
because the banner and the mute control render from the same response and two snapshots
could disagree with each other.

**So `delivery` publishes one combined read, and `personalization` calls it.** The
`personalization` side never touches `delivery`'s models: it receives plain dataclasses, and
the model instances stay inside the app that owns the tables (AD-16).

**This module is a leaf, and it reads the two models directly.** It could have gone through
`services.state_notices` and `services.mutes` — the two published services — but it does not,
for one reason that matters:

**The model never leaves `delivery`.** `state_notices` publishes reads that return
`StateChangeNotice` *model instances*. Handing one of those to `personalization` would put a
reference to `apps.delivery.models` in `personalization`'s hands — the leak that
`tests/delivery/test_ownership.py::test_the_service_does_not_leak_the_model_to_its_callers`
exists to prevent. The projection into `NoticeSummary` happens **here**, inside the owning
app, and the caller receives plain data.

**(There is no import cycle to avoid here, and it is worth saying so plainly.)** An earlier
draft of this module justified reading the models directly by claiming that going through
`state_notices` would close a `personalization` → `notice_state` → `state_notices` →
`scheduled_sends` → `personalization` loop. That was checked against the real import graph
and it is **false**: `scheduled_sends` imports only `apps.personalization.services
.digest_preferences`, and that module reaches none of `detail_read`, `personalization
.schemas`, `detail_conflict` or `neighbor_count`. Routing through `state_notices` would not
have closed a loop, and adding that edge leaves `lint-imports` at 19 kept, 0 broken.

**A false rationale is worse than a missing one**, because it makes a real constraint look
inviolable when it is not — and this one *is* real, on the boundary rule above. So the rule
is stated once, on the ground where it holds.

**This module owns the "newest notice" rule.** It used to live in
`state_notices.latest_notice_for_event`, which had no production caller once this read
arrived — a function and a query that two places could drift apart on. The rule is here now,
and the strip's read in `state_notices.list_undismissed_notices` uses the **same ordering**,
so the strip card and the Detail banner cannot disagree about which notice is newest.

**The two facts are independent, and the read does not merge them.** A muted event can still
have a notice — a terminal change (cancelled, superseded) is raised *despite* a mute
(`services.state_notices`), because FR-55 has already removed the event from the digest and
silence about it would have no second channel. And an unmuted event can have no notice. A
caller that read one and assumed the other would get one of those two cases wrong.
"""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from apps.delivery.models import EventNoticeMute, StateChangeNotice
from shared.db import PERSONAL


@dataclass(frozen=True)
class NoticeSummary:
    """One notice, as the read hands it over. Plain data, not a model instance.

    **The notice's own facts, and no more.** The change's *content* — the before/after
    values — is deliberately absent: it is source payload, and it is the one place a title or
    a venue name could leak into a response (AD-13). `change_kind` is the vocabulary
    `domain.lifecycle.ChangeKind` defines, carried through unchanged.

    **`seen_at` and `dismissed_at` are two different acts.** `seen_at` is when the notice was
    put in front of the user — not an act by them. `dismissed_at` is when they closed it. A
    notice can be seen and not dismissed, and a caller that cannot tell them apart would
    render a dismissed notice as still open.

    **Today, a dismissal sets both.** `dismiss_notice` is the only production writer of
    `seen_at`, so in practice `seen_at` is either `None` or the same instant as
    `dismissed_at`. The two are still separate columns and separate fields, because the
    strip's read deliberately does **not** mark notices seen — a `GET` that writes is the
    shape CSRF exists to stop, and `apps/personalization/detail_api.py` refuses it for the
    Detail Screen. When something eventually *does* mark a notice seen on render, the two
    fields will say different things and the wire shape is already right for it.

    **`state_change_id` is not here.** It is the notice's uniqueness key and an internal id;
    no client acts on it, so it does not travel.
    """

    id: UUID
    event_id: UUID
    change_kind: str
    event_version: int
    local_date: date
    seen_at: datetime | None
    dismissed_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class EventNoticeState:
    """The notice and mute facts about one event, for one user.

    **`notice` is the newest notice for the event, whether or not it has been dismissed.**
    That is this module's rule: the banner is about *this* event, which the user has
    navigated to on purpose, so dismissing a strip on the digest home must not hide *"this
    event was cancelled"* from the event's own page. The notice's own `dismissed_at` says
    which state it is in.

    **`muted` says nothing about the event.** A mute silences the correction, not the event:
    reminders still fire on the user's Reminder Plan and the event still places in the Pulse
    Digest (FR-55).
    """

    event_id: UUID
    muted: bool
    notice: NoticeSummary | None


def summarize_notice(row: StateChangeNotice) -> NoticeSummary:
    """The model row, projected onto plain data.

    The projection is the boundary: after this, nothing outside `delivery` holds a reference
    to `apps.delivery.models`.

    **It is public because the strip's read needs it too.** The strip lists several
    notices, and the banner names one — and both must carry the same fields by
    construction, or the strip card and the Detail banner would be free to drift.
    """
    return NoticeSummary(
        id=row.id,
        event_id=row.event_id,
        change_kind=row.change_kind,
        event_version=row.event_version,
        local_date=row.local_date,
        seen_at=row.seen_at,
        dismissed_at=row.dismissed_at,
        created_at=row.created_at,
    )


def read_event_notice_state(*, user_id: UUID, event_id: UUID) -> EventNoticeState:
    """The mute state and the newest notice for one event.

    **Two queries, both scoped by `user_id`.** The mute is an `EXISTS` and the notice is the
    newest row for the pair — two tables, so two reads. They are not merged into one query
    because there is no honest way to: a cross-table join would answer "is there a notice"
    only for events that also have a mute row, and an `EXISTS` against a join is the kind of
    thing that is subtly wrong in exactly the case nobody tests.

    **Both reads are unconditional.** The mute is the *control's* state, and the Detail
    Screen has to render "Muted" or "Not muted" every time; the notice is a fact about the
    event whether or not the user has saved it. Neither is gated on the user's save.

    **The newest notice is chosen by `created_at`, and dismissal is not a filter.** See
    `EventNoticeState`'s own docstring.

    **The order has a tiebreaker: `order_by("-created_at", "-id")`.** `created_at` is
    `auto_now_add` with microsecond resolution, and a single ingestion poll can raise
    several notices at once — so two rows can share a `created_at`. Without a secondary
    key the database is free to return either of them, and the strip
    (`state_notices.list_undismissed_notices`) would be free to return a *different* one
    for the same tie. **`-id` is the natural tiebreak** because the primary key is a
    UUIDv7 (`shared.models`), which is time-ordered by construction: of two notices raised
    in the same instant, the later one has the larger id.
    """
    muted = (
        EventNoticeMute.objects.using(PERSONAL).filter(user_id=user_id, event_id=event_id).exists()
    )
    row = (
        StateChangeNotice.objects.using(PERSONAL)
        .filter(user_id=user_id, event_id=event_id)
        .order_by("-created_at", "-id")
        .first()
    )
    return EventNoticeState(
        event_id=event_id,
        muted=muted,
        notice=summarize_notice(row) if row is not None else None,
    )


__all__ = [
    "EventNoticeState",
    "NoticeSummary",
    "read_event_notice_state",
    "summarize_notice",
]
