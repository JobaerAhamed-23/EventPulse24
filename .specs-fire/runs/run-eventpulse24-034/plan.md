---
run: run-eventpulse24-034
work_item: less-like-this-adjustment
intent: relevance-feedback-loop
mode: validate
checkpoint: plan
approved_at: pending
---

# Implementation Plan: FR-25 "Less like this" — the Feedback Loop, From the Swipe to the Mute

## Approach

Build FR-25's loop in the order the dependencies actually run: the vocabulary the mute
keys on, then the embedding infrastructure the clustering reads, then the dismissal
record, then the clustering rule, then the category mute, then the endpoints, then the
screen and the prompt.

**But before any of that: four findings from reading the codebase against the design
doc, each of which changes the shape of the work.** The design doc was written from the
briefs and the mockup; these four came from reading the code. They are recorded here
rather than discovered mid-build, because three of them change what gets built.

### Finding 1 — There is no cost-row model, and AD-8 requires one (D15 is bigger than it looks)

The design says *"every embed call writes a cost row through the same gateway as the
LLM"*. **There is no gateway, and there is no cost row.** Verified:

- `ports/llm.py:24` and `ports/embedding.py:16` both carry `cost_micros` on their result
  dataclasses, and `adapters/llm/fake.py:28,53` return `cost_micros=0`.
- `adapters/logging/redaction.py:30` allow-lists `"cost_micros"` in log payloads — so the
  *shape* is anticipated.
- **But no model has a `cost_micros` column**, no gateway service exists, and there is no
  production caller of `EmbeddingPort` at all.

So D15 is not "wire the existing cost path". It is **build the cost path**: a table, a
migration, and a writer. The coding standard states the rule
(`.specs-fire/standards/coding-standards.md:108`: *"the gateway writes 'a per-call cost
row in the same transaction as the result'"*), and `tech-stack.md:96` says the same
thing. This item is the first caller, so this item builds it.

**The plan builds a `personal.AICostRow`** (see *The cost row* below), because a cost row
is a per-call fact about the user's own traffic and belongs with the user's data — and
because `personal` is where the `personalization` app already owns tables, so the
embedding command does not have to reach across the wall to write it.

### Finding 2 — `Event.category` must NOT be added, and the reason is a precedent (D13/D25 change)

The design says `Event.category` *"must be added"*. **The codebase already has the
category, and it deliberately is not a stored column.**

`apps/ingestion/services/chip_matching.py` computes `chip_keys` for every event at read
time — the chip keys the event's own title and description match, from a small
hand-written keyword table (`shared/constants.py:664+`). `catalog_read.py:280,344`
projects it onto `PublicEventCandidate`. Its module docstring explains why it is *not* a
column:

> *"**Why it is a pure function and not a stored column.** A `chip_keys` column on `Event`
> would need a migration, a write-time computation and a backfill for every existing
> event — and it would be *wrong* the moment the keyword table changed. The matching is a
> function of the event's text and a small, stable table, so computing it at read time is
> both simpler and more correct."*

`shared/constants.py:628-634` and `domain/ranking.py:29,33` both say *"Event has no
category field"* — and the *interest term* of FR-22 (the largest weight, `0.45`) already
reads `chip_keys` today. So the codebase has a category-equivalent, in production, on the
ranking path. Adding a *second* one would be a second opinion about what an event is —
which is exactly what `domain/sources.py` exists to prevent, applied to events.

**So the category mute keys on the chip key, not on a new field.** The design's
`Event.category` column is dropped.

**But the vocabulary does not match the mockup.** The mockup's example is *"Less rooftop
jazz?"* and its cards carry a `jazz · rooftop` tag-pill — and **neither "jazz" nor
"rooftop" is in `INTEREST_CHIP_KEYWORDS`.** The chip vocabulary is 10 broad buckets
(`tech_meetups`, `arts_culture`, …); the mockup's is a fine-grained genre+format pair.

**This is a real question, and the plan answers it: the chip key is the mute's key, and
the *cluster's own* wording is the label.** The mute is keyed on a chip key (stable,
already a vocabulary the user picked at onboarding, already in `personal`), and the
prompt's copy names the category **from the chip key's label** — *"Less arts & culture?"*
— with the mockup's fine-grained example preserved as the mockup's illustration of the
*shape* of the copy rather than the *vocabulary* of it. The alternative — inventing a
finer category vocabulary — would be a second taxonomy, and it would have to be
backfilled, stored, and maintained, for a screen that needs one string.

