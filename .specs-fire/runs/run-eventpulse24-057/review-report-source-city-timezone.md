---
run: run-eventpulse24-057
work_item: source-city-timezone
intent: city-picker-and-auto-collection
generated: 2026-11-20
status: complete
---

# Code Review: A source carries its city's timezone

## Files Reviewed

| File | Change |
|------|--------|
| `backend/shared/constants.py` | +1 constant, +5 comment lines |
| `backend/domain/timezones.py` | +1 keyword arg, +1 branch (6 lines), +2 docstring passages |
| `backend/apps/ingestion/models.py` | +1 field, +6 comment lines |
| `backend/apps/ingestion/services/source_registry.py` | +1 cleaner, +2 tuple/map entries, +1 kwarg |
| `backend/apps/ingestion/services/ingest_item.py` | +1 hash input, +1 call-site kwarg |
| `backend/apps/ingestion/admin.py` | +1 fieldset entry, +1 help text (from finding 1) |
| `backend/apps/ingestion/migrations/0014_source_city_tz.py` | New — one `AddField` |
| 5 test files | +35 tests |

## Project Tooling

| Tool | Result |
|------|--------|
| `ruff check .` | All checks passed |
| `ruff format --check .` | Every file this run touched is clean. One file reports unformatted — `tests/shared/test_retention_published.py`, pre-existing drift on this branch, untouched here |
| `lint-imports` | 21 contracts kept, 0 broken |
| `manage.py check` | No issues (3 silenced) |
| `makemigrations --check --dry-run` | No changes detected |
| `pytest` (full) | 7755 passed, 0 failed |
| Coverage gates | `domain/` 100%, overall 97.42% |

## Findings

### 1. [Architecture] `city_tz` was editable by the service but unreachable in the admin — FIXED

**File**: `apps/ingestion/admin.py:284`

`SourceForm.Meta.fields = list(EDITABLE_SOURCE_FIELDS)`, so adding `city_tz` to that tuple
put it on the form — but `SourceAdmin.fieldsets` lists fields by hand, and Django builds
the admin form from `flatten_fieldsets(fieldsets)`. A field missing from the fieldsets is
silently dropped: no error, no system check, nothing in the test suite. `city_tz` would
have been the only member of `EDITABLE_SOURCE_FIELDS` not reachable by an editor.

It matters because the admin is the **only** human path to `update_source`. Provisioning
sets the field programmatically, but correcting a wrong zone — or adding one to a source
that predates provisioning — would have needed a shell.

Put to the user, who chose to expose it. Added to the first fieldset beside `city`, with a
help text in the house style (`VenueAdmin` already does this for `tz`) that says what the
field is for, that leaving it empty means such times are rejected rather than guessed, and
that a registered venue's zone wins over it.

Three tests came with it, including
`test_every_editable_source_field_is_reachable_in_the_admin`, which asserts
`set(EDITABLE_SOURCE_FIELDS) <= flatten_fieldsets(SourceAdmin.fieldsets)` — the missing
invariant, so the next field added cannot slip the same way. Verified all three fail when
the fieldset entry is removed.

**Risk**: low. One tuple entry and a help string; validation was already wired, since
`SourceForm.clean()` routes through `check_source_change` and therefore the same `_city_tz`
cleaner. A test asserts a bad zone lands as a field error rather than a 500.

### 2. [Documentation] A comment in the test suite became false — FIXED

**File**: `tests/ingestion/test_ingest_tz.py:69`

`test_confidence_of_exactly_0_90_publishes_unflagged` opened with "No resolve_tz row scores
0.90 (plan P2), so the resolution is adjusted on its way in." The `C1b` row now scores
exactly 0.90, so that premise is gone.

The test is unchanged and still earns its place — it pins the *gate boundary* independently
of which row happens to sit on it, which matters precisely because AD-8 calls these scores
tuning anchors rather than truths. Only the comment changed, to say that instead.

## Deliberately Not Changed

- **`canonical_zone(city_tz)` is computed on every call**, including the overwhelming
  majority where a source zone or venue decides and the value is never read. It matches
  what the line above it already does for `source_zone`, and `ZoneInfo` caches, so moving
  it inside the branch would buy nothing and make the chain read less uniformly.
- **An invalid `city_tz` is ignored, not raised.** Asymmetric with `venue_tz`, on purpose,
  and the asymmetry is now stated in `resolve_tz`'s docstring rather than left to be
  discovered. The registry guarantees a venue's zone, so a bad one there is a broken
  invariant worth stopping for; a bad `city_tz` should cost one city its date-only events,
  not raise inside the ingest loop and take the rest of the run's candidates with it.
  Both behaviours have a test.
- **Row code `C1b` rather than renumbering `C2`.** The codes are never persisted — only
  `TzRejection.reason` reaches a record, and the rejection path emits no row code — so
  renumbering would have been safe. It would also have made run-011's FR-60 table and a
  test id disagree with the code for no gain.
- **`tz_coverage` and `city_tz` stay unrelated.** One describes the feed, the other the
  city. The Dhaka seed is honestly `tz_coverage="none"` with a real city zone, and there is
  a test saying both can be true at once.
- **`ExtractedRecord` does not store the resolution's row code.** `TzResolution.reason` is
  documented "for audit and review" but no caller persists it today, so a city-zone
  resolution is distinguishable by its confidence (0.90, unique among the scores) rather
  than by a stored label. Adding that column is a change to the record model with its own
  migration and its own review, not a rider on this item.

## Security

Nothing applicable. The new field is an IANA zone name, validated against a fixed set by
`canonical_zone` before storage, never interpolated into a query, a URL or a template. It
reaches `ZoneInfo`, which rejects anything outside the system's zone database. AD-13 is not
engaged: a `Source`'s city is already written into `register_source`'s audit `details` —
it is editorial data about a public feed, not location data about a person. The brief's
AD-13 line is about `DigestPreference.city`, which this item does not touch.

## Architecture

Clean. The decision lives in `domain.timezones` and `apps.ingestion` only passes a value
through, which is why the whole FR-60 behaviour is tested without a database. D5 holds —
`_venue_for` is untouched and a test asserts no `Venue` is created on the new path. AD-16
holds — `ingestion` remains the sole writer of `Source`. The precedence the AC asked for is
enforced by the shape of the existing `if/elif` chain rather than by a rule someone has to
remember, which is the structural reason it cannot regress quietly.

The migration is a single additive `AddField` with a blank default: applied, reversed to
`0013`, re-applied.

## Summary

| | Count |
|---|---|
| Fixed | 2 (admin exposure + its missing invariant; one false comment) |
| Pending suggestions | 0 |
| Skipped | 0 |

Both fixes applied, the full suite re-run, and both verified to fail without them.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-057*
