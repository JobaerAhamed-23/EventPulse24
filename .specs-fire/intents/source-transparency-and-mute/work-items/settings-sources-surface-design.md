---
work_item: settings-sources-surface
intent: source-transparency-and-mute
created: 2026-11-13
mode: validate
checkpoint_1: approved
---

# Design: Settings → Sources — A Designed Screen With No Endpoints

## Summary

`settings-sources-desktop.html` (Amendment A-18) specifies a complete screen: the sources
behind your events, grouped four ways, each with a 1–5 reliability badge and a 3-state mute
(Mute / Show less / Default), and a "Restore all defaults" footer.

The score is built. The screen is not, and neither is any way to reach it. This design settles
the three questions the brief poses — the grouping taxonomy, what the reliability dots mean,
and where a per-user mute lives — and specifies the model, the endpoints, the composition
change and the screen that make the mockup callable.

**Three of the brief's questions turn out to be answered already**, and one of them is
answered differently than the brief assumes. Those corrections are recorded under
*Corrections to the brief* below, because a design that silently contradicts its own brief is
how the next reader loses an afternoon.

## Scope

**In Scope:**

- The grouped source list: the mockup's four groups, backed by the Source Badge types
- The reliability badge: 1–5 ink-primary dots, and what the number they render means
- A per-user source mute with three states (Mute / Show less / Default), persisted
- The mute's effect on composition — `mute` excludes, `show_less` deprioritises
- "Restore all defaults", confirmed before it completes (§10.4 bulk-action safeguard)
- The `/settings/sources` route, following the five-step settings house pattern
- The three endpoints, and `make client` regenerated (AD-19)

**Out of Scope:**

- **FR-25's category mute.** The mockup for FR-25 reverses in `Settings → Taste`
  (`less-like-this-mute-prompt-desktop.html:122` and `:149`), not here. A category mute and a
  source mute have different subjects, and this screen's subject is sources. See D11.
- **A new source taxonomy.** No mapping is invented from `SourceType` or
  `AcquisitionMethod`. The one that exists is used.
- **FR-16's `PARTIAL` matrix score.** It is a citation problem, not a build problem. See D10.
- **The reliability score's inputs.** This screen *reads* the score; it does not change how it
  is computed, and it does not add observations.
- **Populating the source registry.** This screen renders what the registry holds. It does not
  create sources to make itself look fuller. See D9.

## Corrections to the brief

The brief was written from the mockup and the intent's own history. Reading the code changed
five things. Each is a Key Decision below with its evidence.

| The brief says | The code says | Decision |
|---|---|---|
| The four groups "map to nothing" and must be invented | `source_badges.py:35-52` already maps a source to exactly these four: `official_site`, `community`, `aggregator`, `crawled_html` (FR-23) | D1 |
| The dots are "what the reliability dots actually show" — an open product question | `domain/reliability.py:47-60` proves a 3x drop is impossible; the spike rule measures *negative rates*, not scores | D2 |
| "Where a per-user mute lives, under AD-3" — a question | `EventNoticeMute` (`delivery/models.py:598-640`) is the same shape, already built, with set/unset semantics | D3, D4 |
| "there is no `/settings` index and no sub-nav" | Both exist now — `frontend/app/settings/page.tsx` and `frontend/lib/settings-sections.ts` | D8 |
| A dismissal/mute is "reversible" under a "never-delete constraint" | `personal` rows are hard-deleted on undo throughout (`saved_events.py:278`, `personal_events.py:438`, `onboarding.py:317`); never-delete binds catalog rows and append-only tables | D3 |

One further fact shapes the screen more than any of the above, and it is not in the brief:
**the source registry holds about three rows.** `config/local_feeds.fixtures.json` seeds 3
feeds, `config/local_feeds.json` seeds 2, `seed_browse_catalog` adds 1. Everything else is
added one row at a time by an operator through Django admin. There is no dedicated
`manage.py` command for creating sources — `ingest_source` consumes an existing one.

