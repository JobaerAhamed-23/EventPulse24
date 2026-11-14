---
run: run-eventpulse24-034
work_item: less-like-this-adjustment
intent: relevance-feedback-loop
generated: 2026-11-14
mode: validate
---

# Implementation Walkthrough: "Less like this"

## Summary

This is the loop that makes the product learn what a user does not want. A reader swipes
past a card — three times, on three events that are genuinely alike — and the product
asks, once, *"want us to deprioritize this category for a while?"* If they say yes, the
category is muted. If they say no, nothing happens and the product does not ask again for
that cluster.

The hard part was never the swipe. It was the three things that make the loop honest:

- **The count is the server's.** The cosine, the window, the three-distinct rule and the
  rage guard are all facts the server computes. The client sends one event id and renders
  what comes back. A client that counted would be a client that could be wrong.
- **The copy is the server's.** The prompt's title names a *category*, never an event's
  title — a scraped title is untrusted source content (AD-9) and must never reach a
  user's screen.
- **The way back out exists.** `Settings → Taste` lists every active mute, and one tap
  unmutes. A loop that can only tighten is a trap.

This run built the whole thing: the vector on the event, the real embedding adapter and
its cost accounting, the dismissal record and the cluster that reads it, the category
mute and the filter that applies it, the three endpoints, the bottom-anchored prompt, the
swipe, and the reversal screen.

## Structure Overview

Four layers, and the walls between them are the point.

