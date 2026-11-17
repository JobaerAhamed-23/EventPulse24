---
id: ai-cost-dashboard
title: Make the AI cost rows readable — FR-29
intent: traceability-gap-closure
complexity: low
mode: confirm
status: completed
depends_on: []
created: 2026-11-17
run_id: run-eventpulse24-035
completed_at: 2026-11-17T15:00:40.184Z
---

# Work Item: Make the AI cost rows readable — FR-29

## Description

**The only `MISSING` row in the 2026-11-17 Section C.** `adapters/llm/costs.py:63` writes an
`AICostRow` into the catalog schema on every LLM call and
`adapters/llm/migrations/0001_aicostrow.py` creates the table. Nothing reads it back:
`adapters/llm/` has no `admin.py`, and `grep` finds no `@admin.register(AICostRow)` anywhere
in `backend/`.

So the cost data accrues where no one can see it, and **PRD §10.3's AI cost ceiling has
nothing reporting against it**. The capability row in the Architecture Spine
(`FR-29 → adapters/llm, editorial (Django admin), AD-8, AD-14`) describes a surface that was
never built.

The fix is additive and small: register the model read-only in Django admin, with enough
aggregation that the page answers "are we near the ceiling?" rather than only "what rows
exist?".

## Acceptance Criteria

- [ ] `backend/adapters/llm/admin.py` exists and registers `AICostRow`.
- [ ] The admin is **read-only**: `has_add_permission`, `has_change_permission` and `has_delete_permission` all return `False`, honouring `AppendOnlyModel`.
- [ ] The changelist shows, at minimum, the timestamp, the model/provider, the token counts and the computed cost, with `list_filter` on provider/model and a date hierarchy.
- [ ] The page reports a **total** for the filtered queryset, so PRD §10.3's ceiling is answerable at a glance rather than by exporting rows.
- [ ] The registration reads from the `catalog` database alias correctly (`AICostRow` is written with `.using(CATALOG)`), and the admin does not attempt a cross-schema join that `eventpulse.E002` forbids.
- [ ] A test asserts the admin is registered and that add/change/delete are all refused.
- [ ] `make lint-backend` and `make test-backend` pass.

## Technical Notes

**Model it on `apps/ingestion/admin.py`**, which already solves every problem this item has:
`@admin.register(SourceReliabilityScore)` (line 1147) and `@admin.register(IngestionAuditEntry)`
(line 1162) are existing read-only registrations over append-only, catalog-schema models.
Copy that shape rather than inventing one.

**Watch the database alias.** `costs.py` writes with `.using(CATALOG)`. AD-3 and system check
`eventpulse.E002` forbid relations crossing aliases, so the admin must not add a
`list_select_related` or a filter that reaches into `personal`.

**This is a staff surface, not a product surface.** It is outside the DESIGN.md token system
(Section A scores FR-29 `N/A (no design needed)` for exactly this reason), so plain Django
admin is correct and no EventPulse24 component vocabulary applies.

## Dependencies

(none)