That matters because `reliability_score(positives, negatives)` (`domain/reliability.py:148`)
is a beta-binomial posterior floored at 0.32 until 30 observations, and the prior with zero
observations is exactly 0.50. **At launch every source sits on the prior, and the badge
differentiates nothing.** The screen's most prominent visual element has no population to
separate. The design must name that plainly rather than let the mockup's ten illustrative
sources imply a registry that does not exist. See D9 and the Risks table.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| D1 — The four groups | Group by the **Source Badge type** (`source_badges.py:35-52`), not by `SourceType` or `AcquisitionMethod` | The mockup's four group names *are* FR-23's badge types, server-side, and already resolved for the Pulse Preview and the Digest candidate pool. `source_priority`'s docstring (`domain/sources.py:10-29`) exists precisely to prevent two disagreeing opinions about what a source is: *"the tier is derived from `acquisition_method` to avoid two disagreeing opinions."* A new grouping would be a third opinion. `source_badge_for_type` already handles the awkward cases — an unknown type is an aggregator, and `crawl` beats type ("*how* the facts were obtained is what the ⚠ means") |
| D2 — What the reliability dots show | Render the **stored `Source.reliability_score`** as a 1–5 band, labelled *"trust"*. Never the 0–1 posterior. Never a week-over-week delta | `domain/reliability.py:49` says plainly: *"FR-16 asks for 'a 3x week-over-week drop in reliability score'. **That cannot happen**"* — under 30 observations the floor pins the score between 0.50 and 0.32 (a ratio of at most 1.56), and a cumulative posterior is sticky enough that reaching even 2.96x needs ~100 all-negative events in one week. The spike rule therefore compares *rates of negative observations* (`is_spike`, `:183`), not scores. Rendering the delta would put a number on screen that the domain says is impossible — the AD-10 explanation drift. The 0–1 posterior is meaningless to a reader; the 1–5 band is the mockup's own contract, and the mockup's legend already defines it (5 = trusted, 3 = ok, 1 = low coverage) |
| D3 — Where the mute lives | A new `personal.SourceMute`: `user_id` + `source_id` **by value, no FK**, unique per pair, `retention_category = PREFERENCE_SIGNALS`, hard-deleted on unmute | AD-3's wall makes a cross-schema FK impossible, and the ORM is the enforcement mechanism (*"the mistake is impossible to **write**, not merely wrong at runtime"*). The precedent is exact: `EventNoticeMute` (`delivery/models.py:598-640`) is a personal row carrying a catalog id by value with a unique-per-pair constraint and `PREFERENCE_SIGNALS` retention, set with `get_or_create` (`mutes.py:61-63`) and unset with `.delete()` (`mutes.py:86-90`). `SavedEvent` is the same shape for the same reason (`personalization/models.py:276-281`). `PREFERENCE_SIGNALS` is the category whose own words are *"dwell, swipes, dismissals"* (`:723-725`) |
| D4 — The three states | Store only the two non-default states. `default` **deletes the row** | A row whose state is "default" asserts nothing and must still be read, joined and rendered as a present-but-empty row. Storing absence as `default` makes "Restore all defaults" a single bulk delete, matches `EventNoticeMute`'s unset idiom, and means the screen's Default position is the *absence* of a preference rather than a third value to reconcile |
| D5 — What `mute` and `show_less` do | `mute` = **excluded** from digest and browse candidate pools. `show_less` = **deprioritised**, not excluded — a score penalty at composition | The mockup distinguishes them, and "show less" that hid events entirely would tell the user something untrue. A hard exclusion for `show_less` would also make `mute` redundant. The penalty is applied in `personalization` at composition — the seam that already applies user-shaped filters (`include_personal_events`, `user_city` at `digest_composition.py:628-665`) |
| D6 — Where the filter is applied | At the **candidate set**, before scoring, in `compose_digest` and `browse_read`. Not in `domain/ranking.py`. Not in `catalog_read` | `domain/` is stdlib-only with no database access, and a mute is an exclusion, not a score term — `ranking.py:126` says *"nothing here is computed at render time — `domain` has no idea a render exists."* `catalog_read.list_public_candidates` is not user-scoped (`now, city, limit, starts_before`) and must not learn about a user's preferences. `browse_read` must apply it too: its docstring (`:157-158`) records that Digest and Browse must agree |
| D7 — Carrying the source id | Add `source_id: UUID` to `PublicEventCandidate`, populated in `_to_public_candidate` from the already-`select_related`'d `event.source_id`. **No extra query** | The candidate already carries `source_name`, `source_badge`, `source_type`, `acquisition_method` and `source_reliability` (`catalog_read.py:245-286`), but not the id — `_to_public_candidate` (`:303-332`) drops it. A mute keyed on `source_id` cannot filter without it. The read already joins `source` (`select_related("venue", "source")`), so the id is free. This is how every other personal→catalog reference crosses the wall: by value |
| D8 — The route | `/settings/sources`, the five-step house pattern, **plus a `SETTINGS_SECTIONS` row** | The five steps are documented verbatim at `frontend/app/settings/page.tsx:26-41`: `force-dynamic`; `homeRoute(session)` redirect; not-signed-in → `SettingsStates`; unavailable → `SettingsStates`; otherwise the page in `AppShell` at `max-w-(--layout-container-reading)`. `frontend/app/settings/calendars/page.tsx` is the canonical implementation, with a sibling `loading.tsx`. `frontend/tests/settings-routes.test.ts:53-62` asserts every route in `SETTINGS_SECTIONS` resolves to a real `page.tsx` **and** that every existing route is in the list — so a new route without a list row fails CI. The brief's "no `/settings` index and no sub-nav" is stale: both exist now |
| D9 — The empty registry | Render `component.emptystate.quiet` — the mockup already provides it — and do **not** fabricate sources | The registry legitimately holds ~3 rows. A screen that invented sources to fill itself would assert a registry that does not exist, which is the same failure as D2 in a different costume. The empty state is a first-class state, not a gap |
| D10 — FR-16's matrix score | **Do not** edit `TRACEABILITY.md` or the mockup header to close FR-16's `PARTIAL` as a side effect | The work item states the matrix's own rule: *"editing a document to improve the score in the same pass that measures it is how a matrix stops being trustworthy."* FR-16's score is `PARTIAL (inferred only)` because **nothing cites it** — not because the dots are missing. One line in `EXPERIENCE.md` or a tag in the mockup header closes it, and that is a separate, honest change to be made on its own |
| D11 — FR-25 coupling | **Do not** make this screen FR-25's reversal surface. Build FR-25's own `/settings/taste` | The FR-25 mockup says *"You can undo anytime in **Settings → Taste**"* (`:122`) and *"`Settings → Taste → Muted categories` lists every active mute"* (`:149`). FR-25's subject is a **category** ("Less rooftop jazz in your next digest?"); this screen's subject is a **source**. They are different objects and a single control cannot express both. The brief assumed this screen was FR-25's reversal surface; the mockup says otherwise, and the mockup is the more specific artifact. The two screens become siblings under one settings nav, not one control |

