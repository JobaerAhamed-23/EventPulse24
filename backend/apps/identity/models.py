"""The `identity` module's models (AD-16): the account, its reset tokens, and its audit log.

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

    retention_category = RetentionCategory.ACCOUNT_IDENTITY

    # Uniqueness is the explicit `user_email_uq` constraint below, not a column-level
    # `unique=True`: one named constraint is one thing to read, test and cite.
    email = models.EmailField(max_length=254)
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


class IdentityAuditEntry(AuditEntry):
    """The `identity` audit log (AD-5). Append-only; written only through `write_audit`.

    The audit pattern applies to `identity`: `ingestion` and `personalization` each own one
    concrete table, and AD-5 requires one per owning app, so the row sits in `identity`'s
    schema and `identity` is its only writer (AD-16).

    The actor is stored by value as a UUID. There is no email in a row — not in the actor,
    not in the label, not in the details (AD-13).
    """

    retention_category = RetentionCategory.AUDIT_LOG
