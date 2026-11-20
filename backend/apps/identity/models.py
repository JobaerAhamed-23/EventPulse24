"""The `identity` module's models (AD-16): the account, its reset tokens, its subscription
and its audit log.

`identity` owns `USER` and the auth flows. Everything here lives in the `personal` schema
(AD-3), so nothing here relates to a catalog table.

Design: .specs-fire/intents/onboarding-and-account/work-items/account-auth-core-design.md
(decisions D2, D4-D6, D14). Integrity the database can hold is a constraint; what it can't
(whether a password is strong, whether a token has expired) belongs to the commands.
"""

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.identity.managers import UserManager
from ports.billing import ProPlan
from ports.blob import MAX_KEY_LENGTH
from shared.models import AuditEntry, UUIDv7Model
from shared.retention import RetentionCategory


class User(UUIDv7Model, AbstractBaseUser, PermissionsMixin):
    """The account (Glossary: User). Set as AUTH_USER_MODEL before auth was first migrated.

    AD-18 fixes email and password as the MVP sign-in, so the email **is** the login field
    and `username` is gone: the product has one identity concept, and a username column the
    product never uses would be a second one that can drift.

    The email is unique **case-insensitively**, and the database enforces it: the value is
    normalised (trimmed and lowercased) before it is stored, so `Maya@Example.com` and
    `maya@example.com` are one account. `save()` normalises as a backstop, so even a write
    that bypasses the command layer cannot store a mixed-case value and slip past the
    unique constraint.
    """

    #: The account row *is* the user, so its path to one is its own primary key (FR-52).
    #: Without this it would be the one record missing from a user's own export.
    export_user_path = "id"

    retention_category = RetentionCategory.ACCOUNT_IDENTITY

    # Uniqueness is the explicit `user_email_uq` constraint below, not a column-level
    # `unique=True`: one named constraint is one thing to read, test and cite.
    email = models.EmailField(max_length=254)

    #: The name the product addresses this account by (FR-52). **Blank, not null**: `""`
    #: is the single "no name set" state, and the email-derived fallback the frontend
    #: shows in its place is a *display* concern — the backend does not know how a human
    #: renders their own name from an address, and must not guess. A null would make
    #: "cleared" and "never set" two states with the same meaning.
    #:
    #: It is **not** normalised the way the email is: the email is a key, and this is a
    #: person's name. The case is theirs.
    name = models.CharField(max_length=120, blank=True, default="")

    #: The key of this account's profile picture in the object store — **not the picture**.
    #:
    #: The bytes live in the bucket; this column holds the opaque key that finds them. A
    #: picture in a database column is a picture read on every query that touches the row.
    #:
    #: **Blank, not null**, exactly as `name` above is: `""` is the single "no picture set"
    #: state, so "cleared" and "never set" are one state rather than two with the same
    #: meaning. What the product shows in its place — initials, a silhouette — is a
    #: *display* rule the frontend owns.
    #:
    #: **The key is opaque (AD-13).** It carries no account id, no address and no filename:
    #: `avatars/<random>`. A key derived from the account would let anyone holding one
    #: enumerate the others.
    #:
    #: **A new key on every upload, never an overwrite.** Replacing a picture stores a new
    #: object and deletes the old one after the row commits, so there is no moment at which
    #: this column names a half-written object.
    #:
    #: **The object is removed when the account is destroyed.** `services/deletion.py`
    #: deletes it in `transaction.on_commit`, when the account is actually destroyed rather
    #: than when deletion is requested — so a person who cancels inside the thirty-day
    #: grace period gets their picture back. The object *is* also removed when the picture
    #: is replaced or cleared.
    avatar_key = models.CharField(max_length=MAX_KEY_LENGTH, blank=True, default="")

    is_staff = models.BooleanField(
        default=False,
        help_text="Designates whether the user can log into this admin site.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text=(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        constraints = [
            # The email is the login, and it is unique case-insensitively. The value is
            # normalised on the way in, so this index *is* the case-insensitive index.
            models.UniqueConstraint(fields=["email"], name="user_email_uq"),
        ]

    def __str__(self) -> str:
        return self.email

    def save(self, *args, **kwargs):
        # Normalise before the write, so a direct write cannot store a mixed-case value
        # and slip past the unique constraint.
        self.email = UserManager.normalise_email(self.email)
        super().save(*args, **kwargs)


