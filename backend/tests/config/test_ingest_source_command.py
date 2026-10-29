"""`manage.py ingest_source <source_id> [--sync]` (ingestion-scheduling AC)."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.ingestion.models import IngestionAuditEntry
from config.management.commands import ingest_source as command_module
from ports.registry import get_fetch_port
from shared.db import CATALOG, PERSONAL
from shared.ids import uuid7
from tests.ingestion.factories import SourceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

FIXTURE = "https://fixtures.example.test/calendar.ics"


@pytest.fixture
def fake_fetch(settings):
    settings.ADAPTERS = {**settings.ADAPTERS, "fetch": "adapters.crawl.fake.FakeFetchAdapter"}
    assert type(get_fetch_port()).__name__ == "FakeFetchAdapter"


@pytest.mark.usefixtures("fake_fetch")
def test_sync_runs_inline_and_prints_the_report():
    source = SourceFactory(url=FIXTURE, acquisition_method="ics")
    out = StringIO()

    call_command("ingest_source", str(source.pk), "--sync", stdout=out)

    assert out.getvalue().strip() == (
        "ok: new=6, rejected:tz_unresolvable=2, skipped:no_event_start=1, tz_review_pending=2"
    )
    assert IngestionAuditEntry.objects.using(CATALOG).filter(action="ingest_source").count() == 1


@pytest.mark.usefixtures("fake_fetch")
def test_sync_failure_outcome_shows_its_error_code():
    source = SourceFactory(url="https://fixtures.example.test/down", acquisition_method="rss")
    out = StringIO()

    call_command("ingest_source", str(source.pk), "--sync", stdout=out)

    assert out.getvalue().strip() == "fetch_failed [fetch_http_error]: no items"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"status": "paused"}, "source_paused: This source is paused."),
        ({"acquisition_method": "crawl"}, "crawl_needs_tos_review: "),
    ],
)
def test_sync_refusal_is_a_command_error(overrides, message):
    source = SourceFactory(**overrides)

    with pytest.raises(CommandError, match=message):
        call_command("ingest_source", str(source.pk), "--sync")


def test_sync_unknown_source_is_a_command_error():
    with pytest.raises(CommandError, match="not_found"):
        call_command("ingest_source", str(uuid7()), "--sync")


def test_without_sync_enqueues_the_worker_job_by_name(monkeypatch):
    sent = []
    monkeypatch.setattr(
        command_module.celery_app, "send_task", lambda name, args: sent.append((name, args))
    )
    source_id = uuid7()
    out = StringIO()

    call_command("ingest_source", str(source_id), stdout=out)

    assert sent == [("worker.tasks.ingest_source", [str(source_id)])]
    assert out.getvalue().strip() == f"Enqueued worker.tasks.ingest_source for {source_id}."


def test_source_id_must_be_a_uuid():
    with pytest.raises(CommandError):
        call_command("ingest_source", "not-a-uuid", "--sync")
