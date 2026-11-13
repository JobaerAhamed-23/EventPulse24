---
work_item: less-like-this-adjustment
intent: relevance-feedback-loop
created: 2026-11-13
mode: validate
checkpoint_1: approved
---

# Design: FR-25 "Less like this" — the Feedback Loop, From the Decision to the Swipe

## Summary

FR-25 is MVP scope and exists nowhere in the codebase — no endpoint, no model, no column, no
UI. `less-like-this-mute-prompt-desktop.html` specifies the behaviour precisely: *"Triggered
after 3 clustered dismissals (embedding cosine ≥0.7). Calm copy. Reversible from settings. No
dark-pattern nag."*

This design answers the intent's first question — the architectural one — and specifies the
whole loop: the dismissal record, the vector store the clustering needs, the clustering rule,
the category mute, the prompt, the swipe, and the settings surface that reverses it.

**The intent's first question turns out to have a smaller answer than the brief expects.** The
brief says AD-4 must be amended because *"embeddings only route editorial review candidates"*.
The spine's actual rule is narrower, and reading it changes the work from *amend the spine* to
*record a finding*. That is the single most consequential correction in this document, and it
is D12.

## Scope

**In Scope:**

- The AD-4 finding, written down before any migration (D12)
- The embedding infrastructure the clustering rule needs: the real Voyage adapter, the vector
  column, the backfill, the AD-8 cost accounting
- The dismissal record, under the personal-row pattern
- The clustering rule: 3 distinct events, cosine ≥0.7, within a digest window
- The category mute, with duration, expiry and decay
- The prompt: once per cluster, calm copy, dismissible without choosing
- The swipe on the Pulse Card, plus a keyboard-reachable equivalent
- The reversal surface — `/settings/taste`
- The endpoints, and `make client` regenerated (AD-19)

**Out of Scope:**

- **The real `llm` and `email` adapters.** `ADAPTER_MODE=real` refuses to boot until `llm`,
  `embedding` and `email` all exist (`config/adapters.py:47-51`). This item delivers the
  `embedding` adapter; the other two are not FR-25's to build.
