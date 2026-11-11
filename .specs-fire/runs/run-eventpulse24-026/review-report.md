# Code Review Report

**Run**: run-eventpulse24-026
**Intent**: trust-loop
**Work item**: review-queue-model
**Reviewed**: 2026-11-10T14:40:00Z
**Files Reviewed**: 13

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 2 | 0 | 0 |
| Security | 0 | 1 | 0 |
| Architecture | 0 | 0 | 0 |
| Testing | 0 | 1 | 0 |
| **Total** | **2** | **2** | **0** |

**Tests Status**: Passing (306 targeted). The full suite's 16 failures existed before this item and are unrelated (see `test-report.md`).

---

## Files Reviewed

- `backend/apps/ingestion/models.py` (modified)
- `backend/apps/ingestion/migrations/0008_reviewitem.py` (created)
- `backend/apps/ingestion/services/review_queue.py` (created)
- `backend/shared/constants.py` (modified)
- `backend/config/management/commands/seed_local_stack.py` (modified)
- `backend/tests/ingestion/factories.py` (modified)
- `backend/tests/ingestion/test_review_item_model.py` (created)
- `backend/tests/ingestion/test_review_queue.py` (created)
- `backend/tests/ingestion/test_review_queue_concurrency.py` (created)
- `backend/tests/e2e/test_end_to_end.py` (modified)
- `backend/tests/ingestion/test_models.py` (modified)
- `backend/tests/wall/test_schema_placement.py` (modified)
- `backend/tests/architecture/test_write_ownership.py` (modified)

---

## Auto-Fixed Issues

### 1. [Code Quality] Import order in the generated migration

- **File**: `backend/apps/ingestion/migrations/0008_reviewitem.py:3`
- **Description**: ruff I001. Django's generator put `shared.ids` among the third-party imports. Fixed by `ruff check --fix`.

### 2. [Code Quality] Line too long, plus formatting

- **File**: `backend/apps/ingestion/services/review_queue.py:79`
- **Description**: E501 (103 > 100) on the `RuntimeError` line with its `pragma`. The call was wrapped, and `ruff format` was applied to three new files. No semantic change; tests re-run green.

---

## Applied Suggestions

### 1. [Security] Enforce D4 instead of trusting the caller

- **File**: `backend/apps/ingestion/services/review_queue.py` (`raise_review_item`)
- **Description**: The command refuses `reason=user_reported` from any non-system actor, with a `ValueError`. That's a programming error, so it isn't mapped to HTTP.
- **Rationale**: The audit row lives in `catalog`, and the editorial group holds `view_ingestionauditentry`. A future caller passing `Actor.user(reporter)` would silently show editors who reported what. The design relied on the caller remembering this, and a guard is cheaper than that trust.
- **Risk Level**: Low. There are no callers yet. Non-report reasons are unaffected, and a test covers an editor raising `in_review`.
- **Approved**: 2026-11-10 ("go")
- **Tests**: `test_a_report_raised_as_the_reporter_is_refused_and_writes_nothing` and `test_an_editor_may_raise_a_non_report_item`. Probe: with the guard disabled, the first fails.

### 2. [Testing] Pin `REPORT_FIELDS` to `ReportCategory`

- **File**: `backend/tests/ingestion/test_review_item_model.py`
- **Description**: Asserts that every category has exactly one `reports_*` column and vice versa.
- **Rationale**: A fifth category added without a column would otherwise surface as a `KeyError` inside a live bump.
- **Risk Level**: None (test only).
- **Approved**: 2026-11-10 ("go")

---

## Skipped Suggestions

No suggestions were skipped.

**Considered and not raised:**
- `Event` gaining a 14th `PROTECT` foreign key could block a future retention sweep. There is no catalog sweep yet, and the other 13 foreign keys raise the same question, so it is not specific to this item.
- `withdrawn`'s system label is checked as non-empty, not against `SYSTEM_LABEL`'s regex. `Actor` enforces the regex in Python, and every writer goes through a command.

---

## Project Tooling Used

- **ruff** (lint and format): `backend/pyproject.toml`
- **import-linter** (19 contracts kept): `backend/pyproject.toml`
- **Django system checks** (E001–E005) and `makemigrations --check`

---

## Standards Referenced

- `.specs-fire/standards/constitution.md`
- `.specs-fire/standards/coding-standards.md`
- `.specs-fire/standards/testing-standards.md`

---

## Work Item: event-rejection-state

Reviewed: 7 files created, 7 modified. Standards applied: root scope (the only other
`.specs-fire/standards/` on disk is inside a detached `.puku-cli` worktree and governs
nothing under `backend/`).

### Auto-fixed (mechanical)

| # | Finding | Fix |
|---|---|---|
| A1 | `F401` — `Event` imported but unused in `test_propagation_rejection.py` | Removed |
| A2 | Two files not `ruff format` clean | Formatted |

### Applied after review (semantic, low risk, re-verified)

| # | Finding | Severity | Fix |
|---|---|---|---|
| **R1** | **`_load` read the Event without a row lock.** The next version is computed in Python (`event.event_version + 1`), so two editors rejecting the same event in the same moment would both read N and both write N+1. The trigger would not catch it — `rejected → rejected` is not a boundary crossing and `N+1 ∈ (N, N+1)` holds — so the collision would surface as a `state_change_version_uq` IntegrityError: a raw database error where the obvious behaviour is "the second editor sees it is already rejected". | Medium | Added `select_for_update()`, matching `review_queue.py:162`. The second editor now waits, sees `rejected`, and takes the idempotent `applied=False` path. |
| R2 | `event_id` untyped on both commands and on `_load` | Low | Annotated `UUID` |
| R3 | `UNNOTIFIED_KINDS` is the documented reason for the notice suppression but was absent from `domain/notices.__all__` | Low | Added |
| R4 | Needless forward-ref quotes on `stored: "Event | None"` — `Event` is imported above the dataclass | Low | Unquoted |

All tests and all 11 mutation probes re-run after these: **76 passed, 11/11 probes caught.**

### Reviewed and deliberately left alone

- **`apply_publication_change` trusts the caller's in-memory `event.event_version`.** Using
  `F("event_version") + 1` would be race-proof, but then the function could not know the
  version to stamp on the `EventStateChange`, and the change row's version is the spine of
  AD-17's whole gating story. The `0009` trigger converts a stale read into a loud refusal
  rather than a silent wrong version, and R1 removes the realistic way to get one.
- **`reject_event` does not close the event's `ReviewItem`s.** Correct per the design's
  scope line: one editorial verdict closes *every* open item on the event
  (`review-queue-model` D2), and that belongs to `editorial-review-commands`, which depends
  on this item. Splitting it here would give the verdict two owners.
- **A rejected event keeps its `EventFit` row.** Nothing in this design deletes anything,
  and the read's own filter is what hides it — which is also what makes a reinstatement
  work with no backfill. Pinned by `test_a_rejected_event_is_absent_from_the_event_fit_preview`.
- **`relisted → REMINT` re-creates reminders with no email.** Symmetric with the silent
  cancellation the user chose; `mint_for_plan` already declines a slot whose instant has
  passed, so a long-rejected event reinstated after its start mints nothing.

### Architecture compliance

| Rule | Status |
|---|---|
| AD-3 schema wall — no transaction spans `catalog` and `personal` | ✅ The command is `atomic(using=CATALOG)` only; the personal side is reached through the outbox |
| AD-4 — `ingestion` is the sole writer of catalog entities | ✅ `editorial_state` lives in `apps/ingestion/services/` |
| AD-5 — every write is a named command with an audit entry in the same transaction | ✅ `event.rejected` / `event.reinstated` |
| AD-14 — every editorial action is attributed | ✅ User actor required; system actor refused; probe 10 |
| AD-15 — retention declared | ✅ No new model |
| AD-16 — one owning app per entity | ✅ No new entity |
| AD-17 — lifecycle changes bump the version and ride the existing outbox | ✅ No second fan-out was built |
| `domain-pure` | ✅ `UNNOTIFIED_KINDS` is a frozenset of string literals; `domain` imports no app |
| `import-linter` | ✅ 19 contracts kept, 0 broken |
| Never delete | ✅ Asserted in two suites |

### Carried forward (not this item's scope)

1. **16 pre-existing test failures**, verified identical at clean `HEAD`. The fixture feeds'
   event dates have been overtaken by the wall clock, so catalog reads bounded by "has not
   started yet" return nothing and the saves 404. This will worsen with time and should get
   its own work item.
2. **The local `.env` was missing three keys** (`REVALIDATION_SECRET`,
   `FRONTEND_REVALIDATION_URL`, `PUBLIC_SITE_URL`) that `.env.example` has, which blocked
   the whole suite from importing. Added from `.env.example`; backup at `.env.bak-before-fire-026`.
