"""The composition command: candidates in, one persisted Pulse Digest out (FR-5, FR-8, AD-10).

**This is the application-layer join AD-3 forces.** The candidates live on two sides of
the schema wall — the public events in `catalog`, the user's own agenda and saves in
`personal` — and no query may span them. So the join happens here, in Python, over
plain data: the catalog's public read hands over frozen dataclasses, the personal
reads hand over their own, and this command scores them together.

**It is the only writer of these rows** (AD-16, AD-5: every mutation is a named
command that owns its validation and its audit-log write).

**It runs in the worker, never in a request** (AD-11). The `actor` is passed in
explicitly, and the caller — the scheduling job — passes a system actor.

**The three slots** (FR-5, Amendment A-2) are assigned in a fixed order, and each slot
draws from the candidates the earlier slots did not take:

1. **must-know** — an eligible personal event within 48 hours, if one exists and the
   user has not opted out; otherwise the highest-scoring eligible public event;
2. **nearby** — the highest-scoring remaining public event;
3. **serendipity** — the highest scorer under the **inverted** preference term.

**The ordering is explicit, not inherited.** `domain/ranking.py` is deterministic by
construction, but two events with identical scores leave the choice to whatever order
the queryset returned, and Postgres does not promise one. So every ordering here is by
the key `(-score, start_time_utc, event_id)` — the score first (it is the ranking),
the start time breaking a score tie (soonest first — the sooner one is more
actionable), and the id breaking a start-time tie (a UUIDv7 is unique, so the key is
a **total** order and two runs over the same candidates cannot disagree).

**The empty state is a real digest with zero rows** (FR-8). "Nothing near you today"
and "we never composed for you" are different states, and a parent row with no
children is what tells them apart.

**The re-run is a no-op.** One digest per `(user, local_date)` — the unique constraint
is the backstop, but the command takes a per-user advisory lock and checks first, so a
race serialises rather than surfacing as an `IntegrityError` to the caller.

**The catalog reads happen outside the transaction** (AD-3). No transaction may span
both schemas, so the shape is: read the catalog, score, then open one transaction on
`personal` and write the digest, its compositions and the audit row atomically.

Design: .specs-fire/intents/pulse-digest-and-trust/work-items/
digest-composition-service-design.md (decisions D1-D15).
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import blake2b
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import connections, transaction

from apps.ingestion.services.catalog_read import list_public_candidates
from apps.personalization.models import (
    DIGEST_SLOT_ORDER,
    DigestComposition,
    DigestPreference,
    Interest,
    PulseDigest,
)
from apps.personalization.services.audit import write_audit
from apps.personalization.services.digest_candidates import (
    PersonalEventCandidate,
    list_personal_candidates,
    list_saved_candidates,
)
from domain.ranking import (
    RankingInputs,
    apply_hysteresis,
    city_band,
    interest_overlap,
    recency_band,
    score_slot_1,
    score_slot_2,
    score_slot_3,
    why_this_tags,
)
from shared.actor import Actor
from shared.constants import DEFAULT_DIGEST_TIMEZONE
from shared.db import PERSONAL

#: The lock key namespace for the per-user advisory lock.
#:
#: **Its own namespace, not `digest_preferences.py`'s.** The two commands write rows
#: about the same user's digest, so they *could* share a namespace to serialise against
#: each other — but a shared namespace also means the two commands block each other for
#: no reason, and a lock is only a mutual-exclusion device when the thing it excludes is
#: the same thing. `digest_preferences.py` locks the *preference* row; this locks the
#: *composition*. Distinct rows, distinct locks, and the same 16-byte `person` limit
#: `blake2b` imposes.
#:
#: The value is not equal to any other lock's person (`ep-ident` in `domain/dedup.py`,
#: `ep-source-run` in `ingest_source.py`, `eventpulse24-onb`, `eventpulse24-cal`), so a
#: digest lock can never collide with an ingestion or dedup lock.
_LOCK_PERSON = b"ep-digest-c"


@dataclass(frozen=True)
class DigestCompositionRow:
    """One composed card: the event, the slot it fills, and its explanation.

    Plain data — the caller never holds a model instance, and the read API builds its
    wire shape from this.
    """

    event_id: UUID
    event_kind: str
    slot: str
    score: Decimal
    bucket: int
    tags: tuple[str, ...]
    source_badge: str | None
    event_version: int | None


@dataclass(frozen=True)
class DigestCompositionResult:
    """The outcome of one composition: the digest, and what is on it.

    `created` is the difference between "composed" and "returned what was already
    there". A re-run returns the existing digest with `created=False` and writes
    nothing.
    """

    digest_id: UUID
    user_id: UUID
    local_date: date
    timezone: str
    is_empty: bool
    compositions: tuple[DigestCompositionRow, ...]
    created: bool


def _user_lock_key(user_id: UUID) -> int:
    """The advisory-lock key for one user's digest rows.

    Stable across processes: `blake2b`, never the per-process-salted `hash()`.
    """
    digest = blake2b(str(user_id).encode(), digest_size=8, person=_LOCK_PERSON).digest()
    return int.from_bytes(digest, "big", signed=True)


def _lock_user(user_id: UUID) -> None:
    """Serialise the compositions for one user.

    **Why an advisory lock and not the unique constraint.** `pulse_digest_user_date_uq`
    would catch a race — but as an `IntegrityError` that reaches the caller as a 500.
    The lock makes the second worker *wait*, see the row the first one wrote, and
    return it.

    `pg_advisory_xact_lock` is **transaction-scoped**: the lock is released when the
    transaction commits or rolls back, so a crashed worker cannot leave a user's
    digest wedged.
    """
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_user_lock_key(user_id)])


def _read_preference(user_id: UUID) -> DigestPreference | None:
    """The user's digest preference, if they have one.

    **There is no preference getter in `digest_preferences.py`** — that module is a
    command module, and its `_read_preference` is private to it. The composition
    service needs the preference for three things: the timezone (the local date), the
    city (the candidate filter) and the opt-out (Slot 1's personal preference), and it
    reads the row the same way `onboarding.py` does.
    """
    return DigestPreference.objects.using(PERSONAL).filter(user_id=user_id).order_by("id").last()


def _read_interest_keys(user_id: UUID) -> tuple[str, ...]:
    """The chips the user picked at onboarding, in the order they were picked.

    Ordered by `id` — a UUIDv7, so the id **is** the creation time, and the order is
    the order the user picked them in.
    """
    rows = (
        Interest.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .order_by("id")
        .values_list("chip_key", flat=True)
    )
    return tuple(rows)


def _local_date(*, now: datetime, zone_name: str) -> date:
    """The user's local calendar day.

    **By conversion, not by arithmetic.** `now.astimezone(zone).date()` is the user's
    day; adding 24 hours to a UTC date would be a different day for most of the
    world, and a DST transition would break it twice a year.

    An unknown zone falls back to UTC rather than raising: the zone is validated at
    write time by the onboarding command, so an unknown name here means hand-edited
    data — not that the composition should fail.
    """
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo(DEFAULT_DIGEST_TIMEZONE)
    return now.astimezone(zone).date()


def _inputs_for_public(
    *,
    candidate,
    user_chip_keys: tuple[str, ...],
    user_city: str,
    now: datetime,
) -> RankingInputs:
    """The four ranking inputs for a public candidate.

    **The confidence term is the extraction confidence** — how well the catalog knows
    this event's facts. It is the same number the candidate read used to admit the
    event, so the card's score and the card's eligibility come from one fact.

    **The city band** compares the venue's city to the user's city. The user's
    **country is empty**: the `DigestPreference` holds a city and a zone and no
    country, and the country band is a half-credit consolation for "different city,
    same country". Giving it up costs `0.10` of a score, not the difference between
    relevant and irrelevant.
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
    )


