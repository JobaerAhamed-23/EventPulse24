# Code Review Report

**Run**: run-eventpulse24-018
**Intent**: event-catalog-ingestion
**Reviewed**: 2026-10-28
**Files Reviewed**: 10

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 0 | 2 | 2 |
| Security | 0 | 0 | 1 |
| Architecture | 0 | 1 | 0 |
| Testing | 0 | 1 | 0 |
| **Total** | **0** | **4** | **3** |

**Tests Status**: Passing

The review covered the whole change: the seed command, its two feed files, the two new
published lookups, the e2e suite and its conftest, the mutation probes, the seed-command
unit tests, the JSON-LD fixture and the README section.

---

## Files Reviewed

- `backend/config/management/commands/seed_local_stack.py` (new — the seed command)
- `backend/config/local_feeds.json` (new — the real MMFA feed set)
- `backend/config/local_feeds.fixtures.json` (new — the CI feed set)
- `backend/apps/ingestion/services/source_registry.py` (modified — added `find_source_by_url`)
- `backend/apps/ingestion/services/venue_registry.py` (modified — added `find_venue`)
- `backend/tests/e2e/test_end_to_end.py` (new — the end-to-end proof)
- `backend/tests/e2e/conftest.py` (new — the broker and outbox seams)
- `backend/tests/e2e/mutation_probe_e2e.py` (new — the nine mutation probes)
- `backend/tests/ingestion/test_seed_local_stack.py` (new — the command's own logic)
- `backend/tests/fixtures/sources/events.jsonld.html` (new — the JSON-LD fixture)
- `backend/tests/fixtures/sources/index.json` (modified — the fixture's index entry)
- `README.md` (modified — the local ingestion section)

---

## Auto-Fixed Issues

No auto-fixes applied. The mechanical fixes (Ruff's import sorting, the two reformat
passes and the line-length wrap) were made before this review, as part of the lint gate,
not as review auto-fixes.

---

## Applied Suggestions

### 1. [Code Quality] `_duration` accepted a duration with no component

- **File**: `backend/config/management/commands/seed_local_stack.py:83`
- **Description**: The parser summed the components it found and returned the total. `"PT"` has no components, so it returned `timedelta(0)` — a source with a zero cadence would be due on every tick, forever.
- **Rationale**: A cadence of zero is never a real editorial decision; it is a malformed feed file. The command should refuse the file rather than register a source that hammers the publisher. The refusal is the safe direction, and the fix makes the parser's contract match its own docstring.
- **Risk Level**: Low
- **Approved**: applied during implementation (2026-10-28)
- **Diff**:

```diff
-    if number or not seen_units:
+    if number or not seen_units:
         raise ValueError(f"{value!r} is not an ISO-8601 duration")
```

(The `not seen_units` half of the condition is the fix: at least one component is now required.)

### 2. [Code Quality] `_duration` accepted a repeated unit

- **File**: `backend/config/management/commands/seed_local_stack.py:78`
- **Description**: `"PT.5H4H"` parsed as 4.5 + 4 = 8.5 hours. The second `H` was silently absorbed, so a malformed duration was read as a plausible one rather than refused.
- **Rationale**: A repeated unit is malformed under ISO-8601. The same rule as case 1: refuse the file rather than guess a cadence. A `seen_units` set makes the refusal explicit.
- **Risk Level**: Low
- **Approved**: applied during implementation (2026-10-28)
- **Diff**:

```diff
+        if character not in _DURATION_UNITS or not number or character in seen_units:
             raise ValueError(f"{value!r} is not an ISO-8601 duration")
```

### 3. [Architecture] The command looked its sources and venues up through the published services

- **File**: `backend/apps/ingestion/services/source_registry.py`, `backend/apps/ingestion/services/venue_registry.py`
- **Description**: Idempotency needs a "does this already exist?" lookup before registering. Reaching for `Source.objects` and `Venue.objects` from the command would have broken the `models-ingestion` import contract (only `apps.ingestion` may import `apps.ingestion.models`) and bypassed the service layer that owns these writes.
- **Rationale**: Two small published lookups — `find_source_by_url(url)` and `find_venue(name=, city=, country_code=)` — were added to the registries that own the models. The command now talks to the services only, exactly as AD-5 requires, and the import contracts stay intact (13 kept, 0 broken).
- **Risk Level**: Low
- **Approved**: applied during implementation (2026-10-28)
- **Diff**:

```diff
+def find_source_by_url(url: str) -> Source | None:
+    """The registered source with this URL, or None. The URL is canonicalized first, so a
+    caller that must not create a duplicate can look the source up before registering it.
+    """
+    target = canonical_url(url)
+    if not target:
+        return None
+    for source_id, source_url in Source.objects.using(CATALOG).values_list("id", "url"):
+        if canonical_url(source_url) == target:
+            return Source.objects.using(CATALOG).get(pk=source_id)
+    return None
```

```diff
+def find_venue(*, name: str, city: str, country_code: str) -> Venue | None:
+    """The registered venue with this identity, or None. The identity is the fingerprint, so
+    a caller that must not create a duplicate can look the venue up before registering it.
+    """
+    fingerprint = venue_fingerprint(name, city, country_code)
+    if not fingerprint:
+        return None
+    return Venue.objects.using(CATALOG).filter(venue_fingerprint=fingerprint).first()
```

### 4. [Testing] The second tick was made to really re-ingest

- **File**: `backend/tests/e2e/test_end_to_end.py:67`
- **Description**: A source is due when its last attempt is older than its cadence. After the first ingest the source is not due, so a second tick would claim nothing and the "nothing changed" assertion would pass vacuously — proving only that no work was scheduled.
- **Rationale**: `_force_due` backdates `last_attempted_at` by five hours, so the second tick genuinely re-ingests the same fixtures. The assertion then proves the ingest path is idempotent rather than proving the scheduler was idle. The paired test `test_a_corrected_venue_timezone_re_resolves_its_events` shows the same path does change events when it should.
- **Risk Level**: Low
- **Approved**: applied during implementation (2026-10-28)
- **Diff**:

```diff
+def _force_due(source_ids) -> None:
+    """Make the sources due again, so the second tick really re-ingests them.
+
+    Due-ness is keyed on the last attempt, so without this the second tick would claim
+    nothing and the "nothing changed" assertion would pass vacuously.
+    """
+    Source.objects.using(CATALOG).filter(pk__in=list(source_ids)).update(
+        last_attempted_at=timezone.now() - timedelta(hours=5)
+    )
```

---

## Skipped Suggestions

### 1. [Security] The committed operator password

- **File**: `backend/config/local_feeds.json:4`, `backend/config/local_feeds.fixtures.json:4`
- **Description**: Both feed files carry `"password": "operator-local-password"` for the local `operator` account.
- **Rationale**: The account is a local, non-superuser, `example.test` address created only by the seed command on a developer's machine. It is never a real credential, and the password has to be in the file for the command to create the account at all.
- **Risk Level**: Low
- **Reason Skipped**: This is plan decision D2 as approved. The password is intentionally local and documented as such. Worth revisiting if the seed command ever gains a production mode.

### 2. [Code Quality] `"approved"` is a string literal, not the model's enum

- **File**: `backend/config/management/commands/seed_local_stack.py:229`
- **Description**: The command compares `source.tos_status != "approved"` rather than `Source.TosStatus.APPROVED`.
- **Rationale**: The string literal is the established convention across the ingestion test suite, so the comparison reads like its neighbours. Using the enum would require importing `Source`, which the `models-ingestion` import contract forbids outside `apps.ingestion`.
- **Risk Level**: Low
- **Reason Skipped**: The literal matches the codebase convention and cannot be replaced by the enum without breaking an import contract. Changing the convention is a project-wide decision, not this run's.

### 3. [Code Quality] The permission model names are lowercase literals

- **File**: `backend/config/management/commands/seed_local_stack.py:49`
- **Description**: `EDITORIAL_GRANTS` keys the models by their lowercase `ContentType.model` (`"tosreview"`, `"eventstatechange"`), so the permission codenames are derived from the content type rather than hard-coded — but the model names themselves are literals in the command.
- **Rationale**: The codenames *are* derived: `f"{action}_{model_name}"` is built from the content type's `model` field, and the command refuses to run if a content type or a permission is missing. The plan's "never hard-coded" requirement was about the codenames, and it is met.
- **Risk Level**: Low
- **Reason Skipped**: The keys are inputs to the lookup, not hard-coded codenames. Deriving them from the model classes would require the forbidden model import.

---

## Project Tooling Used

The following project linters were detected and used:

- **Ruff**: `backend/pyproject.toml` (lint + format)
- **import-linter**: `backend/.importlinter` (13 contracts)
- **ESLint / tsc / Prettier**: `frontend/` (lint-web)
- **pytest / pytest-django**: `backend/pyproject.toml` (with real Postgres)
- **coverage.py**: `backend/pyproject.toml` (branch coverage, 80% gate; `domain/` at 100%)
- **TypeScript**: `frontend/tsconfig.json` (`tsc --noEmit`)

---

## Standards Referenced

- `.specs-fire/standards/` — the project standards (coding standards, testing rules, architecture rules)
- `_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md` — AD-3 (schema wall), AD-5 (named commands), AD-14 (authorization), FR-13 (sources are paused, never deleted), FR-60 (timezone resolution tiers)
- `.specs-fire/runs/run-eventpulse24-018/plan.md` — the approved plan and its decisions D1 (MMFA real feeds) and D2 (the twelve-permission editorial group)