**The catalog side (`ingestion`)** owns `Event` and its vector. `Event.embedding` is a
`public.vector(256)` column, written only by `ingestion` (AD-4's sole writer). The embed
command reads the event's own text — title then description, with the description bounded,
because a source can publish a megabyte under a short title (AD-9). The backfill is a
resumable command, not a migration.

**The adapter (`adapters/llm`)** talks to Voyage. It asks for exactly the dimension the
caller wants — `voyage-4-lite` is a Matryoshka model, and the truncation is part of the
model, not a slice applied afterwards. It asks for `input_type=document`, because the
vectors are compared against *each other*. It pairs the provider's vectors back to the
texts by index, whatever order they arrive in.

**The personal side (`personalization`)** owns the preference and the rule. `EventDismissal`
and `CategoryMute` hold `user_id` and their subject **by value** — no foreign key, because
AD-3 forbids a relation across the schema wall and the ORM enforces it. The
`dismissals` service holds the cluster: the candidate pool, the decay, the rage guard, the
serendipity immunity, and the prompt's copy.

**The surface** is the API and the two screens. `POST /api/personal/dismissals` records
one dismissal and answers with what the client should do about it. `/settings/taste` is
the way back out.

```
        swipe past a card
                │
                ▼
    POST /api/personal/dismissals
                │
    ┌───────────┴────────────────────────────┐
    │                                        │
┌───▼──────────────────┐        ┌────────────▼─────────────┐
│  personalization     │        │  ingestion               │
│  record_dismissal()  │        │  read_event_embeddings() │
│  → the row           │        │  → the vectors           │
│  → the cluster       │        │  → the chip keys         │
│  → the prompt's copy │        └──────────────────────────┘
└───┬──────────────────┘
    │
    │  { cluster_advanced, prompt_due, prompt }
    ▼
  the client renders the server's answer
```

## Architecture

### Layer Structure

| Layer | Owns | Knows about |
|-------|------|--------------|
| `adapters/llm` | the Voyage call, the cost row | `ports.embedding`, `shared.constants` |
| `apps/ingestion` | `Event.embedding`, the embed command, the backfill, the read port | `adapters.llm`, `ports.embedding` |
| `apps/personalization` | `EventDismissal`, `CategoryMute`, the cluster, the mute | `apps.ingestion`'s **published reads** only |
| the surface | the API and the screens | the services' plain data |

`personalization` never imports `apps.ingestion.models` — it reads the vectors and the
chip keys through `event_embeddings` and `catalog_read`, which return plain tuples. The
import-linter's 19 contracts all hold.

### The Cost Row (AD-8)

AD-8 says the gateway writes "a per-call cost row in the same transaction as the result".
The coding standard says "the calling command opens `atomic(using=CATALOG)`, and the
gateway writes the row inside it".

**So the adapter does not open a transaction of its own.** A transaction opened in the
adapter would commit the cost row on its own — which is exactly the failure the rule
exists to prevent: *a cost row describing a result that later rolled back*. The writer
**raises** if no catalog transaction is open, rather than quietly opening one.

The row carries **no user id**. A cost row is about a *call*, not a person.

## Domain Model

### Entities

- **`Event.embedding`** (`catalog`, `vector(256)`, nullable) — the event's own text, embedded. Written only by `ingestion`.
- **`EventDismissal`** (`personal`) — `user_id` + `event_id` **by value**, unique per pair, with `dismissed_at`, `cluster_advanced` and `slot`.
- **`CategoryMute`** (`personal`) — `user_id` + `category_key` **by value**, unique per pair, with `expires_at` (null = indefinite).
- **`AICostRow`** (`catalog`, owned by `adapters/llm`) — one row per call: kind, model, tokens, cost, call count. No user id.

### Value Objects

- **`EmbeddingResult`** (`ports/embedding.py`) — the vectors, the model, the tokens, the cost.
- **`MutePromptOut`** (the wire shape) — the title, the description, and the `category_key` the cluster agreed on.

## Key Implementation Details

### 1. The prompt is a sheet, not a modal

The mockup says it in as many words: *"Position: bottom-anchored sheet, NOT a modal. The
user can close it without choosing."*

So the prompt sits at the bottom of the screen, over the digest. It does **not** cover the
digest with a backdrop that swallows the page, and it does **not** take the focus away
from the page — the reader keeps reading while the question sits there, which is the whole
point of it being a sheet.

**It is not the house `Sheet`, and the difference matters.** The house `Sheet` is a native
`<dialog>`, and a native dialog opened with `showModal()` brings its own accessibility
behaviour — the top layer, the backdrop, the browser's focus trap. **A native `<dialog>`
has no `aria-describedby` slot this prompt can use**, because its description is the
element's own text content, and the description here is a *separate* element from the
title.

So the prompt is its own `role="dialog"` component, with `aria-labelledby` pointing at the
title, `aria-describedby` pointing at the description, `aria-modal="true"`, focus moved to
the affirmative button on open, and focus restored on close.

### 2. It is still dismissible

The prompt is a *question*, not a forced choice. A prompt that cannot be closed without
answering is a dark pattern — the exact thing FR-25's guard exists to prevent. So there
is an X, the Escape key works, clicking the backdrop works, and there is a named "Not now"
button.

**The affirmative gets the focus.** The question is "want us to deprioritize this?", so a
keyboard user who presses Enter gets the answer the screen is asking for. The dismissive
path is still one Escape away.

### 3. The swipe has a keyboard-reachable twin

The mockup specifies a swipe-down gesture. **A gesture-only control fails the PRD §11.5
a11y gate** (`axe-core` runs in CI) and excludes keyboard and screen-reader users.

So `SwipeDismiss` exposes a real `<button>` — *"Show me less of this"* — with the **same
action**, and both paths call **one** `dismiss()`. There is exactly one implementation of
the dismissal, and it is the one the tests cover.

The transform lands on the *wrapper*, not the card: the card's stretched `<Link>` is
`absolute inset-0`, so moving the card means moving the wrapper. The button is a
**sibling** of the card, not inside it, so the link cannot cover it.

### 4. A failed write dismisses nothing

The client sends the dismissal, and the server may refuse it — the network is down, the
session expired. If the card vanished anyway, it would come back later with no
explanation. So a failed write **springs the card back and re-enables the button**.

### 5. The client never counts

The cosine threshold (0.70), the three-distinct rule, the 24-hour window, the rage guard
and the serendipity immunity are **all server facts**. The client sends one event id and
renders what comes back. `prompt_due` is the server's answer, not the client's count of
swipes — and the mutation probe "the dismissal endpoint reports the prompt as due
whatever the server said" pins it.

### 6. A chip-less event is never muted

A mute on an event with no chips would exclude nothing, silently, while the screen showed
a row the user could not make sense of. So `is_muted_by_category` returns `False` for an
empty chip list.

### 7. The tie is not a majority

The cluster asks "what do these three events have in common?", and the answer is a chip
key. **A key has to be on a majority to win.** One event in the cluster being a jazz event
does not make the cluster jazz — the cluster is three events, and the mute is for the
thing they have in common.

A tie produces the **generic** prompt: *"Less events like these in your next digest?"* A
mute on the wrong category would be the worst outcome here — the title would be a claim
about what the three had in common, and it would be false.

### 8. The prompt fires once, and the counter resets

So the prompt cannot nag. The third similar dismissal fires it, and the next cluster has to
earn its own. The mockup's *"No dark-pattern nag"* is a rule about the *product*, and this
component is only ever told to open when the server says a cluster completed.

### 9. The decay has three shapes

Past 60 days a dismissal weighs **half**. Past 180 days it weighs **nothing** — and the
row leaves the candidate pool entirely, which is a different thing from weighing half, and
the test asserts the difference.

### 10. The mute is a filter, in both surfaces

A category mute **excludes** — it is not a score term. "Show less" that hid events
entirely would be a lie to the user. The filter is applied in `compose_digest` **and** in
`browse_read`, because a filter present in one surface and absent in the other is the
quietest bug in this feature. Two mutation probes attack it, one per surface.

### 11. `ADAPTER_MODE=real` still refuses to boot — and says why

The real embedding adapter exists now. The real *LLM* and *email* adapters do not, so
`ADAPTER_MODE=real` still refuses to boot. The comment in `config/adapters.py` was
corrected to say exactly that, instead of listing `embedding` among the missing ones.

## Security Considerations

- **A scraped title never reaches the user's screen (AD-9).** The prompt's copy is the server's, computed from the cluster's chips — never from an event's title. The mutation probe pins it.
- **The embedding key never reaches a log line.** httpx logs request URLs at INFO, and this URL carries no secret — the key is a header, and httpx does not log headers. The test asserts the key is in the `Authorization` header and nowhere in the JSON body.
- **The dismissal and the mute are scoped to the caller.** The endpoints take no user id; the state comes from the session (AD-12). Two mutation probes attack the scoping.
- **The event's description is bounded before it is embedded.** A source can publish a megabyte under a 500-character title.
- **The cost row carries no user id.** A cost row is about a call, not a person.

## Performance Considerations

- **The vector is read once per cluster.** The candidate pool is at most `FR25_CLUSTER_MIN_EVENTS * 2` rows, and the vectors for those rows come back in one read.
- **The backfill is resumable and batched.** It embeds only the events with no vector, so a second run costs nothing.
- **The embedding call is batched to 128 texts**, which is the adapter's bound — the caller splits its work rather than the adapter silently truncating a list.
- **The mute filter is a set membership test**, not a query per candidate. The muted categories are read once per composition.

## Decisions Made

| # | Decision | Why |
|---|----------|-----|
| 1 | The chip key **is** the category; no `Event.category` column | The codebase already computes a category, deliberately at read time, and already uses it on the ranking path. A second one would be a second opinion about what an event is |
| 2 | The vector is `vector(256)`, **quantized** | 256 halves the storage and the cosine work, and 256 dims is ample for a cosine ≥0.7 grouping threshold |
| 3 | The adapter **asks** for the dimension rather than slicing | Matryoshka truncation is part of the model; slicing a full vector is a different operation |
| 4 | The cost row's model lives in `adapters/llm/models.py` | Under `apps | adapters` the gateway cannot import an app's models |
| 5 | The slot-3 immunity is enforced **at the dismissal** | The candidate carries no slot; the `discovery` tag is derived at scoring time from a flag it does not have |
| 6 | The read port is a **published read**, not a direct model read | `personalization` may not import `apps.ingestion.models` (AD-3), and the port returns plain tuples |
| 7 | The swipe is a **wrapper**, not a change to the card's internals | The card's link is `absolute inset-0`; moving the wrapper moves the card and leaves the link working |
| 8 | The prompt is its own `role="dialog"`, not the house `Sheet` | A native `<dialog>` has no `aria-describedby` slot, and the description here is a separate element from the title |
| 9 | The duration set is a `Literal` **and** a service check | The `Literal` is the published contract; the service is the runtime defence for the callers that are not this endpoint |
| 10 | The prompt's copy takes the **chip label**, not the mockup's "rooftop jazz" | The mockup's finer wording needs a vocabulary decision and a backfill — a bigger item. The chip label is the server's own vocabulary, which is what AD-9 requires |

## Deviations from Plan

Six, all recorded here because each one changed the shape of the work.

**1. The cost row was built from scratch.** The design doc said the embedding call would
write a cost row "through the same gateway as the LLM" (AD-8). **There is no gateway and
no cost table** — the plumbing the design assumed does not exist. So `AICostRow`,
`adapters/llm/costs.py` and the `adapters.llm` Django app are all new, and
`adapters/llm` had to be registered as an app and routed to the `catalog` schema.

**2. The embedding read port was built from scratch too.** The design doc's diagram named
a read port that was never in the affected-files table. It exists now, as
`apps/ingestion/services/event_embeddings.py`.

**3. `Event.category` was *not* added.** The design doc said the category is a new
`catalog` column. The codebase already computes one — deliberately, at read time, from the
keyword table, because a stored column would be wrong the moment the keyword table
changed. A second one would be a second opinion about what an event is.

**4. The slot-3 immunity moved to the dismissal.** The design doc anchored it to the
`discovery` tag, which is derived at scoring time from a flag the candidate does not
carry. So the immunity resolves the slot from the user's own composition instead.

**5. The prompt was rewritten from a modal into a bottom-anchored sheet.** The inherited
implementation was a centred, backdrop-washing modal. The mockup says *"bottom-anchored
sheet, NOT a modal"* — and the mockup is the spec.

**6. Twenty macOS " 2.tsx" files appeared and were removed.** `prettier --write` triggers
the filesystem's NFD→NFC filename normalisation, and macOS materialised a copy of each
file it touched. Every one was verified byte-identical and untracked before removal.

**Not deviated from, and worth naming:** the FR-25 coupling was *not* introduced. The
briefs assumed `Settings → Sources` would be FR-25's reversal surface; the mockup says
`Settings → Taste` (`:122`, `:149`), and the subjects differ — FR-25 mutes **categories**,
that screen mutes **sources**. Coupling them would have built a control that cannot
express the other. The sibling intent builds `/settings/sources`; this one builds
`/settings/taste`.

## Dependencies Added

**`pgvector`** (`backend/pyproject.toml`) — the Python binding for the `vector` type.

The extension itself was **already enabled** in the database
(`docker/postgres/init/01-schemas-and-roles.sh:75-76`) and had been provisioned for a
column nobody had written. The Python package was the missing half.

**No new frontend package.** The frontend uses the generated client (AD-19) and nothing
else.

## How to Verify

### 1. The cluster fires on three alike, and not before

```bash
cd backend && uv run pytest tests/personalization/test_dismissal_clustering.py -v
```

The threshold is asserted **at the boundary**: a cosine of 0.50 does not cluster and one
of 0.75 does.

### 2. The mute excludes, and the two surfaces agree

```bash
cd backend && uv run pytest tests/personalization/test_category_mute_composition.py -v
```

### 3. The prompt is a sheet, and it can be walked away from

```bash
cd frontend && pnpm exec vitest run components/digest/mute-prompt.test.tsx
```

### 4. The rules are the rules the suite thinks they are

```bash
cd backend && uv run python tests/personalization/mutation_probe_fr25.py
```

35 probes, all caught. A probe that *passes* the suite is not a bad probe — it is a test
that does not prove the rule it claims to.

### 5. The whole thing

```bash
cd backend && uv run pytest -q --ignore=tests/e2e --ignore=tests/wall
cd frontend && pnpm exec vitest run
cd backend && uv run lint-imports
make client && git diff --exit-code frontend/lib/api/
```

### 6. Manually, in a browser

```bash
make up && make api
cd frontend && pnpm dev
```

Sign in, open the digest, and swipe a card down — or press the **"Show me less of this"**
button, which is the same action and works from the keyboard. Dismiss three similar
events inside a day and the prompt appears at the bottom of the screen, over a digest you
can still read. Answer it, then go to **`/settings/taste`** and see the mute listed, with
one tap to undo it.

## Test Coverage

| Module | Cover |
|--------|-------|
| `apps/personalization/services/dismissals.py` | 100% |
| `apps/personalization/services/taste_mutes.py` | 100% |
| `apps/ingestion/services/embedding.py` | 100% |
| `apps/ingestion/services/embedding_backfill.py` | 100% |
| `apps/ingestion/services/event_embeddings.py` | 100% |
| `adapters/llm/voyage.py` | 100% |
| `adapters/llm/costs.py` | 100% |
| `apps/personalization/api.py` | 100% |
| `apps/personalization/taste_mutes_api.py` | 94% |
| **Total** | **98.35%** |

200 new tests (139 backend, 61 frontend), plus **35 mutation probes**, all caught.

## Ready for Review

- [x] All tests passing (6920 backend, 2572 frontend)
- [x] Coverage target met (98.35% against 80%)
- [x] All acceptance criteria validated
- [x] Import contracts intact (19 kept, 0 broken)
- [x] `make client` produces no drift
- [x] No critical issues open

## Developer Notes

- **The `ingestion` side is the one that has to run first.** Nothing clusters until the
  events have vectors, and the backfill is what gives them one:
  `uv run --directory backend python manage.py backfill_embeddings`. Until it has run, an
  event has **no** vector — and a missing vector is *absent*, not zero, so the cluster
  simply does not form.
- **`ADAPTER_MODE=real` still refuses to boot**, and the comment in `config/adapters.py`
  says why: the real `llm` and `email` adapters are still missing. Only the `embedding`
  adapter was in scope for this item.
- **The prompt's copy names a broad chip label** ("Arts & culture"), not the mockup's
  "rooftop jazz". The finer wording needs a vocabulary decision and a backfill — a bigger
  item, and the one thing in this run worth arguing about.
- **The `BrandTopBar` changes in the working tree are not this run's** — a pre-existing
  uncommitted Dark Reader hydration fix, deliberately left out of the diff.
- **The probes are a script, not CI.** The same gap run 033 recorded.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-034*