class PasswordResetToken(UUIDv7Model):
    """One outstanding password-reset token, stored as a digest (AD-18).

    Django's `PasswordResetTokenGenerator` was probed against the pinned Django 6.1.2
    before this table was chosen. It is **not** single-use: two consecutive `check_token`
    calls with no state change both succeed. It becomes single-use only because the
    password changes, so it is replayable between issuance and use, it cannot be revoked,
    and it cannot be listed for a user's outstanding resets.

    This row gives the properties the work item requires:

    - **Single-use** — `used_at` is set in the same transaction that consumes the token, so
      a second attempt finds it set and is refused. This holds even when the reset fails
      before saving, because the consumption is its own committed step.
    - **Short-lived** — `expires_at` is set from a named constant at issue time.
    - **Revocable** — a row can be revoked without touching the password.
    - **No token at rest** — only the digest is stored, so a database dump yields no
      usable reset link.

    The user is held by value (OQ-8): there is no relation to `User`.
    """

    retention_category = RetentionCategory.ACCOUNT_IDENTITY

    user_id = models.UUIDField()
    # sha256(salt + token), hex. The token itself is never stored.
    token_hash = models.CharField(max_length=64, unique=True)
    # The per-row salt, hex. It makes the digest unattackable with precomputed digests
    # of the token space.
    token_salt = models.CharField(max_length=32)
    expires_at = models.DateTimeField()
    # Set when the token is consumed. Null until then.
    used_at = models.DateTimeField(null=True, blank=True)
    # Set when the token is invalidated without being used (a new reset request, an
    # account action).
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            # A token is either used or revoked, never both: "used" means the password
            # changed, "revoked" means it did not and the token was discarded.
            models.CheckConstraint(
                condition=~(models.Q(used_at__isnull=False) & models.Q(revoked_at__isnull=False)),
                name="password_reset_token_used_or_revoked_ck",
            ),
        ]
        indexes = [
            # Ending a user's sessions, and listing their outstanding resets, both look
            # up by user.
            models.Index(fields=["user_id"], name="password_reset_token_user_idx"),
        ]

    def __str__(self) -> str:
        return f"reset token for {self.user_id}"


class PendingEmailChange(UUIDv7Model):
    """One outstanding request to move the login to a new address, as a digest (AD-18).

    **The login is the credential, so the new address is proven before it moves.** This
    row is that proof in flight: it holds the requested address and a token, and only
    that token returning from the new address completes the change.

    **Its shape is `PasswordResetToken`'s, deliberately and almost field for field.** That
    row's docstring records why each property is there — single-use via `used_at` set in
    the consuming transaction, short-lived via `expires_at` from a named constant,
    revocable without being used, no token at rest, the user held by value (OQ-8) — and
    every one of those reasons applies unchanged to a credential move. It also records
    that Django's `PasswordResetTokenGenerator` was *probed* against the pinned Django and
    rejected as replayable and unrevocable; that finding is not re-litigated here.

    **`new_email` is normalised on the way in**, exactly as `User.email` is. The confirm
    compares like with like, and a case variant cannot be smuggled past `user_email_uq`.

    **There is deliberately no unique constraint on `new_email`.** Two people may both
    *request* the same address; only one can *confirm* it, and `User`'s `user_email_uq` is
    what decides between them. A unique constraint here would let whoever requested first
    deny the address to the person who actually owns the mailbox — a squatting vector in a
    table that is supposed to be a queue of unproven claims.

    **The address is not a credential the way a password is, but it is PII**, so it never
    appears in an audit row's details, in a log line, or in `__str__` (AD-13).
    """

    retention_category = RetentionCategory.ACCOUNT_IDENTITY

    user_id = models.UUIDField()
    # The address being proven. Normalised (trimmed, lowercased) before it is stored.
    new_email = models.EmailField(max_length=254)
    # sha256(salt + token), hex. The token itself is never stored.
    token_hash = models.CharField(max_length=64, unique=True)
    # The per-row salt, hex. It makes the digest unattackable with precomputed digests.
    token_salt = models.CharField(max_length=32)
    expires_at = models.DateTimeField()
    # Set when the token is consumed and the login moved. Null until then.
    used_at = models.DateTimeField(null=True, blank=True)
    # Set when the request is invalidated without being used: a newer request, a cancel.
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            # Used means the login moved; revoked means it did not. Never both.
            models.CheckConstraint(
                condition=~(models.Q(used_at__isnull=False) & models.Q(revoked_at__isnull=False)),
                name="pending_email_change_used_or_revoked_ck",
            ),
        ]
        indexes = [
            # Revoking a user's outstanding requests, and showing them the pending one,
            # both look up by user.
            models.Index(fields=["user_id"], name="pending_email_change_user_idx"),
        ]

    def __str__(self) -> str:
        # **No address here** (AD-13): `__str__` reaches logs and the admin changelist.
        return f"pending email change for {self.user_id}"