3. **The PRD amendment for FR-57** ("Reject (deletes from registry)") is still owed.
4. **The AD-17/AD-21 reinstated-conflict defect** remains open. This design routes around it
   by never closing pairs; it does not fix it.

---

## Work Item: reliability-score-domain

Reviewed: 2 files created, 3 modified. Pure `domain/` code — the narrowest surface in the
run, and the one with the strictest gate (100% coverage).

### Auto-fixed (mechanical)

| # | Finding | Fix |
|---|---|---|
| A1 | `E501` — the `ranking.py` table row exceeded 100 chars after the docstring edit | Shortened |
| A2 | `ruff format` on the new module and test | Formatted |

### Found during authoring, fixed before the suite was green

| # | Finding | Fix |
|---|---|---|
| B1 | `zip(scores, scores[1:], strict=True)` in the two monotonicity properties — the slices differ in length by one, so `strict=True` raised rather than compared | `zip(scores[:-1], scores[1:], strict=True)`. Worth recording: `strict=True` is the right default and it caught a real mistake in the test rather than hiding it |

### Reviewed and deliberately left alone

- **`posterior_mean` is exported as well as `reliability_score`.** Slightly redundant, but
  the recompute job records the unclamped value and the floor is only legible beside the
  number it is holding up. Both have tests that show the difference at n = 29.
- **`reliability_score` has no `observations` parameter**, taking `positives` and `negatives`
  and summing them. One source of truth for n, and it makes the FR-25 seam free: dismissals
  become more negatives with no signature change.
- **`weekly_negative_rate` raises when `negatives > observations`.** It is not in the AC, but
  a caller that passes them the wrong way round would otherwise get a plausible rate above
  the real one. This is the same reasoning as refusing `bool`: the dangerous input is the one
  that returns a believable number.
- **`checked_rate` duplicates `checked_confidence` rather than importing it.** They are the
  same validation today, but they answer different questions — "is this a confidence score"
  and "is this a rate" — and FR-16's four-confidences rule says these vocabularies must not
  be conflated. Sharing the function would be the first step to sharing a constant.

### Architecture compliance

| Rule | Status |
|---|---|
| `domain-pure` — stdlib + `shared.constants` / `shared.ids` only | ✅ Imports `decimal` and `shared.constants`; no Django |
| AD-8 / AD-16 — thresholds live once, in `shared/` | ✅ All six constants there, pinned by tests |
| "Four confidences, never conflated" (intent constraint) | ✅ `RELIABILITY_*` shares no constant with `EXTRACTION_CONFIDENCE_*` or `TZ_INFERENCE_CONFIDENCE_*`; recorded in the constants block |
| AD-15 retention | ✅ No model |
| `import-linter` | ✅ 19 contracts kept, 0 broken |
| No faked inputs (the `ranking.py` precedent) | ✅ FR-25's dismissal rate is a documented seam, not a placeholder term |

### Two PRD amendments now owed by this work item

Both were confirmed with the user before implementation, and both are departures from the
PRD's literal text rather than interpretations of silence:

1. **FR-16 min-N:** "a source needs at least 30 dismissal observations before its score
   moves" → "**before its score moves freely**". Without this the 0.32 floor in the same
   requirement is unreachable.
2. **FR-16 spike detection:** "a 3× week-over-week drop in reliability score" → "a **3×
   week-over-week rise in the smoothed rate of negative observations**". The score version
   provably cannot fire: the floor caps the ratio at 1.56 below 30 observations, and above
   30 the `<0.3` escalation has already triggered.

These join the FR-57 amendment owed by `event-rejection-state`. **Three PRD amendments are
now outstanding for this intent.**

---

## Work Item: review-intake-and-backfill

Reviewed: 4 files created, 2 modified (one of them a rename).

### Auto-fixed (mechanical)

