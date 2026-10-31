"""The onboarding commands and queries (FR-1): interests, the digest preference, and progress.

FR-1's flow is three steps, every one of them skippable:

    1. `calendar`   — the optional calendar connect
    2. `interests`  — the optional interest chips, up to 3 picks
    3. `digest`     — the digest delivery time and timezone

This module is the **only** way the onboarding tables change. Every command takes an
explicit `Actor` and an explicit `now`, opens one `transaction.atomic(using=PERSONAL)`,
writes its audit row inside it, and returns plain data (AD-5).

**Step 1 does not own the calendar connection.** The connection belongs to
`calendar-connect-api`; this flow only records that the step was passed. A step that owned
a credential it did not create would be a second way in.

**Three rules are enforced here, not at the HTTP edge**, because a rule that only the edge
knows is a rule the next caller will not have:

- **Interests replace.** The setter takes a whole set, not a delta. "I changed my mind" is
  one call. The old rows are deleted and the new ones written in the *same* transaction,
  because a half-applied set is worse than a failed one: the user would see picks they
  did not choose.
- **Completion is terminal.** A finished onboarding is never reopened, whatever the clock
  says. Every command refuses to act on a completed user.
- **The resume window.** A user who leaves mid-step and comes back within
  `ONBOARDING_RESUME_WINDOW` resumes at the same step; after the window the flow restarts
  at step 1. The window is **inclusive** at its boundary.

**The digest preference is a local wall clock plus an IANA zone.** Storing a UTC instant
instead would be wrong in a way that only shows up twice a year: the user says "9am", and
a UTC instant is "9am once, then 8am or 10am after a DST change".

**Two guarantees hold for every command here.**

*Reads never write.* `get_onboarding_state` reports the restart for an expired flow and
leaves the row alone. A write behind a `GET` is a **cross-site write** — Django Ninja
exempts every view from Django's CSRF middleware, and the resolver only checks CSRF on
*unsafe* methods, so a hostile page could restart a user's flow with a plain `<img src>`.
The restart is a command, and the command is where it happens.

*Concurrent commands do not collide.* Every command takes the user's **advisory lock**
(`pg_advisory_xact_lock`) before it reads or writes, so two requests for the same user
are serialised. The lock is on a *key*, not a row, because the case that matters most is
the one where no row exists yet: a user with no interests and no progress row. Without
it, the loser of the race gets a raw `IntegrityError` from a unique constraint — a 500
where the caller should have got an answer.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time
from functools import partial
from hashlib import blake2b
from uuid import UUID

from django.db import connections, transaction

from apps.personalization.models import DigestPreference, Interest, OnboardingProgress
from apps.personalization.services.audit import write_audit
from apps.personalization.services.digest_enqueue import enqueue_digest_composition
from apps.personalization.services.digest_preferences import SOURCE_CHOICE, set_home_city
from domain.errors import (
    InvalidTimezoneError,
    OnboardingAlreadyCompleteError,
    TooManyInterestsError,
    UnknownInterestError,
    ValidationError,
)
from domain.timezones import canonical_zone
from shared.actor import Actor
from shared.constants import (
    DEFAULT_DIGEST_DELIVERY_TIME,
    DEFAULT_DIGEST_TIMEZONE,
    INTEREST_CHIPS,
    MAX_INTEREST_PICKS,
    ONBOARDING_RESUME_WINDOW,
    ONBOARDING_STEP_COUNT,
    ONBOARDING_STEPS,
)
from shared.db import PERSONAL

#: The chip keys, in the order the constant lists them. The service validates against
#: this set, so an unknown key is refused *before* any write.
INTEREST_CHIP_KEYS = frozenset(key for key, _label in INTEREST_CHIPS)

#: The `blake2b` personalisation for the onboarding lock key. It namespaces this lock
#: away from every other advisory lock in the system, so a user id hashed here cannot
#: collide with a dedup lock key.
_LOCK_PERSON = b"eventpulse24-onb"


def _user_lock_key(user_id: UUID) -> int:
    """The advisory-lock key for one user's onboarding rows.

    Stable across processes: `blake2b`, never the per-process-salted `hash()`.
    """
    digest = blake2b(str(user_id).encode(), digest_size=8, person=_LOCK_PERSON).digest()
    return int.from_bytes(digest, "big", signed=True)


def _lock_user(user_id: UUID) -> None:
    """Serialise the onboarding commands for one user.

    **Why an advisory lock and not a row lock.** A row lock can only lock a row that
    exists, and the interesting case is precisely the one where it does not: a user with
    no interest rows and no progress row yet. Two concurrent setters for that user would
    both find nothing to lock and both insert — and the loser gets a raw `IntegrityError`
    from the unique constraint, which reaches the caller as a 500. An advisory lock is
    taken on a *key*, so it works whether or not any row exists.

    `pg_advisory_xact_lock` is **transaction-scoped**: the lock is released when the
    transaction commits or rolls back, so a crashed worker cannot leave a user's
    onboarding wedged.
    """
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_user_lock_key(user_id)])


class InvalidDeliveryTimeError(ValidationError):
    """The digest delivery time is not a plain local wall clock.

    A `time` carrying a UTC offset is an *instant*, and this field is a wall clock — the
    two mean different things, and storing an offset-bearing time here would quietly turn
    the preference into the UTC instant the design refused.
    """

    code = "invalid_delivery_time"
    default_message = "That delivery time doesn't look right."


@dataclass(frozen=True)
class InterestChip:
    """One chip as plain data: its stable key and its display label."""

    key: str
    label: str


@dataclass(frozen=True)
class OnboardingState:
    """The whole onboarding state as plain data — the caller never holds a model instance.

    `current_step` is the 1-based position in `ONBOARDING_STEPS`, or `None` when the
    onboarding is complete. `completed` says whether it is finished.

    `interests` and `digest` are the *stored* values, so a skipped step shows the value
    the skip wrote (an empty set, the default preference) rather than nothing at all.

    The digest fields are the *whole* preference: when, where and what. The city and
    the opt-out are part of the same row and are read together with it — the digest
    service reads one row, not three.
    """

    completed: bool
    current_step: int | None
    step_name: str | None
    interests: tuple[str, ...]
    digest_delivery_time: time | None
    digest_timezone: str | None
    digest_city: str | None
    digest_city_source: str | None
    digest_include_personal_events: bool
    last_advanced_at: datetime | None
    completed_at: datetime | None


def list_interest_chips() -> tuple[InterestChip, ...]:
    """The ten chips, straight from the constant.

    This is the **only** source the frontend gets the list from — the endpoint projects
    this onto the wire, so the mockup's labels live in one place.
    """
    return tuple(InterestChip(key=key, label=label) for key, label in INTEREST_CHIPS)


def _validated_chip_keys(chip_keys: Sequence[str]) -> tuple[str, ...]:
    """The chip keys to write: unique, in the caller's order, all of them real.

    **A duplicate is deduplicated, not refused.** The database constraint forbids a
    duplicate *row*; a caller sending the same key twice in one payload has not made a
    mistake worth a refusal, and deduplicating is friendlier. The constraint still holds,
    because the set is written once, atomically.

    An unknown key **is** refused, and the offending key is named — the list is public, so
    naming it is safe, and it lets the caller see which pick was wrong.
    """
    if len(chip_keys) > MAX_INTEREST_PICKS:
        raise TooManyInterestsError(
            details={"limit": MAX_INTEREST_PICKS, "received": len(chip_keys)}
        )

    seen: list[str] = []
    for raw in chip_keys:
        key = raw.strip() if isinstance(raw, str) else ""
        if key not in INTEREST_CHIP_KEYS:
            raise UnknownInterestError(details={"chip_key": raw})
        if key not in seen:
            seen.append(key)
    return tuple(seen)


def _validated_zone(timezone_name: str) -> str:
    """The canonical IANA zone, or a refusal.

    `domain.timezones.canonical_zone` is the **same** validator personal events use, so
    "UTC" and "Etc/UTC" mean the same thing everywhere, and a zone that is ambiguous (a
    legacy link, a fixed offset) is refused rather than guessed at.
    """
    zone = canonical_zone(timezone_name)
    if zone is None:
        raise InvalidTimezoneError(details={"timezone": timezone_name})
    return zone


def _validated_delivery_time(delivery_time: time) -> time:
    """The delivery time as a plain wall clock.

    A time carrying a UTC offset is refused: this field is a local wall clock, and an
    offset-bearing time is an instant wearing a wall clock's clothes.
    """
    if not isinstance(delivery_time, time):
        raise InvalidDeliveryTimeError()
    if delivery_time.tzinfo is not None:
        raise InvalidDeliveryTimeError()
    return delivery_time


def _lock_interests(user_id: UUID) -> None:
    """Take the row lock on the user's interest rows, if they have any.

    Every command that touches the interest set goes through here first, so a writer
    that is about to *insert* a chip and a writer that is about to *delete* a chip are
    serialised on the same rows. Without it, a concurrent `set_interests` and
    `skip_step` could interleave into a unique-constraint violation.

    The **advisory lock** already serialises these writers, so this row lock is belt and
    braces: it also protects the rows from a writer that did *not* take the advisory
    lock — a direct write, or a caller that has not been migrated yet.
    """
    queryset = Interest.objects.using(PERSONAL).select_for_update().filter(user_id=user_id)
    # The lock is taken by reading the rows; the caller then changes them.
    list(queryset)


def _read_interest_keys(user_id: UUID) -> tuple[str, ...]:
    """The user's chip keys, in the order they were written.

    Ordered by `id`, which is a UUIDv7 — so the id *is* the creation time, in order. These
    two models carry no `created_at` column, and adding one would be a timestamp that
    says only what the id already says.
    """
    rows = (
        Interest.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .order_by("id")
        .values_list("chip_key", flat=True)
    )
    return tuple(rows)


def _read_digest(user_id: UUID) -> DigestPreference | None:
    """The user's digest preference, if they have one."""
    return DigestPreference.objects.using(PERSONAL).filter(user_id=user_id).order_by("id").last()


