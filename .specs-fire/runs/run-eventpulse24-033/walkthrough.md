---
run: run-eventpulse24-033
work_item: settings-sources-surface
intent: source-transparency-and-mute
generated: 2026-11-13
mode: validate
---

# Implementation Walkthrough: Settings → Sources

## Summary

`Settings → Sources` is the screen that tells a user what is informing their timeline,
and lets them say "less of that" or "none of that" about each source. This run built it
end to end: a new `personal.SourceMute` row holding the user's per-source preference; an
`ingestion` read that publishes the source registry grouped by Source Badge type, with
each source's FR-16 trust band; the three endpoints behind the screen; the show-less
penalty and the mute filter applied in **both** the digest composition and the Browse
read, so the two surfaces agree; and the screen itself, with its three-state control and
its confirmed bulk reset.

**The screen's job is transparency.** Every source in the registry is listed, including
the ones the user has muted — a muted source that disappeared would be a preference they
could not see or undo, on the very screen whose purpose is to tell them what is shaping
their brief.

## Structure Overview

The feature is three layers, and the walls between them are the point.

**The catalog side (`ingestion`)** owns `Source` and publishes the registry. A new read
service — `source_registry_read` — groups every source by its Source Badge type, states
each source's trust band, and hands over *plain data*. It does not know the user exists.

**The personal side (`personalization`)** owns the preference. The `SourceMute` row
stores `user_id` and `source_id` **by value** — no foreign key, because AD-3 forbids a
relation across the schema wall and the ORM enforces that wall. A service
(`source_mutes`) holds the commands: set a state, reset one, reset them all, and the two
reads the composition path uses.

**The surface** is a thin API module (`source_mutes_api`) that resolves the user from
the session, calls the published services, and projects their plain data onto the wire
shape. It never imports a model and never touches the ORM — the architecture test
`test_no_direct_writes.py` enforces that.

**The join happens at the endpoint.** The registry is the catalog's; the mute is the
user's; the client makes one call and learns both. The endpoint reads the registry from
`ingestion` and the user's states from `personalization`, and merges them.

```
        GET /api/settings/sources
                    │
    ┌───────────────┴───────────────┐
    │                               │
┌───▼────────────────┐   ┌──────────▼─────────────┐
│  ingestion         │   │  personalization        │
│  source_registry_  │   │  read_source_states()   │
│  read()            │   │                         │
│  → 4 groups,       │   │  → {source_id: state}   │
│    trust bands     │   │                         │
└───┬────────────────┘   └──────────┬─────────────┘
    │                               │
    └───────────────┬───────────────┘
                    │
        ┌───────────▼─────────────┐
        │  source_mutes_api        │
        │  joins them per source   │
        └───────────┬─────────────┘
                    │
        ┌───────────▼─────────────┐
        │  GET /api/settings/      │
        │      sources             │
        └─────────────────────────┘
```

**And the preference travels back the other way**, into the two places that decide what
the user is shown:

```
        compose_digest()                   browse_read()
              │                                  │
              ▼                                  ▼
      read_source_visibility()           read_source_visibility()
              │                                  │
    ┌─────────┴─────────┐              ┌─────────┴─────────┐
    │                   │              │                   │
  mute → EXCLUDE     show_less →      mute → EXCLUDE     show_less →
  (absent from the   PENALISE the     (absent from the   PENALISE the
   candidate set)     score            candidate set)     score
```

Both surfaces read the same two sets, so a source the user muted is absent from the
digest *and* from Browse. A disagreement between the two would be a worse bug than
either being wrong alone.

## Architecture

### Pattern Used

**Service Layer with a published-read boundary.** The codebase already had this shape
before this run — `ingestion`'s `catalog_read`, `personalization`'s `browse_read` — and
the feature follows it rather than inventing a variant.

Two rules make it work:

