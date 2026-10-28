"""Retention registry (AD-15): every model declares how long its rows live.

A model sets `retention_category = RetentionCategory.X`; models we don't own are covered by
FRAMEWORK_RETENTION. System checks eventpulse.E003/E004 fail on any concrete model without a
valid category. The sweep job, account deletion and export (FR-52) all read `retention_registry()`.
"""

from enum import StrEnum

from django.apps import apps


class RetentionCategory(StrEnum):
    """PRD §10.2 retention categories, plus one explicit exemption."""

    # Personal events + saved events: while the account is active; purged ≤30 days after deletion.
    ACCOUNT_CONTENT = "account_content"
    # Personal email addresses and calendar credentials: while active; encrypted at rest;
    # purged on disconnect or account deletion.
    ACCOUNT_IDENTITY = "account_identity"
    # Preference graph signals (dwell, swipes, dismissals): 12 months rolling.
    PREFERENCE_SIGNALS = "preference_signals"
    # Email delivery events (sent, opened, clicked): 90 days, then aggregated counts.
    EMAIL_DELIVERY_EVENTS = "email_delivery_events"
    # Audit logs (auth events, settings changes, deletions): 24 months.
    AUDIT_LOG = "audit_log"
    # Source Registry contents (third-party event data): event date range + 12 months; archived.
    SOURCE_REGISTRY = "source_registry"
    # Source-acquisition ToS review records: 7 years (legal).
    TOS_REVIEW_RECORDS = "tos_review_records"
    # Billing records (Pro subscribers): 7 years (tax/legal).
    BILLING_RECORDS = "billing_records"
    # Anonymized analytics aggregates: indefinitely (no PII).
    ANALYTICS_AGGREGATES = "analytics_aggregates"
    # Not a PRD category: the table holds no user-derived data. Never shown to users.
    NOT_USER_DATA = "not_user_data"


# The categories users see in Settings → Privacy → "What we store" and in export.
PRD_CATEGORIES = tuple(c for c in RetentionCategory if c is not RetentionCategory.NOT_USER_DATA)

# Models from Django and third-party apps, keyed by `_meta.label_lower`.
FRAMEWORK_RETENTION = {
    # A credential: dies on expiry or logout, immediately on account deletion. Expired rows are
    # cleared by the retention sweep (`clearsessions`).
    "sessions.session": RetentionCategory.ACCOUNT_IDENTITY,
    "admin.logentry": RetentionCategory.AUDIT_LOG,
    "auth.group": RetentionCategory.NOT_USER_DATA,
    "auth.permission": RetentionCategory.NOT_USER_DATA,
    "contenttypes.contenttype": RetentionCategory.NOT_USER_DATA,
}


def retention_category_of(model, framework=FRAMEWORK_RETENTION):
    """Return the model's declared category (possibly invalid), or None if undeclared."""
    declared = getattr(model, "retention_category", None)
    if declared is not None:
        return declared
    return framework.get(model._meta.label_lower)


def retention_registry() -> dict:
    """Map every concrete installed model to its RetentionCategory."""
    return {model: retention_category_of(model) for model in apps.get_models()}