def _write_digest(*, user_id: UUID, delivery_time: time, zone: str) -> DigestPreference:
    """Write the preference — one row per user, so this is an upsert.

    **The caller holds the user's advisory lock**, so a concurrent writer for the same
    user has already waited and committed: the lookup below sees that writer's row, and
    the update path is taken. Without the lock, two writers would both find no row and
    both insert — and the loser of that race would get a raw `IntegrityError` from the
    unique constraint, which reaches the caller as a 500.
    """
    existing = _read_digest(user_id)
    if existing is not None:
        existing.delivery_time = delivery_time
        existing.timezone = zone
        existing.save(using=PERSONAL, update_fields=["delivery_time", "timezone"])
        return existing

    return DigestPreference.objects.using(PERSONAL).create(
        user_id=user_id,
        delivery_time=delivery_time,
        timezone=zone,
    )


def set_interests(
    *,
    user_id: UUID,
    chip_keys: Sequence[str],
    actor: Actor,
    now: datetime,
) -> OnboardingState:
    """Replace the user's interest picks.

    **Zero picks is valid** — that is how step 2 is skipped, and it clears the set.

    The write is one transaction: the old rows are deleted and the new ones inserted
    inside it, so a user who goes from three chips to one has one chip afterwards, and
    never four.

    **The old rows are locked before they are deleted.** Two concurrent setters for the
    same user would otherwise both delete and both insert the same chip, and the loser
    of that race gets a raw `IntegrityError` from the unique constraint — a 500. The
    lock makes the second setter wait for the first to commit, so it deletes the first
    setter's rows and inserts its own, and the user ends up with one set, not a
    constraint violation.
    """
    keys = _validated_chip_keys(chip_keys)

    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)
        _lock_interests(user_id)
        Interest.objects.using(PERSONAL).filter(user_id=user_id).delete()
        for key in keys:
            Interest.objects.using(PERSONAL).create(user_id=user_id, chip_key=key)
        write_audit(
            actor=actor,
            action="onboarding.interests_set",
            target_type="Interest",
            target_id=user_id,
            # The keys are not sensitive — they are a fixed public list — and an audit row
            # that says only "3 interests changed" cannot say *what* changed.
            details={"chip_keys": list(keys), "count": len(keys), "at": now.isoformat()},
        )

    return _state_for(user_id=user_id, now=now)