- **A real Preference Graph.** `PreferenceGraph` does not exist. `domain/ranking.py:24-48`
  records that `novelty_vs_exploration` is *"absent — needs FR-25's graph **and** an event
  category"*, and that FR-25 will replace `interest_overlap` with the real graph at 0.40. This
  item builds the dismissal and mute machinery; it does not build the graph that would change
  the published ranking weights — that is a PRD amendment (A-10's pattern, `docs/adr/ADR-0025.md`).
- **Changing the ranking weights.** The FR-22 formula keeps its published values. A category
  mute is a filter, not a new weight.
- **Any change to `SourceObservation`'s `dismissed` kind.** `OBSERVATION_SIGNS["dismissed"] = 0`
  (`constants.py:162-167`) is the *editorial* dismissal — *"a dismissal is recorded as a fact
  (an editor looked) and contributes nothing to the counts."* A user swipe is a different
  fact, in a different schema, for a different purpose. They must not be conflated.
- **The source mute.** That is `source-transparency-and-mute`'s, on a different subject.

## Corrections to the brief

| The brief says | The code says | Decision |
|---|---|---|
| AD-4 says embeddings *"only route editorial review candidates"*, so using them to rank user-facing content needs a spine amendment | The spine's rule (`ARCHITECTURE-SPINE.md:82-88`) is *"**Embedding cosine similarity is never an identity signal.** Cosine ≥0.95 routes a pair to the editorial review queue as 'possible duplicate'."* AD-4 binds **identity**. FR-25 clusters **preference** | D12 — a **finding**, not an amendment |
| Per-event embeddings need "a vector column, pgvector migration, backfill, a production `EmbeddingPort` caller" | True, and one thing more: **no real Voyage adapter exists**, and `ADAPTER_MODE=real` refuses to boot without one (`config/adapters.py:47-51`). There is no `adapters/llm/voyage.py` | D16 — the adapter is a deliverable, not an assumption |
| The prompt is "reversible from settings", and `settings-sources-surface` may be that surface | The mockup says **twice**: *"You can undo anytime in **Settings → Taste**"* (`:122`) and *"`Settings → Taste → Muted categories` lists every active mute"* (`:149`). No such route exists. FR-25's subject is a **category**; the Sources screen's subject is a **source** | D19 — a new `/settings/taste` route, not the Sources screen |
| "A dismissal is user content under the never-delete constraint" | `personal` rows are hard-deleted on undo throughout (`saved_events.py:278`, `personal_events.py:438`, `onboarding.py:317`). Never-delete binds catalog rows and append-only tables (`shared/models.py:70-97`) | D17 — hard delete on undo |
| The mockup is 5 lines of header | It is a full specification: decay (60d half, 180d expire), a rage-dismiss guard, slot-3 immunity, mute durations (7/30/90 days or indefinite), two copy variants, and the exact clustering rule | D20–D24 |

The last row matters most. The briefs read the mockup's header comment and stopped. The specs
panel at the bottom of the file (`:146-153`) specifies the behaviour in detail, and a design
built from the header alone would be wrong about the decay, the guard and the immunity.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| D12 — The AD-4 question | **Record a finding that the use is within AD-4.** No spine amendment. The finding cites the spine's verbatim rule and names the distinction | AD-4's rule is *"Embedding cosine similarity is never an identity signal."* FR-25 never decides identity — it groups a user's *preference* signal. The two decisions are different in kind: identity decides whether two rows are one event (and merges them); clustering decides whether two things the user swiped away resemble each other (and never merges anything). The briefs misquote the spine as *"only route editorial review candidates"*; the actual clause is *"never an identity signal"*, and the second clause (cosine ≥0.95 → review queue) is about *identity*, not about every cosine comparison everywhere. The brief itself names a finding as an acceptable outcome. The finding must still be written, because the constitution says deviating from an AD requires amending the spine first — and a finding that this is *not* a deviation is the cheapest way to discharge that duty. It goes in the spine's own record, as ADR-0025 did for the ranking weights |
| D13 — What is embedded | The **event's public text** — title plus category chips — one vector per catalog `Event`, stored **quantized at 256 dimensions** | The spine pins `voyage-4-lite` and says *"Matryoshka dimensions allow truncating to 512 or 256."* 256 halves storage and cosine work, and is ample for a ≥0.7 grouping threshold. Embedding public text is what makes the cosine mean *similar events* rather than *similar words in one title*. The category chips matter because the prompt's copy names a category ("Less rooftop jazz?") — the cluster must be able to name it |
| D14 — Where the vector lives | A `catalog.ingestion_event.embedding` column of type `vector(256)`, written **only** by `ingestion` | `ingestion` is the sole writer of `catalog` (AD-4, AD-16), so the embed call belongs there and nowhere else. The pgvector extension is already provisioned and unused: `docker/postgres/init/01-schemas-and-roles.sh:75-76` runs `CREATE EXTENSION IF NOT EXISTS vector` in `public`, and the CI image is `pgvector/pgvector:0.8.6-pg18`. The `pgvector` **Python** package is absent from `backend/pyproject.toml` and must be added in the same change as the column |
| D15 — Cost accounting | Every embed call writes a cost row through the same gateway as the LLM | AD-8: *"embeddings therefore come from `voyage-4-lite`, behind the same gateway, with the same per-call cost row."* `EmbeddingResult` already carries `cost_micros` (`ports/embedding.py:12-16`) — the plumbing exists and is unused. Embedding every event is a real cost and must appear in the AI Cost Dashboard like every other call |
| D16 — The real adapter | **Build the Voyage adapter as part of this item** | There is no `adapters/llm/voyage.py`. `REAL_ADAPTERS` has no `"embedding"` key, and `config/adapters.py:47-51` says so outright: *"the real Stripe adapter … does not make `ADAPTER_MODE=real` bootable — `llm`, `embedding` and `email` are still missing."* A clustering rule over vectors that no production code produces is a rule over nothing. This is the largest piece of infrastructure in the item and the brief did not name it. The `FakeEmbeddingAdapter` stays the test double — the testing standards say to fake at the port boundary, never to mock the ORM |
| D17 — The dismissal record | A `personal.EventDismissal`: `user_id` + `event_id` **by value**, unique per pair, `PREFERENCE_SIGNALS`, **hard-deleted on undo** | `EventNoticeMute` is the exact shape (`delivery/models.py:598-640`) and `SavedEvent` the exact precedent (`personalization/models.py:276-281`: *"`event_id` is the catalog Event's id **by value** — never a foreign key, because AD-3 forbids a relation across the schema wall"*). The work item's "never-delete" framing does not apply: `personal` rows are hard-deleted on undo throughout. Undo of a dismissal deletes the row, and the cluster counter recomputes |
| D18 — The mute | A `personal.CategoryMute`: `user_id` + `category_key`, `expires_at` (nullable = indefinite), a duration choice of 7 / 30 / 90 days, and one-tap unmute | The mockup's subject is a **category** — "Less rooftop jazz in your next digest?" — so the mute keys on a category, not on an event and not on a source. `expires_at` nullable gives the mockup's "indefinite" without a second code path. The mockup's reversal is *"One tap unmutes"* — so the row is deleted, not flipped to a `muted=false` state |
| D19 — The reversal surface | **A new `/settings/taste` route** with a "Muted categories" section, sibling to `/settings/sources` in the settings nav | The mockup names it twice (`:122`, `:149`). No such route exists — `frontend/app/settings/` holds account, calendars, collections, digest, profile, quiet-hours and reminders, and no taste. Building it is this item's work, not a dependency on another intent. The settings nav is one list (`SETTINGS_SECTIONS`), so adding the route makes it reachable everywhere at once |
| D20 — The clustering rule | Cosine ≥0.7 between the newest dismissal and **each** of the previous two, over **3 distinct events**, within a **24-hour digest window** | The mockup: *"3 distinct events dismissed across a digest window (default: a calendar day), embedding cosine ≥0.7 between them."* "Distinct" excludes the same event dismissed twice, which is what the `UniqueConstraint(["user_id","event_id"])` already guarantees. "Each of the previous two" rather than "any pair" makes the cluster tight — all three must be mutually close, not merely two of them |
| D21 — The rage-dismiss guard | Rapid 3-swipes in **<5s** are rate-limited: **only the first dismissal counts** toward the cluster counter; the next two are recorded but do not advance | The mockup states it: *"Rage-dismiss guard: rapid 3-swipes in <5s are rate-limited — only the first dismissal counts toward the cluster counter; the next two are recorded but do not advance."* This is a dark-pattern guard, not a nicety — the same mockup that forbids nagging forbids rewarding a swipe-spree. A per-dismissal `cluster_advanced` boolean records the distinction, so the counter and the record can disagree |
| D22 — Slot 3 immunity | Discovery cards are **not** clustering candidates | The mockup: *"Slot 3 immunity: discovery cards are tagged `discovery, new-to-you` and are NOT candidates for clustering — serendipity is protected."* The anchor is real: `RANKING_TAG_DISCOVERY = "discovery"` (`constants.py:973-980`) and `domain/ranking.py:468-469` — *"Slot 3 (`serendipity=True`) shows `discovery`, and never a chip tag."* The tag already exists; the immunity is a rule that reads it |
| D23 — Decay | Dismissal signals decay: **60 days halves the weight, 180 days expires**. The cluster counter therefore decays too | The mockup: *"even without explicit mute, dismissal signals decay — 60 days halves the weight, 180 days expires. The system never permanently bans a category (PRD: serendipity is a product decision, not a user preference)."* The principle is stated in the PRD and is worth keeping verbatim in the code: a category is never permanently banned |
| D24 — The prompt fires once | The prompt fires **once per cluster**. The counter resets when it fires and when a mute is created. It never reappears for the same cluster | The mockup's *"No dark-pattern nag"* and the brief's *"the prompt is reversible from settings"*. A prompt that reappears on every subsequent dismissal is the dark pattern the mockup forbids. Once the user has answered — either way — the cluster is spent |
| D25 — Where the mute takes effect | In `compose_digest`, a **category** is excluded from the candidate pool — a hard "not these" | Unlike the source mute's `show_less`, a category mute is unambiguous: the user asked for less of a category, so those candidates are excluded. Applied at the candidate set, the same seam as the source mute, before scoring |
| D26 — The swipe | A swipe-down gesture on the Pulse Card, **plus** a keyboard-reachable button with the same action, visually secondary | The mockup specifies the swipe. A gesture-only control fails the PRD §11.5 accessibility gate — `axe-core` runs in CI on PRD §11.5 surfaces, and a gesture has no keyboard equivalent. The button must be present, focusable and labelled, but secondary so the swipe stays the primary affordance. The mockup's own prompt pattern shows the accessibility bar it expects: `role="dialog"` + `aria-labelledby` + `aria-describedby`, and *"Focus moves to 'Mute for 30 days' on open (the affirmative — calm default)"* |

## Data Models Affected

### Creates

**In `personal`** (`backend/apps/personalization/models.py`):

- **`EventDismissal`**: `user_id` UUIDField (by value) · `event_id` UUIDField (by value) ·
  `dismissed_at` timestamptz · `cluster_advanced` boolean · `created_at` — one row per event
  the user swiped away. `cluster_advanced` is the rage-dismiss guard's record: a dismissal is
  always stored, but only an advanced one counts toward the cluster counter.

  Constraints: `UniqueConstraint(["user_id", "event_id"])` · `Index(["user_id", "-dismissed_at"])`.
  Retention: `PREFERENCE_SIGNALS` — *"the category whose own words are 'dwell, swipes,
  dismissals'"*.

- **`CategoryMute`**: `user_id` UUIDField (by value) · `category_key` varchar · `expires_at`
  timestamptz (nullable — null is indefinite) · `created_at` · `updated_at` — the user's
  request for less of a category.

  Constraints: `UniqueConstraint(["user_id", "category_key"])` · `Index(["user_id"])`.
  Retention: `PREFERENCE_SIGNALS`.

### Modifies

**In `catalog`** (`backend/apps/ingestion/models.py`):

- **`Event.embedding`**: `vector(256)`, nullable — the event's embedding, written only by
  `ingestion` (AD-4). Nullable because the backfill is a separate, resumable command, not a
  migration: a migration that backfills every event would embed the whole corpus inside a
  schema transaction.

## Technical Approach

### Architecture

```
                    ┌──────────────────────────────────────────────┐
   swipe / button   │  POST /api/personal/dismissals               │
   on Pulse Card ───►  { event_id }                                │
                    │  → 200 { cluster_advanced, prompt_due }      │
                    └───────────────┬──────────────────────────────┘
                                    ▼
      ┌─────────────────────────────────────────────────────────────────┐
      │  personalization                                                │
      │                                                                 │
      │   dismissals.py                                                  │
      │     record_dismissal(user_id, event_id)                         │
      │       → personal.EventDismissal  (cluster_advanced per D21)     │
      │     cluster_state(user_id)                                       │
      │       → reads catalog.Event.embedding  (by value, via read port) │
      │       → cosine ≥0.7 across 3 distinct, within 24h (D20)         │
      │       → applies decay (60d half / 180d expire) (D23)           │
      │       → prompt_due?  fires ONCE per cluster (D24)               │
      │                                                                 │
      │   taste_mutes.py                                                 │
      │     set_category_mute(user_id, key, duration) ─────────────────►│──► personal.CategoryMute
      │     unmute_category_mute(user_id, key)                          │
      │     active_category_mutes(user_id)                              │
      │                                                                 │
      │   compose_digest()  ── exclude muted categories (D25) ──────────│──► candidate set
      └───────────────┬─────────────────────────────────────────────────┘
                      │ reads candidates by value
                      ▼
      ┌─────────────────────────────────────────────────────────────────┐
      │  ingestion  (catalog)  — sole writer (AD-4)                     │
      │                                                                 │
      │   Event.embedding  vector(256)          ◄── written here only   │
      │                                                                 │
      │   embed_event() ──► EmbeddingPort.embed(texts, dimensions=256)  │
      │        │                                                        │
      │        ├─► VoyageEmbeddingAdapter (adapters/llm/voyage.py)  NEW │
      │        │        └─► Voyage AI · cost_micros → cost row (AD-8)   │
      │        └─► FakeEmbeddingAdapter (tests only)                    │
      │                                                                 │
      │   embed_backfill  (resumable command, not a migration)          │
      └─────────────────────────────────────────────────────────────────┘

      ┌─────────────────────────────────────────────────────────────────┐
      │  frontend                                                       │
      │   Pulse Card  ── swipe down / secondary button (D26)           │
      │   Prompt sheet ── role="dialog" · calm copy · once (D24)        │
      │   /settings/taste ── "Muted categories" · one tap unmute (D19) │
      └─────────────────────────────────────────────────────────────────┘
```

### API Changes

- `POST /api/personal/dismissals` — record a dismissal of one event. The response says
  whether the dismissal advanced the cluster and whether the prompt is now due, so the
  frontend does not have to re-derive the rule. Idempotent on `(user_id, event_id)`: a second
  dismissal of the same event updates `dismissed_at` rather than adding a row.
- `GET /api/settings/taste` — the user's active category mutes, with their expiry.
- `PUT /api/settings/taste/mutes` — set a mute on a category with a duration (7 / 30 / 90
  days, or indefinite).
- `DELETE /api/settings/taste/mutes/{category_key}` — unmute. One tap, per the mockup.

The `/settings` family today is one route (`delivery/preferences_api.py:49-122`) whose PUT is
patch-shaped. These follow that convention. `POST /api/personal/dismissals` sits with the
other personal endpoints (`personalization/api.py`).

The prompt's own copy lives with the dismissals response, so the frontend renders server-owned
text — the same rule AD-10 sets for Event Fit tags: *"the server states facts, the client
speaks the user's language"* (`source_badges.py:14-17`).

### Database Changes

```sql
-- catalog: the vector column. Written only by ingestion (AD-4).
ALTER TABLE catalog.ingestion_event
    ADD COLUMN embedding vector(256);

-- personal: the dismissal record.
CREATE TABLE personal.personalization_eventdismissal (
    id               uuid        PRIMARY KEY,
    user_id          uuid        NOT NULL,
    event_id         uuid        NOT NULL,
    dismissed_at     timestamptz NOT NULL,
    cluster_advanced boolean     NOT NULL DEFAULT false,
    created_at       timestamptz NOT NULL,
    updated_at       timestamptz NOT NULL,
    CONSTRAINT event_dismissal_user_event_uq UNIQUE (user_id, event_id)
);
CREATE INDEX event_dismissal_user_recent_idx
    ON personal.personalization_eventdismissal (user_id, dismissed_at DESC);

-- personal: the category mute.
CREATE TABLE personal.personalization_categorymute (
    id           uuid        PRIMARY KEY,
    user_id      uuid        NOT NULL,
    category_key varchar(64) NOT NULL,
    expires_at   timestamptz,
    created_at   timestamptz NOT NULL,
    updated_at   timestamptz NOT NULL,
    CONSTRAINT category_mute_user_category_uq UNIQUE (user_id, category_key)
);
CREATE INDEX category_mute_user_idx
    ON personal.personalization_categorymute (user_id);
```

No foreign key to `catalog.ingestion_event` — AD-3 makes that impossible, and the ORM
enforces it. `expires_at` nullable means indefinite.

The vector column's `ALTER TABLE` requires the `vector` type, which the database init script
already creates in `public` (`01-schemas-and-roles.sh:75-76`), and the `pgvector` Python
package, which is not yet installed.

## Dependencies

- **`settings-sources-surface`** — **not a dependency.** The briefs assumed FR-25's
  reversal surface was the Sources screen; the mockup says `Settings → Taste` (D19). FR-25
  builds its own route. The two intents share the settings nav and the composition seam, and
  the builder should coordinate those two touch points, but the ordering is free.
- **`Event.category`** — **must be added.** The category mute keys on a category, and no
  `Event` category field exists. `domain/ranking.py:24-48` already names it as one of the two
  things FR-25 owes the ranking formula. It is a `catalog` field, written by `ingestion`,
  and it is the reason the prompt can name a category rather than say "events like these".
- **`EmbeddingPort` + `EmbeddingResult`** — **exist** (`ports/embedding.py`). The port, the
  fake adapter and the registry are all in place; the production caller is what is missing.
- **`VoyageEmbeddingAdapter`** — **must be built** (D16).

## Affected Files

| File | Action | Purpose |
|------|--------|---------|
| `backend/pyproject.toml` | modify | add the `pgvector` dependency |
| `backend/adapters/llm/voyage.py` | create | the real embedding adapter (D16) |
| `backend/config/adapters.py` | modify | register it in `REAL_ADAPTERS` |
| `backend/ports/embedding.py` | modify | pin the 256-dimension constant |
| `backend/apps/ingestion/models.py` | modify | `Event.embedding` (`vector(256)`) and `Event.category` |
| `backend/apps/ingestion/migrations/00XX_event_embedding.py` | create | the vector column |
| `backend/apps/ingestion/services/embedding.py` | create | the embed command and its cost row |
| `backend/apps/ingestion/services/embedding_backfill.py` | create | the resumable backfill command |
| `backend/apps/personalization/models.py` | modify | `EventDismissal`, `CategoryMute` |
| `backend/apps/personalization/migrations/00XX_dismissal_and_mute.py` | create | the two personal tables |
| `backend/apps/personalization/services/dismissals.py` | create | record, cluster, decay, prompt-due |
| `backend/apps/personalization/services/taste_mutes.py` | create | the category mute commands |
| `backend/apps/personalization/services/digest_composition.py` | modify | exclude muted categories (D25) |
| `backend/apps/personalization/dismissals_api.py` (or `api.py`) | modify | the dismissal endpoint |
| `backend/apps/personalization/taste_api.py` | create | the `/api/settings/taste` endpoints |
| `backend/config/api.py` | modify | mount the taste router |
| `backend/domain/` | — | **unchanged.** The cosine rule is a service concern: `domain/` is stdlib-only, and `backend/tests/domain/test_domain_api.py` already asserts that `domain/` contains no symbol matching `embed`/`cosine`/`vector`/`similar` |
| `frontend/components/digest/pulse-card.tsx` | modify | the swipe and the keyboard-reachable button (D26) |
| `frontend/components/digest/mute-prompt.tsx` | create | the prompt sheet |
| `frontend/app/settings/taste/page.tsx` | create | the reversal surface (D19) |
| `frontend/app/settings/taste/loading.tsx` | create | sibling loading state |
| `frontend/lib/settings-sections.ts` | modify | add the "Taste" row |
| `frontend/lib/api/` | regenerate | `make client` output committed (AD-19) |
| `backend/tests/personalization/test_dismissal_clustering.py` | create | the rule, the guard, the decay |
| `backend/tests/personalization/test_category_mutes.py` | create | the mute and its effect on composition |
| `backend/tests/ingestion/test_embedding_backfill.py` | create | the backfill is resumable and costed |
| `frontend/app/settings/taste/page.test.tsx` | create | component tests |
| `frontend/e2e/` | modify | the journey + `axe-core` |

## Security Considerations

- **Auth at the edge.** The dismissal endpoint takes `auth=current_user`; every query filters
  on the authenticated `user_id`.
- **Untrusted input.** Source content is untrusted input (AD-9). An event's title is
  extracted from a source and is therefore untrusted text going into an embedding call.
  It is never executed and never rendered raw. The embedding is a numeric vector; the only
  path back to the user is the cluster's category label, which comes from the **catalog's**
  category chips, not from the title.
- **No PII.** A dismissal is a UUID pair and a timestamp. The event's own text is not copied
  into the personal schema — the vector stays in `catalog`, and the personal row references
  the event by value.
- **Cost abuse.** An embedding endpoint that accepts arbitrary text would be a money leak.
  `POST /api/personal/dismissals` accepts **only an `event_id`** — the server reads the text
  to embed. The user never supplies text to embed, and the rate limiter applies.
- **The prompt's copy is server-owned.** It is derived from catalog category chips and
  rendered as text, never as markup.
- **Retention.** Both personal tables are `PREFERENCE_SIGNALS` and are swept by the retention
  registry (AD-15). The vector column is catalog data and is swept with the catalog.

## Integration Points

| System | Type | Purpose |
|--------|------|---------|
| `EmbeddingPort` | read | the embed call (the first production caller) |
| `Voyage AI` | external | `voyage-4-lite`, Matryoshka-truncated to 256 dims, quantized |
| Voyage AI cost ledger | write | every embed call's cost row, through the AD-8 gateway |
| `catalog.Event.embedding` | write (ingestion only) | the vector the clustering reads |
| `catalog.Event.category` | write (ingestion only) | the category the prompt names and the mute keys on |
| `personal.EventDismissal` | write | the dismissal record |
| `personal.CategoryMute` | write | the category mute |
| `compose_digest` | internal | excludes muted categories (D25) |
| `Pulse Card` | frontend | the swipe and the button (D26) |
| `SETTINGS_SECTIONS` | write | the settings nav row for Taste (D19) |
| OpenAPI client | generated | the contract (AD-19) |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **No real Voyage adapter exists, and `ADAPTER_MODE=real` refuses to boot without one** (`config/adapters.py:47-51`) | High — the entire feature depends on vectors no production code produces | D16 makes the adapter an explicit deliverable of this item. The `FakeEmbeddingAdapter` remains the test double (testing standards: fake at the port boundary). The backfill and the clustering are testable end to end against the fake before the real adapter lands |
| The `pgvector` Python package is absent | High | Add it in the same change as the vector column. The database extension is already enabled (`01-schemas-and-roles.sh:75-76`); only the client library is missing |
| Embedding every event is a real cost, and the corpus is unknown | High | AD-8 cost accounting on every call (D15), so the AI Cost Dashboard shows it from day one. 256 dims, quantized, per the spine. The backfill is a **resumable command, not a migration** (D14) — it can be paced, paused and re-run |
| The AD-4 finding is rejected, and the work becomes a spine amendment | Medium | That is a fallback, not a failure: the amendment is a document, and the build continues behind it. The finding (D12) is written before any migration, so this is discovered at Checkpoint 1 rather than mid-build. The design cites the spine's verbatim rule so the reviewer can check the claim directly |
| AD-4 is read as forbidding this, and the work is blocked | Medium | D12 settles it in writing with the spine's actual words — *"never an identity signal"*, not *"never used for ranking"*. Checkpoint 1 is a human gate precisely so this is caught before code |
| The swipe is gesture-only and fails the accessibility gate | Medium | D26 requires a keyboard-reachable equivalent with the same action. `axe-core` runs in CI on PRD §11.5 surfaces, and a gesture has no keyboard equivalent |
| The prompt nags | Medium | D24: once per cluster, the counter resets when it fires, and the cluster decays (D23). A test asserts the prompt does not reappear for the same cluster |
| A swipe-spree is counted as a preference | Medium | D21: the rage-dismiss guard records but does not advance, so three fast swipes never produce a prompt. The `cluster_advanced` column makes the distinction auditable |
| Slot 3 immunity is claimed but not enforced, and serendipity gets muted away | Medium | D22 anchors it to the existing `discovery` tag (`constants.py:980`, `ranking.py:468-469`). A test asserts a Slot 3 card is never a clustering candidate |
| The category mute needs an `Event.category` field that does not exist | Medium | Recorded as an explicit dependency. The field is written by `ingestion` in `catalog`, and `domain/ranking.py:24-48` already names it as owed by FR-25 — so it belongs here, not to a later intent |
| Two mute controls exist (sources and categories) | Medium | Named distinctly and placed on sibling screens: *a source* on `/settings/sources`, *a category* on `/settings/taste`. The Subjects differ; the controls are not interchangeable. This is the correction to the brief's assumption, and it is why the coupling was dropped rather than implemented |
| The prompt's copy names a category that does not match what the user swiped | Medium | The category comes from the cluster's most-common category chip (the mockup's "explicit category" variant), with the generic "Less events like these in your next digest?" as the fallback when the cluster does not map to a single category. The mockup specifies both variants; both are implemented |
| `domain/` is asked to hold the cosine rule | Medium | It is not. The rule lives in `personalization/services/dismissals.py`. `backend/tests/domain/test_domain_api.py` already asserts `domain/` contains no `embed`/`cosine`/`vector`/`similar` symbol — a placement in `domain/` fails that test |

## Implementation Checklist

- [ ] Write the AD-4 finding (D12) with the spine's verbatim rule, and have it approved as
      part of Checkpoint 1 — **before** any migration is written
- [ ] Add the `pgvector` dependency; pin the 256-dimension constant in `ports/embedding.py`
- [ ] Build `VoyageEmbeddingAdapter`; register it in `REAL_ADAPTERS`; write its cost row
- [ ] `Event.embedding` (`vector(256)`) + `Event.category`, with a forward-only migration
- [ ] A resumable backfill command — not a migration — that embeds unembedded events and
      can be paused and re-run
- [ ] `EventDismissal` and `CategoryMute` models + migrations with AD-15 retention declarations
- [ ] `dismissals.py`: record, the cluster rule (3 distinct, cosine ≥0.7, 24h window), the
      rage-dismiss guard, the decay (60d half / 180d expire), and the once-per-cluster prompt
- [ ] `taste_mutes.py`: set with a duration, unmute, list active
- [ ] Category mutes excluded at composition; a test proves the composition changes, not
      merely that a row was written
- [ ] `POST /api/personal/dismissals` returning `cluster_advanced` and `prompt_due`
- [ ] The swipe on the Pulse Card **and** the keyboard-reachable button (D26)
- [ ] The prompt sheet: calm copy, `role="dialog"`, `aria-labelledby`, `aria-describedby`,
      focus to the affirmative, dismissible without choosing, fires once
- [ ] Both copy variants: explicit category, and the generic fallback
- [ ] `/settings/taste` with "Muted categories" and one-tap unmute; a `SETTINGS_SECTIONS` row
- [ ] `make client` output committed
- [ ] Tests: the clustering rule, the guard, the decay, slot-3 immunity, the prompt firing
      once, the mute changing composition, the ADR/D-12 finding recorded
- [ ] Every test verified by a mutation probe that makes it fail
- [ ] `axe-core` clean on the Pulse Card and the new surface (PRD §11.5)

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-11-13*