## Data Models Affected

### Creates

- **`SourceMute`**: `user_id` UUIDField (by value) · `source_id` UUIDField (by value) ·
  `state` CharField (`show_less` | `mute`) · `created_at` · `updated_at` — the per-user
  disposition of one source. Lives in `personal`, carries the catalog `source_id` by value
  with no foreign key (AD-3), and is deleted when the user returns a source to Default.

  Constraints: `UniqueConstraint(["user_id", "source_id"])` · `Index(["user_id"])`.
  Retention: `PREFERENCE_SIGNALS`.

### Modifies

- **`PublicEventCandidate`** (`backend/apps/ingestion/services/catalog_read.py:245`): add
  `source_id: UUID` — the composition service needs it to apply a source-keyed mute, and
  the read already has the source joined. Additive only; no existing field changes.

## Technical Approach

### Architecture

```
                    ┌──────────────────────────────────────────┐
                    │  GET  /api/settings/sources              │
                    │  PUT  /api/settings/sources/{source_id}   │
                    │  POST /api/settings/sources/restore      │
                    └───────────────┬──────────────────────────┘
                                    │ auth=current_user
                                    ▼
      ┌─────────────────────────────────────────────────────────────┐
      │  personalization                                           │
      │                                                             │
      │   source_mutes.py                                           │
      │     set_source_mute(user_id, source_id, state)   ──────────┼──► personal.SourceMute
      │     unset_source_mute(user_id, source_id)                  │    (user_id, source_id
      │     restore_defaults(user_id)                               │     by value, no FK)
      │     muted_source_ids(user_id) -> set[UUID]                  │
      │                                                              │
      │   compose_digest()  ──── exclude muted sources, penalise ────┼──► candidate set
      │   browse_read()     ──── the same filter (must agree) ──────┼──► candidate set
      └───────────────┬─────────────────────────────────────────────┘
                      │ reads candidates by value
                      ▼
      ┌─────────────────────────────────────────────────────────────┐
      │  ingestion  (catalog)                                      │
      │                                                             │
      │   catalog_read.list_public_candidates()                     │
      │     PublicEventCandidate  ◄── + source_id (D7)              │
      │       source_name · source_badge · source_type ·            │
      │       acquisition_method · source_reliability · source_id   │
      │                                                             │
      │   Source.reliability_score  (stored, weekly recompute)      │
      │   source_badges.source_badge_for_type()  ──► the 4 groups   │
      └─────────────────────────────────────────────────────────────┘
```

