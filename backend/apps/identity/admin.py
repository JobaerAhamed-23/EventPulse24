"""The `identity` admin (AD-14): Django admin is a command client.

`User` has no `username`, `first_name` or `last_name` (AD-18: the email is the login), so
Django's stock `UserAdmin` cannot be used: it lists and orders by fields that no longer
exist. This is a trimmed `UserAdmin` that keeps the same behaviour over the fields the model
has.

`User` is **not** a command-client surface for sign-up: accounts are created by
`apps.identity.services.sign_up.sign_up`, which applies the password validators and the
enumeration-safe rules. The admin is for editorial work on existing accounts.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.identity.models import IdentityAuditEntry, PasswordResetToken, User


class IdentityAuditEntryAdmin(admin.ModelAdmin):
    """The audit log is history: read-only (AD-5, AD-14)."""

    list_display = ["at", "action", "target_type", "actor_kind"]
    list_filter = ["action", "actor_kind"]
    search_fields = ["action", "target_type"]
    date_hierarchy = "at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class PasswordResetTokenAdmin(admin.ModelAdmin):
    """Outstanding reset tokens. Listing a digest is safe; there is no token to leak.

    The rows are never edited by hand: a token is issued by the reset service and consumed
    by it. This admin exists so an operator can see that a reset is outstanding.
    """

    list_display = ["user_id", "expires_at", "used_at", "revoked_at", "created_at"]
    list_filter = ["used_at", "revoked_at"]
    search_fields = ["user_id"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """The account, keyed by email."""

    ordering = ["email"]
    list_display = ["email", "is_staff", "is_active", "date_joined"]
    list_filter = ["is_staff", "is_superuser", "is_active"]
    search_fields = ["email"]

    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        (
            "Permissions",
            {
                "fields": [
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ]
            },
        ),
        ("Dates", {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [
        (
            None,
            {
                "classes": ["wide"],
                "fields": ["email", "password1", "password2"],
            },
        ),
    ]


admin.site.register(IdentityAuditEntry, IdentityAuditEntryAdmin)
admin.site.register(PasswordResetToken, PasswordResetTokenAdmin)
