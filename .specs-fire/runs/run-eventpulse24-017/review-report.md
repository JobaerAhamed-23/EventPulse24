---
run: run-eventpulse24-017
work_item: public-catalog-read-api
intent: event-catalog-ingestion
generated: 2026-10-28
reviewer: fire-builder (code-review skill)
status: complete
---

# Code Review: Public Catalog Read API

## Scope

Reviewed every file created or modified in run-eventpulse24-017.

**Created**

| File | Purpose |
|------|---------|
| `backend/apps/ingestion/services/catalog_read.py` | The published read interface over the catalog |
| `backend/apps/catalog/schemas.py` | `EventOut`, `EventListOut`, `EventPage` — the wire shapes |
| `backend/apps/catalog/api.py` | The two public routes |
| `backend/tests/api/test_catalog_api.py` | The endpoint tests (21) |
| `backend/tests/api/test_catalog_read_service.py` | The read-interface tests (20) |
| `backend/tests/api/mutation_probe_catalog.py` | The 9 mutation probes |
| `frontend/lib/api/openapi.json` | The regenerated OpenAPI schema |
| `frontend/lib/api/schema.ts` | The regenerated TypeScript client |

**Modified**

| File | Changes |
|------|---------|
| `backend/config/api.py` | `api.add_router("/catalog", catalog_router)` |
| `backend/pyproject.toml` | `config.api` added to the `worker-not-api` contract's forbidden modules |
| `backend/tests/architecture/test_import_contracts.py` | The planted `import config.api` violation now expects two broken contracts |

## Summary

| Category | Auto-fixed | Suggested | Skipped |
|----------|-----------|-----------|---------|
| Code Quality | 0 | 1 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 0 | 0 | 0 |
| Testing | 0 | 0 | 0 |
| **Total** | **0** | **1** | **0** |

## Linters

| Tool | Result |
|------|--------|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 240 files already formatted |
| `lint-imports` | 13 contracts kept, 0 broken |
| `eslint .` (frontend) | clean |
| `tsc --noEmit` (frontend) | clean |

There was nothing mechanical to fix: no unused imports, no stray `print`/`console.log`, no
import-order drift, no trailing whitespace. The code is already in the project's shape.

## Findings

### CONFIRM-1 — The endpoint echoes the *unclamped* pagination values

- **Category:** Code Quality (latent correctness)
- **File:** `backend/apps/catalog/api.py:49-56`
- **Status:** Not applied — recorded for a future change.

**Observation.** The read service clamps its inputs:

```python
page = max(page, 1)
page_size = max(1, min(page_size, MAX_PAGE_SIZE))
```

The endpoint then echoes the *unclamped* values and derives `has_next` from them:

```python
page = filters.page
page_size = filters.page_size
has_next = page * page_size < total
```

If the two ever disagreed, the envelope would describe a page the service did not return.

**Why it is not a live bug.** `EventPage` declares `page: int = Field(1, ge=1)` and
`page_size: int = Field(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)`. Django Ninja validates
the query string before the endpoint runs, so an out-of-range value is rejected with a 422.
Verified directly against the running API: `page=0`, `page=-1`, `page_size=0`, `page_size=-5`
and `page_size=99999` all return **422** with the shared error shape, and the endpoint never
sees them. The clamps in the service are therefore defence in depth for direct callers.

**Suggestion.** Have the service return the values it actually used, so the envelope and the
slice can never diverge:

```python
# in list_public_events
page = max(page, 1)
page_size = max(1, min(page_size, MAX_PAGE_SIZE))
...
return items, total, page, page_size
```

**Risk:** Low, but it changes the service's signature and every caller and test of it. Not
worth doing inside this run, where the behaviour is already correct and proven. **Suggested for
the next intent that touches the catalog read path.**

### Verified correct — no action needed

| Check | Result |
|-------|--------|
| **Import wall** | `apps/catalog/*` imports `apps.ingestion.services.catalog_read` only. `apps.ingestion.models` is reached only from inside `apps/ingestion`. `lint-imports` and the planted-violation tests both pass. |
| **No writes from a surface** | `apps/catalog/api.py` contains no `.save()`, `.create()`, `.update()`, `.delete()`, `get_or_create()` or `update_or_create()`. The syntactic scan in `tests/architecture/test_no_direct_writes.py` passes. |
| **No session (AD-12)** | Neither endpoint reads or writes `request.session`. The tests assert `Set-Cookie` is absent from both responses and from the 404. |
| **No raw payload (AD-9)** | The Event's stripped `description` and `ExtractedRecord.payload` never appear. A test asserts the exact response field set. |
| **Error mapping** | `EventNotFoundError` subclasses `domain.errors.NotFoundError`; `config/errors.py` is the only mapping; the endpoint declares `response={404: ErrorOut}`. No per-endpoint `try/except`. |
| **Database alias** | The query uses `.using(CATALOG)` explicitly; no bare `transaction.atomic()`. |
| **Time handling** | `timezone.now()` at the request boundary; the service takes an explicit `now`. No naive datetimes, no time-freezing library (Ruff `DTZ` clean). |
| **Ordering determinism** | `start_time_utc` then `id`. The UUIDv7 id is time-ordered, so the tiebreak is stable and pages neither repeat nor skip. Proven by a dedicated test and by mutation probe 4. |
| **Query-parameter binding** | `EventPage` is bound with `Query(...)`, so it arrives as query parameters. A schema-typed argument without it would become a request *body* — mutation probe 9 proves the binding is actually exercised. |
| **Contract regeneration** | `make client` reproduces the committed `openapi.json` and `schema.ts` byte-for-byte. `tests/api/test_contract.py` passes. |
| **The `worker-not-api` change** | This is a **tightening**: `config.api` was *added* to `forbidden_modules`, because it assembles the app routers and reaches `apps.*.api` transitively. The planted-violation test was updated to expect two broken contracts rather than one, which matches the new behaviour. |

## Conclusion

The implementation is sound, matches the project's standards, and needs no changes. The one
finding is latent rather than live, and is recorded for the next intent that touches this
path. No auto-fixes were applied, so no re-run was needed.

**Auto-fixed: 0. Suggested: 1 (not applied). Skipped: 0.**

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-017*