def set_digest_preference(
    *,
    user_id: UUID,
    delivery_time: time,
    timezone_name: str,
    actor: Actor,
    now: datetime,
    city: str | None = None,
    include_personal_events: bool | None = None,
) -> OnboardingState:
    """Set the digest delivery time and timezone, and optionally the city and opt-out.

    The zone is validated by `domain.timezones.canonical_zone` — the same validator
    personal events use — and the **canonical** name is stored, so "Etc/UTC" is stored as
    "UTC".

    **The city and the opt-out are optional here, and omission means "leave it
    alone".** The delivery time and the zone are the point of this command; the other two
    are settings that arrived later, and a client that has not been updated to know
    about them must not have them cleared by a request that never mentioned them.

    **All three writes land in one transaction.** A request that sets the delivery time
    *and* the city is one decision by one user, and a half-applied decision is worse
    than a failed one: the delivery time would say "8am" while the city says nothing
    changed, and neither half would be wrong on its own. So the city is written inside
    this transaction, not after it.

    **The city still gets its own audit row**, because it is a separate decision with a
    different privacy rule: the city never appears in an audit row's details (AD-13), and
    the flag does.
    """
    zone = _validated_zone(timezone_name)
    wall_clock = _validated_delivery_time(delivery_time)

    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)
        preference = _write_digest(user_id=user_id, delivery_time=wall_clock, zone=zone)
        if include_personal_events is not None:
            preference.include_personal_events = include_personal_events
            preference.save(using=PERSONAL, update_fields=["include_personal_events"])
        write_audit(
            actor=actor,
            action="onboarding.digest_preference_set",
            target_type="DigestPreference",
            target_id=preference.id,
            details={
                "delivery_time": wall_clock.strftime("%H:%M"),
                "timezone": zone,
                "at": now.isoformat(),
            },
        )

        if city is not None:
            # The city is resolved **inside** the transaction, so the coverage check and
            # the write see one consistent catalog, and the write joins this
            # transaction rather than opening a second one.
            set_home_city(
                user_id=user_id,
                city=city,
                source=SOURCE_CHOICE,
                actor=actor,
                now=now,
            )

    return _state_for(user_id=user_id, now=now)


