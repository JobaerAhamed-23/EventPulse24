"""The Source Registry admin (AD-14): every save runs a command, nothing is deleted, history is
read-only, and the audit list shows who did what.
"""

from datetime import timedelta

import pytest
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory
from django.urls import reverse

from apps.ingestion.models import IngestionAuditEntry, Source, TosReview, Venue
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import (
    EventFactory,
    EventStateChangeFactory,
    IngestionAuditEntryFactory,
    SourceFactory,
    VenueFactory,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

FEED_URL = "https://fillmore.example.test/events.rss"
TERMS_URL = "https://fillmore.example.test/terms"
NO_INLINE_FORMS = {
    "tos_reviews-TOTAL_FORMS": "0",
    "tos_reviews-INITIAL_FORMS": "0",
    "tos_reviews-MIN_NUM_FORMS": "0",
    "tos_reviews-MAX_NUM_FORMS": "1000",
}


@pytest.fixture
def editor():
    return (
        get_user_model()
        .objects.db_manager(PERSONAL)
        .create_superuser(email="editor@example.test", password="not-used-in-tests")
    )


@pytest.fixture
def client(client, editor):
    client.force_login(editor)
    return client


def _source_form(**overrides) -> dict:
    data = {
        "name": "Fillmore listings",
        "source_type": "venue",
        "url": FEED_URL,
        "city": "San Francisco",
        "acquisition_method": "rss",
        "ingestion_cadence": "",
        "freshness_ttl_hours": "24",
        "tz_coverage": "full",
        "tos_evidence_url": "",
        "tos_notes": "",
    }
    return data | NO_INLINE_FORMS | overrides


def _form_errors(response) -> dict:
    return response.context["adminform"].form.errors


def _audit(**filters) -> list[IngestionAuditEntry]:
    return list(IngestionAuditEntry.objects.using(CATALOG).filter(**filters).order_by("id"))


# --- Sources ----------------------------------------------------------------------------------


def test_source_add_runs_register_source_as_the_staff_user(client, editor):
    response = client.post(reverse("admin:ingestion_source_add"), _source_form())

    assert response.status_code == 302
    source = Source.objects.using(CATALOG).get()
    assert source.ingestion_cadence == timedelta(hours=4)  # the command's RSS default
    [entry] = _audit(target_id=source.id)
    # A plain obj.save() writes no audit row: this one proves the command ran.
    assert (entry.action, entry.actor_kind, entry.actor_id, entry.actor_label) == (
        "register_source",
        "user",
        editor.pk,
        "",
    )
    assert response.url == reverse("admin:ingestion_source_changelist")


def test_source_change_runs_update_source_with_only_the_changed_field(client):
    source = SourceFactory(name="Before", url=FEED_URL)
    form = _source_form(name="After", city="", ingestion_cadence="4:00:00")

    response = client.post(reverse("admin:ingestion_source_change", args=[source.pk]), form)

    assert response.status_code == 302
    [entry] = _audit(target_id=source.id)
    assert entry.action == "update_source"
    assert entry.details["changes"] == {"name": {"from": "Before", "to": "After"}}


def test_source_add_crawl_without_review_shows_error_and_creates_nothing(client):
    response = client.post(
        reverse("admin:ingestion_source_add"), _source_form(acquisition_method="crawl")
    )

    assert response.status_code == 200
    assert "approved terms-of-service review" in _form_errors(response)["tos_approved"][0]
    assert not Source.objects.using(CATALOG).exists()


def test_source_add_crawl_with_review_records_it(client, editor):
    form = _source_form(acquisition_method="crawl", tos_approved="on", tos_evidence_url=TERMS_URL)

    client.post(reverse("admin:ingestion_source_add"), form)

    source = Source.objects.using(CATALOG).get()
    assert source.tos_status == "approved"
    review = TosReview.objects.using(CATALOG).get(source=source)
    assert (review.acquisition_method, review.reviewed_by_id) == ("crawl", editor.pk)


def _staff(*codenames):
    user = (
        get_user_model()
        .objects.db_manager(PERSONAL)
        .create_user(email="staff@example.test", password="not-used-in-tests", is_staff=True)
    )
    user.user_permissions.set(
        Permission.objects.using(PERSONAL).filter(
            content_type__app_label="ingestion", codename__in=codenames
        )
    )
    return user


def test_source_tos_approval_without_add_tosreview_permission_refused(client):
    """AD-14: change_source alone can't approve terms; the review needs add_tosreview."""
    client.force_login(_staff("view_source", "change_source"))
    source = SourceFactory(url=FEED_URL)
    form = _source_form(
        city="",
        ingestion_cadence="4:00:00",
        acquisition_method="crawl",
        tos_approved="on",
        tos_evidence_url=TERMS_URL,
    )

    page = client.get(reverse("admin:ingestion_source_change", args=[source.pk]))
    response = client.post(reverse("admin:ingestion_source_change", args=[source.pk]), form)

    assert b'name="tos_approved"' not in page.content
    assert "permission" in _form_errors(response)["tos_approved"][0]
    stored = Source.objects.using(CATALOG).get(pk=source.pk)
    assert (stored.acquisition_method, stored.tos_status) == ("rss", "not_reviewed")
    assert not TosReview.objects.using(CATALOG).exists()


def test_source_tos_approval_with_add_tosreview_permission_allowed(client):
    client.force_login(_staff("view_source", "change_source", "add_tosreview"))
    source = SourceFactory(url=FEED_URL)
    form = _source_form(
        city="",
        ingestion_cadence="4:00:00",
        acquisition_method="crawl",
        tos_approved="on",
        tos_evidence_url=TERMS_URL,
    )

    page = client.get(reverse("admin:ingestion_source_change", args=[source.pk]))
    response = client.post(reverse("admin:ingestion_source_change", args=[source.pk]), form)

    assert b'name="tos_approved"' in page.content
    assert response.status_code == 302
    stored = Source.objects.using(CATALOG).get(pk=source.pk)
    assert (stored.acquisition_method, stored.tos_status) == ("crawl", "approved")


def test_source_add_approval_without_evidence_shows_field_error(client):
    form = _source_form(acquisition_method="crawl", tos_approved="on")

    response = client.post(reverse("admin:ingestion_source_add"), form)

    assert "tos_evidence_url" in _form_errors(response)
    assert not Source.objects.using(CATALOG).exists()


def test_source_add_duplicate_feed_shows_form_error(client):
    SourceFactory(url=FEED_URL)

    response = client.post(
        reverse("admin:ingestion_source_add"), _source_form(url=FEED_URL + "?utm_source=x")
    )

    assert _form_errors(response)["__all__"] == ["That source is already registered."]
    assert Source.objects.using(CATALOG).count() == 1


def test_source_delete_is_forbidden_even_for_superuser(client):
    source = SourceFactory()

    response = client.post(
        reverse("admin:ingestion_source_delete", args=[source.pk]), {"post": "yes"}
    )

    assert response.status_code == 403
    assert Source.objects.using(CATALOG).filter(pk=source.pk).exists()


def test_source_changelist_offers_pause_and_resume_but_no_delete(client):
    SourceFactory()

    response = client.get(reverse("admin:ingestion_source_changelist"))

    actions = [name for name, _label in response.context["action_form"].fields["action"].choices]
    assert actions == ["", "pause_sources", "resume_sources"]


def test_source_pause_action_runs_pause_source(client, editor):
    source = SourceFactory()

    client.post(
        reverse("admin:ingestion_source_changelist"),
        {"action": "pause_sources", "_selected_action": [str(source.pk)]},
    )

    assert Source.objects.using(CATALOG).get(pk=source.pk).status == "paused"
    [entry] = _audit(target_id=source.id)
    assert (entry.action, entry.actor_id) == ("pause_source", editor.pk)


def test_source_resume_action_runs_resume_source(client):
    source = SourceFactory(status="paused")

    client.post(
        reverse("admin:ingestion_source_changelist"),
        {"action": "resume_sources", "_selected_action": [str(source.pk)]},
    )

    assert Source.objects.using(CATALOG).get(pk=source.pk).status == "active"
    assert [e.action for e in _audit(target_id=source.id)] == ["resume_source"]


def test_source_form_field_error_shown_without_running_command_checks(client):
    response = client.post(
        reverse("admin:ingestion_source_add"),
        _source_form(freshness_ttl_hours="", acquisition_method="crawl"),
    )

    errors = _form_errors(response)
    assert "freshness_ttl_hours" in errors
    assert "tos_approved" not in errors  # the crawl check waits for valid fields
    assert not Source.objects.using(CATALOG).exists()


@pytest.mark.parametrize("model", [Source, TosReview, Venue, IngestionAuditEntry])
def test_command_admin_direct_write_hooks_refuse(editor, model):
    """Second guard behind the disabled views: nothing reaches obj.save() or obj.delete()."""
    model_admin = admin.site._registry[model]
    request = RequestFactory().post("/")
    request.user = editor

    with pytest.raises(PermissionDenied):
        model_admin.delete_model(request, model())
    with pytest.raises(PermissionDenied):
        model_admin.delete_queryset(request, model.objects.using(CATALOG).none())
    if model is IngestionAuditEntry:  # read-only: the base save_model is the one in effect
        with pytest.raises(PermissionDenied):
            model_admin.save_model(request, model(), None, change=False)


def test_admin_save_writes_no_django_log_entry(client):
    client.post(reverse("admin:ingestion_source_add"), _source_form())

    assert Source.objects.using(CATALOG).exists()
    assert not LogEntry.objects.using(PERSONAL).exists()


# --- ToS reviews and venues ---------------------------------------------------------------------


def test_tos_review_add_runs_record_tos_review(client, editor):
    source = SourceFactory(acquisition_method="ics")

    response = client.post(
        reverse("admin:ingestion_tosreview_add"),
        {"source": str(source.pk), "decision": "rejected", "evidence_url": "", "notes": "No."},
    )

    assert response.status_code == 302
    review = TosReview.objects.using(CATALOG).get()
    assert (review.acquisition_method, review.reviewed_by_id) == ("ics", editor.pk)
    assert Source.objects.using(CATALOG).get(pk=source.pk).tos_status == "rejected"
    assert [e.action for e in _audit(target_id=source.id)] == ["record_tos_review"]


def test_tos_review_approval_without_evidence_shows_error(client):
    source = SourceFactory()

    response = client.post(
        reverse("admin:ingestion_tosreview_add"),
        {"source": str(source.pk), "decision": "approved", "evidence_url": "", "notes": ""},
    )

    assert "evidence_url" in _form_errors(response)
    assert not TosReview.objects.using(CATALOG).exists()


def test_venue_add_runs_register_venue(client):
    response = client.post(
        reverse("admin:ingestion_venue_add"),
        {"name": "The Fillmore", "city": "San Francisco", "country_code": "us", "tz": "US/Pacific"},
    )

    assert response.status_code == 302
    venue = Venue.objects.using(CATALOG).get()
    assert (venue.country_code, venue.tz) == ("US", "America/Los_Angeles")
    assert [e.action for e in _audit(target_id=venue.id)] == ["register_venue"]


def test_venue_add_bad_tz_shows_field_error(client):
    response = client.post(
        reverse("admin:ingestion_venue_add"),
        {"name": "The Fillmore", "city": "San Francisco", "country_code": "US", "tz": "Mars/Base"},
    )

    assert "tz" in _form_errors(response)
    assert not Venue.objects.using(CATALOG).exists()


def test_venue_change_sets_only_the_timezone(client):
    venue = VenueFactory(tz=None)

    response = client.post(
        reverse("admin:ingestion_venue_change", args=[venue.pk]),
        {"name": "Renamed", "tz": "Europe/Berlin"},
    )

    assert response.status_code == 302
    stored = Venue.objects.using(CATALOG).get(pk=venue.pk)
    assert (stored.name, stored.tz) == (venue.name, "Europe/Berlin")
    [entry] = _audit(target_id=venue.id)
    assert entry.action == "set_venue_timezone"


def test_venue_change_without_tz_change_writes_nothing(client):
    venue = VenueFactory(tz="Europe/Berlin")

    response = client.post(
        reverse("admin:ingestion_venue_change", args=[venue.pk]), {"tz": "Europe/Berlin"}
    )

    assert response.status_code == 302
    assert _audit(target_id=venue.id) == []


def test_venue_add_missing_field_shows_error_without_command_checks(client):
    response = client.post(
        reverse("admin:ingestion_venue_add"),
        {"name": "The Fillmore", "city": "", "country_code": "US", "tz": "Mars/Base"},
    )

    errors = _form_errors(response)
    assert "city" in errors
    assert "tz" not in errors  # the command's checks wait for valid fields
    assert not Venue.objects.using(CATALOG).exists()


# --- Read-only history ------------------------------------------------------------------------


@pytest.mark.parametrize("model", ["event", "eventstatechange", "ingestionauditentry"])
def test_history_admin_has_no_add_page(client, model):
    assert client.get(reverse(f"admin:ingestion_{model}_add")).status_code == 403


@pytest.mark.parametrize(
    ("model", "factory"),
    [
        ("event", EventFactory),
        ("eventstatechange", EventStateChangeFactory),
        ("ingestionauditentry", IngestionAuditEntryFactory),
    ],
)
def test_history_admin_change_page_is_view_only(client, model, factory):
    row = factory()

    response = client.get(reverse(f"admin:ingestion_{model}_change", args=[row.pk]))

    assert response.status_code == 200
    assert b'name="_save"' not in response.content
    post = client.post(reverse(f"admin:ingestion_{model}_change", args=[row.pk]), {})
    assert post.status_code == 403


def test_audit_changelist_shows_the_actor_and_system_job(client, editor):
    client.post(reverse("admin:ingestion_source_add"), _source_form())
    IngestionAuditEntryFactory(actor_label="ingest_pipeline")

    response = client.get(reverse("admin:ingestion_ingestionauditentry_changelist"))

    content = response.content.decode()
    assert '<td class="field-who">editor@example.test</td>' in content
    assert "ingest_pipeline (system job)" in content


def test_audit_change_page_shows_the_actor(client, editor):
    client.post(reverse("admin:ingestion_source_add"), _source_form())
    entry = IngestionAuditEntry.objects.using(CATALOG).get()

    response = client.get(reverse("admin:ingestion_ingestionauditentry_change", args=[entry.pk]))

    assert '<div class="readonly">editor@example.test</div>' in response.content.decode()


@pytest.mark.parametrize(
    "model", ["source", "tosreview", "venue", "event", "eventstatechange", "ingestionauditentry"]
)
def test_changelists_render(client, model):
    EventStateChangeFactory()

    assert client.get(reverse(f"admin:ingestion_{model}_changelist")).status_code == 200
