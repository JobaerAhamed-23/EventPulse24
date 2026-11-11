"""The trust loop closes: a report, a verdict, a score, a ranking.

**What this file is for.** The ten items before it each proved their own piece against its
own seam — the model, the intake, the commands, the admin, the score, the ranking, the
control. This file proves the **claim the intent was captured on**: that FR-59, FR-57 and
FR-16 are *one mechanism*, and that the loop closes end to end.

**Every step is driven through the surface a real actor would touch.**

- The user reports through `POST /api/personal/event-reports`, signed in, with a CSRF
  token — not by calling `report_event` directly.
- The editor gives their verdict through the **Django admin**, as a member of the
  `editorial` group with `is_superuser=False`, because AD-14 says the group is the surface
  and "it works for a superuser" proves nothing about a group.
- The stranded event reaches `in_review` through the **real confidence gate**: a venue
  registered in `US/Pacific` and a VEVENT carrying `TZID=America/New_York` is FR-60's A3
  conflict, `tz_inference_confidence = 0.60`, below `TZ_INFERENCE_CONFIDENCE_DIGEST`. No
  gate table is monkeypatched, because a patched gate proves the patch.
- The propagation is drained the way the worker's reconciler drains it.

**The clock is frozen.** Every service here takes `now`, so each boundary is asserted at
the exact second rather than near it.

**Nothing in `apps/`, `domain/` or `worker/` is modified by this item.** If a journey finds
a defect, it is a finding, not a patch smuggled into the item that was meant to measure.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.urls import reverse

from adapters.email.memory import InMemoryEmailAdapter
from adapters.throttle.memory import InMemoryThrottleAdapter
from apps.delivery.models import ReminderPlan, ScheduledSend, StateChangeNotice
from apps.delivery.services.delivery_messages import renderer_for
from apps.delivery.services.delivery_sweep import sweep_due_sends
from apps.delivery.services.reminder_plans import attach_default_plan, set_plan_slots
from apps.ingestion.models import (
    Event,
    EventStateChange,
    IngestionAuditEntry,
    ReviewItem,
    Source,
    SourceObservation,
)
from apps.ingestion.services.catalog_read import (
    EventNotFoundError,
    get_public_event_by_slug,
    list_public_candidates,
    list_public_events,
)
from apps.ingestion.services.editorial_review import approve_review_item, edit_and_publish
from apps.ingestion.services.ingest_source import ingest_source
from apps.ingestion.services.outbox import reconcile_outbox
from apps.ingestion.services.reliability import recompute_due
from apps.ingestion.services.url_feed_read import list_url_feed
from apps.ingestion.services.venue_registry import register_venue
from apps.personalization.models import DigestComposition, EventReport, SavedEvent
from apps.personalization.services import event_reports as event_reports_service
from apps.personalization.services.digest_composition import compose_digest
from apps.personalization.services.saved_events import save_event
from shared.actor import Actor
from shared.constants import (
    EVENT_REPORT_DAILY_LIMIT,
    RELIABILITY_ESCALATION_SCORE,
    RELIABILITY_MIN_OBSERVATIONS,
)
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient
from tests.ingestion.factories import EventFactory, SourceFactory, VenueFactory
from tests.ingestion.pipeline_support import ScriptedFetchPort, calendar, ics_source, vevent
from tests.personalization.factories import DigestPreferenceFactory
from worker import propagation

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

User = get_user_model()

#: A Wednesday. 16:00 UTC is 08:00 in Los Angeles (PST) and 09:00 in San Francisco's zone.
NOW = datetime(2026, 11, 4, 16, 0, tzinfo=UTC)

CITY = "Los Angeles"
ZONE = "America/Los_Angeles"

#: Far enough out to be in the catalog and near enough to be a digest candidate.
START = NOW + timedelta(days=2)

CHANGELIST = "admin:ingestion_reviewitem_changelist"
REPORT_URL = "/api/personal/event-reports"

#: The reminder slot the saver gets, so there is something that *could* fire wrongly.
SLOT = "1hr"


@pytest.fixture(autouse=True)
def pinned_clock(monkeypatch):
    """The wall clock, pinned to `NOW` for the whole module.

    **This is not decoration; the journeys do not work without it.** Every service in this
    codebase takes `now` as a parameter — but the two *surfaces* this file drives do not.
    `POST /api/personal/event-reports` calls `timezone.now()` itself, and so does the
    admin, because an HTTP request has no test's clock to borrow. With the wall clock
    running, an event placed two days after a frozen `NOW` in 2026 is an event in the past,
    the endpoint's visibility check answers 404, and the journey fails for a reason that
    has nothing to do with the loop.

    **`django.utils.timezone.now` is the one patch that reaches all of them**, because it
    is the function the surfaces, the ORM's `auto_now_add` and the services' defaults all
    call. A model field's `default=timezone.now` captured the function at import and is
    *not* reached — which is correct here: every timestamp this file asserts on is one a
    command was handed explicitly.
    """
    from django.utils import timezone

    monkeypatch.setattr(timezone, "now", lambda *args, **kwargs: NOW)


# ── the people ─────────────────────────────────────────────────────────────────────────


def _editorial_group() -> Group:
    """The `editorial` group, holding exactly the two review permissions (AD-14)."""
    group, _created = Group.objects.using(PERSONAL).get_or_create(name="editorial")
    group.permissions.set(
        Permission.objects.using(PERSONAL).filter(
            content_type__app_label="ingestion",
            codename__in=("change_reviewitem", "view_reviewitem"),
        )
    )
    return group


def make_editor(*, email: str = "editor@example.test"):
    """A staff member of the editorial group — **and deliberately not a superuser**.

    The acceptance criterion says "an editor (a group member, not a superuser)". A
    superuser holds every permission, so a journey driven by one would pass whether or not
    the group grant works at all.
    """
    user = User.objects.db_manager(PERSONAL).create_user(
        email=email, password="not-used-in-tests", is_staff=True, is_superuser=False
    )
    user.groups.add(_editorial_group())
    return user


def make_reader(*, email: str = "sam@example.test", city: str = CITY, zone: str = ZONE):
    """A signed-in digest reader: a real `User` row plus a digest preference.

    A real row, not a bare uuid, because this person has to **sign in** to report.
    """
    user = User.objects.db_manager(PERSONAL).create_user(email=email, password="pw")
    DigestPreferenceFactory(user_id=user.pk, timezone=zone, city=city, city_source="choice")
    return user


def signed_in(user) -> CsrfClient:
    client = CsrfClient()
    client.force_login(user)
    return client


# ── the catalog ────────────────────────────────────────────────────────────────────────


def make_event(*, source=None, title="Rooftop Cinema", city=CITY, start=START) -> Event:
    """A published, digest-eligible public event.

    `last_seen_at` is pinned to `NOW`: the digest's staleness bound is measured from it
    against the test's clock, and the column's default is the wall clock, so an event built
    with the default would be dropped before the composition ever saw it.
    """
    return EventFactory(
        title=title,
        source=source or SourceFactory(),
        venue=VenueFactory(city=city, venue_fingerprint=f"venue-{title}|{city}"),
        start_time_utc=start,
        end_time_utc=start + timedelta(hours=2),
        last_seen_at=NOW,
    )


def open_items(event) -> list[ReviewItem]:
    return list(
        ReviewItem.objects.using(CATALOG).filter(event_id=event.pk, status=ReviewItem.Status.OPEN)
    )


def audit(**filters) -> list[IngestionAuditEntry]:
    return list(IngestionAuditEntry.objects.using(CATALOG).filter(**filters).order_by("id"))


# ── the actions ────────────────────────────────────────────────────────────────────────


def report(client: CsrfClient, event, category: str = "wrong_date_time"):
    return client.post(
        REPORT_URL,
        data={"event_id": str(event.pk), "category": category},
        content_type="application/json",
    )


def admin_verdict(client, item, action: str):
    return client.post(reverse(CHANGELIST), {"action": action, "_selected_action": [str(item.pk)]})


def drain_the_outbox(*, now=NOW) -> int:
    """Propagate every unpropagated change, the way the worker's reconciler does."""
    applied = 0
    for change in (
        EventStateChange.objects.using(CATALOG)
        .filter(propagated_at__isnull=True)
        .order_by("event_version")
    ):
        propagation.propagate(state_change_id=change.id, now=now)
        applied += 1
    return applied