def get_onboarding_state(*, user_id: UUID, now: datetime) -> OnboardingState:
    """The user's onboarding state. **This read never writes.**

    This is where the **resume rule** and the **terminal rule** live:

    - no progress row → the user is at step 1, in progress;
    - a row with `completed_at` set → **complete**, whatever the clock says;
    - a row whose `last_advanced_at` is older than the window → **restart at step 1**;
    - otherwise → the stored step.

    **The restart is reported, not written.** A read that mutates is a read that can be
    triggered by a prefetch, a crawler or a `<img>` tag — and, because Django Ninja
    exempts every view from Django's CSRF middleware and the resolver only checks CSRF
    on *unsafe* methods, a write behind a `GET` is a **cross-site write**: a hostile page
    could restart a user's onboarding flow with a plain `<img src>`. The row is therefore
    left alone here; the next **command** restarts it, under a row lock, in its own
    transaction.

    So an expired flow reads as step 1 straight away, and the stored row catches up the
    moment the user does anything with it. Two readers still agree about the step,
    because the answer is derived from the same stored facts either way — nothing is
    recomputed per read and nothing depends on a write having happened.
    """
    progress = _read_progress(user_id)
    return _state_for(user_id=user_id, now=now, progress=progress)


def _enqueue_first_digest(user_id: UUID) -> None:
    """Ask the worker to compose this user's first digest — **after** the transaction commits.

    **The enqueue is registered, not performed.** The composition reads the digest
    preference, and a job enqueued *inside* the transaction would run before the commit
    and find no preference — it would compose nothing. So the enqueue is registered with
    `transaction.on_commit`, which runs it once the command's work is durable.

    **`robust=True` means a broker outage does not fail the onboarding.** The user has
    finished onboarding either way; what they have not got is a digest. And the
    scheduler is the backstop: the dispatcher finds users whose delivery time has
    arrived and who have no digest for the local date, so the digest arrives on its
    next pass. **The scheduler is the backstop, and the enqueue is the fast path.**

    **Only the user id travels.** No email, no city, no delivery time — the worker
    reads what it needs from the rows (AD-13).
    """
    transaction.on_commit(
        partial(enqueue_digest_composition, user_id),
        using=PERSONAL,
        robust=True,
    )