def _inputs_for_personal(
    *,
    candidate: PersonalEventCandidate,
    user_chip_keys: tuple[str, ...],
    now: datetime,
) -> RankingInputs:
    """The four ranking inputs for a personal event.

    **The interest term is `0.0`.** A personal event is not *matched to* the user's
    interests — it *is* theirs. It was not filed under a chip by a source; it is on
    their calendar.

    **The city band is `0.0`.** A personal event's `location` is free text, not a
    city, and matching free text against a city name is exactly the kind of guess
    this codebase refuses elsewhere ("give such events no row rather than a guessed
    one"). So a personal event never carries the `nearby` tag — and it should not: the
    user's own event is not *nearby*, it is *theirs*.

    **The confidence term is `1.0`.** The facts are the user's own; there is no
    extraction to be unsure of. The catalog's confidence gates gate what the *catalog*
    may rank; the user's own agenda is not the catalog's.
    """
    return RankingInputs(
        interest_overlap=interest_overlap(
            event_chip_keys=(),
            user_chip_keys=user_chip_keys,
        ),
        recency=recency_band(start_time_utc=candidate.start_utc, now=now),
        city_match=Decimal("0.00"),
        confidence=Decimal("1.00"),
    )


@dataclass(frozen=True)
class _Scored:
    """A candidate with its score and its explanation.

    **A value, not a handle.** The scoring happens once, outside the transaction, and
    the result is what gets written — so the number on the card and the number that
    was scored cannot be different numbers.
    """

    event_id: UUID
    event_kind: str
    start_time_utc: datetime
    start_time_tz: str
    chip_keys: tuple[str, ...]
    source_badge: str | None
    event_version: int | None
    score: Decimal
    bucket: int
    tags: tuple[str, ...]

    def order_key(self) -> tuple:
        """The ordering key: **the score first**, then the start time, then the id.

        The score is negated so the key sorts ascending-by-best. The start time breaks
        a score tie — soonest first, because the sooner event is more actionable. The
        id breaks a start-time tie, and it is unique, so the key is a **total** order:
        there is never a residual tie, and the ordering never depends on the order the
        rows happened to come back from the database.
        """
        return (-self.score, self.start_time_utc, self.event_id)