**The mockup's own specs panel supports this reading**: the trigger rule is *"3 distinct
events dismissed… embedding cosine ≥0.7"* — the *embedding* is what decides the cluster,
not a category field. The category is what the prompt *names afterwards*. So the
clustering needs the embedding; the naming needs a category; and the category the
codebase already has is the chip key.

### Finding 3 — Slot-3 immunity cannot be enforced from the candidate (D22 changes shape)

The design says discovery cards are not clustering candidates, anchored to
`RANKING_TAG_DISCOVERY`. **The candidate carries no slot information.**

- `PublicEventCandidate` (`catalog_read.py:212-299`) has no slot field and no
  `is_discovery` flag.
- Slot membership is decided at *scoring* time: `_assign_slots()` (`digest_composition.py:484-615`)
  picks slot 3 with `serendipity=True` (`:605`), and `domain/ranking.py:509-510` appends
  the `discovery` tag *from that flag*, not from the event's data.
- `DigestComposition.slot` exists (`personalization/models.py:1036`), and the composition
  is keyed `(user_id, event_id, -composed_at)` (`models.py:1106-1108`) — **so the lookup
  exists.**

**So the immunity is enforced at the dismissal, not at the clustering.** The dismissal
endpoint resolves the event's slot from the user's latest composition; a slot-3 event
records the dismissal but is **not a clustering candidate**. This is more faithful to the
mockup than the design's version, which would have needed the candidate to carry a slot
it cannot know.

**The design's `EventDismissal` therefore gains a `slot` field**, and the clustering rule
filters on it. The row records what the card *was*, which is a fact about the composition
the user saw — and `personalization` owns that composition, so it reads it from its own
table. No cross-wall read.

### Finding 4 — The embedding read crosses the wall, so it needs a published read port

`personalization` may not import `apps.ingestion.models` (AD-3, enforced by
`config/checks.py:50-77`). So the clustering rule — which lives in
`personalization/services/dismissals.py` — **cannot read `Event.embedding` directly**.

The design's own architecture diagram says *"reads catalog.Event.embedding (by value, via
read port)"* — and that read port **does not exist and is not in the affected-files
table.** So this item adds one: an `ingestion` service that returns `(event_id,
embedding)` tuples by value, in the same shape `catalog_read` already uses. This is the
fourth thing the affected-files table misses, alongside the cost row, `catalog_read.py`,
and the `Event.category` column that Finding 2 removes.

### The one open question this plan cannot close for you

**Whether the prompt's copy names the chip key's label (*"Less arts & culture?"*) or
something finer (*"Less rooftop jazz?"*).** The plan takes the first, because the second
needs a category vocabulary the codebase does not have and that the mockup does not
specify as a table. If the finer wording is wanted, it needs a vocabulary decision and
its own backfill — which is a bigger item than this one, and would change `Event`'s shape
back.

Everything else below is settled by the code.

## What the codebase decides, and the plan follows rather than re-derives

1. **The mute row lives in `personal`, keyed by value.** `EventNoticeMute`
   (`delivery/models.py:598-644`) is the exact shape: `PREFERENCE_SIGNALS`, `user_id` +
   `event_id` by value, `UniqueConstraint(["user_id", "event_id"])`, no third-party text.
2. **Retention is a class attribute, not a column.** `retention_category =
   RetentionCategory.PREFERENCE_SIGNALS` (`shared/retention.py:23`), enforced by
   `config/checks.py:80-106` (E003/E004). It never appears in a migration.
3. **A new `personal` table needs no grants.** `docker/postgres/init/01-schemas-and-roles.sh:68-73`
   grants SELECT/INSERT/UPDATE/DELETE on all new `personal` tables to `ep_personal` via
   `ALTER DEFAULT PRIVILEGES`. Only *append-only* tables need an explicit `REVOKE`.
4. **The category is the chip key** (Finding 2). Already computed, already projected,
   already the vocabulary the user picks at onboarding.
5. **The domain layer stays pure.** `backend/tests/domain/test_domain_api.py:10,29-33`
   forbids any symbol matching `embed`/`cosine`/`vector`/`similar` in `domain/` — so the
   cosine rule lives in `apps/personalization/services/dismissals.py`.
