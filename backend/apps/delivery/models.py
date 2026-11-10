"""The Reminder Plan and its audit log (AD-16, AD-7, FR-9, FR-20).

`delivery` owns `REMINDER_PLAN`. `personalization` never writes this table: it calls
`delivery`'s published service (`apps.delivery.services.reminder_plans`) to attach the
default plan when it creates a `PERSONAL_EVENT`. The import-linter contract
`models-delivery` enforces that boundary at build time.

The plan holds **relative** offsets before the event start, never absolute times, so it
survives a postponement: when AD-17 re-propagates an event's new start, the plan's slots
are unchanged and only the computed due times move.

The plan is attached to the *personal-side* record it belongs to, by value. A saved public
event's catalog row lives in the `catalog` schema and AD-3 forbids a FK across that wall;
both target tables here live in `personal`, so `(target_kind, target_id)` needs no relation
at all.
"""

from django.db import models
from django.db.models.expressions import RawSQL

from apps.delivery.send_keys import SEND_KEY_MAX_LENGTH
from shared.models import AuditEntry, UUIDv7Model
from shared.retention import RetentionCategory

# FR-9's "up to 4" bound, as a Postgres expression. Django's `__len` transform does not do
# this: on a JSON *array* it renders `(slots -> 'len') <= '4'`, which reads a key named
# "len" and yields NULL for every array — and a CHECK that evaluates to NULL passes. The
# array's element count is `jsonb_array_length`, which is what the bound actually means.
SLOTS_MAX = 4

# The only columns the bound applies to. A closed set, so the interpolation below is safe.
_SLOT_COLUMNS = frozenset({"slots", "default_reminder_slots"})


def _slots_length_at_most_max(column: str) -> models.Q:
    """The "at most 4 slots" bound for one JSON array column.

    Two tables carry a slot list — `REMINDER_PLAN.slots` (one event's plan) and
    `NOTIFICATION_PREFERENCE.default_reminder_slots` (what new plans start as) — and FR-9's
    bound is the same for both. One expression, parameterised by column name, so the two can
    never drift apart (AD-16).
    """
    # The column name is interpolated, so it is checked against the closed set of columns this
    # bound applies to. That makes the `S611` suppression below a proven claim rather than an
    # asserted one: no caller can reach the f-string with anything but one of these two names.
    if column not in _SLOT_COLUMNS:
        raise ValueError(f"not a slot column: {column!r}")
    return models.Q(
        RawSQL(  # noqa: S611 - column is checked against _SLOT_COLUMNS above; the bound is a param
            f"jsonb_array_length({column}) <= %s",
            (SLOTS_MAX,),
            output_field=models.BooleanField(),
        )
    )


_SLOTS_LENGTH_AT_MOST_4 = _slots_length_at_most_max("slots")


