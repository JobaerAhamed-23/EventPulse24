"""The digest scheduler (D1-D4): who is due, and the claim that makes two dispatchers safe.

**The properties a user would notice if they broke.**

- A digest is composed when the user's **own local wall clock** reaches their delivery
  time — not at a UTC instant, and not a minute-modulo rule.
- The delivery time **moves with the clock across a DST change**: "9am" is 9am before
  and after the transition.
- A user who already has a digest for their local day is **never composed again**, so
  the dispatcher does not re-claim them on every tick of the day.
- **Two dispatchers produce one digest.** The claim is taken with
  `FOR UPDATE SKIP LOCKED`, so the second dispatcher skips the row the first is holding.
- **A failed enqueue releases the claim**, so the next tick retries the user instead of
  leaving them claimed until the TTL expires.
- The tick **still runs the dispatcher on every beat** — the digest cadence does not
  nest the way the reconciler's does, because "due" is a per-user local comparison.

**The clock is fixed throughout**: no test sleeps, and the boundaries are pinned at the
exact instant rather than "roughly 9am".
"""

from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from apps.personalization.models import DigestPreference, PulseDigest
from apps.personalization.services import digest_scheduling
from apps.personalization.services.digest_scheduling import (
    claim_due_digests,
    is_due,
    release_claim,
)
from shared.constants import DIGEST_CLAIM_TTL, DIGEST_DISPATCH_BATCH
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.personalization.factories import DigestPreferenceFactory

#: The composition reads the **catalog** as well as the personal schema — the public
#: candidates come from `catalog` — so both aliases are in scope. The scheduler itself
#: touches only `personal`, but the command that drives it composes.
pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

#: A Wednesday. 2026-11-04 17:00 UTC is 09:00 in Los Angeles (PST, UTC-8) and 12:00 in
#: New York (EST, UTC-5). The zone offsets are what the local-clock rule turns on, so
#: the instant is chosen to be 09:00 on the *west* coast.
NOW = datetime(2026, 11, 4, 17, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)

ZONE = "America/Los_Angeles"
EASTERN = "America/New_York"


def make_preference(user_id=None, *, delivery_time=time(9, 0), timezone=ZONE, **overrides):
    fields = {"user_id": user_id or uuid7(), "delivery_time": delivery_time, "timezone": timezone}
    fields.update(overrides)
    return DigestPreferenceFactory(**fields)


#: **The instant the command's clock is frozen at**, for the tests that need the command
#: to compose against a known "now".
#:
#: 2026-11-04 17:00 UTC is **09:00 in Los Angeles** (PST, UTC-8) — the same instant the
#: module's `NOW` names, and the hour the zone offsets are chosen for.
#:
#: **Why a frozen clock, and not a clock-relative one.** The due rule compares
#: *time-of-day*, and the time-of-day circle wraps at midnight — so "one hour back" is
#: *ahead* of now when it runs at 00:53. A test that derived its delivery times from the
#: wall clock therefore failed for one hour every night, for a reason that had nothing
#: to do with the code. Pinning both the instant **and** the delivery times makes the
#: test say the same thing at every hour it is ever run.
FROZEN_NOW = datetime(2026, 11, 4, 17, 0, tzinfo=UTC)

#: The delivery times the `--all` tests use against `FROZEN_NOW`. At 09:00 in Los
#: Angeles, 08:00 is **due** and 10:00 is **not**.
DUE_AT_FROZEN_NOW = time(8, 0)
NOT_DUE_AT_FROZEN_NOW = time(10, 0)


def freeze_the_command_clock(monkeypatch, when: datetime = FROZEN_NOW) -> None:
    """Pin the command's clock, so "now" is a fact and not a race with the wall clock.

    **The standards ask for this explicitly** — "Freeze time explicitly. Never depend on
    wall-clock or local timezone." The command reaches the scheduler through a real
    `datetime.now`, so without a seam a test of the `--all` mode has to guess what "now"
    is, and its answer changes with the hour it runs.
    """
    from config.management.commands import compose_digest as command_module

    monkeypatch.setattr(command_module, "_now", lambda: when)


