"""The export worker tasks (FR-52): the dispatcher, the build-and-send job, the expiry.

**What these tests pin.**

- The **tick enqueues the dispatcher on every beat**, not on a modulo cadence. The promise
  is "within 24 hours", and a person asking for their own data is owed it as soon as it can
  be built — not at the next five-minute boundary.
- The dispatcher **drains**, so sixty requests after an outage clear in one pass rather than
  one per minute against a 24-hour clock.
- The job **builds and sends together**, because an export nobody is told about is not an
  export — and it **sends with a key derived from the row**, so a Celery retry cannot mail
  a second copy (AD-7).
- The expiry job **clears the payloads**, not just the status.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.identity.models import DataExport, DataExportStatus
from apps.identity.services.data_export import request_export
from shared.actor import Actor
from shared.constants import DATA_EXPORT_LINK_LIFETIME
from shared.db import CATALOG, PERSONAL
from tests.identity.factories import UserFactory
from tests.personalization.factories import DigestPreferenceFactory, PersonalEventFactory
from worker import tasks

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])


def requested_export(user):
    return request_export(user_id=user.pk, actor=Actor.user(user.pk), now=timezone.now())


# ── The tick and the dispatcher ────────────────────────────────────────────────────


def test_the_tick_enqueues_the_export_dispatcher_every_beat(monkeypatch):
    """Not a modulo cadence: a user waiting for their own data should not wait for a
    boundary that exists for the reconcilers' benefit."""
    enqueued = []
    monkeypatch.setattr(tasks, "_enqueue", lambda task, *args: enqueued.append(task.name))

    tasks.tick()

    assert "worker.tasks.schedule_data_exports" in enqueued


def test_the_dispatcher_enqueues_one_job_per_waiting_request(monkeypatch):
    users = [UserFactory() for _ in range(3)]
    for user in users:
        requested_export(user)
    enqueued = []
    monkeypatch.setattr(tasks, "_enqueue", lambda task, *args: enqueued.append(args[0]))

    tasks.schedule_data_exports()

    assert len(enqueued) == 3


def test_the_dispatcher_drains_rather_than_taking_one(monkeypatch):
    """**The property the `while` loop exists for.** Sixty requests after an outage clear
    in one pass; one-per-tick would take an hour against a 24-hour promise."""
    for _ in range(5):
        requested_export(UserFactory())
    calls = []
    monkeypatch.setattr(tasks, "_enqueue", lambda task, *args: calls.append(args[0]))

    tasks.schedule_data_exports()

    assert len(calls) == 5
    assert DataExport.objects.using(PERSONAL).filter(status=DataExportStatus.PENDING).count() == 0


def test_the_dispatcher_does_nothing_when_nothing_is_waiting(monkeypatch):
    enqueued = []
    monkeypatch.setattr(tasks, "_enqueue", lambda task, *args: enqueued.append(args))

    tasks.schedule_data_exports()

    assert enqueued == []


def test_a_broker_failure_stops_the_drain_rather_than_spinning(monkeypatch):
    """The claim stays taken and the next tick retries; a loop that kept claiming into a
    dead broker would empty the queue into nothing."""

    def boom(task, *args):
        raise RuntimeError("broker down")

    for _ in range(3):
        requested_export(UserFactory())
    monkeypatch.setattr(tasks, "_enqueue", boom)

    tasks.schedule_data_exports()  # must not raise

    assert DataExport.objects.using(PERSONAL).filter(status=DataExportStatus.BUILDING).exists()


# ── Build and send ─────────────────────────────────────────────────────────────────


class RecordingPort:
    """An `EmailPort` stand-in that records what it was asked to send."""

    def __init__(self):
        self.sent = []

    def send(self, message, *, stream, idempotency_key):
        self.sent.append((message, stream, idempotency_key))
        return type("Result", (), {"provider_message_id": "test"})()