class ReminderPlan(UUIDv7Model):
    """One user's reminder slots for one event (FR-9).

    A user can save a plan with **0 to 4** slots (FR-9: "0 slots = no reminders (still in
    feed)"; FR-20: "The user can remove all reminders"). An empty plan is a valid state,
    not an error.

    The slots are the values `5d`, `2d`, `1d`, `1hr` — the `shared.constants.ReminderSlot`
    enum, reused and never redeclared (AD-16) — plus at most one custom slot, whose id is
    the user's own. AD-7's send key names the slot as "the custom slot's id", so a slot is
    a *value*, not an offset: the offset arithmetic lives in one place,
    `shared.constants.REMINDER_SLOT_OFFSET`.

    Pulse Ping is **not** a slot. The PRD Glossary is explicit: "Pulse Ping is NOT part of
    any Reminder Plan" — it is a separate, global per-day notification (FR-10). Nothing in
    this model can express it.
    """

    class TargetKind(models.TextChoices):
        """Which kind of personal-side record the plan belongs to.

        A plan attaches to a personal event (FR-20) or to a saved public event (FR-9's
        picker). The kind is stored beside the id because a UUID alone cannot say what it
        refers to — the same reasoning as `ConflictPair.SideKind`.
        """

        PERSONAL_EVENT = "personal_event"
        SAVED_EVENT = "saved_event"

    retention_category = RetentionCategory.ACCOUNT_CONTENT

    # The user, by value (OQ-8): no relation to User, no GenericForeignKey.
    user_id = models.UUIDField()
    # The personal-side record the plan belongs to, by value. `target_id` is the id of a
    # `personalization` row in the `personal` schema — never a catalog Event, which lives
    # behind the AD-3 wall.
    target_kind = models.CharField(max_length=16, choices=TargetKind.choices)
    target_id = models.UUIDField()
    # The chosen slots, in order. At most 4 (FR-9). Each is a `ReminderSlot` value or a
    # custom slot id.
    slots = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # One plan per event: re-attaching updates the row rather than adding another.
            models.UniqueConstraint(
                fields=["user_id", "target_kind", "target_id"], name="reminder_plan_target_uq"
            ),
            # FR-9's "up to 4". The list is a JSON array, so the bound is a length check.
            models.CheckConstraint(
                condition=_SLOTS_LENGTH_AT_MOST_4, name="reminder_plan_slots_max_4_ck"
            ),
        ]
        indexes = [
            # The scheduler finds every plan of one user; AD-7's sweep reads them per user.
            models.Index(fields=["user_id"], name="reminder_plan_user_idx"),
        ]

    def __str__(self) -> str:
        slots = ", ".join(self.slots) if self.slots else "none"
        return f"{self.target_kind} plan [{slots}]"


class NotificationPreference(UUIDv7Model):
    """One user's Quiet Hours window and their own default Reminder Plan (FR-12, FR-20).

    **Why this row lives in `delivery` and not on `personalization`'s `DigestPreference`.**
    A decision taken deliberately on 2026-10-31, not a default. `DigestPreference` already
    holds the delivery time and the zone, and its docstring invites exactly this
    reconsideration — "the shape is reconsidered when a second, genuinely separate preference
    arrives". This is the arrival, and the answer is a separate row, because **`delivery`
    reads the window on the hot path of every `due_at` computation** (AD-7). AD-16 makes write
    ownership total: a `delivery`-owned table that `delivery` reads directly beats a
    cross-module read through a published service on the path that runs most often.

    The accepted cost is two preference rows per user and a settings surface that writes to
    two modules. That is recorded here so a later reader does not "fix" it by merging them.

    **The zone is deliberately not here.** The user has exactly one zone, on
    `DigestPreference`, and a second copy would be free to drift — showing up as sends
    deferred against the wrong night. The minting service reads the zone through
    `personalization`'s published interface once per batch: the rare path, which is the
    reasoning that put this window in `delivery` in the first place.

    **The window is a pair of local wall clocks, never instants.** "10pm" means 10pm wherever
    the user is, and survives travel and DST because it is re-read against the zone every time
    a due time is computed. `domain.quiet_hours.QuietHours` is the value these two columns
    become.

    **A null pair means "no quiet hours", and it is the only spelling of that.** A new user
    gets the 22:00-08:00 default rather than null, because a user who has never opened
    settings still has a night: the first reminder they ever receive already respects it.
    Null is reached only by deliberately turning quiet hours off. `start == end` is a second
    way to write "no quiet hours" and is **refused by the command** for that reason
    (`InvalidQuietHoursWindowError`); `domain.quiet_hours` stays total and treats it as
    disabled, so the pure shift never raises.

    **`default_reminder_slots` is what closes FR-20.** Until this row existed, the default
    plan was the module constant `shared.constants.DEFAULT_REMINDER_PLAN` and a user had no
    way to change what newly saved events got — which is why TRACEABILITY.md could only find
    FR-20 "by adjacency". The constant stays as the fallback for a user who has never set one,
    and is **not duplicated here** (AD-16). An empty list is a valid, deliberate state: new
    saves get no reminders.

    **`pulse_ping_unsubscribed` is the Pulse Ping opt-out, and it is here because the Ping
    is per *user*.** FR-11 scopes the unsubscribe two ways, and the two land in two different
    places for a reason: a reminder's unsubscribe stops **one event's** reminders, which is
    per `(user, event)` and so belongs on that event's `ReminderPlan`; the digest's
    unsubscribe stops **the Pulse Ping**, which is per user and has no event to hang off.

    So the per-user scope lives here and the per-event scope lives on `ReminderPlan`. That
    split is not tidiness — it is what each scope actually *is*, and putting the Ping's
    opt-out on a plan would make it impossible to express "stop the daily digest" without
    also naming an event.

    **`False` is the default, and that is the important part.** A user who has never
    unsubscribed is not unsubscribed: the column distinguishes "never turned it off" from
    "turned it off", and only the second suppresses the Ping. A `NULL` would have made
    "never turned it off" and "turned it on explicitly" the same value, and the second is
    worth telling apart when the settings surface grows.
    """

    retention_category = RetentionCategory.PREFERENCE_SIGNALS

    # The user, by value (OQ-8): no relation to User.
    user_id = models.UUIDField()
    # Local wall clocks (HH:MM), NOT instants. Both null together: see the class docstring.
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    # The slots a newly attached plan starts with. At most 4 (FR-9). Empty is valid.
    default_reminder_slots = models.JSONField(default=list)
    # FR-10 / FR-11: whether the user has turned the Pulse Ping off. `False` means "not
    # unsubscribed", which is the default and the common case — see the class docstring.
    pulse_ping_unsubscribed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user_id"], name="notification_preference_user_uq"),
            # FR-9's "up to 4", shared with ReminderPlan. See `_slots_length_at_most_max`:
            # a `__len` lookup would silently not constrain anything.
            models.CheckConstraint(
                condition=_slots_length_at_most_max("default_reminder_slots"),
                name="notification_preference_slots_max_4_ck",
            ),
            # Both halves of the window travel together. A start with no end is a window that
            # never ends; an end with no start is a window that never begins. Neither half
            # means anything alone, so the database holds the pair — the same reasoning as
            # `DigestPreference`'s city/city_source check.
            models.CheckConstraint(
                condition=(
                    models.Q(quiet_hours_start__isnull=True, quiet_hours_end__isnull=True)
                    | models.Q(quiet_hours_start__isnull=False, quiet_hours_end__isnull=False)
                ),
                name="notification_preference_quiet_hours_pair_ck",
            ),
        ]
        indexes = [
            models.Index(fields=["user_id"], name="notification_pref_user_idx"),
        ]

    def __str__(self) -> str:
        if self.quiet_hours_start is None:
            return "no quiet hours"
        return f"quiet {self.quiet_hours_start}-{self.quiet_hours_end}"