- **The cross-wall read is a published service, never a model import.**
  `personalization` may not import `apps.ingestion.models`, so the registry read lives in
  `ingestion`, returns plain dataclasses, and the personal side joins its own state onto
  them. The wall holds without either side knowing the other's models.
- **Every write goes through a named command.** AD-5: `set_source_mute`,
  `restore_source_defaults`. The API module resolves the actor and calls a command; it
  does not write. The audit row is written inside the command's transaction.

### Layer Structure

```text
┌──────────────────────────────────────────────────────────┐
│  Presentation                                            │
│  frontend/app/settings/sources/  ·  components/settings/ │
├──────────────────────────────────────────────────────────┤
│  Surface                                                 │
│  backend/apps/personalization/source_mutes_api.py         │
│    — resolves the user from the session (AD-12)           │
│    — projects plain data onto the wire shape             │
│    — never imports a model, never touches the ORM        │
├──────────────────────────────────────────────────────────┤
│  Application (commands and reads)                        │
│  backend/apps/personalization/services/source_mutes.py    │
│  backend/apps/ingestion/services/source_registry_read.py  │
├──────────────────────────────────────────────────────────┤
│  Domain (stdlib only, no DB)                             │
│  backend/domain/reliability.py   — source_trust_band()   │
│  backend/domain/ranking.py       — apply_show_less()     │
├──────────────────────────────────────────────────────────┤
│  Infrastructure                                          │
│  personal.SourceMute  ·  catalog.Source  ·  Postgres      │
└──────────────────────────────────────────────────────────┘
```

