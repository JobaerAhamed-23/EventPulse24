---
run: run-eventpulse24-035
work_item: ai-cost-dashboard
intent: traceability-gap-closure
date: 2026-11-17
---

# Code Review: Make the AI cost rows readable — FR-29

## Findings

### 1. Money passed through binary floating point — **fixed**

`cost_dollars` and the changelist total both computed `cost_micros / MICROS_PER_DOLLAR`
with `MICROS_PER_DOLLAR` an `int`, which makes the quotient a Python `float`.

That contradicts the rule the file itself cites. `models.py` stores `cost_micros` as an
integer specifically because *"a float here would make the dashboard's sum drift"* — and
this is the dashboard. The failure mode is the quiet one: correct to four decimal places
on any test-sized number, drifting only on a total large enough to matter, which is
exactly the total a cost ceiling is about.

`MICROS_PER_DOLLAR` is now a `Decimal`, so the division is exact. Tests re-run: 12 passed.

### 2. Checked and found sound

| Concern | Finding |
|---|---|
| Redirect from an invalid filter | `getattr(response, "context_data", {})` guards it; a redirect has no `context_data` and returns early |
| `Sum` over zero rows | Returns `None`; coerced with `or 0` and covered by a test |
| Totals ignoring filters | `cl.queryset` is the changelist's own narrowed queryset, not `objects.all()`; covered by a test |
| Cross-alias access | No FK, no `list_select_related`, no actor lookup — `AICostRow` has no relations, and AD-3 / `eventpulse.E002` forbid a catalog model relating to `personal` |
| Append-only integrity | Four refusals; `delete_model`/`delete_queryset` raise rather than return `False`, since a permission check is advisory and a raise is not |
| Index use | `ordering = ("-created_at",)` matches the model's `(kind, -created_at)` index |

## Not changed, and why

**The 6 pre-existing suite failures are left alone.** Two in `tests/delivery/test_preferences_api.py`
and four in `tests/e2e/test_state_change_proof.py`, all failing identically on a clean
checkout (verified by stashing). Fixing unrelated red tests inside this run would make the
diff describe something other than FR-29. The two delivery ones sit in a file the next work
item (`pulse-ping-control`) will touch.

## Verdict

**Approved.** One finding, found and fixed in review. All gates green: 12 new tests, ruff
clean, 19/19 import contracts kept, `manage.py check` clean.