```
browser ──► Next.js /settings/sources ──OpenAPI client──► Django Ninja
                 (SETTINGS_SECTIONS row)                    (generated, AD-19)
```

### API Changes

- `GET /api/settings/sources` — the grouped source list: each source's name, badge group,
  reliability band (1–5) and current mute state. Read-only; a signed-in user's own settings.
- `PUT /api/settings/sources/{source_id}` — set `mute`, `show_less`, or `default`.
  `default` deletes the row. Patch-shaped body: only the changed field is sent.
- `POST /api/settings/sources/restore-defaults` — the §10.4 bulk reset: delete every
  `SourceMute` row for the user.

The bulk reset is **confirmed before it completes**. The mockup puts the confirmation behind
the tap and does not draw it ("*bulk reset confirmation lives behind this tap (per §10.4
bulk-action safeguard; not shown in this mockup but referenced)*"). The frontend owns the
confirmation dialog; the endpoint is a single idempotent bulk delete, and it returns the
number of rows cleared so the UI can say what happened.

All three sit under the existing `/settings` router (`backend/config/api.py:72`). The current
`/api/settings/*` family is a single route — `GET`/`PUT /api/settings/notifications`
(`delivery/preferences_api.py:49-122`) — whose PUT is patch-shaped: every field optional,
"omitted = leave alone", and `quiet_hours: null` turns quiet hours off (`:17-22`, `:157-218`).
The new endpoints follow that convention.

### Database Changes

```sql
-- Forward-only, one migration, AD-15 retention declaration.
CREATE TABLE personal.personalization_sourcemute (
    id          uuid        PRIMARY KEY,
    user_id     uuid        NOT NULL,
    source_id   uuid        NOT NULL,
    state       varchar(16) NOT NULL,
    created_at  timestamptz NOT NULL,
    updated_at  timestamptz NOT NULL,
    CONSTRAINT source_mute_state_ck
        CHECK (state IN ('show_less', 'mute')),
    CONSTRAINT source_mute_user_source_uq
        UNIQUE (user_id, source_id)
);
CREATE INDEX source_mute_user_idx
    ON personal.personalization_sourcemute (user_id);
```

No foreign key to `catalog.ingestion_source` — AD-3 makes that impossible, and the ORM
enforces it. The table lives in `personal`, so it is swept by the retention registry under
`PREFERENCE_SIGNALS`.

`catalog` is not touched by this item. `source_badges` and `reliability_score` are read-only
here.

## Dependencies

- `less-like-this-adjustment` — **not a dependency.** The two intents are siblings. FR-25
  builds its own `/settings/taste`; this intent builds `/settings/sources`. Neither waits for
  the other. They share the composition seam (D6) and the settings nav (D8), so the builder
  should coordinate those two touch points, but the ordering is free.