class ScheduledSend(UUIDv7Model):
    """One intended send: what it is, who for, when it is due, and its idempotency key (AD-7).

    **The table AD-7 was written around.** The due-index sweep, the five key shapes, "the
    schedule is never in the broker" — all of it is about this row. Until now it existed only
    in docstrings.

    **The key is minted once and is never a function of `due_at`.** This is the invariant
    everything else rests on, and the failure it prevents is quiet: four ordinary user actions
    rewrite `due_at` on pending rows — quiet hours, timezone, delivery time, a plan edit — and
    a key that moved with the time would mint a second send for each one. A user who adjusted
    their settings three times would get four copies of one reminder. The shapes live in
    `apps.delivery.send_keys`, where no builder takes a time at all.

    **`event_version` appears twice, deliberately.** AD-7: the version inside the key is the
    value *at minting*; the column below is the *working* version, which AD-17 propagation
    re-stamps. They are allowed to differ, and the difference is the useful fact — "minted
    against version N, event has since moved to M". It is also the mechanism behind AD-7's
    subtlest sentence: a moved event cancels the old pending rows and mints new ones, so a `1d`
    reminder already sent for the old date does not block the `1d` reminder for the new one.

    **Retention is `ACCOUNT_CONTENT`, and not `EMAIL_DELIVERY_EVENTS`** — which is the first
    thing a reviewer will question, so here is the answer. This table holds two kinds of fact:
    a `pending` row is a *future intention*, and a `sent` row is a *delivery event*. PRD §10.2
    gives delivery events 90 days. But a 5-day reminder for an event eight months out sits
    `pending` for eight months, and a 90-day purge would **delete it before it ever fired** —
    the user is simply never reminded and nothing looks broken. `ACCOUNT_CONTENT` matches
    `ReminderPlan`, which this table is derived from, and has no path to losing a reminder.

    **The accepted cost, recorded so it is not forgotten:** `sent` rows outlive the 90-day
    email-delivery-events policy. Closing that needs a status-aware prune in the retention
    sweep, and it is a known follow-up (design doc D5), not an oversight.

    **The status machine lives in the service, not in a trigger.** `delivery` is the single
    writer (AD-16) and the sweep is the only mutator of status; a trigger would restate in
    plpgsql a rule one module already owns. This repo reserves triggers for *append-only*
    tables, where the guarantee must survive any writer. What the database does hold is the
    pairing a status alone cannot express — a `sent` row with no `sent_at`, or an unsent row
    carrying one, is a lie about whether a user received an email.
    """

    class Kind(models.TextChoices):
        """What is being sent. AD-7's send-key table, one member per shape."""

        EVENT_REMINDER = "event_reminder"
        PERSONAL_REMINDER = "personal_reminder"
        STATE_NOTICE = "state_notice"
        # The daily digest email, which in MVP **is** the Pulse Ping (FR-10, decided
        # 2026-10-31): MVP is email-only, so one send carries both.
        DIGEST = "digest"
        # **Reserved, never minted in MVP.** It is here so AD-7's table stays legible against
        # the code and so a later reader sees a deliberate reservation rather than an
        # omission. It becomes real with the Phase 2 push channel; `send_keys` has no builder
        # for it, and a test asserts nothing in the tree mints it.
        PULSE_PING = "pulse_ping"

    class Status(models.TextChoices):
        """`pending` is a promise; the other three are terminal and never reopened."""

        PENDING = "pending"
        SENT = "sent"
        CANCELLED = "cancelled"
        # The provider refused past the attempt bound. Terminal and **recorded**: a row that
        # exhausts its attempts is never retried forever and never silently dropped.
        FAILED = "failed"

    #: Terminal states. A row in one of these is never re-timed, rekeyed or resurrected.
    TERMINAL_STATUSES = frozenset({Status.SENT, Status.CANCELLED, Status.FAILED})

    retention_category = RetentionCategory.ACCOUNT_CONTENT

    # The user, by value (OQ-8).
    user_id = models.UUIDField()
    kind = models.CharField(max_length=24, choices=Kind.choices)
    # Minted once at creation, unique, never derived from `due_at`. See the class docstring.
    send_key = models.CharField(max_length=SEND_KEY_MAX_LENGTH)

    # The personal-side record this send is about, by value — the `ReminderPlan` convention.
    # Blank for a `digest`, which is about a user and a day rather than one event.
    target_kind = models.CharField(max_length=16, blank=True, default="")
    target_id = models.UUIDField(null=True, blank=True)
    # The Reminder Plan slot, where one applies: a `ReminderSlot` value or a custom slot id.
    slot = models.CharField(max_length=64, blank=True, default="")
    # The **working** version, re-stamped by AD-17 propagation. Not the one inside the key.
    event_version = models.PositiveIntegerField(null=True, blank=True)

    # AD-20: the stream this goes out on. No default — a send without an explicit stream is a
    # type error at the port, and it is not going to acquire one by accident here either.
    stream = models.CharField(max_length=16)
    # **The instant the slot names, BEFORE Quiet Hours moved it.** `due_at` is the shifted
    # instant — the true send time — and the shift *loses the original*: a reminder pushed
    # from 22:30 to 08:00 no longer says when it was for. So the unshifted instant is kept
    # beside it, and the two are the same kind of pair as `event_version`'s: one frozen at
    # minting (in the key), one re-stamped by propagation (in the column). `slot_at` names
    # the slot; `due_at` names the send.
    #
    # **This is what makes a preference rewrite possible at all.** A quiet-hours change has
    # to re-time a *deferred* row — that is the whole point of the write — and a deferred
    # row's start cannot be recovered from `due_at`, because `due_at + offset` compounds the
    # deferral: a row already pushed to 08:00 reads as an event starting at 09:00, and
    # re-shifting that lands on the wrong hour again. The start has to come from somewhere
    # that still remembers it, and the row is the only place that does: it is minted here,
    # it is written by value, and it does not depend on the event still existing.
    #
    # **Null for a row whose pre-shift instant is not a slot.** A `state_notice` has no
    # slot: its send time is not an offset from the event's start, it is *now* — the moment
    # propagation ran. Quiet Hours still apply to it (`shift_to_sendable` takes any aware
    # instant; nothing in it is slot-specific), so the null here is about the slot alone.
    #
    # The rewrite skips such a row, and the reason is stronger than "nothing to shift": a
    # state notice's pre-shift instant is the change itself, which is in the past and never
    # moves, so a later preference change has nothing to recompute. Re-timing it against a
    # new window would move a message whose moment has already passed.
    slot_at = models.DateTimeField(null=True, blank=True)
    # **Already shifted for Quiet Hours** (AD-7): this is the true send time, computed at
    # minting. The sweep must never re-check it — a send deferred twice is a send that never
    # leaves.
    due_at = models.DateTimeField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    sent_at = models.DateTimeField(null=True, blank=True)

    # Null means unclaimed. The sweep claims with `FOR UPDATE SKIP LOCKED` but **must not hold
    # the row lock across the provider call**, so the claim is also recorded here — the same
    # reading as `DigestPreference.digest_claimed_at` and `CalendarConnection.sync_claimed_at`.
    # A claim older than `SEND_CLAIM_TTL` is a dead worker's row and becomes claimable again.
    claimed_at = models.DateTimeField(null=True, blank=True)
    # **AD-17's propagation hold.** Null means not held. Set by the sweep when it claims a row
    # whose event the catalog has already moved past, and cleared when propagation releases it.
    # A held row is **not sent** and is not re-claimed, but it is still `pending`.
    #
    # **Why this is a column and not a `Status` member.** AD-17's words are "the row goes to
    # `held_for_propagation`", and a status is the obvious reading. It is the wrong one here:
    # `scheduled_sends` — the module AD-17 itself calls the sole rewriter of this table —
    # filters on `status = pending` in eight places, and a held row that is no longer `pending`
    # becomes invisible to all of them. `apply_lifecycle_change`, whose whole job is to release
    # these rows, would skip exactly the rows it exists for; the staleness gate would stop
    # seeing them and mint duplicates; a quiet-hours rewrite would silently not re-time them.
    # None of those raise. A nullable timestamp keeps the row `pending`, so every existing
    # writer keeps working unchanged, and the hold costs one predicate on the claim instead.
    # It is also the idiom already used twice above: `claimed_at` here, `sync_claimed_at` on
    # `CalendarConnection`. (Decided with the user 2026-11-04; design doc D1.)
    held_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    # A **kind**, never the provider's message: a provider error can quote the recipient
    # address, and this column reaches logs and admin columns (AD-13).
    last_error_kind = models.CharField(max_length=32, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # The whole point of AD-7: one row per thing-to-be-sent, so an at-least-once
            # retry and a recompute both collapse onto the same row.
            models.UniqueConstraint(fields=["send_key"], name="scheduled_send_key_uq"),
            # A `sent` row has a sent time and nothing else does. Either half alone is a lie
            # about whether a user received an email.
            # The literal "sent" rather than `Status.SENT`: an inner class is not in scope
            # inside `Meta` while the class body is still being evaluated. The value is
            # pinned to the enum by `test_the_sent_at_check_matches_the_status_value`.
            models.CheckConstraint(
                condition=(
                    models.Q(status="sent", sent_at__isnull=False)
                    | ~models.Q(status="sent") & models.Q(sent_at__isnull=True)
                ),
                name="scheduled_send_sent_at_pairs_with_status_ck",
            ),
        ]
        indexes = [
            # **The sweep's index, and this codebase's first partial one.** The query is
            # `WHERE status = 'pending' AND due_at <= now()`, and pending rows are a small,
            # roughly constant set while `sent` rows accumulate forever. Indexing only the
            # pending set keeps the sweep's index permanently small and never indexes a row
            # the sweep will not look at.
            #
            # AD-7 says "a `(due_at, status)` index"; this serves that intent more completely
            # than the literal column pair would, and the choice was taken with the user on
            # 2026-10-31 (design doc D4). It can be changed by a migration alone — it touches
            # no row and no key.
            models.Index(
                fields=["due_at"],
                condition=models.Q(status="pending"),  # literal: see the CHECK above
                name="scheduled_send_due_pending_idx",
            ),
            # Rewriting every pending row of one user: quiet hours, timezone, delivery time.
            models.Index(fields=["user_id"], name="scheduled_send_user_idx"),
            # "Does this user already have a digest row for today?"
            models.Index(fields=["user_id", "kind", "status"], name="scheduled_send_user_kind_idx"),
        ]

    def __str__(self) -> str:
        # The key and the status — never the recipient, which is not stored here anyway, and
        # never anything that would make this line PII (AD-13).
        return f"{self.kind} {self.status} due {self.due_at.isoformat()}"