def test_the_job_builds_the_export_and_mails_the_links(monkeypatch):
    user = UserFactory()
    PersonalEventFactory(user_id=user.pk, name="Dentist")
    view = requested_export(user)
    port = RecordingPort()
    monkeypatch.setattr(tasks, "get_email_port", lambda: port)

    tasks.build_data_export(str(view.id))

    row = DataExport.objects.using(PERSONAL).get(id=view.id)
    assert row.status == DataExportStatus.READY
    assert "Dentist" in row.json_body

    message, stream, key = port.sent[0]
    assert message.to == user.email
    assert stream.value == "transactional"
    # AD-7: the key is the row, so a retry cannot send a second copy.
    assert key == f"data-export-{view.id}"


def test_the_mail_carries_both_links_and_they_point_at_this_export(monkeypatch):
    user = UserFactory()
    view = requested_export(user)
    port = RecordingPort()
    monkeypatch.setattr(tasks, "get_email_port", lambda: port)

    tasks.build_data_export(str(view.id))

    body = port.sent[0][0].text_body
    assert f"/api/exports/{view.id}/json?token=" in body
    assert f"/api/exports/{view.id}/ics?token=" in body


def test_the_mail_says_so_when_locations_were_redacted(monkeypatch):
    """A user who opened a download and found "[redacted]" with no explanation would
    reasonably think the export was broken."""
    user = UserFactory()
    DigestPreferenceFactory(user_id=user.pk, share_precise_location=False)
    PersonalEventFactory(user_id=user.pk, location="21 Harley St")
    view = requested_export(user)
    port = RecordingPort()
    monkeypatch.setattr(tasks, "get_email_port", lambda: port)

    tasks.build_data_export(str(view.id))

    assert "locations" in port.sent[0][0].text_body.lower()


def test_the_mail_is_silent_about_redaction_when_nothing_was_redacted(monkeypatch):
    user = UserFactory()
    DigestPreferenceFactory(user_id=user.pk, share_precise_location=True)
    view = requested_export(user)
    port = RecordingPort()
    monkeypatch.setattr(tasks, "get_email_port", lambda: port)

    tasks.build_data_export(str(view.id))

    assert "redacted" not in port.sent[0][0].text_body.lower()


def test_an_export_is_still_built_when_there_is_no_address_to_send_it_to(monkeypatch):
    """**The better of the two failures.** The row is `READY` and the links work, so the
    settings screen can show it — against a built file nobody can reach."""
    user = UserFactory()
    view = requested_export(user)
    port = RecordingPort()
    monkeypatch.setattr(tasks, "get_email_port", lambda: port)
    monkeypatch.setattr("apps.identity.services.recipients.get_recipient_address", lambda **_: None)

    tasks.build_data_export(str(view.id))

    assert DataExport.objects.using(PERSONAL).get(id=view.id).status == DataExportStatus.READY
    assert port.sent == []


# ── Expiry ─────────────────────────────────────────────────────────────────────────


def test_the_expiry_job_clears_the_payload_and_not_only_the_status(monkeypatch):
    user = UserFactory()
    PersonalEventFactory(user_id=user.pk, name="Dentist")
    view = requested_export(user)
    port = RecordingPort()
    monkeypatch.setattr(tasks, "get_email_port", lambda: port)
    tasks.build_data_export(str(view.id))

    DataExport.objects.using(PERSONAL).filter(id=view.id).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    tasks.expire_data_exports()

    row = DataExport.objects.using(PERSONAL).get(id=view.id)
    assert row.status == DataExportStatus.EXPIRED
    assert row.json_body == ""
    assert row.ics_body == ""


def test_a_live_export_is_left_alone(monkeypatch):
    user = UserFactory()
    view = requested_export(user)
    port = RecordingPort()
    monkeypatch.setattr(tasks, "get_email_port", lambda: port)
    tasks.build_data_export(str(view.id))

    tasks.expire_data_exports()

    row = DataExport.objects.using(PERSONAL).get(id=view.id)
    assert row.status == DataExportStatus.READY
    assert row.expires_at > timezone.now()
    assert row.expires_at <= timezone.now() + DATA_EXPORT_LINK_LIFETIME