class DeletionRequest(UUIDv7Model):
    """One outstanding request to delete an account, and the grace period it carries.

    **The row is the fact.** An account under a deletion request is not deleted yet, is not
    frozen, and is not marked inactive — it is *scheduled*, and this row says when for.

    **Why a row and not a column on `User`.** A column would have to be nullable and would
    travel with every read of the account — including every `me` call and the user's own
    export — for a fact that is true for a thirty-day window and then false. A row that
    exists only while the deletion is pending says exactly what it is, and deleting that
    row is the whole of a cancellation.

    **The grace period is the point of the row.** Amendment A-16 promises a person can
    cancel any time during thirty days. `scheduled_for` is when that promise expires, and
    it is computed once — at request time — from `DELETION_GRACE_PERIOD`, so the deadline
    does not move if the constant ever changes under an outstanding request.

    **Nothing is destroyed while this row exists.** In particular the profile picture's
    object: it is removed when the account is *destroyed*, not when deletion is requested.
    A person who cancels inside the grace period gets their picture back — and removing it
    at request time would make the grace period a lie, because the promise was that the
    account comes back whole.

    **The user is held by value (OQ-8)**, like every other table that reaches an account.
    There is no relation to `User`, and no cascade: the rows are purged by an explicit walk
    (`services/deletion.py`), because a cascade would delete the audit rows that must
    survive the account.

    **The address is not here** (AD-13): `__str__` reaches logs and the admin changelist.

    **The cancel token lives here, and its lifetime is this row's lifetime.** The notice
    mail carries a link that cancels the deletion, and that link has to authenticate the
    person who follows it as the account's owner. The token is therefore held here as a
    salted digest (`token_hash` + `token_salt`), and **its lifetime is the row's**,
    because the row is deleted when the token is spent — spending the token *is* the
    cancellation.

    **There is deliberately no separate expiry column for it.** A second expiry would be a
    second source of truth about when the promise ends, and it could disagree with
    `scheduled_for`: a token expired while the grace period was still live would break
    the promise A-16 makes, and a token alive after the row was destroyed would be a
    token with nothing to cancel. **One row, one lifetime, no way for the two to drift.**

    **Why a long-lived token is defensible here, when it would not be elsewhere.** A
    password-reset token lives thirty minutes because spending it grants *full account
    access*. This token lives the whole grace period because spending it **deletes the
    pending destruction** — it grants no access, reads nothing, exposes no data, and
    leaves the account exactly as it was. **A credential that can only prevent destruction
    is a categorically weaker bearer than one that grants access**, and its worst outcome
    is that the account *survives*. That bounded upside is what makes the window
    acceptable; the same window on a reset token would not be.

    **The address is deliberately not captured here.** A second mail — "your account has
    been destroyed" — cannot exist without it, because when `destroy_account` runs the
    account row is gone and there is nothing left to write to. Capturing the address onto
    a row that outlives the account is a PII question (AD-13) and a retention one
    (AD-15), and it is not settled. **This row does not hold it.**
    """

    retention_category = RetentionCategory.ACCOUNT_IDENTITY

    #: The account being deleted, by value.
    user_id = models.UUIDField()
    #: When the request was made. The grace period runs from here.
    requested_at = models.DateTimeField(default=timezone.now)
    #: When the account is destroyed, if the request is not cancelled first.
    #:
    #: **Computed once, at request time.** A deadline that moved whenever the constant
    #: changed would mean an outstanding request's grace period silently grew or shrank.
    scheduled_for = models.DateTimeField()
    #: sha256(salt + token), hex. The token itself is never stored (AD-18).
    #:
    #: **Nullable**, because the migration is forward-only: a row that existed before
    #: this column did has no token, and the mail that would carry one was never sent for
    #: it. A row with no token simply has no cancel link outstanding.
    token_hash = models.CharField(max_length=64, null=True, blank=True)
    #: The per-row salt, hex. It makes the digest unattackable with precomputed digests
    #: of the token space.
    token_salt = models.CharField(max_length=32, null=True, blank=True)

    class Meta:
        indexes = [
            # The worker asks "which requests are due?" on every tick, and the API asks
            # "does this account have an outstanding request?" — both look up by user.
            models.Index(fields=["user_id"], name="deletion_request_user_idx"),
            models.Index(fields=["scheduled_for"], name="deletion_request_due_idx"),
        ]

    def __str__(self) -> str:
        # **No address here** (AD-13).
        return f"deletion request for {self.user_id}"