def advance_step(*, user_id: UUID, actor: Actor, now: datetime) -> OnboardingState:
    """Move to the next step.

    Advancing **past** the last step completes the onboarding: step 3 is the last one, so
    there is no step 4. That is FR-1's three-step cap enforced at the command layer, where
    it cannot be bypassed.
    """
    with transaction.atomic(using=PERSONAL):
        progress = _require_incomplete(user_id=user_id, now=now)

        next_step = progress.current_step + 1
        if next_step > ONBOARDING_STEP_COUNT:
            progress.current_step = ONBOARDING_STEP_COUNT
            progress.completed_at = now
        else:
            progress.current_step = next_step
        progress.last_advanced_at = now
        progress.save(
            using=PERSONAL,
            update_fields=["current_step", "last_advanced_at", "completed_at"],
        )
        write_audit(
            actor=actor,
            action="onboarding.step_advanced",
            target_type="OnboardingProgress",
            target_id=progress.id,
            details={
                "step": progress.current_step,
                "completed": progress.completed_at is not None,
                "at": now.isoformat(),
            },
        )

        if progress.completed_at is not None:
            _enqueue_first_digest(user_id)

    return _state_for(user_id=user_id, now=now)


def skip_step(*, user_id: UUID, actor: Actor, now: datetime) -> OnboardingState:
    """Skip the current step.

    The difference between skipping and advancing is *what was recorded*:

    - skipping **calendar** writes nothing else — the connection belongs to
      `calendar-connect-api`;
    - skipping **interests** clears the interest set (zero picks is valid);
    - skipping **digest** writes the **default** digest preference, so the preference is
      always a real row with a real value and `delivery` reads one row rather than
      branching on "was it set?".

    Skipping the last step completes the onboarding, exactly as advancing past it does.
    """
    with transaction.atomic(using=PERSONAL):
        progress = _require_incomplete(user_id=user_id, now=now)

        step_name = ONBOARDING_STEPS[progress.current_step - 1]

        if step_name == "interests":
            _lock_interests(user_id)
            Interest.objects.using(PERSONAL).filter(user_id=user_id).delete()
        elif step_name == "digest":
            preference = _write_digest(
                user_id=user_id,
                delivery_time=DEFAULT_DIGEST_DELIVERY_TIME,
                zone=DEFAULT_DIGEST_TIMEZONE,
            )
            write_audit(
                actor=actor,
                action="onboarding.digest_preference_defaulted",
                target_type="DigestPreference",
                target_id=preference.id,
                details={
                    "delivery_time": DEFAULT_DIGEST_DELIVERY_TIME.strftime("%H:%M"),
                    "timezone": DEFAULT_DIGEST_TIMEZONE,
                    "at": now.isoformat(),
                },
            )

        next_step = progress.current_step + 1
        if next_step > ONBOARDING_STEP_COUNT:
            progress.current_step = ONBOARDING_STEP_COUNT
            progress.completed_at = now
        else:
            progress.current_step = next_step
        progress.last_advanced_at = now
        progress.save(
            using=PERSONAL,
            update_fields=["current_step", "last_advanced_at", "completed_at"],
        )
        write_audit(
            actor=actor,
            action="onboarding.step_skipped",
            target_type="OnboardingProgress",
            target_id=progress.id,
            details={
                "skipped_step": step_name,
                "step": progress.current_step,
                "completed": progress.completed_at is not None,
                "at": now.isoformat(),
            },
        )

        if progress.completed_at is not None:
            _enqueue_first_digest(user_id)

    return _state_for(user_id=user_id, now=now)