**The two schemas, side by side.** `SourceMute` lives in `personal` and holds
`source_id` as a bare UUID. `Source` lives in `catalog` and is read by `ingestion`
alone. There is no join between them anywhere, in SQL or in Python — the join is a
dictionary in the API layer, over a UUID.

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/apps/ingestion/services/source_registry_read.py` | The catalog-side registry read: four Source Badge groups, each source's trust band, the paused sources |
| `backend/apps/personalization/services/source_mutes.py` | The mute commands, the bulk reset, and the two reads |
| `backend/apps/personalization/source_mutes_api.py` | The three source-visibility endpoints |
| `backend/apps/personalization/migrations/0016_sourcemute.py` | The `SourceMute` table, with the retention declaration |
| `backend/tests/personalization/test_source_mutes.py` | The service commands |
| `backend/tests/personalization/test_source_mutes_api.py` | The three endpoints |
| `backend/tests/personalization/test_source_mute_composition.py` | The mute's effect on the digest and on Browse |
| `backend/tests/personalization/mutation_probe_source_mutes.py` | Fifteen mutation probes, one per rule |
| `backend/tests/ingestion/test_source_registry_read.py` | The registry read |
| `frontend/app/settings/sources/page.tsx` | The `Settings → Sources` screen |
| `frontend/app/settings/sources/loading.tsx` | The sibling loading skeleton |
| `frontend/components/settings/source-list.tsx` | The grouped list and the bulk reset |
| `frontend/components/settings/source-mute-control.tsx` | The three-state mute control |
| `frontend/components/settings/source-trust-dots.tsx` | The 1–5 trust dots |
| `frontend/components/settings/source-trust-legend.tsx` | The reliability legend |
| `frontend/components/settings/source-list.test.tsx` | The screen's tests (21) |
| `frontend/components/settings/source-trust-legend.test.tsx` | The legend's tests (6) |
| `frontend/lib/source-mutes-read.ts` | The server read |

### Modified

| File | Changes |
|------|---------|
| `backend/apps/personalization/models.py` | Added `SourceMute`: `user_id` and `source_id` by value, a unique constraint per pair, `retention_category = PREFERENCE_SIGNALS` |
| `backend/apps/personalization/schemas.py` | Added the six wire shapes |
| `backend/apps/personalization/services/digest_composition.py` | Applied the mute filter to the candidate set and the show-less penalty to the score, **outside** the persisted Confidence Pulse |
| `backend/apps/personalization/services/browse_read.py` | Applied the same mute filter, so Digest and Browse agree |
| `backend/apps/ingestion/services/catalog_read.py` | Carried `source_id` on `PublicEventCandidate`, from the already-joined event — no extra query |
| `backend/domain/ranking.py` | Added `apply_show_less`, outside FR-22's five-term formula |
| `backend/domain/reliability.py` | Added `source_trust_band`, FR-16's score as the 1–5 trust band |
| `backend/shared/constants.py` | Added the band boundaries, the show-less penalty, and the source id on the candidate |
| `backend/config/api.py` | Mounted the source-visibility router |
| `backend/tests/personalization/test_browse_read.py` | Raised the personal-query bound from 4 to 5, with the bound's purpose written down |
| `backend/tests/personalization/test_grants.py` | Asserted the runtime role's privileges on the new `personalization_sourcemute` table |
| `backend/tests/architecture/test_write_ownership.py` | Added `personalization_sourcemute` to `TABLE_OWNERS` (AD-16) |
| `backend/tests/architecture/test_no_direct_writes.py` | Extended the surface-file rule to the new API module |
| `backend/tests/architecture/test_digest_composition_separation.py` | Extended the composition separation rule |
| `frontend/lib/settings-sections.ts` | Added the Sources row to the settings sub-nav |
| `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` | Regenerated (AD-19) |
| `_bmad-output/.../EXPERIENCE.md` | Corrected the `Component.Settings.Sources` row against the implementation |

## Domain Model

### Entities

| Entity | Properties | Business Rules |
|--------|------------|----------------|
| `personal.SourceMute` | `user_id` (UUID, by value), `source_id` (UUID, by value), `state` (`show_less` \| `mute`), timestamps | Unique per `(user_id, source_id)`; indexed on `user_id`; `retention_category = PREFERENCE_SIGNALS`; **the row's absence is `default`** — a third stored state would be a row that says nothing; every state change writes an audit row inside the same transaction |

### Value Objects

| Value Object | Properties | Constraints |
|--------------|------------|-------------|
| `SourceMuteResult` | `source_id`, `state`, `changed` | `changed` says whether *this* call moved anything; setting a state a source already has is a success, not an error |
| `SourceVisibility` | `muted: frozenset[UUID]`, `show_less: frozenset[UUID]` | The two sets the composition path asks about, read together in one query |
| `RegistrySource` | `id`, `name`, `source_badge`, `source_type`, `acquisition_method`, `city`, `reliability`, `trust_band`, `is_paused` | Plain data — never a model — so the calling app holds no reference to `apps.ingestion.models` |
| `RegistryGroup` | `badge`, `label`, `sources` | The four groups are **always** present, in order, even when empty, so the screen's shape does not depend on the data |

## Key Implementation Details

### 1. `default` is the absence of a row

The control has three positions, but only two are stored. Setting `default` **deletes**
the row rather than writing `"default"` into it. Two things fall out of that: "Restore
all defaults" is a single bulk delete rather than a three-way update, and the row stays
honest — a row that says "default" says nothing at all.

### 2. The show-less penalty sits outside FR-22's formula

`domain/ranking.py` computes `relevance_score()` as exactly five weighted terms summing
to 1.00, and `backend/tests/shared/test_constants.py:147-153` pins those weights in CI
against ADR-0025. A "show less" penalty **cannot** be a sixth term — that would change
a published, CI-pinned formula.

So the penalty is a post-score adjustment: the event still competes, it simply competes
lower. FR-22's formula is byte-identical, and the CI weight pin stays green.

### 3. The Confidence Pulse is bucketed *before* the penalty

This was the deepest finding of the review, and it is worth stating because the code
looks correct at a glance.

`apply_hysteresis` buckets whatever score it is handed. So applying the show-less
penalty *before* bucketing would have lowered the **persisted**
`DigestComposition.bucket` — the Confidence Pulse. A user's source preference would then
have changed the stored confidence of events from that source: two users with identical
event histories would hold different persisted pulses, and the pulse would be explaining a
preference rather than the evidence. That is the explanation-drift AD-10 forbids.

The two numbers are now computed separately:

```
score  = slot_scorer(inputs)                    ← FR-22's formula
bucket = apply_hysteresis(new_score=score)       ← the persisted pulse, from the formula
score  = apply_show_less(score, show_less=...)   ← the ordering, with the preference
```

Two tests pin it (*"show-lessing does not lower the confidence pulse"*, *"show-lessing
lowers the score without lowering the pulse"*) and a fifteenth mutation probe applies
exactly this bug.

### 4. The route order is load-bearing

`POST /api/settings/sources/restore-defaults` is declared **before**
`PUT /api/settings/sources/{source_id}`. Django resolves URL patterns in registration
order, and the first pattern to match the *path* wins — then the method is checked
against it. Registered the other way round, the `PUT` pattern would swallow
`POST /sources/restore-defaults` as a `PUT` against a `source_id` of
`"restore-defaults"`, and the answer would be a **405**, not a 404. A literal path has to
come first.

### 5. There is no 404

The endpoint may not read `catalog` in a write transaction (AD-3), and the service
deliberately does not check that the source exists: a mute for a source that has since
been removed excludes nothing, and the row is purged with the user's data. So the answer
is a 200 with the state recorded, and the declared `404` was removed from the response
map rather than left as a promise the code does not keep.

**A contract that says 404 and answers 200 teaches the client to expect a failure that
never comes**, and a client that handles a 404 it will never see is a client handling the
wrong thing.

### 6. The state travels from the session, never from the payload

The write endpoints take no user id. The API resolves the user from the session and
passes it to the command, so a request cannot talk the scoping out of. The bulk reset
is scoped to the caller the same way, and a test asserts that one user's reset leaves
another user's rows alone.

### 7. The bulk reset confirms before it does

§10.4's safeguard is that the destructive action is confirmed *before it completes*, and
the confirmation is the client's job. The endpoint is a single idempotent bulk delete; a
server-owned confirmation would have to survive a page refresh, which is a state machine
to buy a dialog.

The screen's confirmation **replaces the control in place** rather than opening an
overlay — A-16 reserves that weight for deleting an account, and the calendar screen's
disconnect already set the precedent for a settings screen's in-place two-step. The first
press sends no request.

### 8. The control's prop is its source of truth

The ESLint rule `react-hooks/set-state-in-effect` pointed at a real design problem. The
control had been mirroring the `state` prop into local state through an effect — a
second source of truth that arrives a frame late. The effect is gone: the prop *is* the
state, and the control holds only the write in flight.

That change is what made the next bug visible. The in-flight override was never cleared,
so a bulk reset cleared the row on the server while the control still showed "Mute"
pressed — the screen and the server disagreeing about the user's own preference. The
shipped fix tracks `propSeen` and `propAtWrite`, so the override lives for exactly one
gap in the prop and is dropped when the prop moves.

## Security Considerations

| Concern | Approach |
|---------|----------|
| **Authentication** | The router carries `auth=current_user`; an anonymous caller gets 401. The screen is not Pro-gated — muting a source is a preference, not a feature |
| **Authorisation / scoping** | The user id comes from the session, **never from the payload** (AD-12). The write endpoints take no user id at all, so a request cannot talk the scoping out of |
| **Cross-user isolation** | Every query filters on `user_id`. Tests assert that one user's write does not touch another's, and that one user's bulk reset leaves another's rows alone |
| **CSRF** | Every state-changing request carries the token, and the check is the server's — a write without one is refused with 403 |
| **Input validation** | The state is validated by the parser: an unknown state is a 422. `source_id` is a UUID in the path, and Django rejects a malformed one before the handler runs |
| **Data protection** | The mute holds a UUID and a two-value state. It is a preference, and it is hard-deleted on reset — personal rows are hard-deleted on undo throughout the codebase |
| **The data wall** | `SourceMute` holds `source_id` **by value**, with no FK. AD-3 forbids a relation across the schema wall, and the ORM's `DATABASES` aliases enforce it |
| **Table ownership** | `personalization_sourcemute` is declared in the `TABLE_OWNERS` map, so the architecture test fails if a second app tries to write it (AD-16) |
| **Runtime privileges** | The runtime role may insert, read, update and delete on the new table — it must be able to delete, because "default" is the *absence* of the row. The append-only tables stay fenced off, and the grant assertions prove it |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| **One query for the user's preferences** | `read_source_states` is the single query. `read_source_visibility` folds that answer into the two sets rather than running a second, near-identical query |
| **The preference read must not grow with the pool** | The browse path's personal-query bound is **5** — raised from 4 when the mute read was added, with the bound's purpose written into the test. It is a *fixed* bound, so a new per-card query would break it |
| **The screen is one call** | The client makes one request and learns the registry *and* the user's state. Two calls would have meant two round trips and two chances for the two halves to disagree |
| **No extra query for the source id** | `PublicEventCandidate.source_id` comes from the already-`select_related`'d event |
| **A screen of controls must not cost a query per row** | The states are read once, for all the user's sources, and joined onto the registry in memory |
| **The registry read is one query** | Every source, ordered by name, grouped in Python — not four queries, one per group |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| The four groups | Reuse FR-23's Source Badge types (`official_site` / `community` / `aggregator` / `crawled_html`) as the group key | The mockup's four group names *are* the badge types, already server-side and already used by two reads. A new mapping would be a second opinion about what a source is |
| The reliability reading | The **stored** score banded 1–5, labelled "trust", with the mockup's legend | FR-16 proves a 3× week-over-week drop is impossible, so a delta would assert something the domain says cannot happen. The 0–1 posterior means nothing to a user; the dot count is the mockup's own contract |
| Where the mute lives | A `personal.SourceMute` row: `user_id` + `source_id` by value, unique per pair, hard-deleted on reset | The `SavedEvent` / `EventNoticeMute` precedent. AD-3's wall makes an FK impossible; the ORM enforces the wall |
| What mute and show_less do | `mute` **excludes**; `show_less` **deprioritises** | A show-less that hid events would be indistinguishable from a mute on the wire, and would lie to a user who asked for fewer, not none |
| Where the filter is applied | On the **candidate set** in `compose_digest` and `browse_read`, before scoring | `domain/` is stdlib-only with no DB access, and a mute is a filter, not a score term. `catalog_read` is not user-scoped and must not learn about preferences |
| The `source_id` plumbing | Added `source_id: UUID` to `PublicEventCandidate` | The candidate already carries `source_name` and the read already joins `source`. Carrying the id by value across the wall is how every other personal→catalog reference works |
| The screen's route | `/settings/sources`, following the five-step house pattern, plus a `SETTINGS_SECTIONS` row | The `/settings` index and sub-nav **already exist** — the work item's constraint that they do not is stale. The frontend test fails on a route missing from the list |
| The empty registry | Render the quiet empty state; fabricate nothing | The registry genuinely holds a handful of rows. A screen that invented sources would be asserting a registry that does not exist |
| The bulk reset's confirmation | The client confirms; the endpoint is a single idempotent bulk delete | §10.4's safeguard is that the destructive action is confirmed *before it completes*. A server-owned confirmation would have to survive a page refresh |
| The 404 | There is none — the endpoint accepts the mute for an unknown source | The endpoint may not read `catalog` in a write transaction, and the service deliberately does not check |
| FR-25 coupling | **None.** This screen mutes sources; FR-25 mutes categories | The FR-25 mockup reverses at `Settings → Taste`, which is a category mute — a different subject, on a route that does not exist yet |
| FR-16's matrix score | `TRACEABILITY.md` and the mockup headers are **untouched** | The matrix's own rule: editing a document to improve the score in the same pass that measures it is how a matrix stops being trustworthy |

## Deviations from Plan

Five, all recorded here because each one changed the shape of the work.

**1. The show-less penalty was moved out of the Confidence Pulse.** The plan put the
penalty on the score before the hysteresis, which — as the review found — also moved the
*persisted* bucket. The plan's own acceptance criteria did not distinguish the two
numbers. Fixed, with two tests and a new mutation probe.

**2. The 404 was removed from the API's declared responses.** The plan's schema listed a
404 the endpoint never returns. Removing it changed the OpenAPI document, so the
generated client was regenerated (`make client`) — which is itself a plan step, but one
the plan did not anticipate needing after a contract change.

**3. The browse query bound was raised from 4 to 5.** The plan did not mention it. The
mute read added a fifth personal query. The bound was raised rather than the read
removed, and the reason is written into the test so the next reader knows what the number
means.

**4. The reliability legend was added.** The plan listed the dots but not the legend. The
mockup ships one, the design's Implementation Checklist requires it, and the design's own
risk table names the failure it prevents — *"a trust surface that overstates its own
evidence is worse than no trust surface."* Without it, `trust · 3` is an uninterpretable
number.

**5. The mute update takes a row lock.** The plan's read-then-write had a narrow race:
two concurrent requests with different states could both read the old state, both
conclude they changed it, and both write an audit row claiming a change, while only the
second write survived. `select_for_update` closes it — the second request waits, reads
the first's state, and correctly reports `changed: false`.

**Not deviated from, and worth naming:** the FR-25 coupling was *not* introduced, even
though the work item's brief pointed at it. The briefs assumed this screen was FR-25's
reversal surface; the mockup says `Settings → Taste`, which is a category mute. Coupling
them would have built a control that cannot express the other. The sibling intent builds
`/settings/taste` itself.

## Dependencies Added

**None.** No new package was added to `backend/pyproject.toml` or
`frontend/package.json`.

The one thing worth recording: the `personalization_sourcemute` table needs **no
explicit `GRANT`**. `docker/postgres/init/01-schemas-and-roles.sh:70-71` grants
SELECT/INSERT/UPDATE/DELETE on all new `personal` tables to `ep_personal` via
`ALTER DEFAULT PRIVILEGES`, so a new table inherits its privileges. Only the
append-only tables need explicit `REVOKE`s, and `0016` is not one of them.

## How to Verify

### 1. The screen renders the registry, grouped, with each source's trust

```bash
cd backend && uv run python -m pytest tests/ingestion/test_source_registry_read.py -v
```

Expected: every test passes. The four groups are present even when the registry is
empty; a paused source is still listed and marked; a never-scored source sits at band 3.

### 2. A mute excludes and a show-less deprioritises — and the two surfaces agree

```bash
cd backend && uv run python -m pytest tests/personalization/test_source_mute_composition.py -v
```

Expected: a muted source's events are absent from **both** the digest and Browse; a
show-less source's events are **present but ordered lower**; and — the subtle one — a
show-less does **not** lower the persisted Confidence Pulse.

### 3. The three endpoints answer, and the state comes from the session

```bash
cd backend && uv run python -m pytest tests/personalization/test_source_mutes_api.py -v
```

Expected: the list has four groups in order; a muted source is **still listed** with its
state; the bulk reset is scoped to the caller; a write without a CSRF token is 403; a
source that is not in the registry is a **200**, not a 404.

### 4. The rules are the rules the suite thinks they are

```bash
cd backend && uv run python tests/personalization/mutation_probe_source_mutes.py
```

Expected: `All 15 probes were caught by the suite.` Each probe applies one real bug and
checks that at least one test fails. **This script is not in CI** — it rewrites source
files, which is not something a CI job should do to a working tree. That gap is recorded
rather than overlooked.

### 5. The screen's behaviour

```bash
cd frontend && npx vitest run components/settings/source-list.test.tsx components/settings/source-trust-legend.test.tsx
```

Expected: 27 tests pass. The bulk reset confirms before it sends anything; a failed
write leaves the control where it was; the legend shows all three readings.

### 6. The whole thing

```bash
cd backend && uv run python -m pytest -q        # 7042 passed, 4 failed (pre-existing)
cd frontend && npx vitest run                  # 2511 passed
```

Expected: the four failures in `tests/e2e/test_state_change_proof.py` are **pre-existing**
— they concern the notice strip and the detail banner, not sources, and were verified
pre-existing on a stashed tree.

### 7. Manually, in a browser

```bash
make dev
```

Then, signed in:

1. Open `/settings/sources`. You should see the four group headings, the reliability
   legend in the head, and every source listed.
2. Set a source to **Mute**. The row moves immediately.
3. Open the digest. That source's events are **gone**.
4. Set it to **Show less** instead. Its events are **back**, but lower in the list.
5. Press **Restore all defaults**. The confirmation appears **in place** — no overlay —
   and no request has been sent yet. Press **Reset them**: every row returns to Default,
   including the one you changed by hand.
6. Open `/settings` — the Sources row is in the sub-nav.

## Test Coverage

- **Tests added**: 100 (73 backend, 27 frontend)
- **Mutation probes**: 15, all caught
- **Backend suite**: 7042 passed, 4 failed (pre-existing, verified on a stashed tree)
- **Frontend suite**: 2511 passed (149 files)
- **Lint / format / types**: ruff, ESLint, Prettier and `tsc --noEmit` all clean
- **Client sync**: `make client` produces no diff

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated (`EXPERIENCE.md`'s `Component.Settings.Sources` row)
- [x] Developer notes captured

## Developer Notes

**A muted source is still listed.** This will look wrong to a reader who expects a mute
to remove something. It is deliberate: the screen's job is transparency, and a muted
source that disappeared would be a preference the user could not see or undo.

**The dots are ink, not terracotta.** The terracotta is the Confidence Pulse's. The trust
dots answer a different question ("how much do we trust this source's facts?"), and
colouring them would make two different things look like the same thing. The legend in
the page head teaches the reading — `5 = trusted`, `3 = ok`, `1 = low coverage`.

**`0.50` is band 3, not band 1.** A source the recompute has never reached has no score
and sits at the prior. Banding it at 1 would call every unscored source a bad one on the
strength of no evidence at all.

**The band boundaries are inclusive lower bounds**, the opposite of
`domain.ranking.score_bucket`'s exclusive upper bounds. Not an inconsistency — the two
answer different questions — but worth knowing before you change one.

**The route order is load-bearing.** `restore-defaults` is declared before
`{source_id}`. Reverse them and `POST /sources/restore-defaults` answers **405**, not
404. The tests assert both endpoints answer, which is what catches this.

**The bulk reset is two steps and the first sends nothing.** If a test seems to hang, it
is probably waiting for a confirmation that never came.

**The generated client is the contract.** After any change to the endpoints' declared
responses, run `make client` — six contract tests fail on a stale client. AD-19 makes CI
check `git diff --exit-code frontend/lib/api/`.

**The `EXPERIENCE.md` row was corrected, not the matrix.** `TRACEABILITY.md` and the
mockup headers were deliberately left alone: FR-16's `PARTIAL` is a citation problem, and
editing a document to improve the score in the same pass that measures it is how a matrix
stops being trustworthy.

**The mutation probes are a script, not a test.** They rewrite source files to check the
suite catches a bug, so they cannot run in CI against a working tree. Run them by hand
after changing any of the fifteen rules they cover.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-033*
