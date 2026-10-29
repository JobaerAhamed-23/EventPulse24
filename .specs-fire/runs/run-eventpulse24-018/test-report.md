---
run: run-eventpulse24-018
work_item: real-feeds-and-e2e-proof
intent: event-catalog-ingestion
generated: 2026-10-28
status: passed
---

# Test Report: Real feeds and the end-to-end ingestion proof

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Unit | 1691 | 0 | 0 | 99.08% |
| Integration | 37 | 0 | 0 | 99.08% |
| **Total** | **1691** | **0** | **0** | **99.08%** |

The integration row is a subset of the total: the 37 end-to-end and seed-command tests
are counted in the 1691. No test was skipped anywhere in the suite.

## Acceptance Criteria Validation

- ✅ **The seed command registers the proof sources** — `test_the_seed_command_registers_the_three_methods_and_is_idempotent` asserts exactly one `jsonld`, one `rss` and one `ics` source, each `tos_status == "approved"` and `status == "active"`.
- ✅ **Every source carries exactly one approved ToS review** — `test_each_seeded_source_carries_its_own_tos_review` asserts one review per source with an `https://` evidence URL; `test_re_running_the_command_does_not_stack_duplicate_reviews` asserts the count never grows.
- ✅ **The editorial group holds exactly twelve permissions** — `test_the_editorial_group_holds_exactly_the_granted_permissions` asserts the exact codename set and `len(granted) == 12`; no `delete` on any model.
- ✅ **The operator is staff, never a superuser** — `test_the_operator_is_staff_and_not_a_superuser_and_uses_the_group` and `test_an_operator_who_became_a_superuser_is_demoted_on_the_next_run`.
- ✅ **A stale grant does not survive** — `test_a_stale_grant_is_removed_from_the_editorial_group` adds `delete_source` by hand and proves the next run removes it.
- ✅ **The chain lands events in the public catalog** — `test_the_whole_chain_lands_events_in_the_public_catalog` proves one title from each acquisition method, the correct UTC instant, the source zone, the venue city and `tz_review_pending is False`.
- ✅ **Series instances are distinct events sharing one series id** — `test_the_series_instances_are_distinct_events_sharing_one_series_id`.
- ✅ **A second tick changes nothing** — `test_re_running_the_tick_changes_nothing` and `test_the_second_ingest_finds_every_item_unchanged`, with `_force_due` backdating the last attempt so the second tick genuinely re-ingests (the claim is not vacuous).
- ✅ **A corrected venue timezone re-resolves its events** — `test_a_corrected_venue_timezone_re_resolves_its_events`: New York → Chicago moves every start, proving the re-ingest really re-resolves when it has to.
- ✅ **The catalog API serves the events anonymously** — `test_the_catalog_api_serves_the_events_to_an_anonymous_client` asserts HTTP 200 and no `Set-Cookie` header.
- ✅ **CI never touches the network** — the suite runs against recorded fixtures through `FakeFetchAdapter`; the real-feed run is a documented manual step only.
- ✅ **The real feeds work** — the manual `SOURCE_FETCH=http` run against `mmfa.org` produced 9 new JSON-LD events and 21 new ICS events (9 of them cross-bound to the JSON-LD source), 30 published events in `America/Chicago`, and `GET /api/catalog/events?city=Montgomery` returned `total: 9`.

## Tests Written

### Unit Tests

- `backend/tests/ingestion/test_seed_local_stack.py` — the seed command's own logic, apart from the end-to-end proof: the ISO-8601 duration parser (4 valid forms, 8 invalid forms), the `--list` output, the unreadable feed file, the non-JSON feed file, the missing content type, the missing permission, both feed sets' shape, the seeded summary line, and `--real` swapping the feed set.
- `backend/tests/e2e/mutation_probe_e2e.py` — nine mutation probes, each a real bug applied to the implementation, proving the suite fails when a rule is broken. Not a pytest module: a standalone runner.

### Integration Tests

- `backend/tests/e2e/test_end_to_end.py` — the sixteen end-to-end tests: seed → tick → ingest → catalog API → tick again. The whole chain runs through the real seams (the management command, the registry services, the 60 s tick, the scheduling claim, the ingest pipeline, the catalog read service and the HTTP API). Only the fetch (recorded fixtures) and the broker (recorded by `tests/e2e/conftest.py`, jobs run inline) are substituted.
- `backend/tests/e2e/conftest.py` — the two seam recordings: the broker (`worker.tasks._enqueue`) and the outbox (`apps.ingestion.services.outbox._send`).

## Test Commands

```bash
# Run all tests
make test-backend

# Run with coverage
make coverage-backend

# The end-to-end proof on its own
uv run --directory backend pytest tests/e2e tests/ingestion/test_seed_local_stack.py -q

# The mutation probes (not a pytest module)
uv run --directory backend python tests/e2e/mutation_probe_e2e.py
```

## Coverage Details

| Module | Statements | Branches | Functions | Lines |
|--------|------------|----------|-----------|-------|
| `config/management/commands/seed_local_stack.py` | 96% | 92% | 100% | 96% |
| `apps/ingestion/services/source_registry.py` | 99% | 95% | 100% | 99% |
| `apps/ingestion/services/venue_registry.py` | 99% | 92% | 100% | 99% |
| `domain/` (whole package) | 100% | 100% | 100% | 100% |
| **Total (whole backend)** | **99.08%** | **96%** | **100%** | **99.08%** |

The five uncovered lines in the seed command are the defensive branches that the
command's own refusals make unreachable in a healthy database: the `is_staff` repair
branch on an existing operator (line 149-150), the `DomainError` re-raise (line 124),
the `tos_status != "approved"` re-review branch (line 230) and the venue-timezone
correction branch (line 204).

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| `_duration` accepted `"PT"` as zero seconds (no component required) | Medium | Fixed — a non-empty component set is now required |
| `_duration` accepted `"PT.5H4H"` as nine hours (a repeated unit was silently absorbed) | Medium | Fixed — a repeated unit is now refused |
| The original probe #8 ("an unchanged item is re-resolved and rewritten") was a no-op mutation | Medium | Fixed — replaced by two catchable probes and a new test that reaches them |
| The `--real` unit test used a `Command.handle` spy that verified nothing | Low | Fixed — rewritten to assert the registered URLs contain `mmfa.org` |
| Two refusal tests monkeypatched a queryset the command never calls | Low | Fixed — rewritten to delete the `ContentType` / `Permission` rows instead |
| The committed local operator password (`operator-local-password`) | Low | Observation — a local `example.test` account, per plan decision D2; not a real credential |

## Ready for Completion

- [x] All tests passing
- [x] Coverage target met (80%)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-018*