6. **`domain/ranking.py` keeps its published weights.** FR-22's five terms are
   CI-pinned (`backend/tests/shared/test_constants.py:147-153`). A category mute is a
   *filter*, not a weight.

## The order the work actually runs in

```
 1. Vocabulary & constants        chip key is the category; the thresholds are constants
 2. The cost row                 personal.AICostRow + migration + writer  (Finding 1)
 3. The embedding adapter        VoyageEmbeddingAdapter + REAL_ADAPTERS   (D16)
 4. The vector column            catalog.ingestion_event.embedding vector(256)
 5. The embed command            ingestion/services/embedding.py — write the vector, cost it
 6. The backfill                 a resumable command, not a migration
 7. The read port                ingestion/services/event_embeddings.py — (id, vector) by value
 8. The personal rows            EventDismissal (+ slot) and CategoryMute
 9. The dismissal service        record, the guard, the cluster, the decay, the prompt
10. The category mute service    set with a duration, unmute, list active
11. The composition filter       exclude muted chip keys from the candidate set
12. The endpoints                POST /api/personal/dismissals + the three /settings/taste
13. make client                  AD-19
14. The frontend                 the swipe + the button, the prompt sheet, /settings/taste
15. The tests                    with a mutation probe each
```

## Technical details

### The cost row (Finding 1)

**`personal.AICostRow`** — a new model in `apps/personalization/models.py`:

| Field | Type | Note |
|---|---|---|
| `id` | UUID7 PK | the house key |
| `user_id` | UUID | by value; `null=True` for a system-initiated call (a backfill) |
| `kind` | Char(16) | `embedding` — the model's kind, so the table can hold the LLM's rows later |
| `model` | Char(64) | `voyage-4-lite` |
| `input_tokens` | PositiveInteger | |
| `output_tokens` | PositiveInteger | 0 for an embedding |
| `cost_micros` | PositiveInteger | integer micro-dollars, never a float (`ports/llm.py:24`) |
| `call_count` | PositiveInteger | how many texts the call covered |
| `created_at` | timestamptz | |

`retention_category = RetentionCategory.PREFERENCE_SIGNALS` — it is a per-user fact about
their own traffic.

**The writer is the adapter, and that is AD-8's one named exception.**
`.specs-fire/standards/coding-standards.md:113`: *"An adapter writing rows is AD-5's one
named exception, by AD-8's explicit rule."* So `VoyageEmbeddingAdapter.embed()` writes
the cost row **in the same transaction as the result**, exactly as the standard words it.

**Why `personal` and not `catalog`:** the row's `user_id` is the caller's, and a
backfill's row has no user at all (`user_id = null`). A catalog table would be a
cross-schema write from `ingestion`, and AD-3 says `ingestion` writes `catalog` and
nothing else. `personal` is the schema for "facts about a user's traffic".

**The AI Cost Dashboard** — the design names it as a consumer. It does not exist yet
(it is a later intent). The table is built to be read by it: one row per call, with the
model and the cost, which is the shape a dashboard needs.

### The embedding adapter (D16)

`backend/adapters/llm/voyage.py`, modelled on `adapters/billing/stripe.py` — the
existing real adapter — and `adapters/llm/fake.py` for the port's shape.

- `VoyageEmbeddingAdapter(EmbeddingPort)` with `embed(texts, *, dimensions) -> EmbeddingResult`
- Posts to Voyage's `/v1/embeddings` with `voyage-4-lite` and `output_dimension=dimensions`
- **Quantizes** the returned vectors (`voyage-4-lite` is a Matryoshka model; the spine
  pins 512 or 256)
- Writes the cost row in the same transaction
- The API key comes from `config/env.py`, and a missing key is a `ImproperlyConfigured`,
  not a silent zero

**Registered in `REAL_ADAPTERS`** (`config/adapters.py:47-68`) under `"embedding"`. Note
the comment at `:49-51` will need updating: it says *"this does **not** make ADAPTER_MODE=real
bootable — `llm`, `embedding` and `email` are still missing."* After this change, `embedding`
is no longer missing, and the sentence has to change with it — **a stale comment that
contradicts the code is a defect, and this is the kind the review caught in run 033.**

**`llm` and `email` are still missing**, so `ADAPTER_MODE=real` still refuses to boot.
That is correct and unchanged: this item delivers the embedding adapter, and the comment
must say exactly that.

### The vector column (D14)