def save_with_a_reminder(user, event):
    """The saver, with one reminder slot minted — so something *could* fire wrongly."""
    from apps.delivery.services.reminder_plan_read import resolve_target

    saved = save_event(user_id=user.pk, event_id=event.id, actor=Actor.user(user.pk), now=NOW).saved
    attach_default_plan(
        user_id=user.pk,
        target_kind=ReminderPlan.TargetKind.SAVED_EVENT,
        target_id=event.id,
        actor=Actor.user(user.pk),
        now=NOW,
    )
    set_plan_slots(
        user_id=user.pk,
        target_kind=ReminderPlan.TargetKind.SAVED_EVENT,
        target_id=event.id,
        slots=(SLOT,),
        actor=Actor.user(user.pk),
        now=NOW,
        send_target=resolve_target(user_id=user.pk, target_kind="saved_event", target_id=event.id),
    )
    return saved


def pending_reminders(user, event):
    return ScheduledSend.objects.using(PERSONAL).filter(
        user_id=user.pk,
        target_kind="saved_event",
        target_id=event.id,
        status=ScheduledSend.Status.PENDING,
    )


def compose(user, *, now=NOW):
    return compose_digest(user_id=user.pk, actor=Actor.user(user.pk), now=now)


def composed_event_ids(result) -> set:
    return {row.event_id for row in result.compositions}


