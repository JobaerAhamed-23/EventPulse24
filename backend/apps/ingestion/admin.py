"""Django admin for the Source Registry (FR-13) and the review queue (FR-57): the editorial
surface (AD-14).

Every write goes through an `ingestion` command (AD-5): `save_model` calls one and never
`obj.save()`, delete is disabled everywhere (sources are paused, never deleted, and a
resolved review item is history), and events, state changes and the audit log are read-only.
The forms run the commands' own checks in `clean()`, so a refusal shows on the form. The
admin's `LogEntry` is off: `IngestionAuditEntry` is the only history (plan R8).

---

## Why the review queue's admin is here and not in `apps/editorial/admin.py`

Django's `admin.site.register` needs the model class, and the `models-ingestion`
import-linter contract says only `apps.ingestion` may import `apps.ingestion.models`. So
the `ModelAdmin` for `ReviewItem` lives here, with the table's owner (AD-16), and
`apps/editorial/admin.py` holds the *editorial reading* of the queue — the facts a reviewer
needs and the rule about who may work it. The split is by **who owns the row**, not by who
works it.

---

## The queue's facts come from a read service, not from the template

The queue's three metrics — its size, the age of its oldest open item, and how many items
have missed their SLA — are computed by `services.review_queue_read`, not in a template.
A template has no clock and no query, and FR-29's dashboard will read the same three
numbers later, so they live in one place that both readers call.
"""

