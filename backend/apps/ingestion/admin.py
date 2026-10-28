"""Django admin for the Source Registry (FR-13): the editorial surface (AD-14).

Every write goes through an `ingestion` command (AD-5): `save_model` calls one and never
`obj.save()`, delete is disabled everywhere (sources are paused, never deleted), and events,
state changes and the audit log are read-only. The forms run the commands' own checks in
`clean()`, so a refusal shows on the form. The admin's `LogEntry` is off: `IngestionAuditEntry`
is the only history (plan R8).
"""

from collections.abc import Iterable
from uuid import UUID

from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

from apps.ingestion.models import (
    Event,
    EventStateChange,
    IngestionAuditEntry,
    Source,
    TosReview,
    Venue,
)
from apps.ingestion.services.source_registry import (
    EDITABLE_SOURCE_FIELDS,
    CrawlNeedsTosReviewError,
    TosReviewInput,
    check_source_change,
    clean_tos_review,
    pause_source,
    record_tos_review,
    register_source,
    resume_source,
    update_source,
)
from apps.ingestion.services.venue_registry import (
    check_new_venue,
    clean_venue_tz,
    register_venue,
    set_venue_timezone,
)
from domain.errors import DomainError, ValidationError
from shared.actor import Actor, ActorKind
from shared.db import PERSONAL


def _add_domain_error(form: forms.Form, exc: DomainError, field_map: dict[str, str]) -> None:
    """Show a command's refusal on the form: field errors on their fields, the rest on top."""
    items = (exc.details or {}).get("errors", []) if isinstance(exc, ValidationError) else []
    if not items:
        form.add_error(None, exc.message)
    for item in items:
        field = field_map.get(item["loc"][-1], item["loc"][-1])
        form.add_error(field if field in form.fields else None, item["msg"])


def _usernames(user_ids: Iterable[UUID]) -> dict[UUID, str]:
    # AD-3: the actor is stored by id only; the name is read from `personal` for display.
    user_model = get_user_model()
    rows = user_model.objects.using(PERSONAL).filter(pk__in=set(user_ids))
    return dict(rows.values_list("pk", user_model.USERNAME_FIELD))


class CommandAdmin(admin.ModelAdmin):
    """Base for every ingestion admin: no delete path, no direct save, no `LogEntry`."""

    def has_delete_permission(self, request, obj=None):
        return False

    def delete_model(self, request, obj):
        raise PermissionDenied

    def delete_queryset(self, request, queryset):
        raise PermissionDenied

    def save_model(self, request, obj, form, change):
        raise PermissionDenied  # subclasses that allow saving call a command instead

    def save_related(self, request, form, formsets, change):
        pass  # no M2M fields, and every inline is view-only

    def construct_change_message(self, request, form, formsets, add=False):
        # Only LogEntry reads it, and it would read formset.new_objects, which exists only
        # after the formset.save() that save_related skips.
        return []

    def log_addition(self, request, obj, message):
        pass

    def log_change(self, request, obj, message):
        pass

    def log_deletions(self, request, queryset):
        pass

    @staticmethod
    def actor(request) -> Actor:
        # By value, no label: a username never reaches `catalog` (design D17, OQ-8).
        return Actor.user(request.user.pk)

    @staticmethod
    def adopt(obj, row) -> None:
        """Point the admin's unsaved instance at the row the command stored (for the redirect)."""
        obj.pk = row.pk
        obj._state.adding = False
        obj.refresh_from_db()


