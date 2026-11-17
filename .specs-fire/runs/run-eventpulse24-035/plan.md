---
run: run-eventpulse24-035
work_item: ai-cost-dashboard
intent: traceability-gap-closure
mode: confirm
checkpoint: plan
approved_at: pending
---

# Implementation Plan: Make the AI cost rows readable — FR-29

## Approach

Register `AICostRow` in Django admin, read-only, from a new `adapters/llm/admin.py`, and give
the changelist a **total for the filtered queryset** so PRD §10.3's ceiling question is
answerable at a glance rather than by exporting rows.

Three findings from reading the code changed the shape of this from the work item's first
sketch, and each one is a constraint rather than a preference:

**1. The `ReadOnlyAdmin` base cannot be reused — importing it would break the build.** The
work item said to model this on `apps/ingestion/admin.py`'s registrations, and the pattern is
right, but the *import* is not available. `ReadOnlyAdmin` is defined at
`apps/ingestion/admin.py:154` on top of `CommandAdmin` (line 109), and the import-linter
`layers` contract puts `apps | adapters` on **one layer separated by `|`**, which means they
are independent siblings that may not import each other. `adapters.llm.admin` importing
`apps.ingestion.admin` would fail `make lint-imports` (AD-2). So this file declares its own
small read-only base. That is duplication of four methods, and it is the correct kind: the
alternative is either a contract violation or hoisting a Django-admin base into `shared/`,
which would put an `apps`-flavoured concern in the innermost layer to save eight lines.

**2. No `.using(CATALOG)` anywhere.** `costs.py` writes with `.using(CATALOG)` because a
writer must name its transaction, but **reads are routed automatically**: `config/db_router.py`
`db_for_read` maps by `app_label` through `settings.DATABASE_ROUTING`, and `llm` is in the
catalog set (`settings.py:78`, with a comment explaining why). The ingestion admins over
catalog models use no explicit alias for exactly this reason. Adding one here would be
inconsistent and would mask a routing bug rather than fix one.

**3. The admin may read its own model directly.** `models.py` says the dashboard "reads the
costs through a port query rather than by importing this module" — that rule is about *other*
layers reaching in. This admin lives inside `adapters/llm`, the package that owns the table,
and Django admin needs the model class itself to register. No port is involved and none should
be invented.

**The total is the point of the item, not a decoration.** A changelist that lists rows answers
"what calls happened"; FR-29 and PRD §10.3 ask "what did we spend, and are we near the
ceiling". So the total is computed over the **filtered** queryset — whatever the staff user
has narrowed to by kind, model or date — and rendered in micro-dollars *and* dollars, since
`cost_micros` is an integer in micro-dollars and nobody reads a budget in those.

`call_count` is summed too, and deliberately shown beside the cost: the model's own docstring
warns that `call_count` is how many texts a call covered, not how many calls there were, so a
batched embedding call looks forty times more expensive than it was if you read cost alone.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/adapters/llm/admin.py` | Read-only `AICostRow` registration with a filtered-queryset total |
| `backend/tests/adapters/test_llm_admin.py` | Proves registration, the three refusals, and the total |

## Files to Modify

| File | Changes |
|------|---------|
| (none) | The app is already in `INSTALLED_APPS` and already routed to `catalog`; Django autodiscovers `admin.py` in an installed app, so no wiring changes |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/adapters/test_llm_admin.py` | `AICostRow` is registered; `has_add_permission`, `has_change_permission` and `has_delete_permission` all return `False`; the changelist renders for a superuser; the total reflects the **filtered** queryset, not the whole table; `delete_model`/`delete_queryset` raise `PermissionDenied` |

## Technical Details

**The read-only base, declared locally:**

```python
class ReadOnlyCostAdmin(admin.ModelAdmin):
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
    def delete_model(self, request, obj): raise PermissionDenied
    def delete_queryset(self, request, queryset): raise PermissionDenied
```

`AICostRow` is an `AppendOnlyModel` with `append_only_mutable = frozenset()` and is guarded at
three layers already (guarded QuerySet, `forbid_history_mutation` trigger, `REVOKE UPDATE,
DELETE` on the runtime role). The admin refusals are the fourth and outermost: they stop the
UI *offering* an action the database would refuse, which is the difference between a disabled
button and a 500.

**The total, via `changelist_view`:** override it, read
`response.context_data["cl"].queryset`, aggregate `Sum("cost_micros")` and `Sum("call_count")`,
and put them in the context for the template. This is the standard Django hook and keeps the
filters honoured — `cl.queryset` is already narrowed by the user's search and filters.

**Columns:** `created_at`, `kind`, `model`, `input_tokens`, `output_tokens`, `call_count`,
`cost_micros` plus a `cost_dollars` display method.
**Filters:** `kind`, `model`. **Date hierarchy:** `created_at`. **Ordering:** `-created_at`
(the model's index leads with `kind, -created_at`, so this is index-friendly).

**No `list_select_related`, no FK filters.** `AICostRow` has no relations by design — it
stores no user id, and AD-3/`eventpulse.E002` forbid a catalog model relating to `personal`
models like `User`. Nothing in this admin may reach for an actor.

**Test database markers:** `pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])`
— the superuser fixture writes to `personal` and the cost rows to `catalog`, matching
`tests/ingestion/test_admin.py`.

## Verification

`make test-backend` and `make lint-backend` (ruff check, ruff format --check, lint-imports).
`lint-imports` is the one that would catch the `apps`→`adapters` mistake described above, so it
is not optional here. **No running server or Docker infra is required** — the admin is
exercised through Django's test client.

---
*Plan approved at checkpoint. Execution follows.*
