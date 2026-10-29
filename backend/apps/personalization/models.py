"""The user's world, in the `personal` schema (AD-3, AD-16, AD-21).

`personalization` owns every model here; `delivery` owns `REMINDER_PLAN`, and `ingestion`
owns `EVENT`. Nothing in this module relates to another schema: a saved public event is
held by **value** (`event_id` is a UUID with no FK), and a conflict's two sides are held by
value too. The `catalog` side of a saved event is read through `ingestion`'s published
interface and copied into a snapshot.

Design: .specs-fire/intents/personal-events-and-saved-catalog/work-items/
personalization-models-design.md (decisions D1-D28). Integrity the database can hold is a
constraint or a trigger in migration 0001; what it can't (IANA validity, conflict arithmetic,
the save-race protocol) belongs to the commands.
"""

from django.db import models
from django.utils import timezone

from shared.models import AuditEntry, UUIDv7Model
from shared.retention import RetentionCategory


class PersonalEvent(UUIDv7Model):
    """An event the user created themselves (FR-18).

    UTC is the storage truth and the timezone is explicit (AD-6): `start_utc` is the
    instant and `start_time_tz` is the IANA zone the user meant. The zone is validated at the
    command boundary, because a database check cannot see the timezone database.

    The Reminder Plan is deliberately *not* a field here. `delivery` owns `REMINDER_PLAN`
    (AD-16), and `personalization` attaches the default by calling `delivery`'s published
    service.
    """

    class Source(models.TextChoices):
        """Where a personal event came from. FR-18 fixes the first value."""

        USER_CREATED = "user_created"
        # AD-18's calendar import will add its own value when FR-50 lands.

    retention_category = RetentionCategory.ACCOUNT_CONTENT

    # The user, by value (OQ-8): no relation to User, no GenericForeignKey.
    user_id = models.UUIDField()
    name = models.CharField(max_length=200)
    start_utc = models.DateTimeField()
    # Null means the event has no end: an open-ended interval, which overlaps everything
    # after it (domain.conflict).
    end_utc = models.DateTimeField(null=True, blank=True)
    # IANA name, e.g. "America/Los_Angeles". Validated by the command, not by a check.
    start_time_tz = models.CharField(max_length=64)
    location = models.CharField(max_length=300, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.USER_CREATED)
    # Rises with every mutation. AD-7's send key uses it, so it only ever goes up; the
    # command layer owns the increment (the model cannot know which write is legitimate).
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_utc__isnull=True)
                | models.Q(end_utc__gte=models.F("start_utc")),
                name="personal_event_end_after_start_ck",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1), name="personal_event_version_positive_ck"
            ),
        ]
        indexes = [
            # The Timeline (FR-32) and the Pulse Digest (FR-19) both scan one user's
            # events by start.
            models.Index(fields=["user_id", "start_utc"], name="personal_event_user_start_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class SavedEvent(UUIDv7Model):
    """One user's save of a public catalog Event, with the propagated time snapshot (AD-21).

    `event_id` is the catalog Event's id **by value** — never a foreign key, because AD-3
    forbids a relation across the schema wall. The snapshot (`start_utc`, `end_utc`,
    `event_version`) is taken from `catalog` at save time and thereafter updated only by
    AD-17 propagation; the Timeline and conflict detection read the snapshot and never join
    `catalog`.

    `event_version` is what makes that propagation idempotent: a change is applied only when
    its version is greater than the one stored here, so a retried, partial or out-of-order
    run can neither double-apply nor let an older postponement overwrite a newer one.
    """

    retention_category = RetentionCategory.ACCOUNT_CONTENT

    user_id = models.UUIDField()
    # The catalog Event's id, by value. No FK: this app may not relate to `catalog`.
    event_id = models.UUIDField()
    # The snapshot.
    start_utc = models.DateTimeField()
    end_utc = models.DateTimeField(null=True, blank=True)
    event_version = models.PositiveIntegerField()
    saved_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_id", "event_id"], name="saved_event_user_event_uq"
            ),
            models.CheckConstraint(
                condition=models.Q(event_version__gte=1), name="saved_event_version_positive_ck"
            ),
        ]
        indexes = [
            # AD-17 propagation finds every save of one event, across all users.
            models.Index(fields=["event_id"], name="saved_event_event_idx"),
        ]

    def __str__(self) -> str:
        return f"saved {self.event_id}"