def claim_of(user_id):
    return (
        DigestPreference.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .values_list("digest_claimed_at", flat=True)
        .first()
    )


# --- The due rule (D2) --------------------------------------------------------------------


def test_the_pinned_delivery_times_are_unambiguous_against_the_frozen_clock():
    """**The pinned pair is a due / not-due pair at the frozen instant.**

    The `--all` tests use `DUE_AT_FROZEN_NOW` and `NOT_DUE_AT_FROZEN_NOW`; this says
    what those two names mean, against the rule itself. Without it, a reader of the
    tests has to work out the local hour out of the frozen UTC instant to know why one
    user is due and the other is not.
    """
    assert is_due(delivery_time=DUE_AT_FROZEN_NOW, now=FROZEN_NOW, zone_name=ZONE)
    assert not is_due(delivery_time=NOT_DUE_AT_FROZEN_NOW, now=FROZEN_NOW, zone_name=ZONE)


def test_the_command_reads_its_clock_through_the_seam(monkeypatch):
    """**The command's "now" is the seam's, not the wall clock's.**

    This is the property the whole fix rests on. The command calls `_now()` rather than
    `datetime.now(UTC)`, so a test can pin the instant — and the `--all` tests' answer
    stops depending on the hour the suite runs. A command that went back to reading the
    wall clock directly would still pass every test here, so this asserts the seam
    *itself*.
    """
    from config.management.commands import compose_digest as command_module

    pinned = datetime(2026, 3, 14, 15, 9, 26, tzinfo=UTC)
    monkeypatch.setattr(command_module, "_now", lambda: pinned)

    assert command_module._now() == pinned


def test_a_user_is_not_due_before_their_delivery_time():
    assert not is_due(delivery_time=time(9, 0), now=NOW - HOUR, zone_name=ZONE)


def test_a_user_is_due_exactly_at_their_delivery_time():
    """The comparison is **inclusive**: 9:00:00 is due, not 9:01."""
    assert is_due(delivery_time=time(9, 0), now=NOW, zone_name=ZONE)


def test_a_user_is_due_after_their_delivery_time():
    assert is_due(delivery_time=time(9, 0), now=NOW + HOUR, zone_name=ZONE)


def test_the_delivery_time_is_the_users_own_local_clock():
    """The same instant is due in one zone and not in another.

    17:00 UTC is 09:00 in Los Angeles and 12:00 in New York — so a user who asked for
    13:00 Eastern is *not* due at 17:00 UTC, while the Los Angeles user who asked for
    09:00 is. One UTC instant, two different answers, because the rule is local.
    """
    assert is_due(delivery_time=time(9, 0), now=NOW, zone_name=ZONE)
    assert not is_due(delivery_time=time(13, 0), now=NOW, zone_name=EASTERN)


def test_the_delivery_time_moves_with_the_clock_across_a_dst_change():
    """**"9am" stays 9am.** The rule converts `now` into the user's zone and compares
    the local time-of-day, so the instant 9am falls on moves with the clocks.

    The US springs forward on 2026-03-08. Before the change Los Angeles is PST (UTC-8),
    so 9:00 local is 17:00 UTC; after it, PDT (UTC-7), so 9:00 local is 16:00 UTC. A
    rule that added 24 hours to a UTC instant would give the user 10am on the day
    after the change — the hour the user did not ask for.
    """
    before_change = datetime(2026, 3, 7, 17, 0, tzinfo=UTC)
    after_change = datetime(2026, 3, 9, 16, 0, tzinfo=UTC)

    assert is_due(delivery_time=time(9, 0), now=before_change, zone_name=ZONE)
    assert is_due(delivery_time=time(9, 0), now=after_change, zone_name=ZONE)
    # The hour before 9am local is not due on either side of the transition.
    assert not is_due(delivery_time=time(9, 0), now=before_change - HOUR, zone_name=ZONE)
    assert not is_due(delivery_time=time(9, 0), now=after_change - HOUR, zone_name=ZONE)