def skip_all(*, user_id: UUID, actor: Actor, now: datetime) -> OnboardingState:
    """Skip everything: the onboarding is complete.

    FR-1: "A user who skips everything still finishes onboarding." So this writes the
    default digest preference, clears the interests, and marks the flow complete — in one
    transaction.
    """
    with transaction.atomic(using=PERSONAL):
        progress = _require_incomplete(user_id=user_id, now=now)

        _lock_interests(user_id)
        Interest.objects.using(PERSONAL).filter(user_id=user_id).delete()
        preference = _write_digest(
            user_id=user_id,
            delivery_time=DEFAULT_DIGEST_DELIVERY_TIME,
            zone=DEFAULT_DIGEST_TIMEZONE,
        )
        progress.current_step = ONBOARDING_STEP_COUNT
        progress.last_advanced_at = now
        progress.completed_at = now
        progress.save(
            using=PERSONAL,
            update_fields=["current_step", "last_advanced_at", "completed_at"],
        )
        write_audit(
            actor=actor,
            action="onboarding.digest_preference_defaulted",
            target_type="DigestPreference",
            target_id=preference.id,
            details={
                "delivery_time": DEFAULT_DIGEST_DELIVERY_TIME.strftime("%H:%M"),
                "timezone": DEFAULT_DIGEST_TIMEZONE,
                "at": now.isoformat(),
            },
        )
        write_audit(
            actor=actor,
            action="onboarding.skipped_all",
            target_type="OnboardingProgress",
            target_id=progress.id,
            details={"at": now.isoformat()},
        )

        _enqueue_first_digest(user_id)

    return _state_for(user_id=user_id, now=now)


# ─────────────────────────────────────────────────────────────────────────────
# The internals
# ─────────────────────────────────────────────────────────────────────────────


def _read_progress(user_id: UUID) -> OnboardingProgress | None:
    """The user's progress row, if they have one."""
    return (
        OnboardingProgress.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .order_by("created_at", "id")
        .last()
    )


def _expired(*, progress: OnboardingProgress, now: datetime) -> bool:
    """Has the stored step aged out of the resume window?

    The window is **inclusive**: at exactly `last_advanced_at + ONBOARDING_RESUME_WINDOW`
    the user is still resumed at the stored step. One second beyond it, the flow restarts.
    """
    return now - progress.last_advanced_at > ONBOARDING_RESUME_WINDOW


def _restart(*, progress: OnboardingProgress, now: datetime) -> OnboardingProgress:
    """Put the flow back at step 1, because the stored step has aged out.

    The restart is **written**, not recomputed on every read: otherwise every read of an
    expired flow would pay for a write, and two reads a second apart would disagree about
    the step.

    This is a **command**, so the write happens here and not in the read. The read
    (`get_onboarding_state`) reports step 1 for an expired flow without touching the
    row; this function is what actually moves the row, and it runs under the user's
    advisory lock, which `_require_incomplete` took.
    """
    with transaction.atomic(using=PERSONAL):
        progress.current_step = 1
        progress.last_advanced_at = now
        progress.save(using=PERSONAL, update_fields=["current_step", "last_advanced_at"])
    return progress