def _score_public(
    *,
    candidate,
    slot_scorer,
    user_chip_keys: tuple[str, ...],
    user_city: str,
    now: datetime,
    is_saved: bool,
    serendipity: bool,
) -> _Scored:
    """Score one public candidate for one slot, and derive its tags from the same inputs.

    **The tags come from the same `RankingInputs` the score used.** AD-10's whole
    point is that the explanation and the decision cannot drift apart: a card tagged
    "nearby" whose score did not match the city would be lying.

    **The bucket comes from `apply_hysteresis` with no previous value.** The rule
    lives in the domain, and the domain's function *is* `score_bucket` when there is
    nothing to compare against. Passing `None` is not a shortcut — it is what
    EXPERIENCE.md §4 means by "across days, hysteresis resets... No persistent bucket
    is stored between days".
    """
    inputs = _inputs_for_public(
        candidate=candidate,
        user_chip_keys=user_chip_keys,
        user_city=user_city,
        now=now,
    )
    score = slot_scorer(inputs=inputs)
    bucket = apply_hysteresis(
        previous_bucket=None,
        previous_score=None,
        new_score=score,
    )
    tags = why_this_tags(
        inputs=inputs,
        event_chip_keys=candidate.chip_keys,
        user_chip_keys=user_chip_keys,
        start_time_utc=candidate.start_time_utc,
        start_time_tz=candidate.start_time_tz,
        now=now,
        is_saved=is_saved,
        serendipity=serendipity,
    )
    return _Scored(
        event_id=candidate.id,
        event_kind=DigestComposition.EventKind.PUBLIC,
        start_time_utc=candidate.start_time_utc,
        start_time_tz=candidate.start_time_tz,
        chip_keys=candidate.chip_keys,
        source_badge=candidate.source_badge,
        event_version=candidate.event_version,
        score=score,
        bucket=bucket,
        tags=tags,
    )


def _score_personal(
    *,
    candidate: PersonalEventCandidate,
    user_chip_keys: tuple[str, ...],
    now: datetime,
) -> _Scored:
    """Score one personal event for Slot 1, and derive its tags.

    **A personal event has no source badge and no event version** — the model's
    `digest_composition_kind_shape_ck` says so, and the check constraint is right: a
    personal event has no source, so there is no badge to state.

    **It is not `is_saved`.** The `saved` tag means "you saved this public event". The
    user's own event is not a save; it is their agenda.
    """
    inputs = _inputs_for_personal(
        candidate=candidate,
        user_chip_keys=user_chip_keys,
        now=now,
    )
    score = score_slot_1(inputs=inputs, is_personal_event=True)
    bucket = apply_hysteresis(
        previous_bucket=None,
        previous_score=None,
        new_score=score,
    )
    tags = why_this_tags(
        inputs=inputs,
        event_chip_keys=(),
        user_chip_keys=user_chip_keys,
        start_time_utc=candidate.start_utc,
        start_time_tz=candidate.start_time_tz,
        now=now,
        is_saved=False,
    )
    return _Scored(
        event_id=candidate.id,
        event_kind=DigestComposition.EventKind.PERSONAL,
        start_time_utc=candidate.start_utc,
        start_time_tz=candidate.start_time_tz,
        chip_keys=(),
        source_badge=None,
        event_version=None,
        score=score,
        bucket=bucket,
        tags=tags,
    )