from collections.abc import Iterable
from uuid import UUID

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.editorial.services import review_queue as editorial_review_queue
from apps.ingestion.models import (
    Event,
    EventStateChange,
    IngestionAuditEntry,
    ReviewItem,
    Source,
    SourceReliabilityScore,
    TosReview,
    Venue,
)
from apps.ingestion.services import reliability, review_queue_read
from apps.ingestion.services.editorial_review import (
    EDITABLE_FIELDS,
    approve_review_item,
    check_review_edit,
    dismiss_source_item,
    edit_and_publish,
    reject_review_item,
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
from shared.db import CATALOG, PERSONAL


def _add_domain_error(form: forms.Form, exc: DomainError, field_map: dict[str, str]) -> None:
    """Show a command's refusal on the form: field errors on their fields, the rest on top.

    **Two shapes of error detail.** A command may name a field — `{"loc": ["title"], "msg":
    "not editable"}` — or it may refuse the whole edit — `"no_fields"`. The first lands on
    its field; the second has no field to land on, so it goes to the top of the form, which
    is where a reader will look for it.
    """
    items = (exc.details or {}).get("errors", []) if isinstance(exc, ValidationError) else []
    if not items:
        form.add_error(None, exc.message)
    for item in items:
        if isinstance(item, str):
            form.add_error(None, exc.message)
            continue
        field = field_map.get(item["loc"][-1], item["loc"][-1])
        form.add_error(field if field in form.fields else None, item["msg"])


def _actor_names(user_ids: Iterable[UUID]) -> dict[UUID, str]:
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
        help_text=(
            "For example 4:00:00. Leave empty for the method's default (RSS: 4 hours). "
            "An official source (API or partnership) may not be checked less often than "
            "every 4 hours, and any other source less often than every 24 hours — a "
            "cancellation has to be found inside the window the product promises (FR-53)."
        ),
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
        "ingest_claimed_at",
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
                    "ingest_claimed_at",
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


# --- The FR-57 review queue ---------------------------------------------------------------------


class ReviewItemForm(forms.ModelForm):
    """The edit form: exactly the fields an editor may correct, and nothing else.

    **A `ModelForm` over `ReviewItem`, with the event's fields declared by hand.** The
    editor is not editing the `ReviewItem` row — they are correcting the *event* the item
    is about, and the item itself is closed by the command afterwards. So the model's own
    columns are not on the form (`Meta.fields` is empty), and the five editable event
    fields are declared explicitly.

    **The model's identity is the *item*, and that is deliberate.** Django hands the
    admin's object to the form as `instance`, and every readonly panel on the page is
    rendered against `form.instance`. If the form's instance were the event, the panels
    would have nothing to describe — a panel that answers "which item is this?" needs the
    item. So the instance is the item, the fields describe the event, and the command
    writes neither on its own.

    **The form is never saved.** `save_model` calls `edit_and_publish` instead, and
    `save_form` hands the command the item rather than calling `form.save()`.

    **The field set is `EDITABLE_FIELDS`, and the set is deliberately short.** The slug is
    a public URL and changing it breaks every link that already exists; the source and
    `source_event_id` are the event's *identity* (AD-4); the confidences belong to the gate
    that computed them; and `publication_status` is not here because approve and reject
    *are* the way it moves.
    """

    title = forms.CharField(max_length=500, required=False, label="Title")
    start_time_utc = forms.DateTimeField(
        required=False,
        help_text="UTC. Use the timezone field for the local wall-clock time.",
    )
    end_time_utc = forms.DateTimeField(required=False)
    start_time_tz = forms.CharField(
        max_length=64,
        required=False,
        label="Timezone",
        help_text="IANA name, for example Europe/Berlin.",
    )
    venue = forms.ModelChoiceField(
        # The queryset is set in `__init__`: a queryset built at import time would touch
        # the database while the module loads.
        queryset=Venue.objects.none(),
        required=False,
        empty_label="— no venue —",
        label="Venue",
    )
    #: The event's version when the page was rendered. The command refuses a stale one.
    #:
    #: **Required, not optional.** The check is the optimistic lock that stops an editor
    #: overwriting an update they never saw, and a lock that is skipped when the token is
    #: absent is not a lock. When the field was optional *and* named in no fieldset, a real
    #: browser posted no token, the command's `expected_event_version is not None` check
    #: short-circuited, and the lock was quietly absent in production while every test —
    #: which posted the field by hand — passed. A missing token now means the page is
    #: stale or was tampered with, and the answer is a refusal.
    expected_event_version = forms.IntegerField(widget=forms.HiddenInput, required=True)

    class Meta:
        model = ReviewItem
        # No model fields: the item's own columns are not the editor's to edit, and the
        # fields above are declared rather than derived.
        fields = ()

    def __init__(self, *args, item=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Django passes the admin's object — the `ReviewItem` — as `instance`.
        instance = kwargs.get("instance") or self.instance
        if item is None and isinstance(instance, ReviewItem):
            item = instance
        self.item = item
        # AD-3: the venue list is read from `catalog` explicitly, never through the
        # default alias. The form field's own queryset would use the default manager.
        self.fields["venue"].queryset = Venue.objects.using(CATALOG).order_by("name")

        event = item.event if item is not None else None
        if event is None:
            return
        self.fields["expected_event_version"].initial = event.event_version
        # The form's initial values are the *event's* current facts, so `changed_data`
        # compares the editor's submission against what is true now.
        self.initial.setdefault("title", event.title)
        self.initial.setdefault("start_time_utc", event.start_time_utc)
        self.initial.setdefault("end_time_utc", event.end_time_utc)
        self.initial.setdefault("start_time_tz", event.start_time_tz)
        self.initial.setdefault("venue", event.venue_id)

    def changed_fields(self) -> dict:
        """The editor's changes, as the command's `fields` dict.

        **Only the fields that actually changed.** Sending an unchanged field would be a
        silent update of a fact the editor did not touch, and `edit_and_publish` refuses
        an empty edit — a form submitted with nothing changed would otherwise be a
        request to record a correction that never happened.

        **A cleared field counts as a change.** Setting the venue to "no venue" is a
        correction of a fact, not an absence of one, so `None` is compared rather than
        skipped.
        """
        data = self.cleaned_data
        changed = {}
        for name in EDITABLE_FIELDS:
            # `venue` is the form's name; the command's is `venue_id`.
            form_name = "venue" if name == "venue_id" else name
            if form_name not in data or form_name not in self.changed_data:
                continue
            value = data[form_name]
            changed[name] = value.pk if name == "venue_id" and value is not None else value
        return changed

    def clean(self):
        cleaned = super().clean()
        if self.errors or self.item is None:
            return cleaned
        try:
            check_review_edit(
                item_id=self.item.id,
                fields=self.changed_fields(),
                expected_event_version=cleaned.get("expected_event_version"),
            )
        except DomainError as exc:
            _add_domain_error(self, exc, {})
        return cleaned


@admin.register(ReviewItem)
class ReviewItemAdmin(CommandAdmin):
    """The FR-57 editorial review queue (AD-14): where an editor actually works.

    **Every verdict is a command.** Approve, Edit, Reject and Dismiss call
    `services.editorial_review`; the admin writes nothing itself. Delete is disabled (a
    resolved item is history, and an open one is owned by the commands that raised it),
    and the admin's `LogEntry` is off — the `IngestionAuditEntry` each command writes is
    the only history.

    **A refusal shows on the page, not as a 500.** A stale event version, an
    already-resolved item: the command raises a `DomainError`, the admin reports its
    message and changes nothing.
    """

    form = ReviewItemForm
    list_display = (
        "queue_position",
        "reason",
        "subject",
        "source_name",
        "source_badge",
        "report_count",
        "due_at",
        "sla_breached",
        "status",
        "resolution",
    )
    list_filter = ("reason", "status", "source")
    search_fields = ("event__title", "source__name")
    actions = ("approve_items", "reject_items", "dismiss_items")
    readonly_fields = (
        "reason_label",
        "status_label",
        "resolution_label",
        "raised_at_label",
        "last_raised_at_label",
        "due_at_label",
        "report_tallies",
        "resolved_at_label",
        "resolved_by",
        "event_facts",
        "source_facts",
        "source_history",
    )

    # --- access ---------------------------------------------------------------------------------

    def has_module_permission(self, request):
        # The queue is one module of the admin index, and it opens on the list. A staff
        # user with no review permission sees the index but not the queue.
        return True

    def has_view_permission(self, request, obj=None):
        # Reading the queue needs `view_reviewitem` (or `change_reviewitem`, which implies
        # it). This is the *weaker* gate and it is kept separate from the change gate
        # below — one predicate for both would let a read-only auditor publish events.
        return editorial_review_queue.may_view(request.user)

    def has_change_permission(self, request, obj=None):
        # `change` is what lets a verdict be saved. Without it the queue is read-only.
        #
        # **This is also what `@admin.action(permissions=["change"])` resolves to**, so it
        # is the gate in front of approve, reject and dismiss — and in front of the edit
        # form's POST. It asks for `change_reviewitem` specifically, never for "either
        # review permission".
        return editorial_review_queue.may_review(request.user)

    def has_add_permission(self, request):
        # A review item is raised by the commands that own the queue, never by hand.
        return False

    # --- the changelist --------------------------------------------------------------------------

    def get_queryset(self, request):
        """The queue in the order an editor should work it.

        **Open first, then priority, then the deadline, then the oldest.** The ordering
        and the SLA marks come from the read service, so the list and the summary at the
        top of the page describe the same instant.

        The priority derivation happens in the database (a `Case/When` over the reason), so
        the whole queue is one query rather than one per row.

        **The ordering is the read service's, called rather than copied.** The admin
        writes the same four `order_by` terms the service does; two orderings that
        drifted apart would put the rows in one order and the summary in another, and the
        page would describe a queue that does not exist.

        **AD-3: `using=CATALOG` is stated, not inherited.** The router would route these
        reads correctly, but every other query in this module names its database
        explicitly, and a query that relies on a router is a query whose destination
        depends on configuration elsewhere.
        """
        queryset = super().get_queryset(request).using(CATALOG)
        queryset = queryset.select_related("event", "event__source", "source")
        return review_queue_read.ordered(queryset)

    def changelist_view(self, request, extra_context=None):
        """The queue, with the three FR-57 metrics above it.

        **The numbers are computed by the read service, not in the template** — a template
        has no clock and no query, and FR-29's dashboard reads the same three numbers
        later, so they live in one place both callers use.

        **One instant for all of them.** The summary and the per-reason counts are two
        reads, and a queue that changed between them would show a summary of five beside
        counts of four. So `now` is taken once and handed to both.
        """
        context = dict(extra_context or {})
        now = timezone.now()
        context["queue_summary"] = review_queue_read.queue_summary(now=now)
        context["queue_counts"] = review_queue_read.open_item_count_by_reason(now=now)
        return super().changelist_view(request, context)

    # --- the list columns ------------------------------------------------------------------------

    @admin.display(description="", ordering="raised_at")
    def queue_position(self, item: ReviewItem) -> str:
        """A short position marker: which band of the queue this item is in.

        **The order is the read service's, and this column says so in words.** A reviewer
        reading a list of rows needs to know which one to take next, and "user report,
        overdue" is a thing a person can act on where "0" is not.
        """
        if item.status == ReviewItem.Status.RESOLVED:
            return "resolved"
        if item.reason == ReviewItem.Reason.USER_REPORTED:
            return "user report"
        if item.reason == ReviewItem.Reason.SOURCE_RELIABILITY:
            return "source reliability"
        return "in review"

    @admin.display(description="Subject")
    def subject(self, item: ReviewItem) -> str:
        """The event's title, or the source's name for a source item."""
        if item.event is not None:
            return item.event.title
        if item.source is not None:
            return item.source.name
        return "—"

    @admin.display(description="Source", ordering="source__name")
    def source_name(self, item: ReviewItem) -> str:
        source = self._source_of(item)
        return source.name if source is not None else "—"

    @admin.display(description="Badge")
    def source_badge(self, item: ReviewItem) -> str:
        """The Source Badge type (EXPERIENCE.md §4).

        **The server names the type; the client owns the label.** The admin shows the raw
        type because an editor is reading a table of facts, not a public card.
        """
        source = self._source_of(item)
        if source is None:
            return "—"
        return review_queue_read.source_badge_for(
            source_type=source.source_type,
            acquisition_method=source.acquisition_method,
        )

    @admin.display(description="Reports")
    def report_count(self, item: ReviewItem) -> int:
        """How many people reported this.

        **A count of people, not a list of them.** The `ReviewItem` row holds no user
        column at all (D4), so there is no reporter to show even in principle — the
        report itself lives in `personal`, and it never reaches this surface.
        """
        return item.report_count

    @admin.display(boolean=True, description="Overdue")
    def sla_breached(self, item: ReviewItem) -> bool:
        """Whether this item is past FR-59's 24-hour deadline.

        **Only a `user_reported` item can be overdue.** The other reasons carry no
        deadline (D8), and "overdue" is not a thing that can be true of an item that was
        never due.

        **The rule is the read service's, not a second copy of it.** The service decides
        this for the summary's `sla_breaches` count; if the list's mark and the summary's
        count came from two implementations, an item could be marked overdue on one line
        and not counted on the other, and the page would contradict itself.
        """
        return review_queue_read.item_is_past_its_sla(item)

    # --- the change page -------------------------------------------------------------------------

    def get_form(self, request, obj=None, **kwargs):
        """The edit form, built over the **event**.

        **`super().get_form` is not used.** Django's version runs `modelform_factory` over
        `self.model`, which is `ReviewItem` — and a form over the item would carry the
        item's columns, which are not the editor's to edit. The form is over the *event*,
        and the item travels with it (Django passes it as `instance`, and the form swaps
        it for the event) so `clean()` can check the edit against the item's state.
        """
        kwargs.pop("fields", None)
        return self.form

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return self.readonly_fields

    def get_fieldsets(self, request, obj=None):
        """The page's sections: the facts to decide on, and the form that corrects.

        **The editable fields sit in their own section, and they are the *event's*
        fields.** A source item has no event, so it gets no edit section at all — there is
        nothing to correct, and a form over nothing would be a page that invites a
        change and has nowhere to put it.
        """
        if obj is None:
            return ()

        queue_sections = (
            (
                "The queue",
                {"fields": ("reason_label", "status_label", "resolution_label", "due_at_label")},
            ),
            ("Resolution", {"fields": ("resolved_at_label", "resolved_by")}),
            ("When", {"fields": ("raised_at_label", "last_raised_at_label")}),
        )
        if obj.reason == ReviewItem.Reason.SOURCE_RELIABILITY:
            # A source item has no event, so the event's facts would be an empty block and
            # there is nothing to edit. Dismiss is the only verdict it takes.
            return (
                ("The source", {"fields": ("source_facts", "source_history")}),
                *queue_sections,
            )

        return (
            ("The event", {"fields": ("event_facts",)}),
            (
                "Correct the event",
                {
                    "fields": (
                        "title",
                        "start_time_utc",
                        "end_time_utc",
                        "start_time_tz",
                        "venue",
                        # The staleness token. It must be *in a fieldset* or Django never
                        # renders it, and an unrendered token is a lock that is not
                        # taken. It is a hidden input, so it costs the editor nothing.
                        "expected_event_version",
                    )
                },
            ),
            ("The source", {"fields": ("source_facts", "source_history")}),
            ("The reports", {"fields": ("report_tallies",)}),
            *queue_sections,
        )

    def save_form(self, request, form, change):
        """The row the page is about: the `ReviewItem`, not the event.

        **Django's default returns `form.save(commit=False)`, which is the event.** The
        redirect after a successful save uses the object's pk, and the object must be the
        item — the editor was working on an item, and the item is what is now closed.
        The event is the thing that was corrected, and the command says so in its audit
        row.
        """
        return form.item

    def save_model(self, request, obj, form, change):
        """Run `edit_and_publish`. Never `obj.save()`.

        The form's `clean()` already ran `check_review_edit`, so the refusal path is
        handled; this is the write.
        """
        result = edit_and_publish(
            item_id=obj.pk,
            actor=self.actor(request),
            fields=form.changed_fields(),
            expected_event_version=form.cleaned_data.get("expected_event_version"),
            now=timezone.now(),
        )
        self.adopt(obj, result.item)

    # --- the readonly fact panels ----------------------------------------------------------------

    # **Every fact is a method on this admin, not a raw model field.** The change form is
    # a `ModelForm` over `Event` — the editor corrects the event, not the item — so Django
    # would look a raw `ReviewItem` field's label up on `Event` and fail. A method here
    # resolves its label against this admin, and gives the reviewer a considered label
    # rather than a column name.

    @admin.display(description="Reason")
    def reason_label(self, item: ReviewItem) -> str:
        """Why the item is in the queue, in words."""
        return {
            ReviewItem.Reason.USER_REPORTED: "A user reported this listing.",
            ReviewItem.Reason.IN_REVIEW: "The confidence gate quarantined this event.",
            ReviewItem.Reason.SOURCE_RELIABILITY: "This source keeps being wrong.",
        }.get(item.reason, item.reason)

    @admin.display(description="Status")
    def status_label(self, item: ReviewItem) -> str:
        return "Open" if item.status == ReviewItem.Status.OPEN else "Resolved"

    @admin.display(description="Resolution")
    def resolution_label(self, item: ReviewItem) -> str:
        """The verdict, or a note that there has not been one."""
        if not item.resolution:
            return "— not resolved —"
        return item.resolution.replace("_", " ")

    @admin.display(description="Raised at")
    def raised_at_label(self, item: ReviewItem) -> str:
        return f"{item.raised_at:%Y-%m-%d %H:%M} UTC"

    @admin.display(description="Last raised at")
    def last_raised_at_label(self, item: ReviewItem) -> str:
        return f"{item.last_raised_at:%Y-%m-%d %H:%M} UTC"

    @admin.display(description="Due at (FR-59's 24h SLA)")
    def due_at_label(self, item: ReviewItem) -> str:
        """The deadline, or a note that this item has none.

        **Only a `user_reported` item has a deadline** (D8), so "no deadline" is a fact
        about the kind of item, not a gap in the data.
        """
        if item.due_at is None:
            return "— no deadline (only user reports have one) —"
        return f"{item.due_at:%Y-%m-%d %H:%M} UTC"

    @admin.display(description="Resolved at")
    def resolved_at_label(self, item: ReviewItem) -> str:
        if item.resolved_at is None:
            return "—"
        return f"{item.resolved_at:%Y-%m-%d %H:%M} UTC"

    @admin.display(description="The event")
    def event_facts(self, item: ReviewItem) -> str:
        """The event's current facts, or a note that there is no event.

        **The facts as they are now, not as they were when the item was raised.** An
        editor decides on what is true now, and the version is carried alongside so the
        command can refuse an edit made against a stale view.
        """
        event = item.event
        if event is None:
            return "— this item is about a source, not an event —"
        venue = event.venue.name if event.venue is not None else "no venue"
        # An event may have no end time, and "no end time" is a fact the editor reads.
        ends = (
            f"{event.end_time_utc:%Y-%m-%d %H:%M} UTC"
            if event.end_time_utc is not None
            else "not set"
        )
        return (
            f"{event.title}\n"
            f"Starts: {event.start_time_utc:%Y-%m-%d %H:%M} UTC "
            f"({event.start_time_tz})\n"
            f"Ends: {ends}\n"
            f"Venue: {venue}\n"
            f"Status: {event.status} · publication: {event.publication_status}\n"
            f"Version: {event.event_version}"
        )

    @admin.display(description="The source")
    def source_facts(self, item: ReviewItem) -> str:
        """The source's facts, for both kinds of item.

        **An event item's source is the event's source, not the item's.** D1 says a target
        is an Event *or* a Source, never both: a `user_reported` item names the event and
        leaves `source` null, so the source is one hop away. An editor is told which
        source the listing came from either way.
        """
        source = self._source_of(item)
        if source is None:
            return "—"
        badge = review_queue_read.source_badge_for(
            source_type=source.source_type, acquisition_method=source.acquisition_method
        )
        return (
            f"{source.name}\n"
            f"Type: {source.source_type} · method: {source.acquisition_method} "
            f"· badge: {badge}\n"
            f"Status: {source.status} · terms: {source.tos_status}\n"
            f"City: {source.city or '—'}\n"
            f"URL: {source.url}"
        )

    @staticmethod
    def _source_of(item: ReviewItem) -> Source | None:
        """The source an item is about: its own, or its event's."""
        if item.source is not None:
            return item.source
        if item.event is not None:
            return item.event.source
        return None

    @admin.display(description="Verdict history")
    def source_history(self, item: ReviewItem) -> str:
        """The source's verdict history — the facts FR-16's score is computed from.

        **The stored score is shown, and the observations that produced it.** The score
        itself lives on `Source.reliability_score`, written by
        `reliability-recompute-and-escalation` in the same transaction as the row it
        computed — so this reads it rather than recomputing it, which would be a second
        implementation of that work item's job.

        **The framing is always there, even with no verdicts.** "No verdicts recorded yet"
        would read as "nothing happened"; what is true is "nothing has been decided about
        this source yet", and the label says which.
        """
        source = self._source_of(item)
        if source is None:
            return "—"
        score = reliability.current_score(source)
        lines = [
            f"Reliability score: {score} (as of {source.reliability_scored_at:%Y-%m-%d %H:%M})"
            if source.reliability_scored_at is not None
            else f"Reliability score: {score} (the prior — not yet computed)",
            "",
            "The score is computed from these:",
            "",
        ]
        observations = review_queue_read.list_source_observations(source_id=source.pk)
        if not observations:
            lines.append("No verdicts recorded yet.")
            return "\n".join(lines)
        for observation in observations:
            subject = observation.event_title or "the source itself"
            when = f"{observation.occurred_at:%Y-%m-%d %H:%M}"
            lines.append(f"{when}  {observation.kind:<10} {subject}")
        return "\n".join(lines)

    @admin.display(description="Report tallies")
    def report_tallies(self, item: ReviewItem) -> str:
        """The four report categories, as counts.

        **Counts, never names.** The reporters live in `personal` and their identities
        never reach this surface (AD-3, D4).
        """
        if item.report_count == 0:
            return "No reports."
        parts = []
        for category, column in ReviewItem.REPORT_FIELDS.items():
            count = getattr(item, column)
            if count:
                parts.append(f"{category.replace('_', ' ')}: {count}")
        return " · ".join(parts)

    @admin.display(description="Resolved by")
    def resolved_by(self, item: ReviewItem) -> str:
        """Who resolved it, and how.

        **The name is read from `personal` for display only.** The stored actor is an id
        (AD-3, OQ-8), and a username never reaches `catalog`.
        """
        if item.resolved_by_kind == "":
            return "—"
        if item.resolved_by_kind == ActorKind.SYSTEM:
            return f"{item.resolved_by_label} (system job)"
        name = editorial_review_queue.editor_name(item.resolved_by_id)
        return name or f"unknown user {item.resolved_by_id}"

    # --- the verdicts ----------------------------------------------------------------------------

    def _verdict(self, request, item_ids, command, **kwargs) -> int:
        """Run one command over a selection, reporting each refusal. Returns how many acted.

        **A refusal is a message, not a crash.** A stale version or an item someone else
        already resolved is a thing the reviewer needs to read, so each one becomes its
        own message and the rest of the selection still goes through.

        **The change permission is checked here, and not only by the action decorator.**
        Django's `permissions=["change"]` on an `@admin.action` is *advisory*: it filters
        the action out of the dropdown, and the changelist's own gate is
        `has_view_or_change_permission` — which a read-only viewer satisfies. A POST that
        names the action directly is resolved by name, without a second permission check.
        So the decorator alone would let a user holding only `view_reviewitem` approve,
        reject and dismiss by posting the action name. **This check is the enforcing one**,
        and it is here rather than in each action so that all three share one rule.
        """
        if not editorial_review_queue.may_review(request.user):
            raise PermissionDenied
        acted = 0
        for item_id in item_ids:
            try:
                command(item_id=item_id, actor=self.actor(request), now=timezone.now(), **kwargs)
            except DomainError as exc:
                self.message_user(request, exc.message, level=messages.WARNING)
            else:
                acted += 1
        return acted

    @admin.action(description="Approve selected items", permissions=["change"])
    def approve_items(self, request, queryset):
        """Approve: publish a quarantined event, or confirm a reported one is fine."""
        acted = self._verdict(
            request, list(queryset.values_list("pk", flat=True)), approve_review_item
        )
        self.message_user(request, f"{acted} item(s) approved.")

    @admin.action(description="Reject selected items", permissions=["change"])
    def reject_items(self, request, queryset):
        """Reject: the listing is bad. Hides the event and cancels saved users' reminders."""
        acted = self._verdict(
            request, list(queryset.values_list("pk", flat=True)), reject_review_item
        )
        self.message_user(request, f"{acted} item(s) rejected.")

    @admin.action(description="Dismiss selected source items", permissions=["change"])
    def dismiss_items(self, request, queryset):
        """Dismiss a source item: no fault found. The Source is not touched (FR-16)."""
        acted = self._verdict(
            request, list(queryset.values_list("pk", flat=True)), dismiss_source_item
        )
        self.message_user(request, f"{acted} item(s) dismissed.")


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


@admin.register(SourceReliabilityScore)
class SourceReliabilityScoreAdmin(ReadOnlyAdmin):
    """The score history: one row per source per week (FR-16).

    **Read-only because the score is computed, never typed.** The recompute job is the only
    writer, and it writes the row and the source's current score in one transaction. The
    history is what makes the spike rule's comparison possible — "last week" is a row here.
    """

    list_display = ("source", "period_start", "score", "positives", "negatives", "computed_at")
    list_filter = ("period_start",)
    list_select_related = ("source",)
    ordering = ("-period_start", "source")


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
        names = _actor_names(e.actor_id for e in entries if e.actor_id)
        for entry in entries:
            entry.actor_name = names.get(entry.actor_id)
        return changelist

    @admin.display(description="Who")
    def who(self, entry: IngestionAuditEntry) -> str:
        if entry.actor_kind == ActorKind.SYSTEM:
            return f"{entry.actor_label} (system job)"
        if not hasattr(entry, "actor_name"):  # the detail page: one lookup
            entry.actor_name = _actor_names([entry.actor_id]).get(entry.actor_id)
        return entry.actor_name or f"unknown user {entry.actor_id}"
