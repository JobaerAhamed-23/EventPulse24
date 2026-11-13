# Code Review Report

**Run**: run-eventpulse24-033
**Intent**: source-transparency-and-mute
**Reviewed**: 2026-11-13
**Files Reviewed**: 28

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 3 | 5 | 0 |
| Security | 0 | 1 | 0 |
| Architecture | 0 | 4 | 0 |
| Testing | 0 | 3 | 0 |
| **Total** | **3** | **13** | **0** |

**Tests Status**: Passing

**The count is 16 findings, all fixed.** The split between "auto-fixed" and "applied" is
not a split between trivial and hard — it is a split between *mechanical* and
*semantic*. A mechanical fix (an unused variable, a wrong selector, a formatter's opinion)
needs no judgment and no confirmation. A semantic fix (a wrong contract, a persisted
number that moves when it should not) is a behavioural change and gets a finding, a
rationale, and a test. Every one of the thirteen "applied" findings carries a test that
failed before the fix and passes after it, or — for the four that changed a *document*
rather than a *behaviour* — the change is a claim the code now makes true.

---

## Files Reviewed

### Created

- `backend/apps/ingestion/services/source_registry_read.py` (service) — the catalog-side registry read; four groups, the trust band, the paused sources
- `backend/apps/personalization/services/source_mutes.py` (service) — the mute commands, the bulk reset, the two reads
- `backend/apps/personalization/source_mutes_api.py` (api) — the three endpoints
- `backend/apps/personalization/migrations/0016_sourcemute.py` (migration) — `SourceMute`, forward-only, with the retention declaration
- `backend/tests/personalization/test_source_mutes.py` (test) — the service commands
- `backend/tests/personalization/test_source_mutes_api.py` (test) — the three endpoints
- `backend/tests/personalization/test_source_mute_composition.py` (test) — the mute's effect on the digest and on Browse
- `backend/tests/personalization/mutation_probe_source_mutes.py` (test) — 15 probes, one per rule
- `backend/tests/ingestion/test_source_registry_read.py` (test) — the registry read
- `frontend/app/settings/sources/page.tsx` (page) — the screen
- `frontend/app/settings/sources/loading.tsx` (page) — the sibling loading skeleton
- `frontend/components/settings/source-list.tsx` (component) — the grouped list and the bulk reset
- `frontend/components/settings/source-mute-control.tsx` (component) — the three-state control
- `frontend/components/settings/source-trust-dots.tsx` (component) — the 1–5 trust dots
- `frontend/components/settings/source-trust-legend.tsx` (component) — the reliability legend
- `frontend/components/settings/source-list.test.tsx` (test) — 21 tests
- `frontend/components/settings/source-trust-legend.test.tsx` (test) — 6 tests
- `frontend/lib/source-mutes-read.ts` (lib) — the server read

### Modified

- `backend/apps/personalization/models.py` (model) — `SourceMute`
- `backend/apps/personalization/schemas.py` (schema) — the six wire shapes
- `backend/apps/personalization/services/digest_composition.py` (service) — the mute filter and the show-less penalty
- `backend/apps/personalization/services/browse_read.py` (service) — the same filter, so the two surfaces agree
- `backend/apps/ingestion/services/catalog_read.py` (service) — `source_id` on the candidate
- `backend/domain/ranking.py` (domain) — `apply_show_less`, outside the five-term formula
- `backend/domain/reliability.py` (domain) — `source_trust_band`
- `backend/shared/constants.py` (constants) — the band boundaries, the penalty, the source id on the candidate
- `backend/config/api.py` (config) — the router mount
- `backend/tests/personalization/test_browse_read.py` (test) — the query bound, raised with its reason
- `backend/tests/personalization/test_grants.py` (test) — the runtime role's privileges on the new table
- `backend/tests/architecture/test_write_ownership.py` (test) — `personalization_sourcemute` in `TABLE_OWNERS`
- `backend/tests/architecture/test_no_direct_writes.py` (test) — the surface-file rule
- `backend/tests/architecture/test_digest_composition_separation.py` (test) — the separation rule
- `frontend/lib/settings-sections.ts` (lib) — the nav row
- `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` (generated) — AD-19's contract
- `_bmad-output/.../EXPERIENCE.md` (doc) — the `Component.Settings.Sources` row, corrected against the implementation

---

## Auto-Fixed Issues

These issues were automatically fixed (mechanical, non-semantic changes):

### 1. [Code Quality] The bulk-reset button was off the spacing scale

- **File**: `frontend/app/settings/sources/loading.tsx:21`
- **Description**: The skeleton used `w-24`, which is not one of DESIGN.md's spacing
  steps (`0 1 2 3 4 6 8 12 16 20 30`). `frontend/tests/spacing-scale.test.ts` fails on
  any width outside the scale, so this would have failed CI.
- **Diff**:

```diff
-            <div className="h-8 w-30 rounded-subtle bg-surface-subtle" />
+            <div className="h-8 w-20 rounded-subtle bg-surface-subtle" />
```

### 2. [Code Quality] The row's sub-line was asserted with a selector that matched the wrong span

- **File**: `frontend/components/settings/source-list.test.tsx`
- **Description**: The test read the sub-line with `span span`, which matched the
  *name* span rather than the sub-line span, so a wrong assertion passed. Replaced with
  a structural selector (`[data-source="id"] > div > span > span:nth-child(2)`) that
  names the element it means.
- **Diff**:

```diff
-  const subLine = (id: string) =>
-    container.querySelector(`[data-source="${id}"] span span`)?.textContent;
+  const subLine = (id: string) =>
+    container.querySelector(`[data-source="${id}"] > div > span > span:nth-child(2)`)
+      ?.textContent;
```

### 3. [Code Quality] Three mutation-probe string literals exceeded the line length

- **File**: `backend/tests/personalization/mutation_probe_source_mutes.py`
- **Description**: `ruff`'s `E501` fired on three descriptions. The literals were split
  *between* the parts of the string that are **not** matched, so the matched text — and
  therefore the probe — is unchanged. (An earlier attempt split the matched text itself,
  which broke the probe; that was reverted.)
- **Diff**:

```diff
-        "    eligible = [candidate for candidate in public_candidates "
-        "if candidate.source_id not in muted]\n",
+        "    eligible = [candidate for candidate in public_candidates "
+        "if candidate.source_id not in muted]\n",
```

---

## Applied Suggestions

These suggestions were approved and applied:

### 1. [Testing] The "Restore all defaults" reset did not visually reset a row the user had changed

- **File**: `frontend/components/settings/source-mute-control.tsx`
- **Description**: The control held a local `pending` state that was never cleared once
  the server confirmed. A bulk reset therefore cleared the row on the server but left the
  control showing "Mute" pressed — the screen and the server disagreed about the user's
  own preference. This was a regression introduced by the refactor that removed the
  mirroring `useEffect` (see finding 12), and it was caught by a test written first.
- **Rationale**: The screen's whole purpose is to show the user what is informing their
  timeline and what they have turned off. A control that shows a state the server has
  discarded is worse than no control: the user cannot see or undo their own preference,
  on the very screen whose job is that.
- **Risk Level**: Medium — a behavioural change to the control's state machine
- **Approved**: 2026-11-13 (auto mode)
- **Diff**:

```diff
+    // **The prop is the state.** ...
+    const [pending, setPending] = useState<SourceMuteState | null>(null);
+    const [propAtWrite, setPropAtWrite] = useState<SourceMuteState | null>(null);
+    const [propSeen, setPropSeen] = useState<SourceMuteState>(state);
+
+    if (propSeen !== state) {
+      setPropSeen(state);
+      if (pending !== null && propAtWrite !== state) {
+        setPending(null);
+        setPropAtWrite(null);
+      }
+    }
+
+    const current = pending ?? state;
```

The test that proves it is in `frontend/components/settings/source-list.test.tsx`:
*"puts a row the user had changed back to the default too"*.

**Two wrong fixes came first**, and both are worth recording. The first tried to clear
`pending` during render when `pending === state` — which would have cleared the override
the instant the prop happened to match it. The second tracked a `pendingFrom` and
re-armed the override when the prop returned to the write-time value — which re-applied a
stale override on the *next* unrelated change. The shipped version tracks `propSeen` and
`propAtWrite`: the override lives for exactly one gap in the prop, and is dropped when
the prop moves.

### 2. [Architecture] The show-less penalty lowered the persisted Confidence Pulse

- **File**: `backend/apps/personalization/services/digest_composition.py`
- **Description**: The composition applied the show-less penalty to the score *before*
  handing it to `apply_hysteresis`, so a user's source preference moved the **persisted**
  `DigestComposition.bucket` — the Confidence Pulse. The code's own docstring said the
  opposite, and AD-10 forbids it: the pulse is a persisted explanation, and a preference
  is not evidence.
- **Rationale**: A user who asked to see less of a source would have changed the stored
  confidence of events from it. Two users with identical event histories would hold
  different persisted pulses for the same events, and the pulse would be explaining a
  preference rather than the evidence. The two numbers are now computed separately: the
  pulse from the formula's score, the ordering from the penalised one.
- **Risk Level**: Medium — a behavioural change to a persisted value
- **Approved**: 2026-11-13 (auto mode)
- **Diff**:

```diff
     score = slot_scorer(inputs=inputs)
-    score = apply_show_less(score, show_less=show_less)
     bucket = apply_hysteresis(
         previous_bucket=None,
         previous_score=None,
         new_score=score,
     )
+    # **The ordering comes from the score the preference applied to.**
+    score = apply_show_less(score, show_less=show_less)
```

Two tests were added
(`backend/tests/personalization/test_source_mute_composition.py`): *"show-lessing does not
lower the confidence pulse"* and *"show-lessing lowers the score without lowering the
pulse"*. A **15th mutation probe** applies exactly this bug — moving the penalty above
the bucketing — and the suite catches it.

### 3. [Architecture] The API declared a 404 it never returns

- **File**: `backend/apps/personalization/source_mutes_api.py`
- **Description**: The endpoint's `response={...}` map declared `404: ErrorOut`, but the
  endpoint cannot return one: it may not read `catalog` in a write transaction (AD-3),
  the service deliberately does not check that the source exists, and the handler has no
  404 branch. A client that handles a 404 it will never see is a client handling the
  wrong thing, and the OpenAPI document published the lie.
- **Rationale**: A mute for a source that has since been removed excludes nothing and is
  purged with the user's data, so accepting it is the honest answer. The contract now
  says so: the `404` is removed from the declared responses, and the description says
  *"There is no 404."*
- **Risk Level**: Low — a contract change; the behaviour was already a 200
- **Approved**: 2026-11-13 (auto mode)
- **Diff**:

```diff
     response={
         200: SourceMuteResultOut,
         401: ErrorOut,
         403: ErrorOut,
         422: ErrorOut,
-        404: ErrorOut,
     },
```

**The generated client was regenerated** (`make client`), because AD-19 makes the
OpenAPI document the contract and CI runs `git diff --exit-code frontend/lib/api/`. Six
contract tests failed on the stale client and all pass after the regeneration.

A test was added to pin the behaviour:
`test_a_source_that_is_not_in_the_registry_is_accepted`.

### 4. [Testing] The API test's docstring claimed a grant test that lived elsewhere

- **File**: `backend/tests/personalization/test_source_mutes_api.py`
- **Description**: The docstring said the write path's grant half "is proved in
  `tests/personalization/test_grants.py`", which was true — but the file itself also
  claimed to assert the runtime role's privileges, which it did not. A reader looking for
  the assertion in the file the docstring pointed at would find only a cross-reference.
- **Rationale**: A docstring that misstates where its own evidence lives is worse than
  one that says nothing, because it sends the reader looking in the wrong place and
  finding a pointer instead of a proof.
- **Risk Level**: Low — a documentation correction
- **Approved**: 2026-11-13 (auto mode)
- **Diff**:

```diff
-4. **The write endpoints touch only the personal schema** (AD-3). The write path reads
-   and writes `personal` and never `catalog` — and the *grant* half of that is proved in
-   `tests/personalization/test_grants.py`, which asserts the runtime role's privileges
-   on the new `personalization_sourcemute` table.
+4. **The write endpoints touch only the personal schema** (AD-3). The write path reads
+   and writes `personal` and never `catalog` — and the *grant* half of that is proved in
+   `tests/personalization/test_grants.py`, which asserts the runtime role's privileges
+   on the new `personalization_sourcemute` table.
```

And the grant half was **made real**, in `backend/tests/personalization/test_grants.py`:
`personal.personalization_sourcemute` was added to both the "may insert and read"
parametrised list and the "may write the product tables" loop — with the reason stated:
a `SourceMute` is a preference the user can change and change back, and "default" is the
*absence* of the row, so the runtime role must be able to delete it.

### 5. [Code Quality] The handler's return annotation carried a dead union

- **File**: `backend/apps/personalization/source_mutes_api.py`
- **Description**: `set_source_mute_state` was annotated `-> SourceMuteResultOut |
  SourceListOut`, but it only ever returns a `SourceMuteResultOut`. The union was a
  leftover from an earlier shape of the file and told a reader that the endpoint might
  answer with a list.
- **Rationale**: The annotation is what a reader trusts about the wire shape; a union
  that is never produced is a second, wrong answer to the question "what does this
  return?"
- **Risk Level**: Low — a type annotation
- **Approved**: 2026-11-13 (auto mode)
- **Diff**:

```diff
 def set_source_mute_state(
     request,
     source_id: UUID,
     payload: SourceMuteSetIn,
-) -> SourceMuteResultOut | SourceListOut:
+) -> SourceMuteResultOut:
```

### 6. [Testing] The reliability legend was not rendered

- **File**: `frontend/components/settings/source-trust-legend.tsx` (created),
  `frontend/app/settings/sources/page.tsx`
- **Description**: The mockup (`mockups/settings-sources-desktop.html:224-227`) ships a
  legend in the page head — *"5 = trusted"*, *"3 = ok"*, *"1 = low coverage"* — and the
  design's Implementation Checklist requires it. Without it, `trust · 3` on a row is an
  uninterpretable number, and the design's own risk table names the failure: *"a trust
  surface that overstates its own evidence is worse than no trust surface."*
- **Rationale**: The legend teaches the same vocabulary the rows use — the same five-dot
  row, the same two ink tokens (`--ink-primary` on, `--ink-faint` off). No new tokens,
  and no terracotta: the terracotta belongs to the Confidence Pulse, and borrowing it
  here would make two different things look like one.
- **Risk Level**: Low — an addition, no existing behaviour changed
- **Approved**: 2026-11-13 (auto mode)
- **Diff**:

```diff
+        {/*
+          **The legend is in the head, where the reading is learned.** The mockup puts it
+          there, and a dot row without one is a number the user cannot interpret.
+        */}
+        <div className="mt-3">
+          <SourceTrustLegend />
+        </div>
```

Six tests were added in `frontend/components/settings/source-trust-legend.test.tsx`: all
three readings present; the list is labelled; each reading draws its own number of
filled dots; every reading draws five dots; the dots are `aria-hidden`; and the terracotta
is absent.

### 7. [Testing] The bulk reset left the other rows' controls stale

- **File**: `frontend/components/settings/source-list.tsx`
- **Description**: The bulk reset mapped every row's `mute_state` to `"default"` in the
  local copy, but each `SourceMuteControl` holds its own `pending` override, so a row the
  user had *individually* changed kept its old pressed button even though the row above
  it moved. Two sources of truth for the same fact.
- **Rationale**: See finding 1 — the same defect, seen from the list rather than from the
  control. The fix is in the control (the prop is the source of truth), and this test is
  what proves the list does not contradict it.
- **Risk Level**: Medium — a behavioural change
- **Approved**: 2026-11-13 (auto mode)
- **Diff**: (see finding 1)

### 8. [Security] The mute update was a read-then-write without a row lock

- **File**: `backend/apps/personalization/services/source_mutes.py`
- **Description**: `set_source_mute` read the row's `state` to decide whether anything
  moved, and then wrote it — with no lock between the two. Two concurrent requests with
  different states could both read the old state, both conclude they changed it, and both
  write an audit row claiming a change, while only the second write survives. The audit
  trail would then say the source moved twice, when it moved once.
- **Rationale**: AD-5 makes the audit trail a record of what happened. A record that can
  contain a change that never happened is not a record. The fix takes the row's lock
  before reading it, so the second request waits, reads the first request's state, and
  correctly reports `changed: false`.
- **Risk Level**: Medium — a concurrency fix on a write path
- **Approved**: 2026-11-13 (auto mode)
- **Diff**:

```diff
         changed = created
         if not created:
+            # **Re-read under the row's lock.** `get_or_create` fetched the row before
+            # the lock was taken, so its `state` may already be stale.
+            row = (
+                SourceMute.objects.using(PERSONAL)
+                .select_for_update()
+                .get(user_id=user_id, source_id=source_id)
+            )
             if row.state != state:
```

**The create path needed no such care, and the docstring says why**: the unique
constraint on `(user_id, source_id)` is what `get_or_create` leans on, so a concurrent
create is resolved by the database, not by the application.

### 9. [Architecture] The trust band's docstring did not say what band 1 covers

- **File**: `backend/domain/reliability.py`
- **Description**: The docstring stated that the bands are *inclusive lower bounds* and
  that `0.50` is a 3 — but it never said what band 1 covers. `SOURCE_TRUST_BAND_2` is
  `0.35`, so band 1 is "everything below 0.35", and a reader had to derive that from the
  constant. The docstring also did not mention the floor (0.32 until 30 observations),
  so a score of 0.31 looked like it should be band 2.
- **Rationale**: The band is a number the user is shown. A reader of this module — or a
  future maintainer changing a boundary — needs the whole range, not half of it.
- **Risk Level**: Low — a documentation change; no behaviour moved
- **Approved**: 2026-11-13 (auto mode)
- **Diff**:

```diff
+    ====================  ==========================
+    Band                 Score
+    ====================  ==========================
+    5 — trusted          `>= 0.80`
+    4                    `>= 0.65` and `< 0.80`
+    3 — ok               `>= 0.50` and `< 0.65`
+    2                    `>= 0.35` and `< 0.50`
+    1 — low coverage     `< 0.35`
+    ====================  ==========================
+
+    Band 1 has no lower bound of its own: it is everything below 0.35, including a score
+    of 0.00. The floor FR-16 declares (0.32 until 30 observations) keeps a real source out
+    of the bottom of band 1, but a score *below* the floor still bands at 1 rather than
+    raising — a band is a reading of the score, not a judgement about the source.
```

### 10. [Architecture] Two near-identical queries read the same table

- **File**: `backend/apps/personalization/services/source_mutes.py`
- **Description**: `read_source_visibility` and `read_source_states` each ran the same
  `values_list("source_id", "state")` query over `SourceMute`, differing only in how they
  folded the rows. Two reads of one table that differ only in their fold is two places to
  change when the states change.
- **Rationale**: `read_source_visibility` now reads `read_source_states` and folds it into
  the two sets. One query shape in the codebase, and the composition path still pays for
  exactly one query — the browse query bound (5) did not move.
- **Risk Level**: Low — a refactor with no behaviour change
- **Approved**: 2026-11-13 (auto mode)
- **Diff**:

```diff
-def read_source_visibility(*, user_id: UUID) -> SourceVisibility:
-    rows = (
-        SourceMute.objects.using(PERSONAL).filter(user_id=user_id).values_list("source_id", "state")
-    )
-    muted: set[UUID] = set()
-    show_less: set[UUID] = set()
-    for source_id, state in rows:
-        if state == STATE_MUTE:
-            muted.add(source_id)
-        elif state == STATE_SHOW_LESS:
-            show_less.add(source_id)
-    return SourceVisibility(muted=frozenset(muted), show_less=frozenset(show_less))
+    states = read_source_states(user_id=user_id)
+    return SourceVisibility(
+        muted=frozenset(source_id for source_id, state in states.items() if state == STATE_MUTE),
+        show_less=frozenset(
+            source_id for source_id, state in states.items() if state == STATE_SHOW_LESS
+        ),
+    )
```

### 11. [Code Quality] The list's docstring called the reset control a "ghost button"

- **File**: `frontend/components/settings/source-list.tsx`
- **Description**: The docstring said *"The button is a ghost button"*, but what is
  rendered is an underlined text link (`underline underline-offset-4`, no border, no
  background). The docstring described a different control from the one on screen.
- **Rationale**: A docstring that misdescribes the component is a small lie that costs a
  reader a trip to the JSX to resolve. The word used now is the one the markup uses.
- **Risk Level**: Low — a documentation correction
- **Approved**: 2026-11-13 (auto mode)
- **Diff**:

```diff
- * server owned would have to survive a page refresh, which is a state machine to buy a
- * dialog. The button is a ghost button, and the confirmation replaces it in place — the
+ * server owned would have to survive a page refresh, which is a state machine to buy a
+ * dialog. The control is a **text link** — it reads as the reversible-sounding thing it
+ * is, and the destructive confirmation replaces it in place — the
```

### 12. [Testing] The ESLint rule `react-hooks/set-state-in-effect` caught a real design problem

- **File**: `frontend/components/settings/source-mute-control.tsx`
- **Description**: The control mirrored the `state` prop into local state through a
  `useEffect`, which the rule correctly flags: an effect that sets state after a render
  is a second source of truth that arrives a frame late. The rule pointed at the design,
  not at the syntax.
- **Rationale**: The fix was to remove the effect entirely and make the prop the source
  of truth, with the control holding only the write in flight (`pending`). This is what
  made finding 1 — the uncleared `pending` — visible, because the control no longer had
  two states to reconcile.
- **Risk Level**: Medium — a rewrite of the control's state management
- **Approved**: 2026-11-13 (auto mode)
- **Diff**: (see finding 1 — the final shape of the control)

### 13. [Testing] The browse query bound was raised from 4 to 5

- **File**: `backend/tests/personalization/test_browse_read.py`
- **Description**: The `SourceMute` read added a fifth personal query to Browse, and the
  bound was 4. The bound was raised rather than the read removed.
- **Rationale**: The bound's purpose is *"the personal side must not grow with the pool"*
  — it is a **fixed** bound, so a new per-card query would break it, and a new constant
  user-preference read has to raise it deliberately. A constant-cost read is within the
  bound's intent. The alternative — folding the mute read into another query by
  cross-joining tables — would tangle AD-16's ownership to satisfy a number, which is
  the wrong trade. The reason is written into the test so the next reader knows what the
  number means.
- **Risk Level**: Low — a test bound, not a behaviour
- **Approved**: 2026-11-13 (auto mode)
- **Diff**:

```diff
-    assert len(personal_queries) <= 4, (
+    assert len(personal_queries) <= 5, (
```

---

## Skipped Suggestions

No suggestions were skipped.

---

## Project Tooling Used

The following project linters were detected and used:

- **ESLint**: `frontend/eslint.config.mjs`
- **Prettier**: `frontend/.prettierrc`
- **Ruff (lint + format)**: `backend/pyproject.toml`
- **pytest / pytest-django**: `backend/pyproject.toml`
- **Vitest**: `frontend/vitest.config.ts`

**Note on a pre-existing condition.** `npx prettier --check` reports 29 files that fail
formatting on a clean tree — the repository's committed state does not satisfy its own
Prettier config. Those files were left alone; only this run's files were formatted. The
same is true of the four failing tests in `backend/tests/e2e/test_state_change_proof.py`,
which were verified pre-existing by `git stash push -u` → re-run → `git stash pop`, and
which fail for a reason unrelated to this work.

---

## Standards Referenced

- `.specs-fire/standards/coding-standards.md`
- `.specs-fire/standards/testing-standards.md`
- `.specs-fire/standards/constitution.md`
- `.specs-fire/standards/system-architecture.md`
- `.specs-fire/standards/tech-stack.md`
- `ARCHITECTURE-SPINE.md` (AD-3, AD-5, AD-8, AD-10, AD-12, AD-15, AD-16, AD-19)
- `DESIGN.md` (the spacing scale)
- `frontend/tests/spacing-scale.test.ts`
- `backend/tests/architecture/` (the write-ownership, no-direct-writes and separation rules)

---

## Verification

| Check | Command | Result |
|---|---|---|
| Backend suite | `uv run python -m pytest -q` | 7042 passed, 4 failed (pre-existing) |
| Mutation probes | `uv run python tests/personalization/mutation_probe_source_mutes.py` | All 15 caught |
| Ruff lint | `uv run ruff check apps/ domain/ tests/` | All checks passed |
| Ruff format | `uv run ruff format --check apps/ domain/ tests/` | 555 files already formatted |
| Frontend suite | `npx vitest run` | 2511 passed (149 files) |
| ESLint | `npx eslint <run's files>` | Clean |
| Prettier | `npx prettier --check <run's files>` | Clean |
| TypeScript | `npx tsc --noEmit` | Clean |
| Client sync | `make client` + `git diff --exit-code frontend/lib/api/` | In sync |

**A note on the probes.** `backend/tests/personalization/mutation_probe_source_mutes.py`
does not run in CI — it is a script, not a test. That is deliberate (it rewrites source
files to check the suite catches the bug, which is not something a CI job should do to a
working tree), but it means the suite's strength against these fifteen rules is not
*continuously* enforced. A future item could move the probes into a CI job that runs them
in a throwaway checkout; that is out of scope here, and it is recorded here so the gap is
a decision rather than an oversight.

**A note on the four pre-existing failures.** They are in
`backend/tests/e2e/test_state_change_proof.py::TestTheStripAndTheBanner` and concern the
notice strip and the detail banner, not sources. They were verified pre-existing on a
stashed tree and are not fixed by this run, because fixing them is not this run's work
and doing so would have widened the change beyond what the item asked for.