# ══ 1. The chain ═══════════════════════════════════════════════════════════════════════


class TestTheLoopCloses:
    """A user reports, an editor rejects, the event leaves the world, the score learns."""

    def test_the_whole_chain(self):
        reporter = make_reader()
        saver = make_reader(email="kim@example.test")
        editor = make_editor()

        source = SourceFactory(name="The flaky feed")
        event = make_event(source=source)
        # **The control.** A second event from a healthy source, in the same city, with the
        # same shape. Every "it is gone" assertion below is paired with "and this one is
        # not" — so a reject that emptied the whole catalog would fail rather than pass.
        control = make_event(title="Harbour Jazz")

        save_with_a_reminder(saver, event)

        # --- before: it is public, it is in a digest, and a reminder is waiting ---
        before = compose(reporter)
        assert event.id in composed_event_ids(before)
        assert pending_reminders(saver, event).count() == 1

        # --- 1. the signed-in user reports it, through the API ---
        response = report(signed_in(reporter), event, "does_not_exist")
        assert response.status_code == 201
        assert response.json() == {"reported": True, "category": "does_not_exist"}

        # --- 2. a `user_reported` item appears, carrying no user identity ---
        [item] = open_items(event)
        assert item.reason == ReviewItem.Reason.USER_REPORTED
        assert item.reports_does_not_exist == 1
        assert item.report_count == 1
        # The deadline FR-57 asks for, 24 hours out.
        assert item.due_at == item.raised_at + timedelta(hours=24)

        # **No user identity crosses the wall (AD-3).** The row has no column that could
        # carry one — asserted against the table's own field list, so a column added later
        # fails here rather than leaking quietly.
        columns = {field.name for field in ReviewItem._meta.get_fields()}
        assert not {"user", "user_id", "reporter", "reporter_id"} & columns
        # And the reporter is in `personal`, where they belong.
        assert (
            EventReport.objects.using(PERSONAL)
            .filter(user_id=reporter.pk, event_id=event.id)
            .exists()
        )

        # --- 3. the event is still in the digest: a report never hides anything ---
        event.refresh_from_db(using=CATALOG)
        assert event.publication_status == Event.PublicationStatus.PUBLISHED
        onlooker = make_reader(email="lee@example.test")
        assert event.id in composed_event_ids(compose(onlooker))

        # --- 4. an editor — a group member, not a superuser — rejects it ---
        assert editor.is_superuser is False
        client = signed_in(editor)
        assert admin_verdict(client, item, "reject_items").status_code == 302

        item.refresh_from_db(using=CATALOG)
        assert (item.status, item.resolution) == (
            ReviewItem.Status.RESOLVED,
            ReviewItem.Resolution.REJECTED,
        )
        assert [entry.actor_id for entry in audit(action="review_item_rejected")] == [editor.pk]

        assert reconcile_outbox(now=NOW + timedelta(minutes=10)) == 1
        drain_the_outbox()

        # --- 5. it leaves the digest, the public URL and the sitemap ---
        event.refresh_from_db(using=CATALOG)
        assert event.publication_status == Event.PublicationStatus.REJECTED
        # It is never deleted.
        assert Event.objects.using(CATALOG).filter(pk=event.pk).exists()

        candidates = list_public_candidates(now=NOW)
        assert event.id not in {candidate.id for candidate in candidates}
        assert control.id in {candidate.id for candidate in candidates}

        after = make_reader(email="ash@example.test")
        composed = composed_event_ids(compose(after))
        assert event.id not in composed
        assert control.id in composed

        listed, _total = list_public_events(now=NOW)
        assert event.id not in {row.id for row in listed}
        assert control.id in {row.id for row in listed}

        with pytest.raises(EventNotFoundError):
            get_public_event_by_slug(slug=event.slug)
        assert get_public_event_by_slug(slug=control.slug) is not None

        feed = list_url_feed(now=NOW, page_size=500)
        paths = {entry.path for entry in feed.items}
        assert f"/events/{event.slug}" not in paths
        assert f"/events/{control.slug}" in paths

        # --- 6. the saver is handled as `event-rejection-state` decided ---
        # The reminder is cancelled, so nothing false can fire...
        assert pending_reminders(saver, event).count() == 0
        # ...no email of any kind goes out — not a reminder, not a notice...
        port = InMemoryEmailAdapter()
        counts = sweep_due_sends(
            port=port,
            renderer=renderer_for,
            resolve_recipient=lambda user_id: f"{user_id}@example.test",
            now=NOW + timedelta(days=2),
        )
        assert counts.sent == 0
        assert port.sent == []
        assert not StateChangeNotice.objects.using(PERSONAL).filter(user_id=saver.pk).exists()
        # ...and their save itself is untouched: they chose it, and it stays theirs.
        assert (
            SavedEvent.objects.using(PERSONAL).filter(user_id=saver.pk, event_id=event.id).exists()
        )

        # --- 7. the source's observation count rises ---
        observations = list(SourceObservation.objects.using(CATALOG).filter(source_id=source.pk))
        assert [observation.kind for observation in observations] == ["rejected"]
        # The report count is frozen onto the observation from the item being closed, so
        # the recompute never has to read `personal`.
        assert observations[0].report_count == 1
        assert observations[0].event_id == event.id
        # And the healthy source learned nothing, because nothing happened to it.
        assert (
            not SourceObservation.objects.using(CATALOG)
            .filter(source_id=control.source_id)
            .exists()
        )