`ALTER TABLE catalog.ingestion_event ADD COLUMN embedding vector(256);`

- **The `vector` type lives in `public`, not `catalog`** — `01-schemas-and-roles.sh:75-76`
  runs `CREATE EXTENSION IF NOT EXISTS vector` in `public`. The migration's `RunSQL` must
  say `public.vector(256)`, or set `search_path`. **This is a trap worth naming**: the
  column type is written `public.vector(256)`, and the migration test asserts the type.
- Nullable, because the backfill is a separate resumable command, not a migration. A
  migration that backfilled would embed the whole corpus inside a schema transaction.
- The `pgvector` **Python** package is absent from `backend/pyproject.toml` — added in
  the same change.
- The column is a `catalog` column, written only by `ingestion` (AD-4, AD-16). The
  `TABLE_OWNERS` map gets no new entry — `ingestion` already owns `ingestion_event`.

**The event's text is untrusted (AD-9).** The title and description go into the embedding
call and are never executed and never rendered raw. The only path back to the user is the
category label, which comes from the **chip key** — a key from the server's own
vocabulary, not from the event's text.

### The read port (Finding 4)

`backend/apps/ingestion/services/event_embeddings.py`:

```python
def read_event_embeddings(*, event_ids: Sequence[UUID]) -> dict[UUID, tuple[float, ...]]:
    """The stored embeddings for these events, by value.

    **This is the wall.** `personalization` may not import `apps.ingestion.models`, so the
    clustering rule cannot read `Event.embedding` itself. It asks here, and gets plain
    tuples back — the same shape `catalog_read` already hands over.

    **Only events that have one.** An event with no embedding is simply absent from the
    answer: the backfill has not reached it, or its text was empty. Either way it cannot
    be clustered on, and a missing vector is not a zero vector.
    """
```

**One query, bounded.** The clustering reads at most the user's last three dismissals'
events, so the read is `WHERE id IN (...)` over three ids — not a scan.

### The dismissal record (D17, plus Finding 3)

**`personal.EventDismissal`**:

| Field | Type | Note |
|---|---|---|
| `id` | UUID7 PK | |
| `user_id` | UUID | by value |
| `event_id` | UUID | by value — the catalog Event's id, never an FK |
| `dismissed_at` | timestamptz | when the user swiped |
| `cluster_advanced` | bool | **the rage-dismiss guard's record** (D21) |
| `slot` | SmallInt | **the slot the card was in** (Finding 3) — 3 means discovery |
| `created_at` / `updated_at` | timestamptz | |

Constraints: `UniqueConstraint(["user_id", "event_id"], name="event_dismissal_user_event_uq")` ·
`Index(["user_id", "-dismissed_at"])` · `CheckConstraint(slot__in=[1, 2, 3])`.

`retention_category = RetentionCategory.PREFERENCE_SIGNALS` — and the retention constant's
own comment names dismissals: *"Preference graph signals (dwell, swipes, dismissals):
12 months rolling."*

**`cluster_advanced` and `slot` are both needed, and they are different facts.**
`cluster_advanced` says whether this dismissal counted toward the cluster counter (the
rage-dismiss guard, D21). `slot` says what the card was (the discovery immunity,
Finding 3). A slot-3 dismissal is recorded and does not advance *and* is not a candidate;
a rage dismissal in slot 1 is recorded and does not advance but *is* a candidate.

### The category mute (D18)

**`personal.CategoryMute`** — keyed on the **chip key**:

| Field | Type | Note |
|---|---|---|
| `id` | UUID7 PK | |
| `user_id` | UUID | by value |
| `category_key` | Char(64) | **the chip key** — `tech_meetups`, `arts_culture`, … |
| `expires_at` | timestamptz, nullable | null is *indefinite* (D18) |
| `created_at` / `updated_at` | timestamptz | |

Constraints: `UniqueConstraint(["user_id", "category_key"])` · `Index(["user_id"])`.

**`expires_at` nullable means indefinite** — the mockup's four durations (7/30/90 days,
indefinite) without a second code path.