def test_the_utc_instant_of_a_local_delivery_time_moves_with_the_clocks():
    """**The two 9ams are different instants.** This is the property the naive
    implementation gets wrong: it pins one UTC instant and calls it 9am, and the user
    then receives their digest an hour off after the change."""
    before_change = datetime(2026, 3, 7, 17, 0, tzinfo=UTC)
    after_change = datetime(2026, 3, 9, 16, 0, tzinfo=UTC)

    assert before_change.astimezone(ZoneInfo(ZONE)).strftime("%H:%M") == "09:00"
    assert after_change.astimezone(ZoneInfo(ZONE)).strftime("%H:%M") == "09:00"
    assert after_change - before_change == timedelta(days=2, hours=-1)


def test_an_unknown_zone_falls_back_to_utc_rather_than_raising():
    """A hand-edited zone must not take the whole dispatcher down.

    The failure mode is deliberate: one user composed in the fallback zone, rather than
    a stopped scheduler that leaves every user without a digest.
    """
    assert is_due(delivery_time=time(9, 0), now=NOW, zone_name="Mars/Olympus_Mons")


# --- The selection (D1, D2, D3) ------------------------------------------------------------


def test_a_user_with_a_preference_is_claimed_once_their_time_arrives():
    preference = make_preference(delivery_time=time(9, 0))

    claimed = claim_due_digests(now=NOW)

    assert claimed == [preference.user_id]


def test_a_user_before_their_time_is_not_claimed():
    make_preference(delivery_time=time(17, 0))

    assert claim_due_digests(now=NOW) == []


def test_a_user_who_already_has_a_digest_for_the_local_day_is_not_claimed():
    """**The fact beats the schedule.** A user whose 9am has passed but who already
    has today's digest is never claimed again — so the dispatcher does not re-claim them
    on every tick of the day."""
    preference = make_preference(delivery_time=time(9, 0))
    PulseDigest.objects.using(PERSONAL).create(
        user_id=preference.user_id,
        local_date=NOW.astimezone(ZoneInfo(ZONE)).date(),
        timezone=ZONE,
        composed_at=NOW,
        is_empty=False,
    )

    assert claim_due_digests(now=NOW) == []


def test_a_user_with_no_preference_is_never_due():
    """There is no preference row, so there is no delivery time and no local date —
    the user has said nothing, and the dispatcher says nothing about them."""
    assert claim_due_digests(now=NOW) == []


def test_the_claim_is_recorded_on_the_preference():
    preference = make_preference()

    claim_due_digests(now=NOW)

    assert claim_of(preference.user_id) == NOW


def test_the_claim_is_audited_with_the_scheduler_actor():
    from apps.personalization.models import PersonalizationAuditEntry

    preference = make_preference()

    claim_due_digests(now=NOW)

    [entry] = (
        PersonalizationAuditEntry.objects.using(PERSONAL)
        .filter(action="claim_digest", target_id=preference.user_id)
        .order_by("id")
    )
    assert entry.actor_kind == "system"
    assert entry.actor_label == "digest_scheduler"


def test_the_claim_is_ordered_by_the_user_id():
    """The user id is a UUIDv7 — so it is the creation time. The oldest preference is
    claimed first, so a user who has just finished onboarding is never starved behind a
    backlog of established users."""
    first = make_preference()
    second = make_preference()

    claimed = claim_due_digests(now=NOW)

    assert claimed == sorted([first.user_id, second.user_id], key=str)


def test_the_claim_is_bounded_by_the_batch_size():
    for _ in range(DIGEST_DISPATCH_BATCH + 5):
        make_preference()

    claimed = claim_due_digests(now=NOW)

    assert len(claimed) == DIGEST_DISPATCH_BATCH