class SubscriptionStatus(models.TextChoices):
    """The four states a subscription can be in (FR-48).

    Deliberately four, not Stripe's nine. Stripe's vocabulary is its own
    (`incomplete`, `trialing`, `unpaid`, `paused` …) and most of it describes situations this
    product does not sell into: there is no trial, there is no pause, and a subscription that
    never completed checkout is simply one that does not exist here. The adapter's job is to
    map Stripe's set onto this one; this is the set the product reasons about.

    **`PAST_DUE` is distinct from `CANCELED` because a user must be able to see it.** It is
    the only state in which a person has a problem they can still fix, and the account screen
    has to say so rather than rendering them as plain Free.
    """

    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Past due"
    CANCELED = "canceled", "Canceled"
    EXPIRED = "expired", "Expired"


#: The statuses that occupy a user's one live subscription slot. A user may accumulate any
#: number of `CANCELED` or `EXPIRED` rows — that is the history `BILLING_RECORDS` retains for
#: seven years — but only ever one row in this set, enforced by a partial unique constraint.
LIVE_SUBSCRIPTION_STATUSES = (SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE)


class Subscription(UUIDv7Model):
    """One user's Pro subscription (FR-48, Glossary: Subscription).

    `identity` owns this table because `identity/__init__.py` has always said so — *"Accounts
    and billing state. Owns User and Subscription"* — and because billing state is account
    state: the same app that can tell you an account exists should be the one that tells you
    what it is entitled to.

    **It lives in the `PERSONAL` alias, alongside `User`.** `settings.DATABASE_ROUTING` places
    `identity`, `personalization` and `delivery` in the same alias, so a caller asking about
    entitlement is not crossing the AD-3 wall — that wall runs between `catalog` and
    `personal`. What stops a caller reaching in is AD-2's `models-identity` contract: *"only
    `apps.identity` imports `apps.identity.models` (others call its services)"*. The published
    read is `services/entitlement.is_pro`.

    **`user_id` is a plain UUID, not a `ForeignKey`.** The row is written by webhook-driven
    commands that know a Stripe reference and a user id, never a `User` instance, and a
    relation would invite a caller to join its way to the account from here.

    **There is no delete path.** A lapse is a transition to `CANCELED`; an ended term is
    `EXPIRED`. `BILLING_RECORDS` retains these rows for seven years for tax and legal
    reasons, which would be meaningless against a table anything could delete.

    **`last_event_at` is the ordering guard.** Stripe retries, replays and reorders its
    webhooks; a naive writer lets a stale `customer.subscription.updated` overwrite a newer
    `customer.subscription.deleted` and silently restores entitlement to someone who
    cancelled. The guard lives here, on the row, rather than in the webhook handler, so every
    writer inherits it — the handler, an admin action, a future reconciliation job. This is
    the same reasoning `SavedEvent.event_version` records for AD-17 propagation.
    """

    retention_category = RetentionCategory.BILLING_RECORDS

    user_id = models.UUIDField()
    plan = models.CharField(max_length=16, choices=[(p.value, p.value) for p in ProPlan])
    status = models.CharField(
        max_length=16, choices=SubscriptionStatus.choices, default=SubscriptionStatus.ACTIVE
    )
    current_period_end = models.DateTimeField(null=True, blank=True)
    # The Stripe customer, stored rather than looked up: `create_portal_session(customer_ref=)`
    # needs it, and a round-trip to Stripe to open a settings screen would be absurd.
    stripe_customer_ref = models.CharField(max_length=255)
    stripe_subscription_ref = models.CharField(max_length=255, null=True, blank=True)
    # The external event timestamp last applied to this row. See the class docstring.
    last_event_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # At most one live subscription per user. History is allowed: a user who
            # subscribes, cancels and subscribes again holds one live row and any number of
            # terminal ones.
            models.UniqueConstraint(
                fields=["user_id"],
                condition=models.Q(status__in=LIVE_SUBSCRIPTION_STATUSES),
                name="subscription_one_live_per_user_uq",
            ),
        ]
        indexes = [
            models.Index(fields=["user_id"], name="subscription_user_idx"),
            # The webhook receiver finds a row by what Stripe sends it, which is the
            # subscription reference and not a user id.
            models.Index(fields=["stripe_subscription_ref"], name="subscription_ref_idx"),
        ]

    def __str__(self) -> str:
        return f"subscription {self.status}"