# ══ 2. The score moves the ranking ═════════════════════════════════════════════════════


def collapse(source, *, count: int = RELIABILITY_MIN_OBSERVATIONS) -> list[Event]:
    """Reject `count` of a source's events, each through the real command.

    **Why thirty.** With `α = β = 5` a source with `p` approvals and `n` rejects scores
    `(5 + p) / (10 + p + n)`. Thirty rejects and no approvals is `5 / 40 = 0.125` — below
    `RELIABILITY_ESCALATION_SCORE` (0.30) at exactly `RELIABILITY_MIN_OBSERVATIONS` (30),
    so **both** halves of `should_escalate` are satisfied and neither is satisfied by
    accident. Twenty-nine rejects would leave the min-N unmet; a higher score would leave
    the threshold unmet.

    **One event per reject, because one observation per review item is a constraint.**
    `source_observation_item_uq` permits a single observation per item, and all of an
    event's reports collapse onto one item — so thirty observations need thirty items,
    which need thirty events.
    """
    from apps.ingestion.services.editorial_review import reject_review_item
    from apps.ingestion.services.review_queue import raise_review_item

    editor = Actor.user(uuid4())
    rejected = []
    for index in range(count):
        event = make_event(source=source, title=f"Bad listing {index}")
        item = raise_review_item(
            event=event,
            reason=ReviewItem.Reason.USER_REPORTED,
            category=ReviewItem.ReportCategory.DOES_NOT_EXIST,
            actor=Actor.system("event_report"),
            now=NOW,
        ).item
        reject_review_item(item_id=item.id, actor=editor, now=NOW)
        rejected.append(event)
    return rejected