def _assign_slots(
    *,
    personal_candidates: list[PersonalEventCandidate],
    public_candidates: list,
    user_chip_keys: tuple[str, ...],
    user_city: str,
    include_personal_events: bool,
    saved_event_ids: set[UUID],
    now: datetime,
) -> list[_Scored]:
    """Fill the three slots, in order, and return the compositions.

    **The slots are filled in order and each draws from what the earlier slots did not
    take.** That is how "no duplicate `event_id` across the three slots" holds *by
    construction* rather than by catching an `IntegrityError` afterwards — the
    work item is explicit that the service "must not rely on an `IntegrityError` to
    notice".

    **Slot 1 takes the personal event whenever there is one.** FR-5 puts "Personal
    Events eligible" first and makes the public fallback conditional on "if no
    Personal Event is eligible". So the personal event is not competing with the
    public event for Slot 1 — it *is* Slot 1 when there is one, even if a public
    event would have outscored it.

    **Slot 3 draws from the public candidates only.** A personal event is the user's
    own agenda; a card tagged "discovery" for something the user already has on their
    calendar would be nonsense.

    **The saved set only adds a tag.** A save does not change the score and does not
    change the ordering. A saved event in another city is not a candidate — the
    slots are "nearby", and a save is not a statement that the event is nearby.
    """
    chosen: list[_Scored] = []
    used: set[UUID] = set()

    # --- Slot 1: must-know -------------------------------------------------------
    if include_personal_events:
        scored_personal = [
            _score_personal(
                candidate=candidate,
                user_chip_keys=user_chip_keys,
                now=now,
            )
            for candidate in personal_candidates
        ]
        if scored_personal:
            best = min(scored_personal, key=lambda scored: scored.order_key())
            chosen.append(best)
            used.add(best.event_id)

    if not chosen:
        scored_public = [
            _score_public(
                candidate=candidate,
                slot_scorer=score_slot_1,
                user_chip_keys=user_chip_keys,
                user_city=user_city,
                now=now,
                is_saved=candidate.id in saved_event_ids,
                serendipity=False,
            )
            for candidate in public_candidates
        ]
        if scored_public:
            best = min(scored_public, key=lambda scored: scored.order_key())
            chosen.append(best)
            used.add(best.event_id)

    # --- Slot 2: nearby ----------------------------------------------------------
    remaining = [candidate for candidate in public_candidates if candidate.id not in used]
    scored_slot_2 = [
        _score_public(
            candidate=candidate,
            slot_scorer=score_slot_2,
            user_chip_keys=user_chip_keys,
            user_city=user_city,
            now=now,
            is_saved=candidate.id in saved_event_ids,
            serendipity=False,
        )
        for candidate in remaining
    ]
    if scored_slot_2:
        best = min(scored_slot_2, key=lambda scored: scored.order_key())
        chosen.append(best)
        used.add(best.event_id)

    # --- Slot 3: serendipity -----------------------------------------------------
    remaining = [candidate for candidate in public_candidates if candidate.id not in used]
    scored_slot_3 = [
        _score_public(
            candidate=candidate,
            slot_scorer=score_slot_3,
            user_chip_keys=user_chip_keys,
            user_city=user_city,
            now=now,
            is_saved=candidate.id in saved_event_ids,
            serendipity=True,
        )
        for candidate in remaining
    ]
    if scored_slot_3:
        best = min(scored_slot_3, key=lambda scored: scored.order_key())
        chosen.append(best)
        used.add(best.event_id)

    return chosen


def _existing_digest(*, user_id: UUID, local_date: date) -> PulseDigest | None:
    """The user's digest for that local date, if it has one."""
    return (
        PulseDigest.objects.using(PERSONAL)
        .filter(user_id=user_id, local_date=local_date)
        .order_by("id")
        .last()
    )


def _rows_for(digest: PulseDigest) -> list[DigestCompositionRow]:
    """The digest's compositions, as plain data.

    **The slot order is `DIGEST_SLOT_ORDER`, not the row order.** A `CHAR` index sorts
    alphabetically — which would put "nearby" before "must_know" — so the read sorts in
    Python against the tuple that is the single place the slot order lives.
    """
    rows = DigestComposition.objects.using(PERSONAL).filter(digest_id=digest.id).order_by("id")
    by_slot = {row.slot: row for row in rows}
    ordered = [by_slot[slot] for slot in DIGEST_SLOT_ORDER if slot in by_slot]
    return [
        DigestCompositionRow(
            event_id=row.event_id,
            event_kind=row.event_kind,
            slot=row.slot,
            score=row.score,
            bucket=row.bucket,
            tags=tuple(row.tags),
            source_badge=row.source_badge,
            event_version=row.event_version,
        )
        for row in ordered
    ]


