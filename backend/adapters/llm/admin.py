"""The AI Cost Dashboard (FR-29, AD-8 / AD-14): what the AI spend was, read-only.

**The table was writable long before it was readable.** `costs.py` has written one
`AICostRow` per call since the gateway shipped, and nothing ever read them back — no
admin, no API, no page. The 2026-11-17 traceability pass scored FR-29 `MISSING` for
exactly that: a complete, tested backend with no surface a human can reach. The
Architecture Spine's own Capability row names `adapters/llm` *and* `editorial (Django
admin)`; this file is the half that was never built.

**The dashboard answers "what did we spend", not "who spent it".** There is no user id
in the table and there must never be one — a cost row is a fact about a *call*, and the
same embedding of the same event costs the same whoever asked for it. So nothing here
reaches for an actor, and nothing could: `AICostRow` carries no relations at all, and
AD-3 (with system check `eventpulse.E002`) forbids a `catalog` model relating to
`personal` models like `User`.

**Read-only, as the fourth layer of a guard that already has three.** The model is an
`AppendOnlyModel` with `append_only_mutable = frozenset()`, protected by the guarded
QuerySet, the `forbid_history_mutation` trigger and a `REVOKE UPDATE, DELETE` on the
runtime role. The refusals below add nothing the database would permit — they stop the
*interface* offering an action the database would reject, which is the difference
between a button that is not there and a 500 for whoever pressed it.

**Why this file declares its own read-only base instead of importing one.**
`apps/ingestion/admin.py` already has `ReadOnlyAdmin`, and reusing it is impossible, not
merely undesirable: the import-linter `layers` contract lists `"apps | adapters"` as one
layer whose members are independent, so `adapters.llm` importing `apps.ingestion` fails
`make lint-imports` (AD-2). The alternatives were to hoist a Django-admin base into
`shared/` — putting an app-shaped concern in the innermost layer to save eight lines —
or to violate the contract. Four duplicated refusals is the cheaper of the three.

**No `.using(CATALOG)` here, deliberately.** `costs.py` names the alias because a
*writer* must name the transaction it writes in. Reads route themselves:
`config/db_router.py` maps `db_for_read` by `app_label`, and `llm` is in the `catalog`
set (`settings.DATABASE_ROUTING`). The ingestion admins over catalog models name no
alias either. An explicit one here would not make the read safer — it would hide a
routing failure that should be loud.
"""

from decimal import Decimal

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Sum

from adapters.llm.models import AICostRow

# Micro-dollars per dollar. `cost_micros` is an integer because a float would make the
# dashboard's sum drift (see `models.py`), so the conversion happens at display time and
# never in the stored value.
#
# **A `Decimal`, not an `int`, so the division never produces a float.** The model's rule
# is that money does not pass through binary floating point, and `micros / 1_000_000`
# would do exactly that — silently, and correctly enough to pass a small test while
# drifting on a total large enough to matter. Dividing by a `Decimal` keeps the quotient
# exact.
MICROS_PER_DOLLAR = Decimal(1_000_000)


class ReadOnlyCostAdmin(admin.ModelAdmin):
    """Viewable, never written from admin — an append-only table has no admin writer.

    `delete_model` and `delete_queryset` raise rather than return `False`, because a
    permission check is advisory (a bulk action or a subclass can route around it) and
    the raise is not. The same belt-and-braces pair guards `apps/ingestion`'s admins.
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def delete_model(self, request, obj):
        raise PermissionDenied

    def delete_queryset(self, request, queryset):
        raise PermissionDenied


@admin.register(AICostRow)
class AICostRowAdmin(ReadOnlyCostAdmin):
    """One row per AI call, and the totals for whatever the reader has filtered to.

    **The totals are the feature.** A list of rows answers "which calls happened"; FR-29
    and PRD §10.3 ask "what did we spend, and are we near the ceiling". Reading that off
    a paginated changelist by hand is how a ceiling gets passed unnoticed.

    **`call_count` is shown beside the cost on purpose.** It is how many texts a call
    covered, not how many calls there were — an embedding call takes a batch, so one
    call may cover forty events. Cost read alone makes a batched call look forty times
    more expensive than it was, and the model's own docstring warns about precisely that
    conflation.
    """

    list_display = (
        "created_at",
        "kind",
        "model",
        "input_tokens",
        "output_tokens",
        "call_count",
        "cost_micros",
        "cost_dollars",
    )
    list_filter = ("kind", "model")
    date_hierarchy = "created_at"
    # The model's index is `(kind, -created_at)`, so newest-first is the ordering it
    # already pays for.
    ordering = ("-created_at",)

    @admin.display(description="Cost (USD)", ordering="cost_micros")
    def cost_dollars(self, row: AICostRow) -> str:
        """The stored micro-dollars, in the unit a budget is actually read in."""
        return f"${row.cost_micros / MICROS_PER_DOLLAR:,.4f}"

    def changelist_view(self, request, extra_context=None):
        """Add the filtered totals to the changelist.

        **The totals follow the filters.** `cl.queryset` is the changelist's own
        queryset — already narrowed by the search box, the `kind`/`model` filters and the
        date hierarchy — so the sum answers the question the reader actually asked. A
        sum over `AICostRow.objects.all()` would silently report the whole table under a
        filtered heading, which is worse than no total at all.

        **The super() call comes first and is left alone on failure.** The response may
        be a redirect (an invalid filter sends the user back), and a redirect has no
        `context_data` to decorate — so the totals are attached only when the page is
        the changelist itself.
        """
        response = super().changelist_view(request, extra_context)

        changelist = getattr(response, "context_data", {}).get("cl")
        if changelist is None:
            return response

        totals = changelist.queryset.aggregate(
            cost_micros=Sum("cost_micros"),
            calls=Sum("call_count"),
        )
        # `Sum` over no rows is None, and an empty filter is a normal thing to ask for.
        cost_micros = totals["cost_micros"] or 0
        response.context_data["total_cost_micros"] = cost_micros
        response.context_data["total_cost_dollars"] = f"${cost_micros / MICROS_PER_DOLLAR:,.4f}"
        response.context_data["total_calls"] = totals["calls"] or 0
        response.context_data["title"] = (
            f"AI cost rows — {response.context_data['total_cost_dollars']} "
            f"over {response.context_data['total_calls']:,} calls"
        )
        return response


__all__ = ["AICostRowAdmin", "ReadOnlyCostAdmin"]