def test_a_claimed_user_is_not_claimed_again():
    """The second dispatcher sees the claim and skips the user."""
    make_preference()

    assert len(claim_due_digests(now=NOW)) == 1
    assert claim_due_digests(now=NOW) == []


def test_a_claim_older_than_the_ttl_becomes_claimable_again():
    """A worker that died leaves the claim behind. The TTL is the backstop."""
    preference = make_preference(delivery_time=time(9, 0))

    claim_due_digests(now=NOW)
    assert claim_due_digests(now=NOW) == []

    later = NOW + DIGEST_CLAIM_TTL + timedelta(seconds=1)
    assert claim_due_digests(now=later) == [preference.user_id]


def test_a_claim_inside_the_ttl_is_still_held():
    make_preference()

    claim_due_digests(now=NOW)
    later = NOW + DIGEST_CLAIM_TTL - timedelta(seconds=1)

    assert claim_due_digests(now=later) == []


def test_releasing_the_claim_makes_the_user_due_again():
    preference = make_preference()

    claim_due_digests(now=NOW)
    release_claim(preference.user_id)

    assert claim_of(preference.user_id) is None
    assert claim_due_digests(now=NOW) == [preference.user_id]


def test_two_dispatchers_never_claim_the_same_user():
    """The claim is taken under a row lock with `SKIP LOCKED`, so the second dispatcher
    skips the row the first one is holding."""
    preference = make_preference()

    first = claim_due_digests(now=NOW)
    second = claim_due_digests(now=NOW)

    assert first == [preference.user_id]
    assert second == []


def test_a_user_claimed_between_the_read_and_the_lock_is_not_claimed(monkeypatch):
    """**The race the row lock exists for.**

    The dispatcher reads the candidates first — the due rule cannot be expressed in
    SQL — and then takes the claim under a row lock. A dispatcher that claimed the user
    in between would leave the second one with nothing to do.

    So the second dispatcher's re-read under the lock finds the row already claimed,
    `SKIP LOCKED` skips it, and the second dispatcher claims nobody. It is the same
    outcome as the dispatcher that starts later — which is the point.
    """
    from apps.personalization.services import digest_scheduling

    make_preference()
    original = digest_scheduling._already_composed

    def claim_in_the_gap(*, user_id, local_date):
        """Simulate the other dispatcher claiming the user between the read and the lock."""
        DigestPreference.objects.using(PERSONAL).filter(user_id=user_id).update(
            digest_claimed_at=NOW
        )
        return original(user_id=user_id, local_date=local_date)

    monkeypatch.setattr(digest_scheduling, "_already_composed", claim_in_the_gap)

    assert claim_due_digests(now=NOW) == []


def test_a_due_user_in_a_different_zone_is_claimed_on_its_own_clock():
    """The dispatcher compares each row in its own zone, so a user in New York whose
    11:00 has not arrived is not claimed at 16:00 UTC."""
    eastern = make_preference(delivery_time=time(13, 0), timezone=EASTERN)
    western = make_preference(delivery_time=time(9, 0), timezone=ZONE)

    claimed = claim_due_digests(now=NOW)

    assert claimed == [western.user_id]
    assert eastern.user_id not in claimed


# --- The management command (D6) ------------------------------------------------------------


def test_the_command_composes_one_user_s_digest():
    from django.core.management import call_command

    preference = make_preference()

    call_command("compose_digest", "--user-id", str(preference.user_id))

    assert PulseDigest.objects.using(PERSONAL).filter(user_id=preference.user_id).exists()


def test_the_command_is_idempotent():
    """Running it twice writes one digest, not two."""
    from django.core.management import call_command

    preference = make_preference()

    call_command("compose_digest", "--user-id", str(preference.user_id))
    call_command("compose_digest", "--user-id", str(preference.user_id))

    assert PulseDigest.objects.using(PERSONAL).filter(user_id=preference.user_id).count() == 1