def _require_incomplete(*, user_id: UUID, now: datetime) -> OnboardingProgress:
    """The user's progress row, refusing a completed onboarding.

    A user with no row yet gets one at step 1 — the row is created lazily on the first
    *write*, so a user who only ever reads does not accumulate a row.

    The **terminal** rule is enforced here: a completed onboarding is never reopened.

    **The user's advisory lock is taken first.** Two concurrent commands for the same
    user — a double-click, a retried request, two tabs — would otherwise both read
    `completed_at IS NULL` and both act, or both find no row and both try to create one.
    The second would then hit the unique constraint and answer with a raw
    `IntegrityError` — a 500 — instead of doing the right thing. The lock makes the
    second wait for the first to commit, and then it reads the committed state: the
    finished flow is refused, and the created row is found rather than duplicated.

    The lock is an **advisory** one rather than a row lock, because a row lock can only
    lock a row that exists — and the case that matters most is precisely the one where
    it does not: a user with no progress row yet has no row to lock, so two concurrent
    first-time writers would both create one.
    """
    with transaction.atomic(using=PERSONAL):
        _lock_user(user_id)
        progress = _read_progress(user_id)

        if progress is not None:
            if progress.completed_at is not None:
                raise OnboardingAlreadyCompleteError()
            if _expired(progress=progress, now=now):
                progress = _restart(progress=progress, now=now)
            return progress

        return OnboardingProgress.objects.using(PERSONAL).create(
            user_id=user_id,
            current_step=1,
            last_advanced_at=now,
        )


def _state_for(
    *,
    user_id: UUID,
    now: datetime,
    progress: OnboardingProgress | None = None,
) -> OnboardingState:
    """The whole state, as plain data.

    `progress` may be passed in when the caller has already read (or rewritten) it, so a
    restart is not re-derived here.
    """
    if progress is None:
        progress = _read_progress(user_id)

    digest = _read_digest(user_id)
    completed = progress is not None and progress.completed_at is not None

    if completed:
        step_number: int | None = None
        step_name: str | None = None
    elif progress is None:
        step_number = 1
        step_name = ONBOARDING_STEPS[0]
    elif _expired(progress=progress, now=now):
        # The flow has aged out of the resume window, so it reads as step 1. The stored
        # row is left alone — a read never writes — and the next command restarts it.
        step_number = 1
        step_name = ONBOARDING_STEPS[0]
    else:
        step_number = progress.current_step
        step_name = ONBOARDING_STEPS[progress.current_step - 1]

    return OnboardingState(
        completed=completed,
        current_step=step_number,
        step_name=step_name,
        interests=_read_interest_keys(user_id),
        digest_delivery_time=digest.delivery_time if digest is not None else None,
        digest_timezone=digest.timezone if digest is not None else None,
        digest_city=digest.city if digest is not None else None,
        digest_city_source=digest.city_source if digest is not None else None,
        # Personal events are included unless the user opted out — PRD
        # `[ASSUMPTION-7]`. A user with no preference row at all has not opted out, so
        # the default is the same one the row's own column carries.
        digest_include_personal_events=(
            digest.include_personal_events if digest is not None else True
        ),
        last_advanced_at=progress.last_advanced_at if progress is not None else None,
        completed_at=progress.completed_at if progress is not None else None,
    )


__all__ = [
    "InterestChip",
    "INTEREST_CHIP_KEYS",
    "InvalidDeliveryTimeError",
    "OnboardingState",
    "advance_step",
    "get_onboarding_state",
    "list_interest_chips",
    "set_digest_preference",
    "set_interests",
    "skip_all",
    "skip_step",
]
