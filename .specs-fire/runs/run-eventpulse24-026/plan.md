---
run: run-eventpulse24-026
work_item: review-queue-model
intent: trust-loop
mode: validate
checkpoint: plan (checkpoint 2)
approved_at: 2026-11-10
---

# Implementation Plan: Something to queue onto — the ReviewItem and the editorial group

## Approach

Build exactly what the approved design (D1–D12) fixes, in this order:

1. The constant.
2. The model and its constraints.
3. A migration, hand-checked against `makemigrations` output, with the trigger in `RunSQL` and reverse SQL.
4. The `raise_review_item` command.
5. The editorial grant.

Tests come before or alongside each piece. The constraint and trigger tests use **raw SQL on the catalog connection**, following `tests/ingestion/test_triggers.py`'s `restricted()` helper, so a pass proves the database layer itself and not a Python guard. Every rejection test asserts the specific constraint name or trigger message, so a test cannot pass because a *different* check fired.

The grant change is shown failing first. The existing `test_the_editorial_group_holds_exactly_the_granted_permissions` (`len == 12`, the `EXPECTED_CODENAMES` set) must fail after the `EDITORIAL_GRANTS` edit and before its expectation is updated.

**Concurrency** follows `tests/ingestion/test_ingest_concurrency.py`: `transaction=True` and two threads, each with its own connection. A `threading.Barrier` releases both raisers into `raise_review_item` together, and the test asserts one row with tallies summing to 2. To prove the test can fail, a recorded probe temporarily removes the `IntegrityError` recovery. The test must then raise, and the probe is reported in the test report.

**The closed-row race (D10)** is tested deterministically, not with threads. The first insert is forced to collide, and the open row is resolved between the collision and the locked re-read, using a monkeypatched hook on a private `_reread_open` seam. The assertion is that a fresh row was opened and the closed row is untouched.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/apps/ingestion/migrations/0008_reviewitem.py` | `CreateModel` (generated, then reviewed), plus `RunSQL` for `catalog.guard_review_item()` and the `review_item_guard` trigger, with reverse SQL |
| `backend/apps/ingestion/services/review_queue.py` | `raise_review_item`, `RaiseResult`, and the private `_reread_open` seam (D10) |
| `backend/tests/ingestion/test_review_item_model.py` | D1, D3, D6 and D8 constraints; D2 partial uniqueness; D7 trigger, `FIXED_FIELDS` parity, and delete under purge; the `report_count` property; retention category |
| `backend/tests/ingestion/test_review_queue.py` | Raise, bump, validation, the audit action and actor (D4), a raise after a close, and the closed-row race |
| `backend/tests/ingestion/test_review_queue_concurrency.py` | Two-thread concurrent raise, `transaction=True` |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/shared/constants.py` | `REVIEW_SLA_USER_REPORTED = timedelta(hours=24)`, beside the other review and confidence constants |
| `backend/apps/ingestion/models.py` | The `ReviewItem` class, which has: the `Reason`, `Status`, `Resolution` and `ReportCategory` choices; the `REPORT_FIELDS` map (category to column); `FIXED_FIELDS`; fields; the six constraints; the partial index; `retention_category = SOURCE_REGISTRY`; and the `report_count` property. The module docstring's ownership line already names `ReviewItem`. |
| `backend/tests/ingestion/factories.py` | `ReviewItemFactory`, open, with an `in_review` event target by default |
| `backend/config/management/commands/seed_local_stack.py` | `EDITORIAL_GRANTS["reviewitem"] = ("change", "view")`; docstring "twelve" becomes "fourteen" (both places) |
| `backend/tests/e2e/test_end_to_end.py` | `EXPECTED_CODENAMES` gains `change_reviewitem` and `view_reviewitem`; `len == 14`; adds `has_perm("ingestion.delete_reviewitem") is False` and `has_perm("ingestion.add_reviewitem") is False` |

## Tests

| Test File | Coverage |
|-----------|----------|
| `test_review_item_model.py` | **Target check:** an event item with a source too, an event item with neither target, and a source item with an event (each asserts `review_item_target_ck`). **Uniqueness:** a second open (event, reason) is refused, while a second item with a different reason on the same event, and a second item after a close, are both allowed. **Tallies** on a non-report item are refused. **Due date:** `due_at` null on a report is refused, and `due_at` set on `in_review` is refused. **Resolution (D6):** open with a resolution, resolved without a resolver, `approved` by a system actor, `withdrawn` by a user, `dismissed` on an event item, and `approved` on a source item. **Trigger (D7):** an update of a resolved row is refused, a change to `reason`/`event_id`/`source_id`/`raised_at` on an open row is refused, delete is refused, and delete is allowed under `retention_purge`. **Parity:** the trigger body's fixed columns equal `ReviewItem.FIXED_FIELDS`. |
| `test_review_queue.py` | **Raise:** creates an open row with `due_at = now + 24h` for a report, and none otherwise. **Bump:** increments the right tally, leaves `due_at` alone, and moves `last_raised_at`. **Audit:** `review_item_raised`, then `review_item_bumped`, with the passed actor. **D4:** a report-raised audit row has `actor_kind=system` and `actor_id IS NULL`. **Validation:** a missing category on a report, a category on a non-report, a reason/target mismatch, and no target at all each raise `ValidationError` and write nothing. **After a close**, a raise opens a new row. **Closed-row race:** handled by the seam. **Transaction:** calling inside an outer catalog atomic block that then rolls back leaves no row and no audit. |
| `test_review_queue_concurrency.py` | Two threads raise the same (event, `user_reported`) with different categories. The result is one open row, two tallies at 1, `report_count == 2`, and two audit rows. |
| `tests/e2e/test_end_to_end.py` (modified) | The grant set is exactly 14 codenames, and there is no add or delete on `reviewitem` |

## Technical Details

- **Migration numbering.** The latest is `0007_source_cadence_ceiling`, so this is `0008_reviewitem`. One migration, forward-only, per the constitution.
- **Resolver columns** are `resolved_by_kind` (CharField, blank), `resolved_by_id` (UUID, null) and `resolved_by_label` (CharField(64), blank). The D6 check is written out in full rather than reusing `actor_check()`, because `actor_check()` requires a non-empty kind.
- **The bump** is `ReviewItem.objects.using(CATALOG).filter(pk=…, status="open").update(**{col: F(col) + 1}, last_raised_at=now, updated_at=now)` after the `select_for_update()` read. If the filtered update returns 0, the row closed under us, and we retry the insert once (D10).
- **Errors:** `domain.errors.ValidationError`, with the `details={"errors": [...]}` shape `_add_domain_error` already reads, so the admin item can surface refusals for free.
- **No new ruff or import-linter exceptions.** `review_queue.py` imports only `apps.ingestion.models`, `apps.ingestion.services.audit`, `shared.*` and `domain.errors`.
- **Verification commands**, using the existing toolchain: `uv run pytest`, `uv run python manage.py check`, `uv run python manage.py makemigrations --check --dry-run`, `uv run lint-imports`, `uv run ruff check` and `uv run ruff format --check`. The local Postgres must be up; if Docker is stopped, run `systemctl --user start docker-desktop` and then `make up`.

## Based on Design Doc

Reference: `.specs-fire/intents/trust-loop/work-items/review-queue-model-design.md` (checkpoint 1 approved, 2026-11-10)

---
*Plan approved at checkpoint. Execution follows.*
