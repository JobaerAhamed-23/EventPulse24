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

from apps.personalization.fields import EncryptedTextField
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
        # AD-18 / FR-50: an event imported from a connected calendar.
        CALENDAR_IMPORT = "calendar_import"

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
    # AD-18: the connection an imported event came from, **by value** — no foreign key.
    # `CalendarConnection` is in the same schema (`personal`), so this does not cross the
    # AD-3 wall, but the project holds every relation by value (OQ-8), and a foreign key
    # would couple the purge of a connection to the purge of its events. Disconnect
    # destroys the credential first and purges the events second (D7), which is two
    # explicit steps rather than a cascade.
    # Null for a user-created event; the check constraint below ties the two together.
    calendar_connection_id = models.UUIDField(null=True, blank=True)
    # The provider's own identifier for the event (the ICS UID). Null for a user-created
    # event. Together with the connection id it makes a re-sync an upsert rather than a
    # duplicate.
    source_uid = models.CharField(max_length=255, null=True, blank=True)
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
            # AD-18: an imported event always names its connection, and a user-created
            # event never does. The database holds this, so a bug in the import path
            # cannot leave an imported event orphaned.
            models.CheckConstraint(
                condition=(
                    models.Q(source="calendar_import")
                    & models.Q(calendar_connection_id__isnull=False)
                )
                | (
                    ~models.Q(source="calendar_import")
                    & models.Q(calendar_connection_id__isnull=True)
                ),
                name="personal_event_source_connection_ck",
            ),
            # AD-18 / FR-50: a re-sync upserts on (connection, uid) instead of duplicating.
            # Postgres treats NULLs as distinct, so the many user-created rows with no
            # source_uid do not collide.
            models.UniqueConstraint(
                fields=["calendar_connection_id", "source_uid"],
                name="personal_event_connection_uid_uq",
            ),
        ]
        indexes = [
            # The Timeline (FR-32) and the Pulse Digest (FR-19) both scan one user's
            # events by start.
            models.Index(fields=["user_id", "start_utc"], name="personal_event_user_start_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class CalendarConnection(UUIDv7Model):
    """One connected calendar and its encrypted credential (AD-18, FR-50).

    The secret ICS/webcal address **is** the credential: Google classifies it as a secret
    and offers a reset for it. So the stored value is ciphertext, produced by
    `EncryptedTextField` (AD-18's application-level key, separate from `SECRET_KEY`).

    The user is held **by value** (OQ-8): no relation to `User`, no `GenericForeignKey`.

    The status is the connection's health, which is a fact about the last interaction with
    the provider — not something derivable from the stored credential — so it is persisted
    and a poll sets it. `disconnected` means the user disconnected it: the credential has
    been destroyed (the column is `NULL`) and the row is waiting for the retention sweep.
    It is never a row that still holds a live secret (D7).

    `last_error_kind` holds a **slug**, never a message: an `httpx` exception message
    contains the full request URL, which is the credential (AD-13).

    Design: .specs-fire/intents/onboarding-and-account/work-items/
    calendar-connection-model-design.md (decisions D7, D8).
    """

    class Provider(models.TextChoices):
        """Which provider the address came from.

        The MVP connects all three the same way — by pasting an ICS/webcal address
        (Amendment A-9) — so the provider is a label on the connection, not a different
        code path. OAuth and CalDAV arrive later behind the same port.
        """

        GOOGLE = "google"
        APPLE = "apple"
        OUTLOOK = "outlook"

    class Status(models.TextChoices):
        """The connection's state (D7)."""

        ACTIVE = "active"
        # The provider said the address is no longer valid (401/403/404/410), or the
        # credential could not be read. The user is prompted to reconnect.
        NEEDS_RECONNECT = "needs_reconnect"
        # The user disconnected it. The credential is gone; the row awaits the sweep.
        DISCONNECTED = "disconnected"

    retention_category = RetentionCategory.ACCOUNT_IDENTITY

    # The user, by value (OQ-8): no relation to User.
    user_id = models.UUIDField()
    provider = models.CharField(max_length=16, choices=Provider.choices)
    # The encrypted credential. `NULL` means it has been destroyed (D7). The field
    # encrypts on write and decrypts on read; the column never holds plaintext.
    credential = EncryptedTextField(null=True, blank=True)
    # A keyed HMAC of the normalised address (D6). It makes "is this calendar already
    # connected?" one indexed lookup instead of decrypting every row, and it cannot be
    # computed by anyone without the application key.
    credential_fingerprint = models.CharField(max_length=64)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.ACTIVE)
    # When the last poll finished, and when the next one is due (AD-18: the poll interval
    # is ours to choose — `shared.constants.CALENDAR_POLL_INTERVAL`).
    last_polled_at = models.DateTimeField(null=True, blank=True)
    next_poll_at = models.DateTimeField(null=True, blank=True)
    # A slug such as "revoked" or "transient", never a message and never a URL.
    last_error_kind = models.CharField(max_length=32, null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    # A user-supplied *name* for the calendar ("Work", "Family") — not the URL, and not a
    # secret. It is shown in the UI so two calendars can be told apart.
    display_label = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # One calendar per user. The fingerprint is keyed, so this also means the same
            # address cannot be connected twice (D6).
            models.UniqueConstraint(
                fields=["user_id", "credential_fingerprint"],
                name="calendar_connection_user_credential_uq",
            ),
            # D7's state machine, held by the database: a connection that is not
            # disconnected must have a credential, and a disconnected one must not.
            models.CheckConstraint(
                condition=(models.Q(status="disconnected") & models.Q(credential__isnull=True))
                | (~models.Q(status="disconnected") & models.Q(credential__isnull=False)),
                name="calendar_connection_status_credential_ck",
            ),
        ]
        indexes = [
            # The poll scan: one user's connections by status.
            models.Index(fields=["user_id", "status"], name="calendar_conn_user_status_idx"),
            # The due-time query: the connections whose next poll is due. Partial, because
            # only an active connection is ever due.
            models.Index(
                fields=["next_poll_at"],
                name="calendar_connection_due_idx",
                condition=models.Q(status="active"),
            ),
        ]

    def __str__(self) -> str:
        # The provider and nothing else. Django's `Model.__repr__` uses `__str__`, so this
        # is also what `repr(conn)` shows — and what the admin's list column shows (AD-13).
        return f"{self.provider} calendar"


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