class StateChangeNotice(UUIDv7Model):
    """One calm correction, raised once, for one user and one catalog state change (FR-54).

    **The notice is the record; the email is one of its two deliveries.** FR-54 asks for
    "in-app **+** email", and the in-app half outlives the send: the digest strip is still
    dismissible after the mail has gone, and is still the only surface left when a mute or
    the daily cap stops the mail entirely. A `SCHEDULED_SEND` cannot be this row — it is the
    send ledger, swept continuously on `(due_at, status)`, and its vocabulary is `pending`
    / `sent` / `cancelled` / `failed`, which has no way to say *seen*. Hanging `event_id`,
    `change_kind`, `seen_at` and `dismissed_at` off it would also widen the hottest table in
    the schema for columns one of its five kinds would use.

    **"Never repeats" is about retries, not about second events.** FR-54 says both "one-time
    per event; never repeats" and "at most one per event per day" — and taken literally the
    first makes the second meaningless, since "per day" presumes there can be a second day.
    Its own four consequence bullets expect distinct notices for cancel, move, relocate and
    sold-out. So uniqueness here is per **state change**, which is exactly what AD-7's send
    key already says (`user_id · state_notice · state_change_id`), and the repeat being
    forbidden is a propagation retried after a partial run. The unique constraint below is
    that rule, held by the database rather than by whichever service remembers to check.

    **The daily cap is a separate rule and lives in the write path**, not in the key. It
    cannot be in the key: re-keying on `(event, local_date)` would make a cancellation at
    14:00 collide with a sold-out minted at 09:00 and be dropped as a duplicate — losing the
    one message FR-54 most requires. And it is not protecting against a rare burst.
    `ingestion.event_writes` appends **one `EVENT_STATE_CHANGE` per kind** in a single poll,
    so a source update that moves the time *and* marks it sold out already produces two
    notices seconds apart. `services.state_notices` resolves them with
    `domain.lifecycle.PRECEDENCE`, the ordering the tree already has.

    **`local_date` is stored, not recomputed.** The cap is "per event per day", and a day is
    the user's own — so it has to be the local date at the moment the notice was raised. A
    date recomputed at read time would make the cap depend on when it was asked, and would
    move under a user who changes zone. `DigestPreference` stores a local date for the same
    reason. The accepted cost is that a zone change can allow or suppress one extra notice
    around it.

    **`change_kind` is `domain.lifecycle.ChangeKind`'s vocabulary, carried through.** Not a
    second enum: the kind is decided by `classify_change` and the screens already follow the
    rule that the vocabulary is the backend's. A copy here would be free to drift from the
    one that does the deciding.

    **A catalog id by value, with no FK** (AD-3): `event_id` and `state_change_id` both name
    rows in the `catalog` schema, which this table may not relate to. The same shape
    `SAVED_EVENT` uses.
    """

    retention_category = RetentionCategory.ACCOUNT_CONTENT

    # The user, by value (OQ-8): no relation to User.
    user_id = models.UUIDField()
    # The **catalog** Event's id, by value. No FK: this schema may not relate to `catalog`.
    event_id = models.UUIDField()
    # The `EVENT_STATE_CHANGE` this notice was raised for, by value. What makes the notice
    # unique, and what AD-7's send key is minted from.
    state_change_id = models.UUIDField()
    # A `domain.lifecycle.ChangeKind` value. Not re-declared here: see the class docstring.
    change_kind = models.CharField(max_length=20)
    # The version the change carried. AD-17's gate compares against it, so a retried or
    # out-of-order propagation can neither double-raise nor let an older change win.
    event_version = models.PositiveIntegerField()
    # The user's local date when this was raised — what the one-per-day cap is keyed on.
    local_date = models.DateField()
    # **Put in front of the user.** Set when the Detail banner or the digest strip renders
    # it. This is what makes a notice stop being *new*; it is not an act by the user.
    seen_at = models.DateTimeField(null=True, blank=True)
    # **Closed by the user.** An act, which is why it is not the same column as `seen_at`:
    # a user who opens the Detail screen has seen the notice and dismissed nothing, and
    # treating that as a dismissal would empty a strip they never looked at.
    dismissed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # "Never repeats" (FR-54), held here rather than in a service. One notice per
            # user per state change; a retried propagation adds nothing.
            models.UniqueConstraint(
                fields=["user_id", "state_change_id"], name="state_notice_change_uq"
            ),
            models.CheckConstraint(
                condition=models.Q(event_version__gte=1), name="state_notice_version_positive_ck"
            ),
        ]
        indexes = [
            # The one-per-day cap's lookup, and the digest strip's read: both are "this
            # user, this day".
            models.Index(fields=["user_id", "local_date"], name="state_notice_user_date_idx"),
            # The Detail banner: "this user, this event".
            models.Index(fields=["user_id", "event_id"], name="state_notice_user_event_idx"),
        ]

    def __str__(self) -> str:
        # The kind and the event — never a title or an address (AD-13).
        return f"{self.change_kind} notice for {self.event_id}"