class TestTheScoreMovesTheRanking:
    """FR-16's second half: the score is computed, it escalates, and ranking consumes it."""

    def test_enough_rejects_escalate_the_source_without_pausing_it(self):
        source = SourceFactory(name="The collapsing feed")
        healthy = SourceFactory(name="The dependable feed")
        before = Source.objects.using(CATALOG).get(pk=source.pk)

        collapse(source)
        assert (
            SourceObservation.objects.using(CATALOG).filter(source_id=source.pk).count()
            == RELIABILITY_MIN_OBSERVATIONS
        )

        # **The job the tick calls**, not `recompute_source` — the weekly path is what
        # FR-16 promises, and a direct call would skip the claim.
        results = recompute_due(now=NOW)
        by_source = {result.source_id: result for result in results}

        collapsed = by_source[source.pk]
        assert collapsed.score == Decimal("0.13")  # 5/40 = 0.125, stored at two decimals
        assert collapsed.score < RELIABILITY_ESCALATION_SCORE
        assert collapsed.counts.observations == RELIABILITY_MIN_OBSERVATIONS
        assert collapsed.escalated is True

        # A `source_reliability` item is open, and it is about the Source, not an Event.
        [item] = list(
            ReviewItem.objects.using(CATALOG).filter(
                source_id=source.pk,
                reason=ReviewItem.Reason.SOURCE_RELIABILITY,
                status=ReviewItem.Status.OPEN,
            )
        )
        assert item.event_id is None

        # **Escalation, never removal.** Only the two score columns moved.
        after = Source.objects.using(CATALOG).get(pk=source.pk)
        assert after.status == Source.Status.ACTIVE
        moved = {
            field.name
            for field in Source._meta.concrete_fields
            if getattr(before, field.attname) != getattr(after, field.attname)
        }
        assert moved == {"reliability_score", "reliability_scored_at", "reliability_claimed_at"}

        # The healthy source was recomputed too, and sits at the prior with no escalation.
        assert by_source[healthy.pk].score == Decimal("0.50")
        assert by_source[healthy.pk].escalated is False
        assert not ReviewItem.objects.using(CATALOG).filter(source_id=healthy.pk).exists()

    def test_the_collapsed_sources_event_ranks_below_a_healthy_sources(self):
        """**The ranking consumes the real score** — FR-22's `source_reliability` term.

        The two events are identical in every input the formula reads: same city, same
        start, same extraction confidence, same (absent) interest overlap. **They differ
        only in their Source**, so any difference in their scores is the reliability term
        and nothing else.
        """
        collapsing = SourceFactory(name="The collapsing feed")
        healthy = SourceFactory(name="The dependable feed")
        collapse(collapsing)
        recompute_due(now=NOW)

        collapsing.refresh_from_db(using=CATALOG)
        healthy.refresh_from_db(using=CATALOG)
        assert collapsing.reliability_score == Decimal("0.13")
        assert healthy.reliability_score == Decimal("0.50")

        from_collapsed = make_event(source=collapsing, title="Tonight at the flaky venue")
        from_healthy = make_event(source=healthy, title="Tonight at the solid venue")

        reader = make_reader(email="ranker@example.test")
        result = compose(reader)

        scores = {
            row.event_id: row.score
            for row in DigestComposition.objects.using(PERSONAL).filter(digest_id=result.digest_id)
        }
        assert set(scores) >= {from_collapsed.id, from_healthy.id}

        # The claim the AC makes, stated as an ordering...
        assert scores[from_healthy.id] > scores[from_collapsed.id]

        # ...and as the arithmetic, so a term that was *dropped* rather than merely
        # reordered fails too.
        #
        # **Both totals are pinned, not their difference.** The first version of this
        # asserted `healthy - collapsed == 0.10`, and that was wrong in a way worth
        # recording: the true gap is `0.25 × (0.50 − 0.13) = 0.0925`, and each total is
        # quantized **independently** in `domain/ranking.py` with the default
        # `ROUND_HALF_EVEN` (unlike `domain/reliability.py`, which passes `ROUND_HALF_UP`
        # explicitly). So the *stored* gap is 0.09 or 0.10 depending on the fractional part
        # of the terms the two events share. Changing `RANKING_WEIGHT_RECENCY` — which has
        # nothing to do with reliability — would have flipped it to 0.09 and failed this
        # test with a message blaming a dropped reliability term.
        #
        # Pinning both totals says the same thing more precisely and fails honestly: a
        # changed weight moves both numbers and names itself, and a dropped reliability
        # term collapses them onto each other.
        assert scores[from_healthy.id] == Decimal("0.48")
        assert scores[from_collapsed.id] == Decimal("0.38")


# ══ 3. The stranded event ══════════════════════════════════════════════════════════════


