"""The `personalization` admin (AD-14): Django admin is a command client.

`CalendarConnection` is registered read-only, and — the point of this module — the
**credential is excluded from the admin entirely**. It is not in `list_display`, not in
`readonly_fields`, and not in `fieldsets`.

That is stronger than making it a readonly field: a readonly field is still *rendered* into
the page, which would put the ciphertext in the operator's browser and in the response
body. Excluded means the ciphertext never leaves the server at all.

The fingerprint is excluded for the same reason from the other direction: it is a stable
identifier of a secret, and it has no business in a browser either.

Design: .specs-fire/intents/onboarding-and-account/work-items/
calendar-connection-model-design.md (decision D10).
"""

from django.contrib import admin

from apps.personalization.models import CalendarConnection


class CalendarConnectionAdmin(admin.ModelAdmin):
    """Connected calendars, without their credentials.

    The rows are never edited by hand: a connection is created by
    `apps.personalization.services.calendar_connections.connect_calendar`, and its status
    is set by a poll. This admin exists so an operator can see that a calendar is
    connected, and when it was last polled.
    """

    list_display = [
        "provider",
        "status",
        "last_polled_at",
        "next_poll_at",
        "last_error_kind",
        "display_label",
        "created_at",
    ]
    list_filter = ["provider", "status"]
    search_fields = ["user_id", "display_label"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(CalendarConnection, CalendarConnectionAdmin)