class EventNoticeMute(UUIDv7Model):
    """One user silencing FR-54's notices for one event (FR-55).

    **Its own table, although FR-11's per-event reminder opt-out lives on `REMINDER_PLAN`.**
    That precedent looks like it should transfer and does not, for two reasons: a saved
    public event usually has **no plan at all** — `save_event` does not attach one, which is
    why `save_plan_slots` needs its attach branch — and an unsave now *deletes* the plan, so
    a mute stored there would vanish with the save and silently un-mute on a re-save. A
    preference that disappears when the user changes their mind about something else is not
    a preference.

    Not on `NOTIFICATION_PREFERENCE` either: that is one row per user, and this is a
    per-event fact. Its own docstring already draws that line — the Pulse Ping's opt-out is
    per user and lives there; a per-event scope lives beside the event.

    **There is no global off switch**, deliberately (decided at capture, 2026-11-04).
    FR-54's notices are the mechanism that keeps reminders *correct*: a user who silenced
    them globally would be opting into wrong reminders without being told that is what they
    were doing. A per-event mute is a choice about one event the user is looking at.

    **A mute silences the correction, not the event.** Reminders still fire and the event
    still places in the digest; only the "this changed" message stops. And a **terminal**
    change — cancelled or superseded — is raised anyway (`services.state_notices`): a mute
    means "stop telling me about tweaks to this event", and reading it as "do not tell me it
    is off" would turn a preference into a trap, with FR-55 having already removed the event
    from the digest so that no second channel catches it.
    """

    retention_category = RetentionCategory.PREFERENCE_SIGNALS

    user_id = models.UUIDField()
    # The **catalog** Event's id, by value. No FK across the AD-3 wall.
    event_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Muting twice is the same mute. The command is idempotent on top of this.
            models.UniqueConstraint(fields=["user_id", "event_id"], name="event_notice_mute_uq"),
        ]

    def __str__(self) -> str:
        return f"notices muted for {self.event_id}"


class DeliveryAuditEntry(AuditEntry):
    """The `delivery` audit log (AD-5). Append-only; written only through `write_audit`."""

    retention_category = RetentionCategory.AUDIT_LOG