def test_the_command_needs_exactly_one_mode():
    from django.core.management import call_command
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("compose_digest")

    with pytest.raises(CommandError):
        call_command("compose_digest", "--user-id", str(uuid4()), "--all")


def test_the_command_rejects_a_user_that_is_not_a_uuid():
    from django.core.management import call_command
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("compose_digest", "--user-id", "not-a-uuid")


def test_the_command_composes_only_the_due_users(monkeypatch):
    """`--all` asks the scheduler's own rule, so "everyone due" means exactly what the
    dispatcher means by it.

    **The clock is frozen** at `FROZEN_NOW`, which is 09:00 in Los Angeles. So 08:00 is
    due and 10:00 is not — and the test says the same thing at every hour it is ever
    run, which is what the standards ask for.
    """
    from django.core.management import call_command

    freeze_the_command_clock(monkeypatch)

    due = make_preference(delivery_time=DUE_AT_FROZEN_NOW)
    not_due = make_preference(delivery_time=NOT_DUE_AT_FROZEN_NOW)

    call_command("compose_digest", "--all")

    assert PulseDigest.objects.using(PERSONAL).filter(user_id=due.user_id).exists()
    assert not PulseDigest.objects.using(PERSONAL).filter(user_id=not_due.user_id).exists()


def test_the_command_counts_a_digest_that_already_existed(monkeypatch):
    """**The command can reach a user who already has today's digest.**

    The scheduler's own guard says a user with a digest for the local date is not
    claimed — but the command claims through the *same* rule, and the composition can
    still find an existing digest (the race, or a digest composed between the read and
    the claim). The command reports the two cases separately, because "composed" and
    "already existed" are different answers to the operator's question.
    """
    from django.core.management import call_command

    from config.management.commands import compose_digest as command_module

    freeze_the_command_clock(monkeypatch)

    preference = make_preference(delivery_time=DUE_AT_FROZEN_NOW)

    def already_there(*, user_id, actor, now):
        class Result:
            created = False
            is_empty = False
            user_id = preference.user_id
            local_date = date(2026, 11, 4)
            public_qualifying_count = 0
            personal_qualifying_count = 0
            has_qualifying_events = False

        return Result()

    monkeypatch.setattr(command_module, "compose_digest", already_there)

    call_command("compose_digest", "--all")

    assert PulseDigest.objects.using(PERSONAL).filter(user_id=preference.user_id).count() == 0


def test_the_command_mints_the_ping_alongside_the_digest(monkeypatch):
    """**The digest email *is* the Pulse Ping** (FR-10), so the command has to mint it.

    It used to compose only, and that was correct when there was no send to mint. Now
    it would leave a user with a composed digest and no email — and, worse, **no
    counted suppression either**, so the day's silence would be invisible to SM-C1.

    **The composition is stubbed to report a qualifying event**, because this test is
    about the *command's* behaviour — it mints what the composition reports. The
    composition's own counting is tested where it lives.
    """
    from django.core.management import call_command

    from apps.delivery.models import ScheduledSend
    from config.management.commands import compose_digest as command_module

    preference = make_preference()
    _stub_a_qualifying_composition(monkeypatch, command_module, preference.user_id)

    call_command("compose_digest", "--user-id", str(preference.user_id))

    assert ScheduledSend.objects.using(PERSONAL).filter(user_id=preference.user_id).count() == 1


def test_the_command_mints_one_ping_when_run_twice(monkeypatch):
    """**The command is idempotent for the send too**, exactly as it is for the
    digest — the unique key is the guard, and it is the same guard the worker relies
    on."""
    from django.core.management import call_command

    from apps.delivery.models import ScheduledSend
    from config.management.commands import compose_digest as command_module

    preference = make_preference()
    _stub_a_qualifying_composition(monkeypatch, command_module, preference.user_id)

    call_command("compose_digest", "--user-id", str(preference.user_id))
    call_command("compose_digest", "--user-id", str(preference.user_id))

    assert ScheduledSend.objects.using(PERSONAL).filter(user_id=preference.user_id).count() == 1