- `source_badges.source_badge_for_type` — **exists**, read as-is.
- `domain.reliability.reliability_score` and `Source.reliability_score` — **exist**, read as-is.
- `EventNoticeMute` — **exists**, used as the shape precedent for D3.

## Affected Files

| File | Action | Purpose |
|------|--------|---------|
| `backend/apps/personalization/models.py` | modify | `SourceMute` model, next to `Interest` / `EventDetailOpen` |
| `backend/apps/personalization/migrations/00XX_sourcemute.py` | create | forward-only migration + AD-15 retention declaration |
| `backend/apps/personalization/services/source_mutes.py` | create | set / unset / restore-defaults / `muted_source_ids` |
| `backend/apps/personalization/services/digest_composition.py` | modify | exclude muted sources; penalise show-less sources |
| `backend/apps/personalization/services/browse_read.py` | modify | the same filter, so Digest and Browse agree |
| `backend/apps/ingestion/services/catalog_read.py` | modify | carry `source_id` on `PublicEventCandidate` |
| `backend/apps/personalization/source_mutes_api.py` (or a sibling on the settings router) | create | the three endpoints |
| `backend/config/api.py` | modify | mount the router if it is not the existing settings router |
| `backend/apps/personalization/services/__init__.py` | modify | export the service |
| `frontend/app/settings/sources/page.tsx` | create | the screen, five-step pattern |
| `frontend/app/settings/sources/loading.tsx` | create | sibling loading state |
| `frontend/lib/settings-sections.ts` | modify | add the "Sources" row (D8) |
| `frontend/components/settings/source-reliability-dots.tsx` | create | the 1–5 ink-primary dots |
| `frontend/components/settings/source-mute-control.tsx` | create | the 3-state control |
| `frontend/components/settings/sources-groups.tsx` | create | the grouped list |
| `frontend/lib/api/` | regenerate | `make client` output committed (AD-19) |
| `backend/tests/personalization/test_source_mutes.py` | create | service and API tests |
| `backend/tests/personalization/test_source_mute_composition.py` | create | proof the mute changes what is shown |
| `frontend/app/settings/sources/page.test.tsx` | create | component tests |
| `frontend/e2e/` | modify | the journey + `axe-core` on the new surface |

## Security Considerations

- **Auth at the edge.** Every endpoint takes `auth=current_user`, matching
  `preferences_api.py:49`. A source mute is personal state; another user's row must be
  unreachable.
- **User scoping.** Every query filters on the authenticated `user_id`. The unique constraint
  is per-user, so a cross-user read would be a bug the tests must catch.
- **No PII, no free text.** A source mute is a UUID and an enum. Nothing is rendered from
  user input; the source name is catalog-owned, and source content is untrusted input (AD-9) —
  it is rendered as text, never as markup.
- **Rate limiting.** The per-source PUT is a cheap write, but it is an endpoint an
  unauthenticated client will try. The edge limiter applies as it does to the rest of the API.