**One tap unmutes** (the mockup's reversal): the row is **deleted**, not flipped to a
`muted=false` state.

### The clustering rule (D20, D21, D23)

Lives in `apps/personalization/services/dismissals.py` — **not** in `domain/`
(`tests/domain/test_domain_api.py:10` forbids `cosine`/`similar`/`vector` symbols there).

```
record_dismissal(user_id, event_id, now)
  │
  ├─ 1. Resolve the slot from the user's latest composition for that event.
  │     (slot 3 → recorded, but never a clustering candidate — D22)
  │
  ├─ 2. The rage-dismiss guard (D21).
  │     If the previous TWO dismissals were within 5s of each other AND of this one,
  │     this dismissal is recorded with cluster_advanced = False and does not advance.
  │     Otherwise cluster_advanced = True.
  │
  ├─ 3. Read the vectors (the read port) for the candidate events:
  │     the newest dismissal's event, and the previous two ADVANCED dismissals.
  │
  ├─ 4. The window (D20): all three within 24 hours.
  │
  ├─ 5. The cosine (D20): cosine ≥ 0.7 between the newest and EACH of the previous two.
  │     All three must be mutually close — "each", not "any pair".
  │
  ├─ 6. The decay (D23): a dismissal older than 180 days is expired (ignored);
  │     one older than 60 days counts for half.
  │
  ├─ 7. The prompt (D24): if all of the above hold AND the cluster has not already
  │     fired, the prompt is due. The cluster's counter resets when it fires.
  └─ 8. Return { cluster_advanced, prompt_due, prompt_copy }.
```

**The threshold is a constant, not a literal** (AD-8): `FR25_CLUSTER_COSINE_THRESHOLD =
Decimal("0.70")`, `FR25_CLUSTER_MIN_EVENTS = 3`, `FR25_CLUSTER_WINDOW_HOURS = 24`,
`FR25_RAGE_GUARD_SECONDS = 5`, `FR25_DECAY_HALF_DAYS = 60`, `FR25_DECAY_EXPIRE_DAYS = 180`,
`FR25_MUTE_DURATIONS_DAYS = (7, 30, 90)` — all in `shared/constants.py`.

**"Each of the previous two" is load-bearing.** The mockup says *"cosine ≥0.7 between
them"* — but "each" makes the cluster tight (all three mutually close) rather than loose
(two of them close). The design chose "each"; the plan follows it and the test pins it:
a cluster of two-close-and-one-distant must **not** fire.

### The prompt's copy is server-owned (AD-10)

The design says the copy lives with the dismissals response. **The copy is built from the
cluster's most-common chip key**, and the mockup's two variants become:

- **Explicit** — the cluster has one dominant chip key:
  *"Less {chip label} in your next digest?"* — e.g. *"Less arts & culture in your next
  digest?"*
- **Generic** — no single key dominates:
  *"Less events like these in your next digest?"*

The description follows the mockup's shape:
*"You've swiped past 3 similar events. Want us to deprioritize this category for a while?
You can undo anytime in Settings → Taste."*

**The chip label comes from `shared.constants.INTEREST_CHIPS`** — the server's own
vocabulary, not the event's text. A user cannot get arbitrary text into the prompt.

### The endpoints

- `POST /api/personal/dismissals` — body `{ event_id }` → `{ cluster_advanced, prompt_due,
  prompt }`. **Accepts only an `event_id`** — never text to embed. That is the cost-abuse
  guard: the server reads the text, the user never supplies it.
- `GET /api/settings/taste` — the user's active category mutes, with their expiry and the
  chip's label.
- `PUT /api/settings/taste/mutes` — body `{ category_key, duration_days }` where
  `duration_days` is `7 | 30 | 90 | null` (null is indefinite).
- `DELETE /api/settings/taste/mutes/{category_key}` — unmute. One tap.

**`restore-defaults` is declared before `{category_key}`**, for the same reason
`source_mutes_api.py` declares it before `{source_id}`: Django matches the path first and
checks the method second, so the literal path has to come first or the answer is a **405**.

**The auth is on the router** (`auth=current_user`), and the user id comes from the
session, never from a payload (AD-12).

### The composition filter (D25)

In `compose_digest`, alongside the source-mute filter at `digest_composition.py:539`:

```python
eligible = [c for c in public_candidates if c.source_id not in muted]
eligible = [c for c in eligible if not (c.chip_keys and set(c.chip_keys) & muted_categories)]
```

**A candidate with no chip keys is never excluded.** An event that matches no keyword
belongs to no category, so it belongs to no muted category. Excluding it would mean a
mute silenced everything the keyword table does not recognise — a mute that silences the
unknown, which is the opposite of what the user asked for.

**The filter is a filter, not a weight.** FR-22's five terms and their CI-pinned weights
do not move.

### The frontend

**The swipe.** `pulse-card.tsx` (598 lines) has **no gesture code and no `data-*`
attributes** today. The plan adds:

- Pointer handlers on the card's root, with a vertical-drag threshold
- `data-pulse-card={event_id}` and `data-dismiss` selectors, because the card has none
- **A secondary, keyboard-reachable button** (D26). The mockup specifies the swipe; a
  gesture-only control fails PRD §11.5. The button must be present, focusable and
  labelled, but visually secondary so the swipe stays the primary affordance.
- **The stretched `<Link>` conflict.** `pulse-card.tsx:343-356` is an
  `absolute inset-0 z-0` link that paints over the card; the trust row and share row are
  `relative z-10` specifically to stay above it. The gesture layer must not swallow the
  card's tap target — **so the swipe is bound to a dedicated handle area, not the whole
  card**, or the pointer handlers must ignore drags that start on the link.

**The prompt sheet.** The house `Sheet` (`components/sheets/sheet.tsx`) is a native
`<dialog>` opened with `showModal()` — a *modal*, with `aria-label` and **no**
`aria-describedby` support. The mockup wants a **bottom-anchored sheet, NOT a modal**,
that the user can close without choosing, with `aria-labelledby` + `aria-describedby` and
**focus on the affirmative** ("Mute for 30 days").

**So the prompt gets its own component**, not the house `Sheet`: a
`role="dialog"` region with `aria-labelledby` + `aria-describedby`, `aria-modal="false"`,
dismissible with Escape and a close control, focus moved to the affirmative on open, and
focus returned to the card on close.

**Two existing guard tests forbid a dismiss button elsewhere** —
`frontend/tests/event-detail-boundary.test.ts:242-250` and
`frontend/app/events/[id]/page.test.tsx:691-701`. The Dismiss control goes on the **Pulse
Card only**.

**`/settings/taste`.** The five-step house pattern, exactly as
`frontend/app/settings/sources/page.tsx` does it — `force-dynamic`, the `homeRoute`
redirect outside any try/catch, the signed-out branch, the unavailable branch, and the
page. **Three list updates:**
1. `frontend/lib/settings-sections.ts` — a "Taste" row (`frontend/tests/settings-routes.test.ts:53-62`
   fails if a route exists without a row)
2. `frontend/e2e/settings-navigation.spec.ts:44-52` — the hand-written `SECTIONS` array,
   which **currently omits "Sources" too** — so both are added
3. `frontend/app/settings/taste/page.tsx` — the route itself

**The screen shows "Muted categories"** — the mockup's name — with each mute's label, its
expiry, and a one-tap unmute.

### The tests

| File | What it holds |
|---|---|
| `backend/tests/personalization/test_dismissal_clustering.py` | the rule (3 distinct, cosine ≥0.7, "each" not "any pair", the 24h window), the rage guard, the decay, the slot-3 immunity, the prompt firing once |
| `backend/tests/personalization/test_category_mutes.py` | the mute's duration and expiry, one-tap unmute, the effect on composition, and that a chip-less event is never excluded |
| `backend/tests/personalization/test_dismissals_api.py` | the endpoint's auth, the session scoping, the CSRF, the 422 on a bad state |
| `backend/tests/ingestion/test_embedding_backfill.py` | the backfill is resumable, costed, and skips what it has done |
| `backend/tests/ingestion/test_event_embeddings_read.py` | the read port's shape, and that a missing vector is absent rather than zero |
| `backend/tests/personalization/test_embedding_cost.py` | every embed call writes a cost row, in the same transaction as the result |
| `backend/tests/personalization/mutation_probe_fr25.py` | one probe per rule |
| `frontend/components/digest/pulse-card.test.tsx` | the swipe, the button, the keyboard path |
| `frontend/components/digest/mute-prompt.test.tsx` | the copy, the focus, the dismissal without choosing, the once-per-cluster rule |
| `frontend/app/settings/taste/page.test.tsx` | the screen, the one-tap unmute |
| `frontend/tests/taste-a11y.test.tsx` | the axe gate, over every state |

**There is no `settings-a11y.test.tsx` today** — the Sources screen from run 033 is
ungated. This item adds a gate for the new surfaces, and the digest-home gate already
exists (`tests/digest-home-a11y.test.tsx`).

**A mutation probe per rule**, run as a script (not in CI — it rewrites source files,
which is not something a CI job should do to a working tree). This is the same shape as
run 033's `mutation_probe_source_mutes.py`, and the same gap is recorded.

## Files to create

| File | Purpose |
|---|---|
| `backend/adapters/llm/voyage.py` | the real embedding adapter (D16) |
| `backend/apps/ingestion/services/embedding.py` | the embed command: read the text, embed, store the vector, cost it |
| `backend/apps/ingestion/services/embedding_backfill.py` | the resumable backfill command |
| `backend/apps/ingestion/services/event_embeddings.py` | the published read port for the vectors (Finding 4) |
| `backend/apps/ingestion/migrations/00XX_event_embedding.py` | the `vector(256)` column |
| `backend/apps/personalization/migrations/00XX_dismissal_mute_cost.py` | `EventDismissal`, `CategoryMute`, `AICostRow` |
| `backend/apps/personalization/services/dismissals.py` | record, the guard, the cluster, the decay, the prompt |
| `backend/apps/personalization/services/taste_mutes.py` | the category mute commands |
| `backend/apps/personalization/services/cost_rows.py` | the AD-8 cost-row writer |
| `backend/apps/personalization/dismissals_api.py` | `POST /api/personal/dismissals` |
| `backend/apps/personalization/taste_api.py` | the three `/api/settings/taste` endpoints |
| `backend/tests/personalization/test_dismissal_clustering.py` | the rule, the guard, the decay, the immunity |
| `backend/tests/personalization/test_category_mutes.py` | the mute and its effect on composition |
| `backend/tests/personalization/test_dismissals_api.py` | the endpoint |
| `backend/tests/personalization/test_embedding_cost.py` | the cost row |
| `backend/tests/personalization/mutation_probe_fr25.py` | the probes |
| `backend/tests/ingestion/test_embedding_backfill.py` | the backfill |
| `backend/tests/ingestion/test_event_embeddings_read.py` | the read port |
| `frontend/components/digest/mute-prompt.tsx` | the prompt sheet |
| `frontend/components/digest/mute-prompt.test.tsx` | its tests |
| `frontend/components/digest/pulse-card.test.tsx` | the swipe and the button |
| `frontend/app/settings/taste/page.tsx` | the reversal surface |
| `frontend/app/settings/taste/loading.tsx` | the sibling loading state |
| `frontend/app/settings/taste/page.test.tsx` | the screen's tests |
| `frontend/lib/taste-read.ts` | the server read |
| `frontend/tests/taste-a11y.test.tsx` | the axe gate |

## Files to modify

| File | Change |
|---|---|
| `backend/pyproject.toml` | add `pgvector` |
| `backend/config/adapters.py` | register the embedding adapter in `REAL_ADAPTERS`; **correct the `:49-51` comment** that says `embedding` is missing |
| `backend/ports/embedding.py` | pin the 256-dimension constant |
| `backend/shared/constants.py` | the FR-25 thresholds (AD-8) |
| `backend/apps/ingestion/models.py` | `Event.embedding` |
| `backend/apps/ingestion/services/catalog_read.py` | project `chip_keys` where needed — it already does (`catalog_read.py:280,344`) |
| `backend/apps/personalization/models.py` | `EventDismissal`, `CategoryMute`, `AICostRow` |
| `backend/apps/personalization/services/digest_composition.py` | the category filter |
| `backend/config/api.py` | mount the two routers |
| `backend/tests/architecture/test_write_ownership.py` | the new tables' owners |
| `backend/tests/shared/test_constants.py` | pin the new constants, in the same style as the existing pins |
| `frontend/components/digest/pulse-card.tsx` | the swipe, the button, the selectors |
| `frontend/lib/settings-sections.ts` | the "Taste" row |
| `frontend/e2e/settings-navigation.spec.ts` | the "Taste" row **and** the missing "Sources" row |
| `frontend/lib/api/` | regenerated (AD-19) |
| `_bmad-output/.../EXPERIENCE.md` | the new surfaces' rows |

## The design doc's items this plan does NOT build, and why

| Design doc says | This plan | Why |
|---|---|---|
| `Event.category` (a new `catalog` column) | **Not built.** The chip key is the category | Finding 2 — the codebase already computes a category, deliberately at read time, and already uses it on the ranking path. A second one would be a second opinion about what an event is |
| `Event.embedding` written by `ingestion` | **Built** | D14 — the design's own decision, and the spine's |
| The cost row "through the same gateway as the LLM" | **Built, but from scratch** — there is no gateway and no cost table | Finding 1 — the plumbing the design assumed does not exist |
| "reads catalog.Event.embedding (by value, via read port)" | **Built** — the read port does not exist | Finding 4 — the design's diagram named a thing that was never in the affected-files table |
| Slot 3 immunity, anchored to the `discovery` tag | **Built, but at the dismissal** — the candidate carries no slot | Finding 3 — the tag is derived at scoring time from a flag the candidate does not carry |
| The prompt naming "the cluster's most-common category chip" | **Built** — and the chip *is* the category | Finding 2 |

## Risks, and what this plan does about them

| Risk | What the plan does |
|---|---|
| **The prompt's copy names a broad chip label, not the mockup's "rooftop jazz"** | The plan takes the chip label. The finer wording needs a vocabulary decision and a backfill — a bigger item. **This is the one thing worth the user's objection at this checkpoint** |
| **The cost-row table is a new table with no precedent** | It is small, its columns come from the port dataclasses that already carry them, and the standard states the rule it implements. The AI Cost Dashboard reads it later |
| **The `public.vector` schema qualification** | The migration says `public.vector(256)` explicitly, and a test asserts the column's type |
| **`ADAPTER_MODE=real` still refuses to boot** | Unchanged and correct — `llm` and `email` are still missing. The comment in `config/adapters.py` is corrected to say exactly that |
| **The swipe conflicts with the card's stretched link** | The swipe is bound to a dedicated handle, and a test asserts the card's link still navigates |
| **Slot 3 immunity depends on resolving the composition** | `DigestComposition` is keyed `(user_id, event_id, -composed_at)`, so the lookup is one indexed read. A dismissal of an event that was never in a composition is recorded with no slot and does not advance |
| **The probes are a script, not CI** | Recorded, the same gap as run 033's. A CI job could run them in a throwaway checkout; out of scope here |

## How to verify

```bash
# The rule, the guard, the decay, the immunity, the prompt-once
cd backend && uv run python -m pytest tests/personalization/test_dismissal_clustering.py -v

# The mute, its expiry, and its effect on composition
cd backend && uv run python -m pytest tests/personalization/test_category_mutes.py -v

# The cost row — every embed call is costed, in the same transaction
cd backend && uv run python -m pytest tests/personalization/test_embedding_cost.py -v

# The backfill is resumable
cd backend && uv run python -m pytest tests/ingestion/test_embedding_backfill.py -v

# The probes
cd backend && uv run python tests/personalization/mutation_probe_fr25.py

# The screen and the prompt
cd frontend && npx vitest run components/digest/ app/settings/taste/

# The axe gate
cd frontend && npx vitest run tests/taste-a11y.test.tsx

# The contract
make client && git diff --exit-code frontend/lib/api/
```

## Checkpoint 2 — what is being asked for

**Approval of this plan, and one decision.**

The plan follows the design doc's decisions D13, D14, D16, D17, D18, D20, D21, D22, D23,
D24, D25 and D26 as written. It **changes the shape of four of them** because the code
says so:

1. **The category is the chip key, not a new `Event.category` column** (Finding 2). The
   codebase already computes a category, deliberately at read time, and already uses it
   on FR-22's largest weight. Adding a second one would be a second opinion.
2. **The cost row is built from scratch** (Finding 1). There is no gateway and no cost
   table; the design assumed one.
3. **The slot-3 immunity is enforced at the dismissal** (Finding 3), because the
   candidate carries no slot.
4. **A published read port for the vectors is added** (Finding 4), because the
   clustering rule cannot cross the wall.

**The decision:** the prompt names the chip's label (*"Less arts & culture?"*), not the
mockup's finer wording (*"Less rooftop jazz?"*). The mockup's example is preserved as the
*shape* of the copy, not the vocabulary of it.

**Why this is a checkpoint and not a note.** The four findings each change what gets
built, and the fifth — the vocabulary of the prompt — changes what the user sees. A
plan that assumed the design doc was complete would have built a second category field, a
cost row with no table, a slot-3 immunity with nothing to read, and a clustering rule
with no read port.

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 2 pending approval*