def compose_digest(
    *,
    user_id: UUID,
    actor: Actor,
    now: datetime,
) -> DigestCompositionResult:
    """Compose this user's Pulse Digest for their local day.

    **The command reads its own candidates** — there is no `candidates=` parameter,
    because a caller-supplied pool would let the card and the score drift apart, and
    AD-10's whole point is that they cannot.

    **The catalog reads happen first, outside the transaction.** AD-3: no transaction
    may span both schemas, so the shape is "read the catalog, score, then open one
    transaction on `personal` and write everything atomically". The window between the
    read and the write is microseconds wide, and it is the accepted cost of the wall.

    **The re-run is a no-op.** A digest already exists for this `(user, local_date)`,
    so the existing one is returned with `created=False` and nothing is written — no
    second composition, no update to an append-only row, and no second audit row. A
    re-run decides nothing, and the audit table records decisions.

    **A short digest is a short digest.** FR-5's "exactly 3 cards on a standard day"
    describes a day with a normal catalog. When there is only one or two candidates,
    the digest holds one or two cards — padding from a relaxed pool would publish a
    card the gates forbid, and falling to the empty state would tell the user there is
    nothing happening when there is.
    """
    preference = _read_preference(user_id)
    zone_name = preference.timezone if preference else DEFAULT_DIGEST_TIMEZONE
    user_city = (preference.city or "") if preference else ""
    include_personal_events = preference.include_personal_events if preference else True
    local_date = _local_date(now=now, zone_name=zone_name)
    user_chip_keys = _read_interest_keys(user_id)

    # --- the reads, outside the transaction (AD-3) --------------------------------
    personal_candidates = list_personal_candidates(user_id=user_id, now=now)
    saved_candidates = list_saved_candidates(user_id=user_id, now=now)
    public_candidates = list_public_candidates(now=now, city=user_city or None)

    saved_event_ids = {saved.event_id for saved in saved_candidates}

    scored = _assign_slots(
        personal_candidates=personal_candidates,
        public_candidates=public_candidates,
        user_chip_keys=user_chip_keys,
        user_city=user_city,
        include_personal_events=include_personal_events,
        saved_event_ids=saved_event_ids,
        now=now,
    )

    # --- the write, atomic on the personal side -----------------------------------
    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)

        existing = _existing_digest(user_id=user_id, local_date=local_date)
        if existing is not None:
            return DigestCompositionResult(
                digest_id=existing.id,
                user_id=user_id,
                local_date=local_date,
                timezone=zone_name,
                is_empty=existing.is_empty,
                compositions=tuple(_rows_for(existing)),
                created=False,
            )

        is_empty = not scored
        digest = PulseDigest.objects.using(PERSONAL).create(
            user_id=user_id,
            local_date=local_date,
            timezone=zone_name,
            composed_at=now,
            is_empty=is_empty,
        )

        DigestComposition.objects.using(PERSONAL).bulk_create(
            [
                DigestComposition(
                    digest_id=digest.id,
                    user_id=user_id,
                    event_id=item.event_id,
                    event_kind=item.event_kind,
                    slot=slot,
                    score=item.score,
                    bucket=item.bucket,
                    tags=list(item.tags),
                    source_badge=item.source_badge,
                    event_version=item.event_version,
                    composed_at=now,
                )
                for slot, item in zip(DIGEST_SLOT_ORDER, scored, strict=False)
            ]
        )

        write_audit(
            actor=actor,
            action="digest.composed",
            target_type="PulseDigest",
            target_id=digest.id,
            details={
                "local_date": local_date.isoformat(),
                "is_empty": is_empty,
                "composition_count": len(scored),
                "at": now.isoformat(),
            },
        )

    return DigestCompositionResult(
        digest_id=digest.id,
        user_id=user_id,
        local_date=local_date,
        timezone=zone_name,
        is_empty=is_empty,
        compositions=tuple(
            DigestCompositionRow(
                event_id=item.event_id,
                event_kind=item.event_kind,
                slot=slot,
                score=item.score,
                bucket=item.bucket,
                tags=item.tags,
                source_badge=item.source_badge,
                event_version=item.event_version,
            )
            for slot, item in zip(DIGEST_SLOT_ORDER, scored, strict=False)
        ),
        created=True,
    )


__all__ = [
    "DigestCompositionResult",
    "DigestCompositionRow",
    "compose_digest",
]