class DataExportStatus(models.TextChoices):
    """Where one export request has got to.

    Four states and no `FAILED`-with-retry distinction: a build that raises leaves the row
    `BUILDING` and the task's own retry is what moves it on. A separate failure state would
    be a second thing to reconcile for no decision anybody makes differently.
    """

    PENDING = "pending"
    BUILDING = "building"
    READY = "ready"
    EXPIRED = "expired"


class DataExport(UUIDv7Model):
    """One user's request for everything this product holds about them (FR-52, GDPR Art. 20).

    `identity` owns it because an export is about an **account**, not about any one app's
    records — the same reasoning that put `Subscription` here. The rows it exports belong to
    `personalization`, `delivery` and `identity` alike, and none of those apps could own a
    request that spans all three.

    **The payloads are columns, not files.** This project configures no object storage, and a
    heavy user's records are tens of kilobytes of JSON. A bucket would mean a dependency,
    credentials, settings and a local-dev service for a payload that fits in a `TextField` —
    and the 30-day lifetime stays one column the retention sweep already understands.

    **`claimed_at` is what makes a second request join the first** rather than queue a second
    job. It is the same claim idiom `DigestPreference.digest_claimed_at` and
    `Source.reliability_claimed_at` use: a row is claimed by the worker that will build it,
    and an unclaimed pending row is the only thing a new request creates.

    **`expires_at` is the authority on a dead link, not the token's age.** The signed link
    carries its own `max_age`, but a link is also dead once the row says so — which is what
    lets an export be revoked without inventing a revocation list, and what a later account
    deletion will set to stop a download mid-window.

    **It holds `ACCOUNT_CONTENT`, not a category of its own.** What the row contains *is* the
    user's account content, copied; retaining it longer than the content it copies would be
    the privacy mistake of keeping a snapshot after the original is gone.
    """

    retention_category = RetentionCategory.ACCOUNT_CONTENT

    #: **This row is exported, but its payloads are not** (FR-52).
    #:
    #: The row is a fact about the user — when they asked, when it was ready, when it
    #: expired — and that is portable. The two body columns are a *copy of everything else
    #: in the export*, so copying them in would nest one export inside the next: a second
    #: request would carry the first's whole payload, a third would carry both, and the
    #: file would grow without bound while saying nothing new.
    export_redact_fields = ("json_body", "ics_body")

    user_id = models.UUIDField()
    status = models.CharField(
        max_length=16, choices=DataExportStatus.choices, default=DataExportStatus.PENDING
    )
    requested_at = models.DateTimeField(default=timezone.now)
    #: Set when a worker takes the row. An unclaimed pending row is the one a new request
    #: joins instead of duplicating.
    claimed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    #: After this, the links are dead whatever their signature says.
    expires_at = models.DateTimeField(null=True, blank=True)
    json_body = models.TextField(blank=True, default="")
    ics_body = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            # **One live request per user.** The partial index is what makes "requesting
            # twice does not queue two jobs" a database fact rather than a race the
            # command layer has to win.
            models.UniqueConstraint(
                fields=["user_id"],
                condition=models.Q(status__in=["pending", "building"]),
                name="data_export_one_in_flight_per_user_uq",
            ),
        ]
        indexes = [
            # The worker's sweep: unclaimed requests, oldest first.
            models.Index(
                fields=["requested_at"],
                condition=models.Q(claimed_at__isnull=True),
                name="data_export_unclaimed_idx",
            ),
        ]

    def __str__(self) -> str:
        # No email, no payload — this reaches every log line and admin column (AD-13).
        return f"export {self.status}"


class IdentityAuditEntry(AuditEntry):
    """The `identity` audit log (AD-5). Append-only; written only through `write_audit`.

    The audit pattern applies to `identity`: `ingestion` and `personalization` each own one
    concrete table, and AD-5 requires one per owning app, so the row sits in `identity`'s
    schema and `identity` is its only writer (AD-16).

    The actor is stored by value as a UUID. There is no email in a row — not in the actor,
    not in the label, not in the details (AD-13).
    """

    retention_category = RetentionCategory.AUDIT_LOG
