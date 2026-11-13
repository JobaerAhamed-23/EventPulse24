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
from django.db.models.functions import Lower
from django.utils import timezone

# Aliased as well, because `PulseDigest` has a field named `timezone`, and a field that
# shadows the module name is a trap for whoever edits that class next.
from django.utils import timezone as django_timezone

from apps.personalization.fields import EncryptedTextField
from shared.constants import ONBOARDING_STEP_COUNT, REPORT_CATEGORIES
from shared.models import AppendOnlyModel, AuditEntry, UUIDv7Model
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
    # Whether the **user** has edited this row (D2 of the calendar-sync design).
    #
    # An imported event is a mirror of somebody else's agenda, and the user may disagree
    # with it. This flag decides who owns a row when the feed and the row disagree: the
    # feed owns an untouched import, the user owns an edited one.
    #
    # It is a stored flag rather than a heuristic ("does the row differ from the feed?"),
    # because that heuristic's answer depends on which side you look from — and because a
    # user's edit must survive the feed disagreeing with it.
    #
    # Always False for a user-created event (the user made it; there is no feed).
    user_modified = models.BooleanField(default=False)
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
            # D2: only an imported event can be "user-modified". A user-created event has
            # no feed to disagree with, so the flag would be meaningless on it — and a
            # stray True would tell the sync that the user owns a row the sync never
            # touches. The database holds this, so the flag cannot drift onto the wrong
            # kind of row.
            models.CheckConstraint(
                condition=(~models.Q(source="calendar_import") & ~models.Q(user_modified=True))
                | models.Q(source="calendar_import"),
                name="personal_event_user_modified_import_only_ck",
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
    # AD-7 scheduling: when the dispatcher claimed this connection for a sync. A claim
    # older than `CALENDAR_CLAIM_TTL` is a lost job (a worker died) and the connection
    # becomes claimable again. Null means "not claimed".
    #
    # The claim is what stops two overlapping ticks syncing the same connection twice.
    sync_claimed_at = models.DateTimeField(null=True, blank=True)
    # The provider's opaque cache validators (AD-18). They are sent back as conditional
    # headers on the next fetch, so an unchanged feed costs one 304 instead of a full
    # download.
    #
    # They are per-connection state and are not secrets — but they are never logged
    # either, on the same principle as the address: they identify the connection to
    # whoever holds the provider's log.
    etag = models.CharField(max_length=255, null=True, blank=True)
    last_modified = models.CharField(max_length=255, null=True, blank=True)
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
            # One **live** calendar per address, per user. The fingerprint is keyed, so
            # this also means the same address cannot be connected twice (D6).
            #
            # **Partial, so a disconnected row does not squat the address.** A
            # disconnected connection has had its credential destroyed, but the
            # fingerprint — a keyed HMAC of the old address — is still on the row, and
            # the row waits for the retention sweep (D7). Under an unpartial constraint
            # that fingerprint would still occupy the address, and a user who
            # disconnected a calendar and then re-added the same one would hit the
            # constraint and get a 500 for an ordinary, everyday sequence. Excluding the
            # disconnected rows says what the constraint means: *one live connection per
            # address*. The same shape as `ingestion`'s `event_live_source_item_uq`.
            models.UniqueConstraint(
                fields=["user_id", "credential_fingerprint"],
                condition=~models.Q(status="disconnected"),
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

        `skip_public` is the one resolution that acts on a **saved** side: it releases the
        user's save of a public event. It is a value of its own rather than a second
        meaning for `delete_new`, because a stored word must mean one thing — otherwise
        `/conflicts`' Resolved list and the audit trail would both have to disambiguate
        by the side's kind before they could say what the user did.
        """

        KEEP_BOTH = "keep_both"
        EDIT_NEW = "edit_new"
        DELETE_NEW = "delete_new"
        UPDATE_EXISTING = "update_existing"
        SKIP_PUBLIC = "skip_public"

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
            #
            # `skip_public` is legal for **both** kinds: the kind decides the *name* of the
            # middle action (edit_new vs update_existing), while the *side's* kind decides
            # the destructive one (delete_new against a personal side, skip_public against
            # a saved one). Which side a resolution may act on is a rule about the pair's
            # two sides, and that is only knowable by joining them — so it is enforced in
            # the service, and this constraint stays a kind-level rule.
            models.CheckConstraint(
                condition=(
                    models.Q(kind="time")
                    & (
                        models.Q(resolution__isnull=True)
                        | models.Q(
                            resolution__in=["keep_both", "edit_new", "delete_new", "skip_public"]
                        )
                    )
                )
                | (
                    models.Q(kind="duplicate")
                    & (
                        models.Q(resolution__isnull=True)
                        | models.Q(
                            resolution__in=[
                                "keep_both",
                                "update_existing",
                                "delete_new",
                                "skip_public",
                            ]
                        )
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


class Interest(UUIDv7Model):
    """One interest chip the user picked (FR-1).

    The user is held **by value** (OQ-8): no relation to `User`, no `GenericForeignKey`.

    One row per chip, with the unique constraint on `(user_id, chip_key)` — so the
    "same chip twice" rule is held by the **database**, not merely by the service. A
    concurrent double-write would be caught by the constraint even if the service's
    replace were not atomic.

    `chip_key` is a stable slug from `shared.constants.INTEREST_CHIPS` — e.g.
    `"tech_meetups"`. The display label is **not** stored: the label is prose and may
    change, and a stored label would orphan the key the day it did.
    """

    retention_category = RetentionCategory.PREFERENCE_SIGNALS

    # The user, by value (OQ-8): no relation to User.
    user_id = models.UUIDField()
    # A stable key from `shared.constants.INTEREST_CHIPS`.
    chip_key = models.CharField(max_length=64)

    class Meta:
        constraints = [
            # The same chip cannot be held twice. This is the acceptance criterion's
            # "DB constraint", held by the database so it holds under a race.
            models.UniqueConstraint(fields=["user_id", "chip_key"], name="interest_user_chip_uq"),
        ]
        indexes = [
            # The digest reads one user's chips.
            models.Index(fields=["user_id"], name="interest_user_idx"),
        ]

    def __str__(self) -> str:
        return self.chip_key


class OnboardingProgress(UUIDv7Model):
    """Where the user is in the 3-step onboarding flow (FR-1).

    One row per user. The row holds the *position* (`current_step`, 1–3) rather than the
    step's name, because the resume rule is about the position: "resumed at the same
    step" means the same place in the flow. The name is resolved through
    `shared.constants.ONBOARDING_STEPS`, so the two cannot drift.

    `last_advanced_at` is the moment the user last advanced, completed or skipped a step.
    It is what the resume window is measured against — a user who leaves mid-step and
    comes back within `ONBOARDING_RESUME_WINDOW` resumes at the same step; after the
    window, the onboarding restarts at step 1.

    `completed_at` makes completion **terminal**: a completed user is never sent back
    into onboarding, whatever the clock says.
    """

    retention_category = RetentionCategory.PREFERENCE_SIGNALS

    # The user, by value (OQ-8): no relation to User.
    user_id = models.UUIDField()
    # 1..3 — the index into `shared.constants.ONBOARDING_STEPS`.
    current_step = models.PositiveSmallIntegerField(default=1)
    # The moment the user last advanced, completed or skipped a step.
    last_advanced_at = models.DateTimeField()
    # Set when onboarding ends. A completed user is never sent back into it.
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user_id"], name="onboarding_progress_user_uq"),
            # FR-1's three-step cap, held by the database. The constant
            # `ONBOARDING_STEP_COUNT` is the source of truth; this is the backstop for a
            # row written by anything other than the command layer.
            models.CheckConstraint(
                condition=models.Q(current_step__gte=1)
                & models.Q(current_step__lte=ONBOARDING_STEP_COUNT),
                name="onboarding_progress_step_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["user_id"], name="onboarding_progress_user_idx"),
        ]

    def __str__(self) -> str:
        if self.completed_at is not None:
            return "onboarding complete"
        return f"onboarding step {self.current_step}"


class DigestPreference(UUIDv7Model):
    """When, where, and what the Pulse Digest should contain (FR-1, step 3; FR-19).

    The user is held **by value** (OQ-8): no relation to `User`.

    **The delivery time is a local wall clock, not an instant.** It is paired with an
    IANA zone, and the pair is the whole preference. Storing a UTC instant instead would
    be wrong in a way that only shows up twice a year: the user says "9am", and a UTC
    instant is "9am once, then 8am or 10am after a DST change". A wall clock plus a zone
    is what the user actually meant, and it is what `delivery` will read when it computes
    the next send time.

    **This is a small dedicated model, not a `PREFERENCE_GRAPH`.** A graph is a structure
    for a *set* of preferences with edges between them; these are a single value with
    three parts, read as a unit and written as a unit. A graph would add a node type, an
    edge type and a traversal for one row. The shape is reconsidered when a second,
    genuinely separate preference arrives — and the reason is recorded here so the next
    reader knows the decision was deliberate, not accidental.

    **The reconsideration came, and the answer was three columns on one row.** The home
    city and the personal-events opt-out arrived together, and neither is *genuinely
    separate*: the city is a third coordinate of the same question this row already
    answers — where and when the digest arrives — and the opt-out says what goes *into*
    this user's digest. Both are one row per user, read together by the composition
    service and written together by one settings command. A separate table would add an
    owner, a retention category, a backfill and a second lookup for information that
    belongs in the same row.

    **`city` is nullable, and `NULL` means "we do not know where this user is".** That is
    a real, reachable state — it is what an account has before this item, and what a user
    who declined location inference has (the personal-events opt-out is about personal
    *events*; the city is a separate choice). It is *not* the same as "the user is in
    New York City", and the difference is the whole point of the fallback: a digest that
    ranks on NYC for a user who declined inference would be showing them a city's events
    under a city they did not choose.

    **`city_source` says how the city was arrived at**, and it is what makes the
    fallback honest rather than invisible. Without it, a user whose city was inferred
    and a user whose city they chose look identical — and the digest would show
    "Brooklyn, NY" for both. A fallback the user did not pick must be *labelled* as one,
    not passed off as their city.

    **The city is not encrypted.** The email address is encrypted because it is a
    *credential* — it authenticates. A city is not a credential and authenticates
    nothing; encrypting it would make it unqueryable and unindexable for no gain. It is
    in the `personal` schema, readable only by `ep_personal`, and purged with the
    account.

    **`include_personal_events` defaults to `True`**: personal events are included unless
    the user opts out. That is PRD `[ASSUMPTION-7]` — and it is an *assumption*, still
    open as PRD Open Question #13 (owner: Product). The default **is** the assumption,
    so a reader who changes it is changing the product's default behaviour, and the
    docstring says so where they will see it.

    **The city is never in `__str__`.** It is weak location data about a real person,
    and `__str__` reaches every log line and every admin list column (AD-13). The
    delivery time and the zone are shown; the city is not.

    The zone is validated by the command, not by a check constraint: a database check
    cannot see the timezone database. The city is validated against the catalog's
    covered cities by the command, for the same reason — the database cannot know which
    cities the catalog serves.
    """

    class CitySource(models.TextChoices):
        """How the home city was arrived at.

        Not decoration: a fallback the user did not pick must be *labelled* as one, and
        the digest says "we don't have your city yet" for a fallback rather than
        implying New York City is the user's city.
        """

        # The edge's geo header, at sign-up.
        GEO = "geo"
        # The visitor's explicit choice on the preview, carried across sign-up.
        CHOICE = "choice"
        # The catalog does not cover the city we were given, so the fallback was stored.
        FALLBACK = "fallback"
        # The backfill command filled it, because the account predates this item.
        BACKFILL = "backfill"

    retention_category = RetentionCategory.PREFERENCE_SIGNALS

    # The user, by value (OQ-8): no relation to User.
    user_id = models.UUIDField()
    # A local wall clock (HH:MM), NOT an instant. Paired with `timezone`.
    delivery_time = models.TimeField()
    # An IANA zone name, e.g. "America/Los_Angeles". Validated by the command.
    timezone = models.CharField(max_length=64)
    # The user's home city, in the **catalog's own spelling** — the spelling the events
    # are filed under. Null means "not known"; see the class docstring.
    city = models.CharField(max_length=64, null=True, blank=True)
    # How the city was arrived at. Null exactly when `city` is null.
    city_source = models.CharField(max_length=16, choices=CitySource.choices, null=True, blank=True)
    # FR-19 / PRD [ASSUMPTION-7]: personal events are included unless the user opts out.
    include_personal_events = models.BooleanField(default=True)
    #: Whether this user's own event locations may leave the product in full (FR-52).
    #:
    #: **It defaults to `True`, and the default is the only thing a user has until a
    #: toggle exists.** DESIGN.md A-14 specifies the control; no surface writes this yet,
    #: so the export's redaction branch is reachable today only by a direct write. That is
    #: recorded rather than hidden: a privacy control with no UI is half a control.
    #:
    #: **It is about *export*, not about the digest.** `include_personal_events` above says
    #: what goes *into* the digest; this says whether a location leaves the product when the
    #: user asks for their data. Conflating them would let one checkbox govern two unrelated
    #: things, and a user who hid personal events from their own digest would be surprised
    #: to find their addresses stripped from their own download.
    share_precise_location = models.BooleanField(default=True)
    # When the scheduler's claim on this user's daily digest is held (AD-7).
    #
    # **Null means unclaimed.** The dispatcher takes the claim with `FOR UPDATE SKIP
    # LOCKED`, so two overlapping ticks never claim the same user: the second tick's
    # `SKIP LOCKED` skips the row the first one is holding. A claim older than
    # `DIGEST_CLAIM_TTL` is a lost job (a worker died) and becomes claimable again.
    #
    # **The claim lives here, on the preference, and not on the digest.** The thing
    # being scheduled is the *user's daily digest*, and the two facts that decide when
    # it is due — the local date and the delivery time — are both on this row. It is
    # also one row per user, so claiming it claims the user's daily composition.
    digest_claimed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user_id"], name="digest_preference_user_uq"),
            # A city and a source travel together. A city with no source is a claim
            # about where the user is with no record of how we learned it; a source with
            # no city is a record of a decision about a city we do not have. Neither is
            # a state anything should produce, so the database holds it.
            models.CheckConstraint(
                condition=(models.Q(city__isnull=True) & models.Q(city_source__isnull=True))
                | (models.Q(city__isnull=False) & models.Q(city_source__isnull=False)),
                name="digest_preference_city_source_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["user_id"], name="digest_preference_user_idx"),
        ]

    def __str__(self) -> str:
        # The delivery time and the zone — and **not the city**. The city is weak
        # location data about a real person; this string reaches every log line and every
        # admin list column (AD-13). Django's `__repr__` delegates to `__str__`, so
        # `repr()` is safe for free.
        return f"digest at {self.delivery_time} {self.timezone}"


class PersonalizationAuditEntry(AuditEntry):
    """The `personalization` audit log (AD-5). Append-only; written only through `write_audit`."""

    retention_category = RetentionCategory.AUDIT_LOG


class EventDetailOpen(UUIDv7Model):
    """That a user opened the Detail Screen for a public catalog Event (FR-24).

    **This is one of the two halves of FR-24's "qualifying user"** — the other is a save,
    and `SavedEvent` already records that. This row records the half that did not exist.

    **It is a signal about the user's behaviour, so it is `PREFERENCE_SIGNALS`.** Not
    `ACCOUNT_CONTENT`: this is not the user's own content, it is a record of what they
    looked at. Not `AUDIT_LOG`: it is not a record of a change. `PREFERENCE_SIGNALS` is
    the category whose own words are "dwell, swipes, dismissals" — this is a dwell.

    **One row per `(user, event)`, holding the *most recent* open.** An append-only log of
    every open would answer the same question with a query that counts rows, and it would
    store the user's entire viewing history of the catalog — a far larger privacy cost
    than the feature needs. The count asks one question ("has this user opened this
    event in the last 30 days?") and the answer is a boolean per pair, so the row holds
    the latest time and nothing else.

    **The last-open timestamp is enough for the window.** A user who opened an event
    sixty days ago and again today has a row saying "today", and qualifies; a user who
    opened it sixty days ago and never again has a row saying so, and does not. Because
    the row holds the most recent open, the 30-day window is exact: there is no stale
    open that survives the window, because the most recent open is the only one that
    matters.

    **What is not stored.** No IP address, no user agent, no referrer, no duration, no
    count of views. The row answers exactly one question and nothing more — and nothing
    that would be PII reaches a table (AD-13).

    **Every relation is by value (OQ-8).** `event_id` is the catalog Event's id by value,
    never a foreign key: AD-3 forbids a relation across the schema wall.

    **This row is not append-only.** It is *updated* when the user opens the same event
    again — the most recent open replaces the older one. It is not append-only because
    the whole point is to hold the most recent, and an append-only table could not do
    that without holding every open forever.

    Design: .specs-fire/intents/pulse-digest-and-trust/work-items/
    event-detail-api-design.md (decision D5).
    """

    retention_category = RetentionCategory.PREFERENCE_SIGNALS

    # The user, by value (OQ-8): no relation to User.
    user_id = models.UUIDField()
    # The catalog Event's id, by value. No FK: AD-3 forbids the relation.
    event_id = models.UUIDField()
    # When the user last opened the Detail Screen for this event.
    opened_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            # One row per pair. The count counts distinct users, and a second row for
            # the same pair would make the pair ambiguous — and would let a repeated
            # open inflate the count.
            models.UniqueConstraint(
                fields=["user_id", "event_id"], name="event_detail_open_user_event_uq"
            ),
        ]
        indexes = [
            # The neighbor count: every qualifying user for one event, within the
            # 30-day window. The index is on the event and the time, because the query
            # asks about one event and a recent window.
            models.Index(fields=["event_id", "-opened_at"], name="event_detail_open_event_idx"),
        ]

    def __str__(self) -> str:
        # The event id and nothing else. The event's title is untrusted source text, and
        # this string reaches every log line (AD-9, AD-13).
        return f"detail open {self.event_id}"


class SourceMute(UUIDv7Model):
    """How one user has asked to see (or not see) one source (FR-13, FR-16).

    **The mute is per-user state over a global catalog object.** A `Source` belongs to
    everyone; a mute belongs to one person. So the row is on the `personal` side, and the
    source is held **by value** — `source_id` is a UUID with no FK — because AD-3 forbids a
    relation across the schema wall.

    **Every relation is by value (OQ-8).** `user_id` is the user's id with no relation to
    `identity`'s `User`, and `source_id` is the catalog `Source`'s id with no relation to
    `ingestion`'s model. This is the same shape `EventNoticeMute` and `EventDetailOpen`
    already use, and the ORM is what enforces the wall.

    **There are two states, not three.** `show_less` and `mute` are stored; `default` is
    the **absence of a row**. The mockup's control has three positions, but a third
    stored state saying "default" would be a row that says nothing — and it would make
    "Restore all defaults" a three-way update instead of the bulk delete it is.

    **`mute` and `show_less` are different promises, and the model keeps them apart.**
    `mute` means "do not show me this source's events"; `show_less` means "show me fewer",
    which is a deprioritisation, not an exclusion. A "show less" that hid the events
    would be indistinguishable from a mute on the wire, and would be a lie to the user.

    **It is `PREFERENCE_SIGNALS`.** Not `ACCOUNT_CONTENT`: this is not the user's own
    content, it is a record of what they chose to see. Not `SOURCE_REGISTRY`: that
    category is the registry's own contents, and this row is about a person.

    Design: .specs-fire/intents/source-transparency-and-mute/work-items/
    settings-sources-surface-design.md (decisions D3, D4).
    """

    class State(models.TextChoices):
        """The two states a row can hold. `default` is the absence of a row."""

        SHOW_LESS = "show_less"
        MUTE = "mute"

    retention_category = RetentionCategory.PREFERENCE_SIGNALS

    # The user, by value (OQ-8): no relation to User.
    user_id = models.UUIDField()
    # The catalog `Source`'s id, by value. No FK: AD-3 forbids the relation.
    source_id = models.UUIDField()
    state = models.CharField(max_length=16, choices=State.choices)

    class Meta:
        constraints = [
            # One row per (user, source). Two rows for the same pair would make the
            # user's preference for that source ambiguous — and the read that applies it
            # would have to guess which one wins.
            models.UniqueConstraint(
                fields=["user_id", "source_id"], name="source_mute_user_source_uq"
            ),
            # The two states, enforced in the database. The model's `choices` already
            # refuse a third value in Python, but a row written by raw SQL or by a future
            # migration would not go through the model's validation — and a state the
            # composition path does not understand would be a source whose visibility
            # silently fell back to the default.
            models.CheckConstraint(
                condition=models.Q(state__in=["show_less", "mute"]),
                name="source_mute_state_ck",
            ),
        ]
        indexes = [
            # "What has this user muted, and what should they see less of?" — the question
            # the composition path asks on every read. It is asked about one user, so the
            # index leads with the user.
            models.Index(fields=["user_id"], name="source_mute_user_idx"),
        ]

    def __str__(self) -> str:
        # The source id and the state. Both are safe: the source's *name* is third-party
        # text, and this string reaches every log line (AD-9, AD-13).
        return f"source mute {self.source_id} {self.state}"


class PulseDigest(UUIDv7Model):
    """One user's Pulse Digest for one local calendar day (FR-5, FR-8, AD-10).

    **This row is the empty state.** FR-8's empty digest — a real digest with no cards —
    is a fact the user is shown ("nothing near you today"), and it is different from
    "we never composed for this user today", which is a job that has not run. One model
    with nullable columns cannot tell those apart; a parent row with zero children can.

    `is_empty` is **stored, not derived**, so a reader does not have to count children to
    know whether this was a deliberate empty digest or a composition that happened to
    fail. It is set at composition time.

    **Unlike `DigestComposition`, this row is not append-only.** A digest is a fact about
    a day, not a mutable record — but the row is still correctable, and the runtime role
    keeps `UPDATE` on it so a correction can land. That is why `is_empty` is not
    "immutable" here: the composition service sets it once, and nothing in this model
    forbids a later correction.

    **The local day is the user's day, not UTC's.** `local_date` is a `DateField` and
    `timezone` records the IANA zone it was computed in, because "today" means different
    things in Tokyo and Los Angeles and the digest must be able to say which it meant.
    The pair is the unit; `local_date` alone would be ambiguous.

    **Every relation is by value (OQ-8).** The user is a `UUIDField`, not a relation to
    `User`.

    There is no `updated_at`. A digest is a fact about a day, not a mutable record, and a
    row whose `updated_at` can change invites the question of what changed.

    Design: .specs-fire/intents/pulse-digest-and-trust/work-items/
    digest-composition-models-design.md (decisions D1, D2, D4, D8, D9, D10).
    """

    retention_category = RetentionCategory.ACCOUNT_CONTENT

    # The user, by value (OQ-8): no relation to User.
    user_id = models.UUIDField()
    # The user's local calendar day. A `DateField`, not a `DateTimeField`: the day is the
    # unit, and `timezone` says which day it was.
    local_date = models.DateField()
    # The IANA zone the local date was computed in, e.g. "America/Los_Angeles".
    timezone = models.CharField(max_length=64)
    # When the digest was composed.
    #
    # `django.utils.timezone.now` spelled out, not `timezone.now`: the field named
    # `timezone` above shadows the module inside this class body, and a field that
    # shadows an import is a trap for whoever edits this class next.
    composed_at = models.DateTimeField(default=django_timezone.now)
    # FR-8: this digest is the empty state. Stored, not derived (D1).
    is_empty = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # One digest per user per local calendar day. This is the constraint that
            # makes "deterministic per user per day" true at the database (D8).
            models.UniqueConstraint(
                fields=["user_id", "local_date"],
                name="pulse_digest_user_date_uq",
            ),
        ]
        indexes = [
            # The digest read: today's digest for this user.
            models.Index(fields=["user_id", "local_date"], name="pulse_digest_user_date_idx"),
        ]

    def __str__(self) -> str:
        # The local date and whether this is the empty state. A local date is not PII —
        # it is the user's own day, and it is already on the row (AD-13).
        state = "empty" if self.is_empty else "composed"
        return f"digest {self.local_date} ({state})"


#: The slots, in the order they are read on a digest (FR-5: the must-know card is first).
#:
#: This order is **not** alphabetical and **not** the order rows were written in, so it
#: needs a home of its own. A database index on a `CHAR` column sorts alphabetically, which
#: would put "nearby" before "must_know" and "serendipity" last — so the read sorts the
#: three rows in Python, against this tuple, and this tuple is the single place the slot
#: order lives (D12).
#:
#: It is defined here, outside `DigestComposition.Slot`, because a `TextChoices` member
#: holds a scalar: a tuple attribute inside the enum class would be read as an enum
#: member and fail at import.
DIGEST_SLOT_ORDER = ("must_know", "nearby", "serendipity")


class DigestComposition(AppendOnlyModel, UUIDv7Model):
    """One event's persisted explanation within one user's digest (AD-10, FR-5, FR-22).

    **AD-10:** "the persisted Why-this Tags, Confidence Pulse, and Source Badge for one
    Event in one user's digest at one composition time. A **Pulse Card is a projection of
    it**, never a stored entity."

    This row is not a cache of a decision — it **is** the decision. The card, the detail
    screen and (later) the email all read this row, which is the only way three surfaces
    cannot give three answers to "why this?". That is why it is append-only: a row that
    could be rewritten would let the card and the detail screen disagree.

    **Immutable, with nothing settable later (D3).** `append_only_mutable` is the
    inherited empty frozenset, so no field may ever change after insert. This differs
    from `EventStateChange`, whose `propagated_at` goes from NULL to a value exactly
    once; nothing about a composition becomes known later.

    **Every relation is by value (OQ-8, D2).** `digest_id` is the parent `PulseDigest`'s
    id as a plain `UUIDField`, *not* a foreign key — even though `PulseDigest` is in the
    same schema. A foreign key would cascade a digest's deletion into its children, and
    AD-10 says a composition is immutable and must outlive its day. `event_id` is the
    catalog Event's id by value, because AD-3 forbids a relation across the wall (the
    same treatment `SavedEvent.event_id` uses).

    `user_id` is denormalised onto the row. It is redundant with the parent digest, and
    that redundancy is the point: the Detail Screen looks up "the most recent composition
    for this `(user, event)` pair" in a single indexed lookup, and it must not have to
    join through the parent to do it (D8).

    **The score is an exact decimal, never a float.** `numeric(3,2)` holds `0.00`–`1.00`,
    the range `domain/ranking.py` produces. FR-22's bucket boundaries are exact, so the
    stored value has to be exact too.

    **The tags are keys, not display strings** (D6). The server states facts; the client
    speaks the user's language. The list order is the Why-this Tag order, exactly as
    `EventFit.tags` stores it — the two explanation kinds stay structurally parallel.

    **The Source Badge is a type, not a label and not an icon** (EXPERIENCE.md §4). The
    server names the type; the frontend owns the label and the glyph. A personal event
    has no source at all, so its badge is null — and a check constraint says so (D7).

    Design: .specs-fire/intents/pulse-digest-and-trust/work-items/
    digest-composition-models-design.md (decisions D2-D12).
    """

    class Slot(models.TextChoices):
        """Which slot the event occupies (FR-5, Amendment A-2).

        **The order the slots are read in lives in `DIGEST_SLOT_ORDER`**, just above this
        class (D12). The three slots are read in a fixed order — must-know, then nearby,
        then serendipity — and that order is not alphabetical, not numeric, and not the
        order rows were written in. A `CHAR` index sorts alphabetically, so the index on
        `(digest_id, slot)` is for *lookup*, not for *ordering*: the read sorts the three
        rows in Python, against that order.

        The order cannot live *inside* this class: a `TextChoices` member holds a scalar,
        so a tuple attribute here would be read as an enum member and fail at import.
        """

        MUST_KNOW = "must_know"
        NEARBY = "nearby"
        SERENDIPITY = "serendipity"

    class EventKind(models.TextChoices):
        """Whether the event is a public catalog Event or the user's own (D7).

        Not decoration: a personal event is a row in `personal`, not in `catalog`, so it
        has no source, no Source Badge, and no catalog `event_version`.
        """

        PUBLIC = "public"
        PERSONAL = "personal"

    retention_category = RetentionCategory.ACCOUNT_CONTENT
    # Nothing about a composition becomes known after it is written (D3).
    append_only_mutable = frozenset()

    # The parent digest's id, by value — no foreign key (D2).
    digest_id = models.UUIDField()
    # The user, by value (OQ-8): no relation to User.
    user_id = models.UUIDField()
    # The event's id, by value. A catalog Event's id for a public composition, a
    # PersonalEvent's id for a personal one. No FK: AD-3 forbids the relation.
    event_id = models.UUIDField()
    event_kind = models.CharField(max_length=16, choices=EventKind.choices)
    slot = models.CharField(max_length=16, choices=Slot.choices)
    # The raw Relevance Pulse. `numeric(3,2)` — exact, and exactly the range
    # `domain/ranking.py` produces (D5).
    score = models.DecimalField(max_digits=3, decimal_places=2)
    # FR-22's Confidence Pulse: 1 to 5, and no sixth value (D5).
    bucket = models.PositiveSmallIntegerField()
    # The ordered Why-this Tag keys. The list order is the tag order (D6).
    tags = models.JSONField(default=list)
    # The Source Badge *type*. Null for a personal event, which has no source (D6, D7).
    source_badge = models.CharField(max_length=32, null=True, blank=True)
    # The catalog Event's version at composition time. Null for a personal event (D7).
    event_version = models.PositiveIntegerField(null=True, blank=True)
    # When this composition was made.
    composed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        # The append-only guards must also apply to related-object paths (D3).
        base_manager_name = "objects"
        constraints = [
            # No duplicate event within one digest — FR-5's "a Pulse Card in the digest
            # is not a duplicate of another", held at the database (D8).
            models.UniqueConstraint(
                fields=["digest_id", "event_id"], name="digest_composition_digest_event_uq"
            ),
            # FR-22's bucket is 1 to 5.
            models.CheckConstraint(
                condition=models.Q(bucket__gte=1) & models.Q(bucket__lte=5),
                name="digest_composition_bucket_ck",
            ),
            # FR-5's three slots, and no fourth — the same argument D5 makes for the
            # bucket.
            #
            # `choices` is a Python-level convenience only: Django does not turn it into
            # a database constraint, so without this a row with `slot='bogus_slot'` is
            # perfectly writable and the digest read would silently drop it (the read
            # sorts against `DIGEST_SLOT_ORDER`, and a slot outside it has nowhere to
            # sort). The check constraint is what makes the fourth slot impossible at
            # the database, exactly as the bucket's makes a sixth bucket impossible.
            #
            # The literals are the enum's values, pinned to the enum by
            # `test_digest_composition_slot_values_match_the_constraint`.
            models.CheckConstraint(
                condition=models.Q(slot__in=["must_know", "nearby", "serendipity"]),
                name="digest_composition_slot_ck",
            ),
            # A public event has a source and a version; a personal one has neither (D7).
            #
            # The kind is compared as a literal string, not as `EventKind.PUBLIC`: the
            # enum and the model class are both still being defined while this body
            # executes, so neither name is bound yet. The literal *is* the enum's value —
            # the two are pinned together by `test_digest_composition_kind_values_match_the
            # _constraint`.
            models.CheckConstraint(
                condition=(
                    models.Q(event_kind="public")
                    & models.Q(event_version__isnull=False)
                    & models.Q(source_badge__isnull=False)
                )
                | (
                    models.Q(event_kind="personal")
                    & models.Q(event_version__isnull=True)
                    & models.Q(source_badge__isnull=True)
                ),
                name="digest_composition_kind_shape_ck",
            ),
        ]
        indexes = [
            # The Detail Screen's "most recent composition for this (user, event) pair" —
            # one indexed lookup, and the descending `composed_at` means the newest row
            # is the first the index yields (D8).
            models.Index(
                fields=["user_id", "event_id", "-composed_at"], name="digest_comp_user_event_idx"
            ),
            # The digest read: every composition of one digest. For lookup, not order (D12).
            models.Index(fields=["digest_id", "slot"], name="digest_comp_digest_slot_idx"),
        ]

    def __str__(self) -> str:
        # The slot and the bucket, and nothing else (D10). The event's title is untrusted
        # source text; putting it here would put it in every log line and every admin
        # list column (AD-9, AD-13). Django's `__repr__` delegates to `__str__`, so
        # `repr()` is safe for free — the same one-lever pattern `CalendarConnection`
        # uses to keep its credential out of `repr`.
        return f"{self.slot} digest composition, bucket {self.bucket}"


class EventReport(UUIDv7Model):
    """One user saying a catalog Event is wrong (FR-59, Amendment A-4).

    **It lives here, and its ReviewItem lives in `catalog`, and that split is the point.**
    A report is attributable to a person, so it belongs in `personal` under the retention
    rules that let a user be forgotten. The editorial queue it feeds carries **no user
    identity at all** (AD-3): `raise_user_report` passes the event id and the category and
    nothing else, and raises as `Actor.system("event_report")` so the reporter's id cannot
    reach a `catalog` audit row that every editor can read.

    **The FR-16 signal survives a deletion.** What FR-16 counts is the anonymous per-category
    tally on the `ReviewItem`, not these rows — so purging a user's reports with their account
    does not erase the editorial evidence. That is AD-3's separation paying off.

    **Unique on (user, event, category), because the tally has no decrement.**
    `raise_review_item` bumps a tally with `F() + 1` and never subtracts, so a design where a
    user could *change* their category would have to invent one. With all three in the key,
    each tally counts **distinct reporters of that category** — which is what "4 people say
    the date is wrong" has to mean — and one person can contribute at most 1 to each of the
    four. A repeat of the same category is an idempotent no-op.

    **`raised_at` is this model's outbox marker.** It is null until the ReviewItem exists.
    The report is written first and the ticket raised afterwards, outside the transaction
    (AD-3 forbids one spanning both schemas), so a failure leaves the row here and the
    reconciler re-offers it. A lost ticket is recoverable from the report; a lost report
    would not be recoverable from the ticket, which is why the order is this way round.

    **No free-text field.** FR-59 puts it in Phase 2, so there is nothing here to moderate.
    """

    class Category(models.TextChoices):
        """FR-59's four, the same vocabulary `ReviewItem.ReportCategory` holds (D3)."""

        WRONG_DATE_TIME = "wrong_date_time"
        WRONG_VENUE = "wrong_venue"
        DOES_NOT_EXIST = "does_not_exist"
        DUPLICATE = "duplicate"

    retention_category = RetentionCategory.ACCOUNT_CONTENT

    user_id = models.UUIDField()
    # The catalog Event's id, by value. No FK: this app may not relate to `catalog` (AD-3).
    event_id = models.UUIDField()
    category = models.CharField(max_length=24, choices=Category.choices)
    created_at = models.DateTimeField(default=timezone.now)
    #: When this report's ReviewItem was raised. Null means the reconciler still owes it.
    raised_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user_id", "event_id", "category"], name="event_report_user_event_cat_uq"
            ),
            models.CheckConstraint(
                condition=models.Q(category__in=REPORT_CATEGORIES),
                name="event_report_category_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["event_id"], name="event_report_event_idx"),
            # The reconciler's query: the unraised reports, oldest first.
            models.Index(
                fields=["created_at"],
                condition=models.Q(raised_at__isnull=True),
                name="event_report_unraised_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} reported {self.event_id}: {self.category}"


class SavedCollection(UUIDv7Model):
    """One user's named, ordered grouping of their saves (FR-49).

    FR-49 is the requirement that reached MVP with no design: TRACEABILITY.md records
    *"Nothing designed. 'Named collections' exists only as a marketing bullet"*. This is the
    storage it never got.

    **It groups the user's saves, never the catalog's events.** Membership points at
    `SavedEvent`, which already holds the catalog Event's id by value. Nothing here relates
    to `catalog`, so AD-3's wall is never approached, and a collection is as personal as the
    saves it holds.

    **No tier is stored or checked here, deliberately.** Gating belongs to
    `saved-collections-api`, because a lapsed Pro user's collections must stay readable —
    the brief forbids deleting over-cap data on downgrade. A model that refused on tier
    could not express "yours, still here, currently read-only".

    **`position` is dense: `0..n-1`, with no gaps and no ties.** The acceptance criterion
    asks for exactly that, which is why this is an integer and not a fractional rank — a
    fractional rank is *defined* by leaving gaps to insert into. The cost is that a reorder
    renumbers, and a renumber transiently puts two rows on one position, so
    `saved_collection_user_position_uq` is **deferred to commit**. Postgres checks it when
    the list is whole again; a plain constraint would reject the middle of a legal reorder.

    **The name is stored exactly as the user typed it and compared case-insensitively.**
    `Lower(name)` in the unique constraint means "Weekend" and "weekend" are one name for
    one user — a list showing both reads as a bug to the person who made them — while the
    row keeps the capitalisation they chose.
    """

    retention_category = RetentionCategory.ACCOUNT_CONTENT

    # The user, by value (OQ-8): no relation to User.
    user_id = models.UUIDField()
    name = models.CharField(max_length=80)
    #: `0..n-1` within one user, dense and unique. See the class docstring.
    position = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Case-insensitive: "Weekend" and "weekend" are one name. Stored verbatim.
            models.UniqueConstraint(
                "user_id",
                Lower("name"),
                name="saved_collection_user_name_uq",
            ),
            # **Deferred on purpose.** A reorder renumbers the whole list in one
            # transaction and is transiently inconsistent; the list is what must be
            # unique, not every intermediate state of it.
            models.UniqueConstraint(
                fields=["user_id", "position"],
                name="saved_collection_user_position_uq",
                deferrable=models.Deferrable.DEFERRED,
            ),
            models.CheckConstraint(
                condition=~models.Q(name=""), name="saved_collection_name_not_blank_ck"
            ),
        ]
        indexes = [
            # The list read: one user's collections, in their order.
            models.Index(fields=["user_id", "position"], name="saved_collection_user_pos_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class SavedCollectionItem(UUIDv7Model):
    """That one of a user's saves is in one of their collections (FR-49).

    **Membership is explicit, and that is an acceptance criterion rather than a style
    choice.** A row per `(collection, saved_event)` is what lets one save belong to two
    collections, lets a collection be empty, and keeps a save from ever being filed
    somewhere the user did not put it. An array column on `SavedEvent` would make "which
    collections is this save in?" a scan, and could not be constrained.

    **The two foreign keys are the first in `personal`, and they are here on purpose.**
    Every other model in this schema holds its references by value. These do not, because
    the acceptance criteria are *about* referential behaviour: deleting a collection must
    leave its saves intact, and unsaving an event must not strand a membership row. Both
    `CASCADE`s say so declaratively, in the one place that cannot be forgotten on some
    future code path. Neither crosses an app or a schema — `ingestion` holds seventeen such
    keys — so AD-3 is not in question.

    **Deleting a collection deletes these rows and no `SavedEvent`.** That is the single
    delete this intent permits: it removes a grouping, not the user's content, and the saves
    inside simply become uncollected.
    """

    retention_category = RetentionCategory.ACCOUNT_CONTENT

    #: This table holds no `user_id`: its user is the collection's. Export reads this
    #: rather than carrying a list of exceptions of its own (FR-52).
    export_user_path = "collection__user_id"

    collection = models.ForeignKey(SavedCollection, on_delete=models.CASCADE, related_name="items")
    saved_event = models.ForeignKey(
        SavedEvent, on_delete=models.CASCADE, related_name="collection_items"
    )
    added_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            # A save is in a collection once. Adding it twice is the same statement.
            models.UniqueConstraint(
                fields=["collection", "saved_event"],
                name="saved_collection_item_membership_uq",
            ),
        ]
        indexes = [
            # "Which collections is this save in?" — the question an array column could
            # not answer without a scan.
            models.Index(fields=["saved_event"], name="saved_coll_item_save_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.saved_event_id} in {self.collection_id}"
