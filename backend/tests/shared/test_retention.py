"""Retention registry (AD-15): PRD §10.2 categories and full model coverage."""

from django.apps import apps
from django.contrib.sessions.models import Session

from apps.identity.models import User
from shared.retention import (
    FRAMEWORK_RETENTION,
    PRD_CATEGORIES,
    RetentionCategory,
    retention_category_of,
    retention_registry,
)


def test_prd_categories_are_exactly_the_nine_prd_bullets():
    assert {str(category) for category in PRD_CATEGORIES} == {
        "account_content",
        "account_identity",
        "preference_signals",
        "email_delivery_events",
        "audit_log",
        "source_registry",
        "tos_review_records",
        "billing_records",
        "analytics_aggregates",
    }
    assert RetentionCategory.NOT_USER_DATA not in PRD_CATEGORIES


def test_registry_covers_every_installed_model_with_a_valid_category():
    registry = retention_registry()

    assert set(registry) == set(apps.get_models())
    assert all(isinstance(category, RetentionCategory) for category in registry.values())


def test_user_is_account_identity():
    assert retention_category_of(User) is RetentionCategory.ACCOUNT_IDENTITY


def test_sessions_are_account_identity():
    assert retention_category_of(Session) is RetentionCategory.ACCOUNT_IDENTITY


def test_framework_map_covers_django_models_by_label():
    assert FRAMEWORK_RETENTION["admin.logentry"] is RetentionCategory.AUDIT_LOG
    for label in ("auth.group", "auth.permission", "contenttypes.contenttype"):
        assert FRAMEWORK_RETENTION[label] is RetentionCategory.NOT_USER_DATA