class TestTheStrandedEventGetsOut:
    """The bug the intent exists for: an `in_review` event with no way out of the queue.

    **It gets most of the way out.** The queue gives the editor a way to release it, and
    the release reaches the public catalog, the event's own URL and the sitemap. It does
    **not** reach a Pulse Digest, and the two tests after the first one pin why — see
    `test_an_approved_event_is_still_barred_from_every_digest`. The class is named for
    what the intent set out to do; the tests are named for what it actually does.
    """

    def test_a_low_confidence_event_is_ticketed_approved_and_made_public(self):
        """**The real gate, not a patched one.**

        A venue registered in `US/Pacific` and a VEVENT carrying `TZID=America/New_York`
        is FR-60's A3 conflict: two explicit claims disagree, `TZ_SCORE_CONFLICT` is 0.60,
        and 0.60 is below `TZ_INFERENCE_CONFIDENCE_DIGEST`. So the event lands in
        `in_review` because the resolver put it there, not because a gate table was
        monkeypatched into saying so.
        """
        staff = Actor.user(uuid4())
        register_venue(
            actor=staff,
            name="The Fillmore",
            city="San Francisco",
            country_code="US",
            tz="US/Pacific",
        )
        source = ics_source(city="San Francisco")

        ingest_source(
            source.id,
            fetch_port=ScriptedFetchPort().serve(
                calendar(
                    vevent(
                        "stranded@fillmore.example.test",
                        "20261105T200000",
                        tzid="America/New_York",
                        location="The Fillmore",
                        summary="The stranded show",
                    )
                )
            ),
        )

        event = Event.objects.using(CATALOG).get(source=source)
        assert event.tz_inference_confidence == Decimal("0.60")
        assert event.publication_status == Event.PublicationStatus.IN_REVIEW

        # It is stranded: absent from every public read, and therefore from the digest.
        reader = make_reader(email="sf@example.test", city="San Francisco")
        assert event.id not in composed_event_ids(compose(reader))

        # But it is ticketed, so an editor can find it.
        [item] = open_items(event)
        assert item.reason == ReviewItem.Reason.IN_REVIEW
        # An `in_review` item has no SLA: it is not a user's complaint with a deadline.
        assert item.due_at is None

        # --- the editor approves it ---
        editor = make_editor(email="releaser@example.test")
        assert admin_verdict(signed_in(editor), item, "approve_items").status_code == 302

        item.refresh_from_db(using=CATALOG)
        assert (item.status, item.resolution) == (
            ReviewItem.Status.RESOLVED,
            ReviewItem.Resolution.APPROVED,
        )
        event.refresh_from_db(using=CATALOG)
        assert event.publication_status == Event.PublicationStatus.PUBLISHED

        # The approval is attributed to the editor and recorded.
        assert [entry.actor_id for entry in audit(action="review_item_approved")] == [editor.pk]

        # --- and it comes back into the world ... most of the way ---
        listed, _total = list_public_events(now=NOW)
        assert event.id in {row.id for row in listed}
        assert get_public_event_by_slug(slug=event.slug) is not None
        feed = list_url_feed(now=NOW, page_size=500)
        assert f"/events/{event.slug}" in {entry.path for entry in feed.items}

        # --- but NOT into the digest. See `test_an_approved_event_is_still_barred_...`. ---
        released = make_reader(email="released@example.test", city="San Francisco")
        assert event.id not in composed_event_ids(compose(released))

    def test_an_approved_event_is_still_barred_from_every_digest(self):
        """**A defect this item found, pinned as it actually behaves (2026-11-11).**

        The acceptance criterion asked that a stranded event, once approved, *"appears in
        the digest"*. **It does not, and no editorial action can make it.**

        `list_public_candidates` gates the digest pool on
        `tz_inference_confidence >= TZ_INFERENCE_CONFIDENCE_DIGEST` (0.70), and **nothing
        in the editorial path moves that column**:

        - `approve_review_item` flips `publication_status` only;
        - `edit_and_publish` carries the old confidence through deliberately —
          `_incoming_for` says *"an edit changes exactly what the editor named and nothing
          else — including the gates, which stay where the pipeline put them"* — so even
          an editor correcting `start_time_tz` to the right zone leaves it at 0.60.

        The only thing that lifts it is the **pipeline** seeing a clean resolution on a
        later poll, which requires the *source* to fix its own feed — the very situation
        the editor exists to work around. All three paths were probed before this was
        written down.

        **The consequence, stated plainly:** an approved timezone-quarantined event is
        public, reachable at its URL and listed in the sitemap, and is absent from every
        Pulse Digest forever. The intent's "events can get stuck with no exit" is closed
        for the public catalog and still open for the digest.

        **This test asserts the defect, not the requirement.** It will fail on the day the
        gate is lifted — which is the point: whoever fixes it is told to come here and
        turn this into the assertion the AC originally asked for.
        """
        staff = Actor.user(uuid4())
        register_venue(
            actor=staff,
            name="The Independent",
            city="San Francisco",
            country_code="US",
            tz="US/Pacific",
        )
        source = ics_source(city="San Francisco")
        ingest_source(
            source.id,
            fetch_port=ScriptedFetchPort().serve(
                calendar(
                    vevent(
                        "barred@independent.example.test",
                        "20261105T200000",
                        tzid="America/New_York",
                        location="The Independent",
                        summary="The barred show",
                    )
                )
            ),
        )
        event = Event.objects.using(CATALOG).get(source=source)
        [item] = open_items(event)
        reader = make_reader(email="barred@example.test", city="San Francisco")

        # **Approve does not lift it.**
        approve_review_item(item_id=item.id, actor=Actor.user(uuid4()), now=NOW)
        event.refresh_from_db(using=CATALOG)
        assert event.publication_status == Event.PublicationStatus.PUBLISHED
        assert event.tz_inference_confidence == Decimal("0.60")
        assert event.id not in {row.id for row in list_public_candidates(now=NOW)}

        # **And the only thing that does lift it is the source correcting its own feed.**
        # This is the negative control: without it, the two assertions above could be
        # passing because the event was unrankable for some unrelated reason.
        ingest_source(
            source.id,
            fetch_port=ScriptedFetchPort().serve(
                calendar(
                    vevent(
                        "barred@independent.example.test",
                        "20261105T200000",
                        tzid="US/Pacific",
                        location="The Independent",
                        summary="The barred show",
                    )
                )
            ),
        )
        event.refresh_from_db(using=CATALOG)
        assert event.tz_inference_confidence == Decimal("1.00")
        assert event.id in {row.id for row in list_public_candidates(now=NOW)}
        assert event.id in composed_event_ids(compose(reader))

    def test_an_editors_correction_of_the_timezone_does_not_lift_the_gate_either(self):
        """The other half of the same defect: **Edit does not lift it either.**

        An editor who diagnoses the problem exactly right — "the source's zone is wrong,
        it is US/Pacific" — and corrects it through the admin's edit form still leaves the
        event barred, because `_incoming_for` carries `tz_inference_confidence` over
        unchanged. Without this test the defect could be half-fixed and look whole.
        """
        staff = Actor.user(uuid4())
        register_venue(
            actor=staff,
            name="Bimbo's",
            city="San Francisco",
            country_code="US",
            tz="US/Pacific",
        )
        source = ics_source(city="San Francisco")
        ingest_source(
            source.id,
            fetch_port=ScriptedFetchPort().serve(
                calendar(
                    vevent(
                        "edited@bimbos.example.test",
                        "20261105T200000",
                        tzid="America/New_York",
                        location="Bimbo's",
                        summary="The edited show",
                    )
                )
            ),
        )
        event = Event.objects.using(CATALOG).get(source=source)
        [item] = open_items(event)

        edit_and_publish(
            item_id=item.id,
            actor=Actor.user(uuid4()),
            fields={"start_time_tz": "US/Pacific"},
            expected_event_version=event.event_version,
            now=NOW,
        )

        event.refresh_from_db(using=CATALOG)
        assert event.start_time_tz == "US/Pacific"  # the editor's correction landed...
        assert event.publication_status == Event.PublicationStatus.PUBLISHED
        assert event.tz_inference_confidence == Decimal("0.60")  # ...and the gate did not
        assert event.id not in {row.id for row in list_public_candidates(now=NOW)}