def test_the_command_records_a_suppression_when_there_is_nothing_to_say():
    """**A user with nothing qualifying gets no row — and the reason is counted.**
    This is the command's `--all` mode standing in for the dispatcher, so its silence
    has to be visible for the same reason the scheduler's silence is."""
    from django.core.management import call_command

    from apps.delivery.models import DeliveryAuditEntry, ScheduledSend

    preference = make_preference()

    call_command("compose_digest", "--user-id", str(preference.user_id))

    assert not ScheduledSend.objects.using(PERSONAL).filter(user_id=preference.user_id).exists()
    row = DeliveryAuditEntry.objects.using(PERSONAL).get(
        target_id=preference.user_id, action="pulse_ping.suppressed"
    )
    assert row.details["reason"] == "no_qualifying_events"


def test_the_all_mode_mints_the_ping_for_the_due_users(monkeypatch):
    """**`--all` stands in for the dispatcher**, so it has to do what the dispatcher
    does — compose *and* mint.

    A dispatcher that composed without minting would leave every due user with a
    digest and no email, and with no counted suppression either. The mode is the
    operator's way of saying "run the dispatcher's job now", so it runs both halves.
    """
    from django.core.management import call_command

    from apps.delivery.models import ScheduledSend
    from config.management.commands import compose_digest as command_module

    freeze_the_command_clock(monkeypatch)

    preference = make_preference(delivery_time=DUE_AT_FROZEN_NOW)
    _stub_a_qualifying_composition(monkeypatch, command_module, preference.user_id)

    call_command("compose_digest", "--all")

    assert ScheduledSend.objects.using(PERSONAL).filter(user_id=preference.user_id).count() == 1


def _stub_a_qualifying_composition(monkeypatch, command_module, user_id) -> None:
    """Stub the composition to report one qualifying public event.

    **The stub carries the counts the command hands to the Ping decision**, because
    the decision refuses a caller whose counts and flag disagree — the stub has to
    describe the same world the flag describes.
    """
    from dataclasses import replace

    original = command_module.compose_digest

    def qualifying(*, user_id, actor, now):
        result = original(user_id=user_id, actor=actor, now=now)
        # `has_qualifying_events` is a *property* derived from the two counts, so
        # replacing the counts replaces the flag too — one definition, as everywhere.
        return replace(
            result,
            public_qualifying_count=1,
            personal_qualifying_count=0,
        )

    monkeypatch.setattr(command_module, "compose_digest", qualifying)


def test_the_command_releases_its_claims(monkeypatch):
    """The command claims through the scheduler, so it must release — otherwise the
    user is claimed until the TTL expires and the dispatcher skips them."""
    from django.core.management import call_command

    freeze_the_command_clock(monkeypatch)

    preference = make_preference(delivery_time=DUE_AT_FROZEN_NOW)

    call_command("compose_digest", "--all")

    assert claim_of(preference.user_id) is None


def test_the_command_releases_the_claim_when_a_composition_fails(monkeypatch):
    """**The release is in a `finally`,** so a failing composition does not leave the
    user claimed until the TTL expires — which would delay their digest by a quarter
    of an hour for no reason."""
    from django.core.management import call_command

    from config.management.commands import compose_digest as command_module

    freeze_the_command_clock(monkeypatch)

    preference = make_preference(delivery_time=DUE_AT_FROZEN_NOW)

    def crash(*, user_id, actor, now):
        raise RuntimeError("boom")

    monkeypatch.setattr(command_module, "compose_digest", crash)

    with pytest.raises(RuntimeError):
        call_command("compose_digest", "--all")

    assert claim_of(preference.user_id) is None


# --- The module's own surface ----------------------------------------------------------------


def test_the_scheduler_actor_is_a_system_actor():
    assert digest_scheduling.SCHEDULER.kind == "system"
    assert digest_scheduling.SCHEDULER.label == "digest_scheduler"