| # | Finding | Fix |
|---|---|---|
| A1 | `E501` in the `review_intake` module docstring | Rewrapped |
| A2 | Import ordering in `ingest_item.py` after the new import | `ruff --fix` |
| A3 | One file not `ruff format` clean after the probe edits | Formatted, then **all 16 probes re-verified** (a format pass can invalidate a probe's exact-match pattern) |

### Found during implementation — a plan correction worth recording

**The plan's test for "same transaction" would not have proved it.** The plan said to test
the invariant by rolling back; writing it exposed that a raise deferred to
`transaction.on_commit` *also* leaves no item after a rollback, so that test would pass
against the bug it was meant to catch.

The invariant was inverted instead: **if the raise fails, the Event must not exist either.**
That is true only when the two share a transaction. Probe 13 plants the realistic version of
the bug — wrapping the raise in `try/except` so it becomes best-effort — and the test catches
it. This is a strengthening of the plan, not a deviation from its intent.

### Reviewed and deliberately left alone

- **`sync_review_item` is called at four sites rather than once centrally.** A single call at
  the end of `_resolve_and_write` would miss the early returns (`new`, `superseded`,
  `bound_other_source`), and each of those needs different handling. Four calls beside the
  four existing `_write_fit` calls keeps the two "after the event's own write" concerns
  visibly parallel.
- **`event.refresh_from_db` before the update-path sync.** `apply_lifecycle_change` and
  `apply_silent_update` write through `F()` expressions and a filtered `UPDATE`, so the
  in-memory instance still carries the old `publication_status`. Without the refresh the sync
  would decide on a stale gate — the same class of bug `_write_fit` documents at
  `ingest_item.py` and solves by re-reading.
- **`withdraw_review_item` filters on `status='open'` inside the `UPDATE`** rather than
  reading then saving. Two concurrent withdrawals would otherwise both read an open row and
  the loser would hit `guard_review_item`'s "a resolved ReviewItem is immutable". The filter
  makes the loser a no-op returning 0.
- **The backfill query lives in the service, not the command.** `apps.ingestion.models` is
  importable only from `apps.ingestion` (AD-2) — the same reason `backfill_event_fit` states
  in its own docstring.
- **Superseded events are excluded from the backfill.** Terminal under AD-4; a ticket would
  be work no editor can do.

### Architecture compliance

| Rule | Status |
|---|---|
| AD-2 layering — `config` holds no model query | ✅ Query in `review_intake`, command calls it |
| AD-3 — one schema per transaction | ✅ `atomic(using=CATALOG)` only |
| AD-5 — named command + audit in the same transaction | ✅ `review_item_withdrawn`; the raise audits inside `raise_review_item` |
| AD-14 — editorial actions attributed to a person | ✅ Withdrawal is a **system** close and cannot masquerade as a verdict; `ReviewItem`'s D6 check enforces it at the database |
| AD-16 — one writer | ✅ `ingestion` only |
| `import-linter` | ✅ 19 kept, 0 broken |
| No migration | ✅ `withdrawn` was provisioned by `review-queue-model` D5 for exactly this |

### Carried forward

1. **The rejection gap**, now pinned by a test rather than only a comment:
   `reject_event` does not close review items, so a rejected `in_review` event keeps an open
   one until `editorial-review-commands` lands. That test is written to be **changed** by
   that work item, and says so.
2. The **three PRD amendments** remain outstanding (FR-57, and FR-16 twice).
3. The **16 pre-existing failures** are unchanged.

---

## Work Item: event-report-api

Reviewed: 4 files created, 9 modified (including the two generated client files).

### Auto-fixed (mechanical)

| # | Finding | Fix |
|---|---|---|
| A1 | Import ordering in three modules after the new imports | `ruff --fix` |
| A2 | Three files not `ruff format` clean | Formatted, then **all 21 probes re-verified** |

### Found during implementation and corrected

| # | Finding | Severity | Fix |
|---|---|---|---|
| **B1** | **I had written a bespoke `ReportThrottled` exception and caught it in the endpoint to build a 429 by hand.** `domain/errors.py` already has `ThrottledError` and `config/errors.py` already maps it to 429 with the shared `{code, message}` body. A second mapping would have been free to drift from the first. | Medium | Use `ThrottledError`; the endpoint catches nothing. `EventNotFoundError` is likewise already mapped to 404, so the handler is now four lines with no `try` at all |
| B2 | The endpoint returned `201, body` as a bare tuple, which Ninja deprecates (16 warnings) | Low | `Status(201, ...)`, matching the five existing uses in this module |
| B3 | The throttle fixture reached for a `reset()` the in-memory adapter does not have, so the limit never tripped and two tests passed vacuously | Medium | Inject a fresh `InMemoryThrottleAdapter` with a controlled clock at the calling module, the way `test_preview_api` does |

**B3 is the one worth dwelling on:** the tests were *green* with a throttle that never counted.
Probe 18 now fails if the throttle is bypassed, so the suite can no longer be satisfied by a
limit that does not exist.

### Reviewed and deliberately left alone

- **`raise_user_report` fixes the actor rather than taking it.** Making it a parameter would
  turn AD-3's identity leak into a one-line mistake at any future call site. Probe 17 plants
  exactly that mistake.
- **The throttle is checked before the idempotence shortcut.** A client hammering one report
  still spends attempts; a limit a repeat can slip past is not a limit (probe 18).
- **A report whose event has since been deleted is stamped, not retried.** There is nothing
  to review and nothing a retry would fix, so it leaves the reconciler's queue instead of
  looping forever — the same reasoning `propagate_state_change` uses for a missing change.
- **`EventReport` has no FK to the user either**, just a `UUIDField`, matching `SavedEvent`
  and every other row in `personal`.
- **The category `Literal` on the wire** means an invalid value is a 422 from the parser
  before any service sees it, so the service never has to validate what the schema already
  guarantees.

### Architecture compliance

| Rule | Status |
|---|---|
| **AD-3 — no user identity crosses the wall** | ✅ Asserted over every column of the `ReviewItem` **and** its catalog audit row |
| AD-3 — no FK across schemas, no transaction spanning both | ✅ `event_id` by value; the hop is an outbox |
| AD-5 — named command with an audit row | ✅ Inside `raise_review_item` |
| **AD-16 — every table has one owning app** | ✅ `TABLE_OWNERS` extended; the test caught the omission |
| AD-15 — retention declared | ✅ `ACCOUNT_CONTENT`; `manage.py check` green |
| **AD-19 — the OpenAPI schema is the contract** | ✅ `make client`; regeneration proven idempotent |
| AD-7 — the tick is the only beat entry | ✅ The reconciler hangs off the existing 5-minute branch; `test_tick` extended |
| `import-linter` | ✅ 19 kept, 0 broken |

### Carried forward

1. The **three PRD amendments** remain owed.
2. The **16 pre-existing failures** are unchanged.
3. **FR-16's "upheld report" is still undefined.** This item stores what that definition will
   need — the per-report `(user, event, category, created_at)` and the anonymous per-category
   tally — but `reliability-recompute-and-escalation` must decide what counts as upheld.
4. **No frontend surface yet.** The endpoint exists and the generated client knows it;
   `frontend-report-control` builds the Detail Screen's flag action against it.

---

## Work Item: editorial-review-commands

Reviewed: 4 files created, 7 modified.

### Auto-fixed (mechanical)

| # | Finding | Fix |
|---|---|---|
| A1 | Import ordering and two long lines | `ruff --fix` |
| A2 | Three files not `ruff format` clean | Formatted; **all 27 probes re-verified** |

### Found during implementation and corrected

| # | Finding | Severity | Fix |
|---|---|---|---|
| **B1** | **`select_for_update()` with `select_related("event", "source")` is invalid here.** Both FKs are nullable, so Django builds a LEFT OUTER JOIN and Postgres refuses: *"FOR UPDATE cannot be applied to the nullable side of an outer join"*. Every command failed. | High | `select_for_update(of=("self",))` — which is also the correct *intent*: the item is the row two editors race for, and the event is locked separately |
| **B2** | **A venue edit silently did nothing.** `EventFacts` carries `venue_fingerprint`, not `venue_id`, so `classify_change` compared two identical hashes, found no change, fell through to the silent path — and the silent path does not write `venue_id`. The edit was accepted, reported success, and moved nothing. | High | `_incoming_for` loads the new Venue and carries its fingerprint, which also makes the edit a `detail_changed` and produces FR-54's third subject ("moved to [new location]") for saved users. Probe 26 plants the original bug |

**B2 is the kind of bug that ships.** No exception, no failing assertion in the obvious test,
a success response, and an editor who believes they fixed the venue. It was caught only
because the test asserted the *outcome* (`event.venue_id == venue.id`) rather than that the
call returned without raising.

### Reviewed and deliberately left alone

- **An edit to a lifecycle field's current value still closes the item as `edited`.** The
  editor looked and decided; that decision is a fact about the source whether or not the
  facts turned out to need changing. The version correctly does not bump.
- **`_close_open_items` uses a filtered `UPDATE`,** not read-then-save, for the same reason
  `withdraw_review_item` does: the loser of a race becomes a no-op rather than hitting
  `guard_review_item`'s immutability error.
- **`EDITABLE_FIELDS` excludes the slug, the source, `source_event_id`, the confidences and
  `publication_status`.** The module docstring says why for each; the absences are the
  content of the list.
- **`dismiss_source_item` writes no `Source` column at all.** FR-16's "escalation, never
  removal" is asserted by comparing every column before and after rather than by trusting
  that no line writes one.

### Architecture compliance

| Rule | Status |
|---|---|
| **AD-14 — `editorial` gets no privileged write path** | ✅ All four commands are `ingestion` services; the admin will call them |
| AD-14 — every editorial action attributed | ✅ User actor required (probe 24); `ActorColumns` on the observation; audit row per command |
| AD-17 — an editorial lifecycle edit is indistinguishable downstream | ✅ Goes through `apply_lifecycle_change` itself |
| AD-4 — identity is not editable | ✅ `source` and `source_event_id` are not in `EDITABLE_FIELDS` |
| AD-3 / AD-15 / AD-16 | ✅ All four inventory tests extended |
| `import-linter` | ✅ 19 kept, 0 broken |

### Gaps closed by this item

1. **`reject_event` now has its verdict-recorder.** `test_rejecting_an_in_review_event_leaves_its_item_open`
   was written in `review-intake-and-backfill` to be changed by this work item, and it has
   been — it now asserts the item closes `rejected` with the editor's id. A second test pins
   the other half: `reject_event` called *directly* still leaves the queue alone, so the
   split stays a design rather than a coincidence.
2. **One verdict closes every open item** (`review-queue-model` D2's integration requirement).

### Carried forward

1. The **three PRD amendments** remain owed.
2. The **16 pre-existing failures** are unchanged.
3. **`SourceObservation` has no consumer yet.** `reliability-recompute-and-escalation` reads
   it, and must still decide **what an edit is worth** — the one FR-16 input the brief does
   not assign a sign to. That deferral is recorded in this item's design and in the model's
   own docstring, where the next reader will meet it.

---

## Work Item: editorial-admin-queue

Reviewed: 4 files created, 4 modified. Reviewed by an independent agent against the
project's ADRs, then every finding verified against the running code.

**The headline: two CRITICAL findings, both confirmed by execution, both now fixed.**
Neither was found by reading the code. Both were found by a test that rendered the page
and looked at it.

### CRITICAL — a read-only viewer could approve, reject, dismiss and edit-and-publish

**Found by:** the independent review, then reproduced here.
**Severity:** CRITICAL (security)

`may_review` was the single gate for *both* reading and working the queue:

```python
REVIEW_PERMISSIONS = ("ingestion.change_reviewitem", "ingestion.view_reviewitem")
return any(user.has_perm(codename) for codename in REVIEW_PERMISSIONS)
```

`any` over both permissions meant a user holding **only** `view_reviewitem` satisfied
`may_review` — and the admin used that one function for `has_view_permission` *and*
`has_change_permission`. So a read-only auditor could publish quarantined events, hide
listings and rewrite event facts, with no more authority than they were given to read.

**The fix** splits the rule, and the split is the point:

| Predicate | Requires | Used for |
|---|---|---|
| `may_view` | `view_reviewitem` (or `change_reviewitem`) | `has_view_permission` — reading the queue |
| `may_review` | `change_reviewitem` **only** | `has_change_permission` — the verdicts and the edit |

**The second half of the fix matters as much as the first.** Django's
`@admin.action(permissions=["change"])` is *advisory*: it filters the action out of the
dropdown, but the changelist's own gate is `has_view_or_change_permission` — which a
read-only viewer satisfies — and `response_action` resolves the action **by name** from
the POST without a second permission check. The decorator alone would not have stopped
the attack. The enforcing check now lives in `_verdict`, the one helper all three actions
share, so all three obey one rule and a fourth action cannot forget it.

**Six regression tests** pin it: a view-only user may read the queue, may not approve,
reject, dismiss or edit, is offered no verdict actions in the dropdown, and leaves no
audit row behind.

### CRITICAL — the staleness lock was absent in production, and every test passed anyway

**Found by:** the independent review, then reproduced here.
**Severity:** CRITICAL (correctness)

The edit form declared `expected_event_version` as a field but named it in **no
fieldset** — and Django's admin only renders fields that appear in a fieldset. The
rendered page therefore contained no `name="expected_event_version"` input at all.

The field was also `required=False`, so a real browser posted no token, and both the
form's `clean()` and the command's own check short-circuited on
`if expected_event_version is not None`. **The optimistic lock was not running.** Two
editors racing, or an editor working from a page open for an hour, would silently
overwrite an ingestion update.

**The fix:** the field is in the "Correct the event" fieldset (a hidden input, so it
costs the editor nothing) and is `required=True` — **the check now fails closed**. A post
with no token is a refusal, not a write that skips the lock.

**Why every test passed anyway:** the tests hand-built the POST body and always included
the token. A test that posts what the code expects cannot catch a field the page never
rendered. The new tests read the **rendered page** instead:

- `test_the_change_page_carries_the_expected_event_version` — asserts the input is in the
  HTML with the right value. This one test would have caught the bug on its own.
- `test_the_edit_form_refuses_a_post_without_the_staleness_token` — asserts a tokenless
  post is refused and nothing is written.

### MEDIUM — findings fixed

| # | Finding | Fix |
|---|---|---|
| M1 | `change_view` computed `review_detail` and `editable_fields` into the context; **no template read either** — a whole extra query tree per page view for data nobody renders | The override is removed. The panels read the model directly |
| M2 | The admin's `order_by` and the read service's `_ordered` were **two implementations of one rule** — the exact drift the plan warned about | The read service's ordering is now public (`ordered`) and the admin **calls** it |
| M3 | The admin's `sla_breached` column **re-implemented** the SLA rule the read service uses for the summary's count. An item could be marked overdue on its row and missing from the total | `review_queue_read.item_is_past_its_sla` — one rule, called |
| M4 | The summary and the per-reason counts were read at **two different instants** — a queue that changed between them would show a summary of five beside counts of four | `now` is taken once in `changelist_view` and handed to both |

### LOW — findings fixed

| # | Finding | Fix |
|---|---|---|
| L1 | `get_queryset` relied on the db router rather than naming its database, while every other query in the module names it (AD-3) | `.using(CATALOG)` |
| L2 | A docstring claimed `seed_local_stack` grants the group "precisely these two permissions — no more". It grants **fourteen** | The claim is corrected; the group is wider than this queue, and the two permissions below are the ones it is gated on |
| L3 | `open_item_count_by_reason(now=...)` took a `now` it never used | The parameter is kept for shape consistency and its docstring says why it is unused |
| L4 | `list_review_items` and `queue_view` had no production caller | `queue_view` is the published editorial read model FR-29's dashboard will call, and it now has a test. `list_review_items` is the service behind it |

### Reviewed and deliberately left alone

- **A view-only user's action POST returns 200, not 403.** Django filters the action out
  of `get_actions`, so the POST is a no-op that re-renders the page. The security property
  that matters — *nothing was written, no audit row exists* — is what the test asserts.
  Forcing a 403 would mean overriding Django's action machinery for a cosmetic gain.
- **`get_review_item_detail` is still in the read service** even though the admin's
  panels read the model directly. It is the plain-data read FR-29's dashboard will call,
  and it is exported and documented as such.
- **`source_history` shows the observations, not a score.** FR-16's score does not exist
  yet; computing a live one here would be a second implementation of another work item's
  job. The label says so on the page.

### Categories with no findings

- **Direct writes in the admin (AD-5):** none. Every mutation goes through
  `apps/ingestion/services/editorial_review.py`. No `.save()`, `.update()`, `.delete()`
  or `.create()` on any model in admin code.
- **XSS / injection:** none. No `mark_safe`, `format_html` or `__html__` anywhere in the
  reviewed files. Django's `AdminReadonlyField.contents` ends in `conditional_escape`, so
  `event_facts`, `source_facts`, `source_history` and `report_tallies` are escaped even
  though they are built in Python from `event.title`, `source.name` and `source.url`.
- **AD-2 import contract:** intact. The `ModelAdmin` lives in `apps/ingestion/admin.py`;
  `apps/editorial/admin.py` is a pure re-export facade that imports no models.
  `lint-imports` reports 19 kept, 0 broken.
- **Tautological tests:** none. Every assertion can fail — and the two CRITICAL findings
  are the proof, since they survived a suite of 41 tests that all passed.

### Gates after the fixes

| Gate | Result |
|---|---|
| `pytest tests/editorial/` | ✅ **55 passed** (41 before the review, +14 regression tests) |
| `pytest` (full) | ✅ **16 failed** — all pre-existing at `HEAD` · 6050 passed |
| `ruff check` / `ruff format --check` | ✅ all checks passed · 571 files formatted |
| `lint-imports` | ✅ 19 kept, 0 broken |
| `manage.py check` / `makemigrations --check` | ✅ no issues / no changes detected |

### The lesson worth carrying

Two CRITICAL defects survived 41 passing tests. Both lived in the gap between *what the
code expects* and *what the browser sends*, and both were invisible to a test that
hand-builds a POST body.

**The tests that would have caught them are cheap:** read the rendered page and assert
the field is in it; and exercise the permission matrix with the *weakest* permission, not
just the group. Neither needs a new tool or a new framework — they need the test to look
at the surface the user actually gets, rather than at the surface the developer imagined.


---

## Work Item: reliability-recompute-and-escalation

*FR-16's second half: the score that remembers — history, weekly recompute, and escalation.*

**Reviewer:** a fresh agent with no context from the implementation, given the design doc,
the constitution (AD-2/3/5/8/14/15/16), the coding and testing standards, and the seven
files this work item touched.

### The headline

**Two CRITICAL defects survived 68 passing tests.** Both are about the *same* thing — the
claim — and both are the kind of defect a test that exercises the happy path cannot see.

The design doc promised: *"two overlapping ticks cannot recompute the same source twice —
which is what makes the job's idempotence requirement reachable at all."* The code did not
do that. The claim was a `SELECT ... FOR UPDATE SKIP LOCKED` that **wrote nothing**, and
the recompute ran in its *own* transaction — so the lock was released before the work it
was supposed to protect, and two ticks both got the same source.

**Both findings were verified empirically before being fixed**, not merely read:

```
SEPARATE TXN first claim:  [UUID('01a1c835-2e94-764c-99e5-138f0674e75d')]
SEPARATE TXN second claim: [UUID('01a1c835-2e94-764c-99e5-138f0674e75d')]   ← the same source
```

and the second CRITICAL finding, the write race:

```
COLLISION: duplicate key value violates unique constraint "source_reliability_score_period_uq"
```

### Findings and what was done about them

| # | Severity | Finding | Action |
|---|---|---|---|
| 1 | **CRITICAL** | The `SKIP LOCKED` claim **prevented nothing** — it released its lock with its transaction, before the recompute ran. Two overlapping ticks both claimed and both recomputed the same source. | **Fixed.** The claim is now **persisted** on `Source.reliability_claimed_at` — the same shape as `scheduling.claim_due_sources`'s `ingest_claimed_at`. The marker outlives the transaction that took it. A claim older than `RELIABILITY_CLAIM_TTL` is a lost job and is reclaimed. Migration `0012`. |
| 2 | **CRITICAL** | `_write_row` was a `SELECT`-then-`INSERT` **TOCTOU race**. Two concurrent runs both read "no row" and both inserted; the loser got an uncaught `IntegrityError` that failed the whole job. The docstring claimed `ON CONFLICT … DO UPDATE` — there was no `ON CONFLICT`. | **Fixed.** The write is now `get_or_create` under `select_for_update` inside the same transaction. The window between "is there a row?" and "write the row" is closed. |
| 3 | HIGH | **One failing source aborted the rest of the batch.** No `try/except` around `recompute_source`, so an exception skipped every remaining source for the week. The task's own docstring claimed otherwise. | **Fixed.** The batch catches per source and logs a warning, and **releases the failed source's claim** so it is retried on the next tick. Matches `schedule_sources`. |
| 4 | HIGH | **The observations were read outside the recompute's transaction**, so an observation committed between the read and the write was lost from the period's score. | **Fixed.** The read and the arithmetic moved inside the `atomic` block. |
| 5 | HIGH | `should_escalate` was given `counts.observations` (which **includes** dismissals) while `reliability_score` floors on `positives + negatives` (which **excludes** them). Two thresholds, two meanings of "30 observations". | **Fixed.** Both now use `counts.total`. The semantics are documented on the property, and a test asserts them. |
| 6 | MEDIUM | `RELIABILITY_PERIOD_DAYS` and `RELIABILITY_SCORE_MAX_AGE` were **dead constants** — zero uses, and the comment above them described a due-rule the code did not have. | **Fixed.** `RELIABILITY_SCORE_MAX_AGE` is **deleted** (the rule it promised is not the rule the AC asks for). `RELIABILITY_PERIOD_DAYS` is kept and now used. `RELIABILITY_CLAIM_TTL` and `RELIABILITY_BATCH_SIZE` were **added** — both are now used. |
| 7 | MEDIUM | The claim had **no batch limit** — it held a lock on every due source for the length of the batch, while every comparable batch job in the codebase is bounded. | **Fixed.** `RELIABILITY_BATCH_SIZE = 100`, mirroring `SCHEDULE_BATCH`. |
| 8 | MEDIUM | The admin said *"The reliability score is computed from these; it is not stored yet."* — but this work item **stores** it. | **Fixed.** The admin reads `Source.reliability_score` and shows it, with the prior and "not yet computed" when there is none. `review_queue_read`'s docstring was corrected too. |
| 9 | MEDIUM | **Dead code**: `ObservationCounts.total` was never called; `latest_score()` was exported with **zero callers and zero tests**; `_escalate()` took `score` and `spiked` parameters it never used. | **Fixed.** `total` is now used (finding 5). `latest_score()` is **deleted** — nothing called it. `_escalate`'s unused parameters are **removed**. |
| 10 | MEDIUM | `shared/constants.py` cited **the wrong design decision** — "D13" for the counting rule, which is D14. | **Fixed.** |
| 11 | LOW | `SourceReliabilityScore` was **not registered in the admin**. | **Fixed.** It is now a read-only `SourceReliabilityScoreAdmin` — the score is computed, never typed. |
| 12 | LOW | The new table had **no runtime-role grants**. The append-only standard is three layers: the Python guard, the trigger, *and* the privileges. | **Fixed.** Migration `0011` now carries the `REVOKE`/`GRANT` and the `DO` block that fails the migration if the privileges did not apply. Three tests assert them. |
| 13 | LOW | The design doc **contradicted itself** on the spike predecessor — D3 and the risk table said "the row for the previous ISO week", while the Technical Approach and the code computed the predecessor rate from *observations*. | **Fixed.** The risk row now matches the code. D3 was already right. |
| 14 | LOW | `domain/` coverage and the test gaps: `latest_score` untested (now deleted); **the concurrent recompute path untested** — the gap that hid findings 1 and 2; `weekly_counts` with an unknown kind untested; `counts.observations` vs `counts.total` untested; **the counting table's *values* untested** — a sign flip (`"rejected": 1`) would pass every test in the suite. | **Fixed.** New tests: the counting table's values, the `total` semantics, the concurrent write, the second claim, the released claim, the stale claim, the failed source's claim release, the batch isolation, and the three runtime-role privileges. |

### The tests the review added

**The counting table's values.** `test_the_counting_table_holds_the_signs_it_promises` asserts
`OBSERVATION_SIGNS == {"approved": 1, "rejected": -1, "edited": -1, "dismissed": 0}`. The
existing test only proved the table and the model agree on *which kinds exist* — every
other test in the suite *reads* the table to work out what to expect, so a flipped sign
would have passed all of them. A table that is the only source of truth needs a test that
pins the truth.

**The claim's three states.** `test_a_second_claim_does_not_return_a_claimed_source` is
the test the old claim failed. `test_a_released_claim_can_be_claimed_again` and
`test_a_stale_claim_is_reclaimed` pin the other two sides of the TTL rule.

**The batch's isolation.** `test_one_failing_source_does_not_lose_the_rest_of_the_batch`
and `test_a_failed_source_releases_its_claim`.

### The lesson worth carrying

**A lock is not a claim when the work happens in a different transaction.**

The design doc's D10 said the right thing — *"two overlapping ticks cannot recompute the
same source twice"* — and the code implemented something that **sounded** like it: a
`FOR UPDATE SKIP LOCKED` claim, the same words the scheduler's claim uses. But the
scheduler's claim is *also* persisted to a column, and the reliability claim was not. The
lock was released by the transaction that took it, and the recompute — the thing the lock
existed to protect — ran after that release.

**The gap was between two true-sounding claims.** The docstring said the lock "is what
stops two overlapping ticks"; the code review found that the lock was gone before the
work began. Nothing contradicted the other on the page.

The generalisable form: **when a lock is meant to protect work in another transaction, the
lock is not the mechanism — a persisted marker is.** The `scheduling` service already knew
this; the reliability service did not, and it was written by copying the *shape* of the
scheduling claim without its *substance*.

**And the test that would have caught it is one assertion:** claim twice, assert the second
claim returns nothing. It took a reviewer writing a throwaway script to find, because a
test that exercises the happy path once cannot see a claim that does not hold.

### Gates after the fixes

| Gate | Result |
|---|---|
| `pytest` (full suite) | ✅ **6140 passed, 16 failed** — the 16 verified as pre-existing by stashing the branch and re-running at HEAD |
| `pytest` (the four reliability files + the worker file + `tests/editorial/`) | ✅ **157 passed** (68 before the review, +16 new) |
| `ruff check` / `ruff format --check` | ✅ all checks passed · 578 files formatted |
| `lint-imports` | ✅ 19 kept, 0 broken |
| `manage.py check` / `makemigrations --check --dry-run` | ✅ no issues (3 silenced) / no changes detected |

### Areas checked and found CLEAN

- **AD-3 schema wall.** No `personal` reads anywhere in the new code. Every query passes
  `using=CATALOG`; every `transaction.atomic` passes `using=CATALOG`. The
  `raise_review_item(source=…)` path is catalog-only, and the report count is frozen from
  the closed item's own catalog columns — the report identity never crosses the wall.
- **AD-8 domain purity.** `domain/reliability.py` imports only `decimal` and
  `shared.constants`. No Django. `lint-imports` "AD-2 domain is pure" KEPT.
- **AD-5.** The recompute is a named command in `apps/ingestion/services/`, owns its
  validation, and writes its audit row inside the same transaction as the score row and
  the source's field.
- **AD-16.** `ingestion` owns `REVIEW_ITEM`; the escalation *calls* `raise_review_item`
  rather than reimplementing the queue's bump-not-duplicate rule.
- **The ISO-week boundary.** No off-by-one. Postgres's `date_trunc('week', …)` and the
  Python `weekday()` agree across a full year (2025-01-01 → 2026-12-31, 0 mismatches), so
  the service and the check constraint agree on where a week starts.
- **The Postgres trigger.** Correctly permits the four-column same-period refresh while
  refusing to move `source_id`, `period_start`, `id` or `created_at`; handles the
  retention purge flag; raises `restrict_violation`. No `SECURITY DEFINER` and no
  `search_path` — consistent with every other trigger in the project.
- **N+1.** No N+1 within a source; per-source queries are bounded and constant.
- **Tautological tests.** None. Every assertion can fail — and the two CRITICAL findings
  are the proof, since they survived 68 tests that all passed.

---

## Work Item: ranking-consumes-reliability

Reviewed: 3 files created, 8 modified. The gate for this item is the hardest in the run:
a **weight change** is a PRD amendment, so the review's first question was not "is the
code correct" but "**is the amendment real**" — whether the PRD, the ADR, the constants
and the pin tests actually agree.

### Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 1 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 0 | 2 | 0 |
| Testing | 0 | 2 | 0 |
| Documentation | 0 | 1 | 0 |
| **Total** | **1** | **5** | **0** |

**Tests Status**: Passing (6158 passed, 16 failed — the same 16, verified as pre-existing
at clean `HEAD` by stashing the branch and re-running).

---

### Auto-fixed (mechanical)

| # | Finding | Fix |
|---|---|---|
| A1 | `ruff format` reflowed two `offenders.append(...)` calls in the new AD-10 guard | `ruff format` applied; no semantic change |

---

### Applied after review (semantic)

#### R1 [Documentation] The ADR cited a PRD amendment that did not exist

- **File**: `docs/adr/ADR-0025.md:5`, `_bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md`
- **Severity**: Medium
- **Description**: The ADR's header read *"Amends: FR-22 (Confidence Pulse), via PRD
  Amendment A-10"*. **The PRD's highest amendment is A-9**, and A-10 is already spoken
  for in the UX lineage as the Browse-surface amendment. The number was invented to fill
  a slot — a dangling pointer in the one document FR-22 says users are shown.
- **Rationale**: FR-22's amendment policy has two halves: the weights are locked, **and**
  the amendment is tracked where a user can find it. An ADR citing a PRD amendment the PRD
  has never heard of satisfies neither half. The lock was already real (the pin test
  fails CI); the disclosure was not.
- **Fix**: The PRD's FR-22 section now carries an **`Amendment A-10 (2026-11-11)` block**,
  in the same shape as A-9's — recording that **the MVP weights are unchanged** and that
  what changes is which term the implementation evaluates for each published component.
  The ADR's header now says where the amendment lives rather than implying it already did.
- **Risk Level**: Low. Documentation only; no code path changes. The weights are
  unchanged, so no card's score changes.
- **Tests**: the pin test still passes (it greps the ADR, which still lists all five
  weights); the ADR-file assertion still holds.

#### R2 [Architecture] The candidate DTO's default was a literal where the module's own rule says it must be the prior

- **File**: `backend/apps/ingestion/services/catalog_read.py:286`
- **Severity**: Low
- **Description**: `PublicEventCandidate.source_reliability` defaulted to
  `Decimal("0.50")` — a **second copy of the prior's value**, in a module whose own
  docstring says the prior is *"asked of the domain module, not written here"*, and whose
  neighbouring helper `_source_reliability` asks `domain.reliability` for exactly that
  value. Two copies of a number is the drift the codebase's own comments rail against.
- **Rationale**: If FR-16's α/β were re-tuned, the helper would follow the domain module
  and the default would not — and the disagreement would be invisible until a card's dots
  were wrong.
- **Fix**: The default is now `reliability_score(0, 0)` — the same domain call.
- **Note**: The **asymmetry with `RankingInputs` is deliberate and stays.**
  `RankingInputs.source_reliability` has **no** default at all, because a default there
  would let a construction site forget the term and score every card as if its source
  were unscored — an inert weight by construction. The DTO's default is reachable only
  when a candidate is built *without* a source's score, and the prior is right there.
- **Risk Level**: None. The value is identical today; only the source of truth changed.
- **Tests**: full suite green.

#### R3 [Testing] `test_an_unscored_source_is_at_the_prior` was a false green

- **File**: `backend/tests/personalization/test_digest_composition.py`
- **Severity**: Medium
- **Description**: The test's name claimed "a source the recompute has not reached
  contributes the prior, not a zero", and its assertions were `score > Decimal("0.00")`
  and `reliability_score(0, 0) == Decimal("0.50")`. **The first is true of any reliability
  value, including zero**, because four other terms contribute; the second asserts a
  *domain constant*, not the composition's behaviour.
- **Verified, not assumed**: replacing the prior with `Decimal("0.00")` in
  `_source_reliability` left **all 63 tests in the file green** — the mutation passed.
  The test proved nothing about the thing it was named for.
- **Fix**: The assertion is now **relative**, the only shape that can fail. The same
  event is composed for three users, with its source's score at *nothing*, at *0.00* and
  at *0.80* in turn, and the unscored card must fall **strictly between** the other two.
  Only a value that really is the prior sits there — a zero would tie the first and a
  1.00 would tie the second. The same mutation now fails with a message naming which
  comparison broke.
- **Note**: The first attempt at the rewrite was itself wrong, and the failure is worth
  recording. It built *three separate events*, one per source score — and the
  composition's three slots hold three **different** events, so `compositions[0]` was not
  the event under test. The "worst" card came back scoring exactly the prior. The fix was
  the shape the sibling test already used: **one event, three users**, changing only the
  source's score between compositions.
- **Risk Level**: Low. Test only; the production code is unchanged.
- **Tests**: mutation-verified — the zero-prior mutation now fails.

#### R4 [Architecture] The ranking must consume FR-16's score, never write it

- **File**: `backend/tests/architecture/test_ad10_explanation_persistence.py`
- **Severity**: Low
- **Description**: The ranking is a **consumer** of `Source.reliability_score`, which
  FR-16's weekly recompute owns. Nothing stopped it from becoming a writer, and a writer
  would make a source's reliability depend on whether a digest had been composed — and
  would race the recompute that owns the column.
- **Fix**: A new AST-based guard in the AD-10 file, beside the other AD-10 guards. It
  looks for exactly two shapes: an **attribute assignment**
  (`source.reliability_score = ...`) and a **write call naming the column**
  (`update(reliability_score=...)`, `setattr(source, "reliability_score", ...)`).
- **Note**: The **first version of this guard was a name match, and it failed on correct
  code.** The composition writes `source_reliability=reliability_score(0, 0)` — a *keyword
  argument* whose value happens to be a function named `reliability_score`. A substring
  check on the name read that as a write of the column. This is the name-based-wall
  failure the work item's own Technical Notes warn about, arriving from the other
  direction: a wall that fails on the code it was written to permit. Hence the AST.
- **Risk Level**: Low. Test only.
- **Tests**: mutation-verified — a planted assignment fails the guard with the offending
  line and column named.

#### R5 [Testing] The false green in the e2e mutation probe

- **File**: `backend/tests/e2e/mutation_probe_contract_e2e.py`
- **Severity**: Medium
- **Description**: Probe #5 hard-coded `RANKING_WEIGHT_INTEREST = Decimal("0.45")`. After
  this item the constant is `0.35`, so the probe's edit would have found **nothing to
  replace** and the suite would have stayed green — a probe that proves nothing while
  looking like a pass.
- **Fix**: The literal was moved to `0.35`, and a script confirmed the probe literal and
  the constant literal **match** and that the exact target line is present.
- **Risk Level**: Low. Test only.
- **Tests**: all 10 contract probes caught.

---

### Reviewed and deliberately left alone

- **`PublicEventCandidate.source_reliability` still has a default at all**, while
  `RankingInputs.source_reliability` has none. This is a real asymmetry, and it is
  correct: the DTO is a *transport* for a value the catalog resolved, and the ranking
  input is the thing a construction site must not forget. Recorded in R2 and in the
  design's D4.
- **The weights are a reduced formula, not FR-22's published one.** `novelty_vs_exploration`
  is still absent (it needs FR-25's graph and an `Event` category field) and
  `preference_graph_match` is still stood in for by the interest chips. The ADR is
  explicit that the *MVP weights* are unchanged and what changes is *which term the
  implementation evaluates for each published component*. This is the FR-22 clause
  ("the Architecture spec describes the *implementation* of the formula but does not
  redefine the weights") read literally, and it is why no PRD weight changed.
- **`score_slot_3` does not invert the reliability.** FR-5 *multiplies by*
  `source_reliability` — a quality gate, not a popularity term — and FR-5's only
  inversion is `(1 − normalized_popularity)`. Inverting reliability would make Slot 3
  structurally prefer the *least* reliable sources. The docstring says so, and
  `test_slot_3_does_not_invert_the_reliability` pins it.
- **Stored `DigestComposition` rows are not rewritten.** The rows cannot be recomputed —
  their *inputs* were never persisted, only the resulting score — so a rewrite would be a
  rewrite under today's formula, changing a user's archive under them. Two new guards
  enforce it (the composition may not `update`/`save`/`update_or_create`/
  `get_or_create` a row, and every `apply_hysteresis` call must pass `previous_bucket`
  and `previous_score` as the literal `None`).
- **The prior is not gated on FR-16's minimum observation count.** Gating would make the
  formula's *shape* depend on a fact the formula does not carry — two formulas in the
  product at once — and would put a cliff in the ranking at 30 observations. The
  rejected alternative is recorded in the ADR §3 and in `domain/ranking.py`'s docstring.

### Architecture compliance

| Rule | Status |
|---|---|
| AD-8 domain purity | ✅ `domain/ranking.py` imports only `shared.constants`; `domain/reliability.py` is stdlib-only. `lint-imports` "AD-2 domain is pure" KEPT |
| AD-10 two explanations, neither recomputed at render | ✅ The read paths serve persisted rows; two new guards enforce it |
| AD-2 / AD-3 schema wall | ✅ The reliability score is read on the joined source row — `select_related("venue", "source")` — so the term costs **no extra query** and crosses no schema |
| AD-4 / AD-5 | ✅ No write at all in this item; the only writer of the column is FR-16's recompute |
| AD-16 | ✅ No new entity. The `DigestComposition` model is untouched |
| FR-22's amendment policy | ✅ A weight change fails CI twice — the number assertion and the ADR-document assertion — and the PRD now carries the matching A-10 block |
| Never delete | ✅ Nothing deleted |

### Gates after the fixes

| Gate | Result |
|---|---|
| `pytest` (full suite) | ✅ **6158 passed, 16 failed** — the 16 verified as pre-existing by stashing the branch and re-running at HEAD |
| `pytest tests/architecture/ tests/domain/ tests/personalization/ tests/shared/` | ✅ **2882 passed** |
| `pytest tests/domain/ --cov=domain` | ✅ 643 passed · `domain/ranking.py` at **100%** |
| `pytest tests/e2e/mutation_probe_contract_e2e.py` | ✅ all **10** contract probes caught |
| `ruff check` / `ruff format --check` | ✅ all checks passed · 578 files formatted |
| `lint-imports` | ✅ 19 kept, 0 broken |
| `manage.py check` / `makemigrations --check --dry-run` | ✅ no issues (3 silenced) / no changes detected |

### Mutation verification

Every proof in this item was checked by **breaking the code**, not by reading the test.

| Mutation | Result |
|---|---|
| Remove `RANKING_WEIGHT_RELIABILITY * inputs.source_reliability` from `relevance_score` | ✅ **12 failures** — every domain reliability test, all three slot-ordering tests, and both service tests |
| Replace the prior with `Decimal("0.00")` in `_source_reliability` | ✅ caught — and it **was not caught before R3**; the rewritten test now fails with the comparison that broke |
| Look the source's score up per candidate (N+1) | ✅ caught — "12 catalog queries for ten candidates and 2 for one" |
| Insert an `.update()` on the compositions | ✅ caught — "A persisted Relevance Pulse is history" |
| Carry a previous bucket into `apply_hysteresis` | ✅ caught — the composition must pass `None` literally |
| Plant a `source.reliability_score = ...` assignment in `personalization` | ✅ caught — R4's new guard, with the line and column named |
| Move the interest weight in the e2e probe | ✅ caught — all 10 contract probes go red |

### Areas checked and found CLEAN

- **The N+1 claim.** `list_public_candidates` already does
  `.select_related("venue", "source")`, so the reliability score is a column on an
  already-joined row. The AC's "no N+1" requirement turned out to be a structural
  property rather than a design problem, and the query-count test pins it.
- **The inert-weight argument.** The module's own definition — a term that *cannot
  distinguish two candidates* — is answered on the module's own terms rather than by
  assertion: the term is a per-candidate **variable** read from a stored computed
  number, and the prior is a **value** (`reliability_score(0, 0)`) rather than a literal.
- **The `Decimal` precision.** Each score is quantised to two decimals *after* the sum,
  so the raw difference (0.15) and the observed difference (0.16) differ by a hundredth.
  Both are pinned, because "the term is worth 0.15" and "the two cards are 0.16 apart"
  are both true and a reader checking either must find it.
- **`ROUND_HALF_EVEN`.** The prior's own contribution is 0.125, which quantises to
  **0.12**, not 0.13. The test says so.
- **The formula's arithmetic.** `RANKING_WEIGHT_SUM` is 1.00 across the five weights,
  the score is clamped to [0, 1] before bucketing, and `Decimal` is used throughout —
  a float `0.85` would land the card in the wrong bucket.
- **No user-visible regression in stored rows.** A digest composed before this change
  keeps its scores; a digest composed after it uses the new formula. The invariant that
  holds is that every card within one digest is scored by the same formula.

### Carried forward (not this item's scope)

1. **16 pre-existing test failures**, verified identical at clean `HEAD`. The fixture
   feeds' event dates have been overtaken by the wall clock, so catalog reads bounded by
   "has not started yet" return nothing and the saves 404. This will worsen with time
   and should get its own work item.
2. **The PRD amendments for FR-16** are still owed: "before its score moves" → "before
   its score moves freely", and the spike wording. (FR-22's own amendment, A-10, is
   **not** owed — it was written as part of this item.)
3. **FR-25** still owes the product `novelty_vs_exploration` and a real
   `preference_graph_match`. Until it ships, the interest chips stand in for the graph
   and the formula stays reduced — legibly, as a debt.
4. **ADR-0024** remains "forthcoming". EXPERIENCE.md names it as the document for the
   reliability formula, and this ADR cites it as the score its fifth term reads. It
   should be written when FR-16's formula is next revised.

---

## Work Item: frontend-report-control

**Files reviewed**: 7
**Reviewed**: 2026-11-11T11:05:00Z

| Category | Auto-Fixed | Applied | Skipped |
| --- | --- | --- | --- |
| Code Quality | 1 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 0 | 0 | 0 |
| Testing | 0 | 0 | 0 |
| **Total** | **1** | **0** | **0** |

**Files reviewed**

- `frontend/components/detail/event-report-control.tsx` (created)
- `frontend/components/detail/event-report-control.test.tsx` (created)
- `frontend/components/detail/detail-actions.tsx` (modified)
- `frontend/app/events/[id]/page.test.tsx` (modified)
- `frontend/tests/event-detail-a11y.test.tsx` (modified)
- `frontend/tests/ad19-endpoint-coverage.test.ts` (modified)
- `frontend/tests/report-control-mutation-probe.mjs` (created)
- `frontend/tests/report-flag-page-probe.mjs` (created)

**Tests after the review**: 107 files, 1810 tests, all passing. `tsc --noEmit` clean,
`eslint .` clean, `prettier --check .` clean. The mutation probes: **24/24** control,
**2/2** page, **7/7** AD-19 — none BROKEN.

### Auto-fixed

**R1 — The `Message` union had a member no code path could reach.** *(Code quality;
mechanical; non-semantic.)*

`type Message = "reported" | "failed"` — but `setMessage("failed")` is **never called**.
Every failure path sets `refusal` instead: the 429 (`setRefusal(response.error?.message ??
OFFLINE_MESSAGE)`), the other non-2xx (`setRefusal(...)`), and the network failure
(`setRefusal(OFFLINE_MESSAGE)`). So `"failed"` was unreachable, and with it
`FAILED_MESSAGE` was dead code.

This is not cosmetic. The docstring above the type said *"Three outcomes, and they are
different outcomes"* — and there are **two**: the toast carries the success, and the
modal carries every refusal. A reader of the type would have gone looking for a failure
toast that does not exist, and a future author could have "fixed" the 429 by setting
`message` instead of `refusal` — which would have put a *transient* toast where the
design says the rate limit belongs, because a toast disappears on a timer and the limit
lasts until tomorrow.

**The fix** narrows the union to the one member that exists and says why the others do
not:

```ts
/**
 * What the control last said.
 *
 * **One outcome, and it is the only one the toast carries.** "Reported" means the
 * server accepted the report. **Every refusal is the server's answer, and it is shown
 * inside the modal** — the rate limit, a 404, a 422 and a network failure all set
 * `refusal` and none of them sets a toast. So this union has exactly one member: there
 * is no failure toast to render, because a failure is not a toast.
 */
type Message = "reported";
```

`FAILED_MESSAGE` and the `message === "failed"` arm of the toast expression are gone.
**The mutation probe's pattern moved with it** — `tests/report-control-mutation-probe.mjs`
hard-codes the toast's source line, and the probe that plants "the live region is only
rendered once there is a message" would have found **nothing to replace** and reported
itself BROKEN had the pattern not been moved with the code. It was moved, and the probe
re-run: still **24/24 caught**.

### Areas checked and found CLEAN

- **The signed-out behaviour is inherited, not re-implemented.** The whole action row is
  inside `{personal ? … : null}` (`app/events/[id]/page.tsx:477`), so the flag cannot
  drift from Save's rule — it is the same `if`. There is no second gate to get wrong,
  and the page probe proves the gate is load-bearing by lifting it.
- **The generated contract is the only source of the request's shape.**
  `ReportBody = components["schemas"]["EventReportIn"]` and
  `ReportCategory = ReportBody["category"]`, so `CATEGORIES`' four `value`s are typed by
  the **generated union** — a category the API does not have is a compile error at the
  call site, not a request the server refuses (AD-19). The endpoint is registered in
  `tests/ad19-endpoint-coverage.test.ts` with its operation id and its caller, so the
  contract gate covers it too.
- **The toast is not a second status region.** The Detail Screen's action row already
  owns one (`detail-actions.tsx`'s conflict-failure line). The report toast is a bare
  `<p aria-live="polite">` with **no** `role`, and it is **always in the DOM** — a live
  region added to the page together with its text is not announced reliably; a region
  that is already there and then changes is.
- **The focus return is a transition, not a condition.** The effect is guarded by
  `wasOpen.current && !open`. An effect that ran "when the modal is closed" would also
  run on the first render and would steal focus to the flag before the user had done
  anything. The probe that disables the focus move proves the assertion can fail.
- **The rate limit and the network failure are different answers, and both are
  rendered calmly.** The 429 shows the **API's own sentence** — `lib/api-errors.ts`
  exists so the frontend quotes the API verbatim rather than writing its own — inside
  the modal, with the modal **open** and the selection **kept**. The network failure
  shows `OFFLINE_MESSAGE` (the one string the frontend owns, because in that case the
  API never spoke), also with the modal open, the selection kept and the Submit live
  again.
- **The radio group is a group of *states*, not of actions.** `role="radiogroup"` +
  `role="radio"` + `aria-checked`, because exactly one of the four is true — unlike the
  conflict prompt's `role="group"` of three *actions*. The radio's accessible name is
  the label alone; the mockup's description is `aria-hidden`, so
  `getByRole("radio", { name: "Wrong date or time" })` resolves to exactly the phrase
  FR-59 words it with.
- **The subordination is stated as an absence.** "Not a primary button" is asserted as
  the **absence** of the tokens Save and Share have — no `bg-accent-terracotta`, no
  `bg-surface-elevated`, no `border-border-subtle` — which is the only shape of the
  claim that can fail.
- **The report does not change the event.** Nothing on the page re-reads, nothing
  badges, the flag still reads "Report this event", and the body says nothing matching
  `/reported/i`. This is FR-59's own rule — *"a single report does not auto-reject an
  event"* — and the reason one person's report cannot become a lever on a listing.
- **The one existing test this item breaks was handled honestly.**
  `app/events/[id]/page.test.tsx:1137` asserted the Detail Screen renders no "report
  this event" text. **One** assertion was removed; the test's other three — reviews,
  similar events, "attended" — are untouched. The `DetailActions` **stub** gained a
  `<button>Report this event</button>` so the removal is not true for the wrong reason:
  a stub that fell behind the real row would have made the assertion pass vacuously.
  The **positive** form of the claim lives in `tests/event-detail-a11y.test.tsx`, which
  renders the **real** row — `page.test.tsx` stubs `DetailActions` out and cannot see
  the flag at all.
- **No hand-written request shape.** The body is
  `const body: ReportBody = { event_id: eventId, category: selected }` — typed by the
  contract, and the request goes through `api.POST`, the generated client. The probes
  that bypass the client and that hand-write a body both fail the suite.

### Carried forward (not this item's scope)

1. **The native-Escape desync in the shared `Sheet` is a house-wide gap, not this
   item's.** `components/sheets/sheet.tsx` does not listen for the `<dialog>`'s native
   `close` event — `onClose` is called only from the backdrop-click handler. In a real
   browser, pressing Escape closes the native dialog, React's `open` state stays `true`,
   and the state and the DOM disagree. **This item inherits it** (it is the fourth
   `Sheet` caller, alongside `account-menu`, `more-menu` and `personal-event-form`), and
   it is **not** introduced here. Two consequences worth naming: after a native Escape
   the focus does not return to the flag, and the modal's `open` state is stale. **It is
   also not testable here** — jsdom does not implement `dialog.close()`, so the native
   path cannot be exercised in this repository at all (verified: `dialog.close is not a
   function`). **The fix belongs in `Sheet`**, not in this control: a `close` listener
   that calls `onClose` would fix all four call sites at once. **Not fixed in this
   item** — it is a shared-component change with three other call sites, and this item's
   mandate is the report control.
2. **The Playwright half of the AC is a gap, not a satisfied criterion.** Playwright is
   not in this repository — no `playwright.config.ts`, no `@playwright/test`
   dependency, no e2e runner. The **axe half** is honoured in the house's own way (a
   Vitest + axe-core case in `tests/event-detail-a11y.test.tsx`, the file that already
   is the Detail Screen's axe gate, auditing `document.body` with the modal open and
   `color-contrast` disabled explicitly as in every other case). **The Playwright half
   is reported as a gap.**
3. **Three mockup features do not ship, each recorded with its reason**: the **daily
   report counter** (no endpoint carries the tally, and FR-59 rejects the visible
   counterpart), the **pre-emptively disabled Submit** (the client cannot know the user
   is on their sixth report — the server's limit is *discovered by attempting* and
   rendered calmly), and the **repeat-reporter warning** (needs the user's editorial
   rejection history; no endpoint carries it — **a remaining FR-59 consequence**).
4. **The backend's 16 standing failures** are owed to the earlier intents in this run.
   This item writes no backend file.
5. **FR-16's two PRD amendments** and **ADR-0024** remain owed, carried from the
   reliability items.

---

## Work Item: e2e-proof-and-contract-tests

**Reviewer:** `/code-review medium` over the three new files (the only code in the diff;
everything else is `.specs-fire/` planning documents).

**Eight findings, all eight verified against the implementation before being accepted, all
eight applied.** Two of them were defects in tests that *passed* — the worst kind, because
a green test that asserts nothing is indistinguishable from a green test that works.

### 1. HIGH — the probe harness could print a false green

`mutation_probe_trust_loop_e2e.py` read **any** non-zero pytest exit as "the bug was
caught". The contract suite shells out to `pnpm`, `openapi-typescript` and `lint-imports`
and `pytest.fail`s when they are missing — so on a machine with no Node, every probe would
exit non-zero for a reason unrelated to its planted bug and the script would print
*"All 10 trust-loop probes were caught by the suite"* and return 0.

**A false green on exactly the acceptance criterion the script exists to satisfy.** The
`-x` added in this file (not present in the sibling it was modelled on) made it worse: the
first environmental failure short-circuited the whole run.

**Applied:** a `baseline()` run of the unmutated suite before any mutation, aborting with
exit 2 if it is not green, and `-x` removed.

### 2. MEDIUM — the sync test could corrupt the tracked `schema.ts`

`assert result.returncode == 0` sat **outside** the `try/finally` that restores the file,
and the generator had already been pointed at `--output lib/api/schema.ts`. A generator
that writes a partial file and then exits non-zero would leave the developer's tracked
`frontend/lib/api/schema.ts` clobbered — by the test whose docstring promises it *"leaves
the tree exactly as it found it"*.

**Applied:** restore first, assert afterwards. (The sibling `test_state_change_contract.py`
has the same ordering; it is pre-existing and was not touched by this item.)

### 3. MEDIUM — the AD-14 "writes nothing through the ORM" test asserted nothing

It scanned for the literal strings `.objects.create(`, `.objects.update(`, `.save(` and
`.bulk_create(`. **This codebase writes `Model.objects.using(CATALOG).create(...)`** — the
intervening `.using()` means not one of those four patterns matches anywhere in `apps/`.
Verified: `grep -c '\.objects\.create(' apps/` returns **0**, against 10 for the real
idiom. Adding a `create(...)` to `apps/editorial/services/review_queue.py` — the exact
second write path the test is named for — would have passed it.

**Applied:** delegated to `checkers.direct_write_calls`, the architecture suite's own AST
checker, which parses the call and cannot be side-stepped by a chained method.

### 4. MEDIUM — the import wall missed the obvious evasion

The AST check read `node.module` only, so `from apps.ingestion.models import ReviewItem`
was caught and `from apps.ingestion import models` was not — which is the form someone
reaches for *after* being told the dotted path is forbidden.

**Applied:** each alias is checked as `f"{module}.{alias.name}"` too.

### 5. MEDIUM — the ranking delta was pinned to a rounding coincidence

`healthy - collapsed == Decimal("0.10")`. The true gap is `0.25 × (0.50 − 0.13) = 0.0925`,
and each total is quantized **independently** in `domain/ranking.py` with the default
`ROUND_HALF_EVEN` — unlike `domain/reliability.py`, which passes `ROUND_HALF_UP`
explicitly. So the stored gap is 0.09 or 0.10 depending on the fractional part of the terms
the two events *share*. Changing `RANKING_WEIGHT_RECENCY`, which has nothing to do with
reliability, would have failed this test with a message blaming a dropped reliability term.

**Applied:** both totals pinned (`0.48` and `0.38`) instead of their difference. A changed
weight now moves both numbers and names itself; a dropped reliability term still collapses
them onto each other. **Not** widened to a `>=` bound — that would have been the
or-fallback this run's standard forbids.

### 6. LOW — the FR-29 gap scan could not see the root router

It globbed `apps/**/*api*.py`, missing `config/api.py` and `config/health.py`, which
`checkers.api_modules` appends by name — and the root router is exactly where a dashboard
route would be registered.

**Applied:** `checkers.api_modules()`. **`api_modules`, not `surface_files`**: the latter
includes every app's `admin.py`, and the admin is *where the metrics are supposed to live*.
The first attempt at this fix used `surface_files` and failed correctly, which is how the
distinction got made explicit in the test.

### 7. LOW — the offline check missed every idiomatic import

`"import httpx" not in source` misses `from httpx import AsyncClient` and
`import httpx as http`.

**Applied:** the imports are parsed and compared by module name, with `aiohttp` and
`http.client` added to the forbidden set.

### 8. LOW — the contract count could mask a deleted contract

`^id = "..."` over the whole `pyproject.toml` counts any tool section's `id` key. One added
elsewhere and one contract removed would leave the count at 19 and the wall one shorter.

**Applied:** the `[[tool.importlinter.contracts]]` blocks are isolated before counting.

### What the review did not find

No finding against the **proof's** journeys — the chain, the escalation, the refusals — or
against the defect the proof reports. The reviewer independently confirmed the `0.13` score
pin (`_mean` uses `ROUND_HALF_UP`), that every probe pattern matches exactly once, and that
probe 8 is genuinely caught (`has_module_permission` returns `True`, so loosening
`has_view_permission` really does turn the 403 into a 200).

### Gates after the fixes

| Gate | Result |
| --- | --- |
| `tests/e2e/test_trust_loop_proof.py` | ✅ 10 passed |
| `tests/e2e/test_trust_loop_contract.py` | ✅ 21 passed |
| `mutation_probe_trust_loop_e2e.py` | ✅ **baseline green, 10/10 caught** |
| `ruff check` + `ruff format` | ✅ clean |
| `lint-imports` | ✅ 19 kept, 0 broken |

**The probe output got better as well as safer.** With `-x` removed, the counts show how
*wide* each bug's blast radius is: the dismissal-sign probe and the ticketing probe each
fail **three** tests, not one. A probe that trips three independent assertions is stronger
evidence than one that trips the first and stops.