class ReadOnlyAdmin(CommandAdmin):
    """History and pipeline output: viewable, never written from admin."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# --- Sources and ToS reviews ---------------------------------------------------------------


class SourceForm(forms.ModelForm):
    ingestion_cadence = forms.DurationField(
        required=False,
        help_text="For example 4:00:00. Leave empty for the method's default (RSS: 4 hours).",
    )
    tos_approved = forms.BooleanField(
        required=False,
        label="Terms reviewed and approved",
        help_text=(
            "I reviewed this source's terms for its acquisition method and approve them. "
            "Required to register a crawl source, switch a source to crawl, or move a crawl "
            "source to a new host (FR-17)."
        ),
    )
    tos_evidence_url = forms.CharField(required=False, max_length=2048, label="Terms page reviewed")
    tos_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    TOS_INPUTS = ("tos_approved", "tos_evidence_url", "tos_notes")

    # Set per request by SourceAdmin.get_form: recording a ToS review needs the same per-model
    # grant as the TosReview admin (AD-14), not just change_source.
    can_review_tos = False

    class Meta:
        model = Source
        fields = list(EDITABLE_SOURCE_FIELDS)

    def source_values(self) -> dict[str, object]:
        """The registry fields to send: all of them on add, the changed ones on change."""
        data = self.cleaned_data
        if self.instance._state.adding:
            names = [f for f in EDITABLE_SOURCE_FIELDS if f in data]
            if data.get("ingestion_cadence") is None:
                names.remove("ingestion_cadence")  # the command applies the method default
        else:
            names = [f for f in EDITABLE_SOURCE_FIELDS if f in self.changed_data]
        return {f: data[f] for f in names}

    def tos_review(self) -> TosReviewInput | None:
        if not (self.can_review_tos and self.cleaned_data.get("tos_approved")):
            return None
        return TosReviewInput(
            decision=TosReview.Decision.APPROVED,
            evidence_url=self.cleaned_data.get("tos_evidence_url", ""),
            notes=self.cleaned_data.get("tos_notes", ""),
        )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("tos_approved") and not self.can_review_tos:
            self.add_error("tos_approved", "Recording a terms review needs permission to add one.")
        if self.errors:
            return cleaned
        # Before _post_clean, the instance still holds the stored values.
        current = None if self.instance._state.adding else self.instance
        try:
            check_source_change(
                values=self.source_values(), current=current, tos_review=self.tos_review()
            )
        except CrawlNeedsTosReviewError as exc:
            self.add_error("tos_approved", exc.message)
        except DomainError as exc:
            _add_domain_error(self, exc, {"evidence_url": "tos_evidence_url", "notes": "tos_notes"})
        return cleaned


class TosReviewInline(admin.TabularInline):
    model = TosReview
    fields = ("reviewed_at", "acquisition_method", "decision", "evidence_url", "notes")
    readonly_fields = fields
    ordering = ("-reviewed_at",)
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Source)
class SourceAdmin(CommandAdmin):
    form = SourceForm
    inlines = (TosReviewInline,)
    list_display = (
        "name",
        "acquisition_method",
        "status",
        "tos_status",
        "tz_coverage",
        "last_ingested_at",
        "is_stale",
    )
    list_filter = ("acquisition_method", "status", "tos_status", "tz_coverage")
    search_fields = ("name", "url", "city")
    ordering = ("name",)
    actions = ("pause_sources", "resume_sources")
    readonly_fields = (
        "status",
        "tos_status",
        "last_ingested_at",
        "last_attempted_at",
        "consecutive_failures",
        "last_error_code",
        "stale_since",
        "etag",
        "last_modified",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (None, {"fields": ("name", "source_type", "url", "city")}),
        (
            "Acquisition",
            {
                "fields": (
                    "acquisition_method",
                    "ingestion_cadence",
                    "freshness_ttl_hours",
                    "tz_coverage",
                )
            },
        ),
        (
            "Terms of service",
            {"fields": ("tos_status", "tos_approved", "tos_evidence_url", "tos_notes")},
        ),
        (
            "Ingestion state",
            {
                "fields": (
                    "status",
                    "last_ingested_at",
                    "last_attempted_at",
                    "consecutive_failures",
                    "last_error_code",
                    "stale_since",
                    "etag",
                    "last_modified",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.can_review_tos = request.user.has_perm("ingestion.add_tosreview")
        return form

    def get_fieldsets(self, request, obj=None):
        if request.user.has_perm("ingestion.add_tosreview"):
            return self.fieldsets
        hidden = SourceForm.TOS_INPUTS
        return [
            (name, {**opts, "fields": [f for f in opts["fields"] if f not in hidden]})
            for name, opts in self.fieldsets
        ]

    @admin.display(boolean=True, description="Stale")
    def is_stale(self, source: Source) -> bool:
        # FR-13: set by the scheduler when no ingestion landed within 2x the cadence.
        return source.stale_since is not None

    def save_model(self, request, obj, form, change):
        if change:
            row = update_source(
                actor=self.actor(request),
                source_id=obj.pk,
                changes=form.source_values(),
                tos_review=form.tos_review(),
            )
        else:
            row = register_source(
                actor=self.actor(request), tos_review=form.tos_review(), **form.source_values()
            )
        self.adopt(obj, row)

    @admin.action(description="Pause selected sources", permissions=["change"])
    def pause_sources(self, request, queryset):
        for source_id in queryset.values_list("pk", flat=True):
            pause_source(actor=self.actor(request), source_id=source_id)
        self.message_user(request, "The selected sources are paused.")

    @admin.action(description="Resume selected sources", permissions=["change"])
    def resume_sources(self, request, queryset):
        for source_id in queryset.values_list("pk", flat=True):
            resume_source(actor=self.actor(request), source_id=source_id)
        self.message_user(request, "The selected sources are active again.")


class TosReviewForm(forms.ModelForm):
    class Meta:
        model = TosReview
        fields = ("source", "decision", "evidence_url", "notes")

    def review(self) -> TosReviewInput:
        return TosReviewInput(
            decision=self.cleaned_data["decision"],
            evidence_url=self.cleaned_data.get("evidence_url", ""),
            notes=self.cleaned_data.get("notes", ""),
        )

    def clean(self):
        cleaned = super().clean()
        if not self.errors:
            try:
                clean_tos_review(self.review())
            except DomainError as exc:
                _add_domain_error(self, exc, {})
        return cleaned


@admin.register(TosReview)
class TosReviewAdmin(CommandAdmin):
    """Reviews are records (kept 7 years): added through `record_tos_review`, never edited."""

    form = TosReviewForm
    list_display = ("source", "acquisition_method", "decision", "reviewed_at")
    list_filter = ("decision", "acquisition_method")
    list_select_related = ("source",)
    ordering = ("-reviewed_at",)

    def has_change_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        row = record_tos_review(
            actor=self.actor(request),
            source_id=form.cleaned_data["source"].pk,
            review=form.review(),
        )
        self.adopt(obj, row)


# --- Venues ---------------------------------------------------------------------------------


class VenueForm(forms.ModelForm):
    class Meta:
        model = Venue
        fields = ("name", "city", "country_code", "tz")
        help_texts = {"tz": "IANA timezone, for example Europe/Berlin."}

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        try:
            if self.instance._state.adding:
                check_new_venue(
                    name=cleaned.get("name"),
                    city=cleaned.get("city"),
                    country_code=cleaned.get("country_code"),
                    tz=cleaned.get("tz"),
                )
            elif "tz" in self.changed_data:
                clean_venue_tz(cleaned.get("tz"))
        except DomainError as exc:
            _add_domain_error(self, exc, {})
        return cleaned


@admin.register(Venue)
class VenueAdmin(CommandAdmin):
    """Name, city and country make the fingerprint, so only `tz` changes later (plan R7)."""

    form = VenueForm
    list_display = ("name", "city", "country_code", "tz")
    list_filter = ("country_code",)
    search_fields = ("name", "city")
    ordering = ("name",)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ("name", "city", "country_code", "tz")
        return ("name", "city", "country_code", "venue_fingerprint", "tz", "created_at")

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return ("name", "city", "country_code", "venue_fingerprint", "created_at")

    def save_model(self, request, obj, form, change):
        data = form.cleaned_data
        if not change:
            row = register_venue(
                actor=self.actor(request),
                name=data["name"],
                city=data["city"],
                country_code=data["country_code"],
                tz=data.get("tz"),
            )
        elif "tz" in form.changed_data:
            row = set_venue_timezone(actor=self.actor(request), venue_id=obj.pk, tz=data["tz"])
        else:
            row = obj
        self.adopt(obj, row)


# --- Read-only: events, state history, audit log --------------------------------------------


@admin.register(Event)
class EventAdmin(ReadOnlyAdmin):
    list_display = (
        "title",
        "start_time_utc",
        "start_time_tz",
        "status",
        "publication_status",
        "tz_review_pending",
        "source",
    )
    list_filter = ("status", "publication_status", "tz_review_pending")
    list_select_related = ("source",)
    search_fields = ("title", "slug")
    ordering = ("-start_time_utc",)


@admin.register(EventStateChange)
class EventStateChangeAdmin(ReadOnlyAdmin):
    list_display = ("event", "kind", "event_version", "occurred_at", "propagated_at")
    list_filter = ("kind",)
    list_select_related = ("event",)
    ordering = ("-occurred_at",)


@admin.register(IngestionAuditEntry)
class IngestionAuditEntryAdmin(ReadOnlyAdmin):
    """Who changed what, and when (FR-13: every registry change is logged)."""

    list_display = ("at", "who", "action", "target_type", "target_id")
    list_filter = ("action", "target_type")
    date_hierarchy = "at"
    ordering = ("-at",)
    readonly_fields = ("who",)

    def get_changelist_instance(self, request):
        changelist = super().get_changelist_instance(request)
        entries = list(changelist.result_list)  # evaluates and caches the page's rows
        names = _usernames(e.actor_id for e in entries if e.actor_id)
        for entry in entries:
            entry.actor_name = names.get(entry.actor_id)
        return changelist

    @admin.display(description="Who")
    def who(self, entry: IngestionAuditEntry) -> str:
        if entry.actor_kind == ActorKind.SYSTEM:
            return f"{entry.actor_label} (system job)"
        if not hasattr(entry, "actor_name"):  # the detail page: one lookup
            entry.actor_name = _usernames([entry.actor_id]).get(entry.actor_id)
        return entry.actor_name or f"unknown user {entry.actor_id}"