# ══ 4. The refusals ════════════════════════════════════════════════════════════════════


class TestTheRefusals:
    """Three negative paths. Each one is a door that has to stay shut."""

    def test_a_non_editor_is_refused_by_the_admin(self):
        """A staff user with no review permission cannot read or work the queue.

        **Staff, not anonymous.** An anonymous visitor is bounced by Django's admin login
        before any of this code runs, so refusing them proves nothing about the group
        grant. The case that matters is someone who is *already inside* the admin.
        """
        event = make_event()
        reporter = make_reader()
        report(signed_in(reporter), event)
        [item] = open_items(event)

        intruder = User.objects.db_manager(PERSONAL).create_user(
            email="not-an-editor@example.test", password="pw", is_staff=True
        )
        client = signed_in(intruder)

        assert client.get(reverse(CHANGELIST)).status_code == 403
        assert (
            client.get(reverse("admin:ingestion_reviewitem_change", args=[item.pk])).status_code
            == 403
        )
        assert admin_verdict(client, item, "reject_items").status_code == 403

        # Nothing moved, and nothing was recorded as having moved.
        item.refresh_from_db(using=CATALOG)
        assert item.status == ReviewItem.Status.OPEN
        event.refresh_from_db(using=CATALOG)
        assert event.publication_status == Event.PublicationStatus.PUBLISHED
        assert audit(action="review_item_rejected") == []

    def test_the_sixth_report_in_a_day_is_refused(self, monkeypatch):
        """FR-59's cap: five per user per day, declared through the throttle port.

        **The adapter is pinned to one instance on purpose.** `get_adapter` constructs a
        *new* adapter per call, and the in-memory fake keeps its counter in an instance
        dict — so the fake's counter would reset on every request and the limit could not
        be observed at all. In production the adapter is Redis-backed and the state lives
        outside the instance, which is why a fresh instance per call is fine there. Here,
        the single instance is what makes the port's own window visible.
        """
        throttle = InMemoryThrottleAdapter(now=lambda: 1_000_000.0)
        monkeypatch.setattr(event_reports_service, "get_throttle_port", lambda: throttle)

        reporter = make_reader()
        client = signed_in(reporter)
        events = [make_event(title=f"Event {index}") for index in range(EVENT_REPORT_DAILY_LIMIT)]

        for event in events:
            assert report(client, event).status_code == 201

        one_too_many = make_event(title="The sixth")
        refused = report(client, one_too_many)

        assert refused.status_code == 429
        assert refused.json()["details"]["retry_after_seconds"] > 0
        assert EventReport.objects.using(PERSONAL).filter(user_id=reporter.pk).count() == (
            EVENT_REPORT_DAILY_LIMIT
        )
        # And the sixth event got no item: the refusal happened before the catalog write.
        assert open_items(one_too_many) == []
        # A different person is unaffected: the cap is per user, not global.
        other = make_reader(email="other@example.test")
        assert report(signed_in(other), one_too_many).status_code == 201

    def test_a_stale_version_resolve_is_refused(self):
        """The event moved while the editor was reading it: the edit is refused.

        **The token comes off the rendered page**, not out of the test's head. A hand-built
        POST body would pass even if the form never rendered the field — which is exactly
        the defect the admin suite found once already.
        """
        event = make_event()
        reporter = make_reader()
        report(signed_in(reporter), event)
        [item] = open_items(event)

        editor = make_editor()
        client = signed_in(editor)

        page = client.get(reverse("admin:ingestion_reviewitem_change", args=[item.pk]))
        assert page.status_code == 200
        assert 'name="expected_event_version"' in page.content.decode()

        stale = event.event_version - 1
        response = client.post(
            reverse("admin:ingestion_reviewitem_change", args=[item.pk]),
            {
                "title": "A title the editor typed",
                "start_time_utc": event.start_time_utc.strftime("%Y-%m-%d %H:%M:%S"),
                "end_time_utc": "",
                "start_time_tz": event.start_time_tz,
                "venue": str(event.venue_id) if event.venue_id else "",
                "expected_event_version": str(stale),
            },
        )

        assert response.status_code == 200
        assert "changed while you were looking at it" in response.content.decode()
        event.refresh_from_db(using=CATALOG)
        assert event.title != "A title the editor typed"
        assert ReviewItem.objects.using(CATALOG).get(pk=item.pk).status == ReviewItem.Status.OPEN
        assert audit(action="review_item_edited") == []


# ══ The period boundary, so the weekly job's arithmetic is pinned somewhere ════════════


def test_the_recompute_period_is_the_iso_monday_of_the_frozen_clock():
    """A sanity pin on the clock this file reasons about.

    `NOW` is a Wednesday; the period it belongs to starts on the Monday before it. If this
    were wrong, `recompute_due` above would be computing a different week's score from the
    one the observations were written into, and every score assertion would be measuring
    the wrong period.
    """
    from apps.ingestion.services.reliability import period_start_for

    assert period_start_for(NOW) == date(2026, 11, 2)