- **Bulk reset is destructive** (deletes the user's rows). It is authenticated, scoped to the
  caller, and confirmed (§10.4). It is not reversible — which is the point: "Default" is the
  state the system returns to on its own.

## Integration Points

| System | Type | Purpose |
|--------|------|---------|
| `catalog.Source` | read | the source list and each source's stored reliability score |
| `catalog.SourceReliabilityScore` | read | the append-only weekly score history behind the stored score |
| `source_badges.source_badge_for_type` | read | the group each source falls into (FR-23) |
| `personal.SourceMute` | write | the per-user mute |
| `compose_digest` / `browse_read` | internal | the filter that makes the mute change what is shown |
| `EventNoticeMute` (delivery) | reference | the shape precedent — a *different* control, on a different subject |
| `SETTINGS_SECTIONS` | write | the settings nav row |
| OpenAPI client | generated | the contract (AD-19) |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **The registry holds ~3 sources, all at the 0.50 prior, so the badge differentiates nothing at launch** | High — the screen's most prominent element has no population to separate, and the mockup's ten illustrative sources imply a registry that does not exist | Name it in the design, not in a footnote. Ship the empty state first-class (D9). The walkthrough states plainly that reliability differentiates only once a source accumulates ≥30 observations. Do not fabricate sources to populate the screen |
| A reader trusts a dot that means nothing | High — a trust surface that overstates its own evidence is worse than no trust surface | D2: the dot count is the stored score banded to 1–5, labelled "trust", with the legend the mockup defines. Never a delta. The legend text ("5 = trusted, 3 = ok, 1 = low coverage") is honest about what a low dot means |
| `PublicEventCandidate` gains a field, and every consumer of the dataclass is affected | Medium | The change is purely additive; no field changes or is removed. Every construction site is in `catalog_read.py`. The existing candidate tests pin the shape and will catch an omission |
| `mute` is implemented as an exclusion and `show_less` as the same exclusion | Medium | They are different codes with different effects (D5). Two distinct tests: muted events are absent from the digest; show-less events are present but ordered below an otherwise-equal candidate |
| The mute is applied at composition but `DigestComposition` is append-only, so "the digest changes" is ambiguous | Medium | The mute is a **read-time filter over candidates**, not a mutation of a persisted composition row. A past composition is a record of a past decision and is unaffected. The test asserts the *next* composition omits the source |
| Two mute controls confuse users: FR-55's `EventNoticeMute`, this `SourceMute`, and FR-25's category mute | Medium | They are three distinct subjects and the UI names them distinctly: *notices for one event* (notices), *a source* (this screen), *a category* (FR-25's `/settings/taste`). `EventNoticeMute` already documents that it explicitly does not affect the digest (`notices_api.py:161-165`). State the distinction in the design and in the copy |
| "Restore all defaults" completes without confirmation | Medium | §10.4 is a safeguard the mockup names. The client confirms; the endpoint is idempotent and returns the count cleared. A test asserts the endpoint is not called without the confirmation step |
| The reliability dots are rendered with the terracotta confidence pulse | Low | The mockup is explicit: 1–5 ink-primary, *"NOT the terracotta confidence pulse from A-8"*, and **no new tokens**. A token test asserts no terracotta in this surface |
| The bulk reset deletes a user's rows and cannot be undone | Low | It is exactly what "restore defaults" means, and it is confirmed first (D8's §10.4). The user can re-mute. It is the intended direction of travel |
| The work item's "no `/settings` index and no sub-nav" constraint is stale | Low | Correct it in the design (D8). Add the `SETTINGS_SECTIONS` row or `frontend/tests/settings-routes.test.ts` fails CI |

## Implementation Checklist

- [ ] Write the AD-10 explanation for what the dots mean (D2) — into this design's rationale
      and, separately, into `EXPERIENCE.md`'s source-badge row. **Do not** touch
      `TRACEABILITY.md` or the mockup header (D10)
- [ ] Add `source_id: UUID` to `PublicEventCandidate`; prove no extra query is added
- [ ] `SourceMute` model + forward-only migration with the AD-15 retention declaration
- [ ] `source_mutes.py`: `set_source_mute`, `unset_source_mute`, `restore_defaults`,
      `muted_source_ids(user_id) -> set[UUID]`
- [ ] Apply `mute` as exclusion and `show_less` as a score penalty in `compose_digest`
- [ ] Apply the same filter in `browse_read` — Digest and Browse must agree
- [ ] The three endpoints under the `/settings` router, patch-shaped PUT
- [ ] `make client`; the generated output committed
- [ ] `/settings/sources/page.tsx` on the five-step house pattern, with a sibling `loading.tsx`
- [ ] Add the "Sources" row to `SETTINGS_SECTIONS`
- [ ] The reliability dots: 1–5 ink-primary, no terracotta, no new tokens, the mockup's legend
- [ ] The 3-state control: Mute / Show less / Default, with `default` deleting the row
- [ ] "Restore all defaults" with a confirmation before it completes (§10.4)
- [ ] The empty-registry state (`component.emptystate.quiet`)
- [ ] Tests: a composition test proving a mute changes what is shown (not merely that a row
      was written); an API test proving user scoping; a test that show-less deprioritises
      rather than hides
- [ ] Every test verified by a mutation probe that makes it fail
- [ ] `axe-core` clean on the new surface (PRD §11.5)

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-11-13*