class ConflictPair(UUIDv7Model):
    """One persisted conflict between two of a user's events (AD-21, FR-58).

    The Pulse Card indicator, the Timeline block indicator and `/conflicts` all read these
    rows, so the indicator is symmetric by construction: there is one row per pair, not one
    per surface.

    Each side is a `(kind, id)` pair held **by value**. A `GenericForeignKey` is forbidden
    (OQ-8), and the side's type cannot be read from a UUID, so the kind is stored beside the
    id.

    The unique constraint below is symmetric only if the two sides are normalised before
    writing — lexicographically on `(kind, id)` — so `(A, B)` and `(B, A)` are one row.
    That normalisation belongs to the command layer, which is this table's only writer.
    """

    class SideKind(models.TextChoices):
        """Which kind of record a side refers to."""

        PERSONAL_EVENT = "personal_event"
        SAVED_EVENT = "saved_event"

    class Kind(models.TextChoices):
        """Which prompt the pair came from.

        Not derivable from the sides: a personal event can conflict with a saved event by
        time, or be a duplicate of it by name. The prompt's button set depends on it.
        """

        TIME = "time"
        DUPLICATE = "duplicate"

    class Status(models.TextChoices):
        """AD-21 names these three exactly."""

        ACTIVE = "active"
        RESOLVED = "resolved"
        # Closed because a catalog state change removed the overlap. Not a user resolution.
        CLEARED_BY_STATE_CHANGE = "cleared_by_state_change"

    class Resolution(models.TextChoices):
        """The user's decision on a conflict prompt (PRD §3).

        There is no `dismiss` value: FR-58 says the user must make an explicit choice.
        `edit_new` is for a time conflict; `update_existing` is for a duplicate.
        """

        KEEP_BOTH = "keep_both"
        EDIT_NEW = "edit_new"
        DELETE_NEW = "delete_new"
        UPDATE_EXISTING = "update_existing"

    retention_category = RetentionCategory.ACCOUNT_CONTENT

    user_id = models.UUIDField()
    kind = models.CharField(max_length=16, choices=Kind.choices)
    # The two sides, by value.
    left_kind = models.CharField(max_length=16, choices=SideKind.choices)
    left_id = models.UUIDField()
    right_kind = models.CharField(max_length=16, choices=SideKind.choices)
    right_id = models.UUIDField()
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.ACTIVE)
    # The user's decision. Null for a pair closed by a state change: that is exactly what
    # makes a cleared pair distinguishable from a resolved one.
    resolution = models.CharField(max_length=32, choices=Resolution.choices, null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    detected_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_id", "left_kind", "left_id", "right_kind", "right_id"],
                name="conflict_pair_pair_uq",
            ),
            # The two sides are the same record only when the kind *and* the id match, so the
            # sides differ unless both match.
            models.CheckConstraint(
                condition=~(
                    models.Q(left_kind=models.F("right_kind"))
                    & models.Q(left_id=models.F("right_id"))
                ),
                name="conflict_pair_sides_differ_ck",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="active")
                    & models.Q(resolution__isnull=True)
                    & models.Q(resolved_at__isnull=True)
                )
                | (
                    models.Q(status="resolved")
                    & models.Q(resolution__isnull=False)
                    & models.Q(resolved_at__isnull=False)
                )
                | (
                    models.Q(status="cleared_by_state_change")
                    & models.Q(resolution__isnull=True)
                    & models.Q(resolved_at__isnull=False)
                ),
                name="conflict_pair_status_ck",
            ),
            # A time conflict offers edit_new; a duplicate offers update_existing. keep_both
            # and delete_new are legal for both.
            models.CheckConstraint(
                condition=(
                    models.Q(kind="time")
                    & (
                        models.Q(resolution__isnull=True)
                        | models.Q(resolution__in=["keep_both", "edit_new", "delete_new"])
                    )
                )
                | (
                    models.Q(kind="duplicate")
                    & (
                        models.Q(resolution__isnull=True)
                        | models.Q(resolution__in=["keep_both", "update_existing", "delete_new"])
                    )
                ),
                name="conflict_pair_resolution_kind_ck",
            ),
        ]
        indexes = [
            # The conflict list and the Pulse Card indicator both read a user's open pairs.
            models.Index(fields=["user_id", "status"], name="conflict_pair_user_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.kind} conflict {self.status}"


class PersonalizationAuditEntry(AuditEntry):
    """The `personalization` audit log (AD-5). Append-only; written only through `write_audit`."""

    retention_category = RetentionCategory.AUDIT_LOG
