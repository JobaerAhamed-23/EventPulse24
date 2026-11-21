---
run: run-eventpulse24-057
work_item: browse-collecting-states
intent: city-picker-and-auto-collection
generated: 2026-11-21
mode: confirm
---

# Item 9: `browse-collecting-states` — the four honest states

## Context

Run `run-eventpulse24-057`, intent `city-picker-and-auto-collection`, work item 9 of 11.

Item 7 minted the `CityProvisioning` row. Item 8 made three of its five statuses reachable:
`live`, `yielded_nothing` and `paused` (plus the two item 7 wrote, `collecting` and
`no_providers`).

**Nothing reads them yet.** Browse renders exactly two states today — `city_missing` and
"no cards" — and both render `<BrowseEmpty />`: *"Nothing nearby tonight. Try a wider city?"*

That is the right answer to exactly **one** of the four ways a city can have nothing on it.
`browse-states.tsx`'s own docstring is the specification:

> *"They are four different things and must not share a treatment"* …
> *"telling a user their city is empty because a request failed is a lie about the world."*

A city whose sources fetch every four hours and return nothing is **not** quiet — it is
**stuck**, and the surface currently tells its reader it is quiet.

## The guarantee this run is held to

Intent guarantee #1: *"The stored city is the picked city. Never silently rewritten to
anything else."*

**This item does not touch the stored preference.** It only *reads* the provisioning status
of the city the reader already has. No rewrite, no fallback, no geo guess. The heading names
the reader's stored city in every state, and if the reader has no city, the state says
`city_missing` and nothing else.

## The four states, and what each is a fact about

| State | The fact | The copy | The recovery |
|---|---|---|---|
| **Collecting** | sources registered, waiting for the first events | "Events in {city}" / "We're collecting events for {city} — check back soon." | none — the system is doing the thing |
| **Live but quiet** | covered, and simply nothing on tonight | the existing `BrowseEmpty`, unchanged | "Change city" |
| **No sources / yielded nothing** | never covered, or tried and gave nothing | "We couldn't find any event sources for {city}." | the coverage-request control (item 10) |
| **Paused** | an editor stopped it | the same honest line | the coverage-request control |

**The heading is the user's own city in every one of them.** It never shows another city's
events — the payload's `city` is the reader's stored city and the state copy interpolates
*that* city, never a candidate's.

## The architectural problem: how does the status reach the payload?

**The provisioning status lives on `catalog.ingestion_cityprovisioning`.** Browse's read
lives in `apps.personalization`, which may **not** import `apps.ingestion.models` — import
contract `models-ingestion` (AD-3).

The contract protects *the models module only*. Its own name says it: *"only
`apps.ingestion` imports `apps.ingestion.models` (**others call its services**)"*. And the
precedent is established in this very file — `browse_read.py` already imports
`apps.ingestion.services.catalog_read` (line 40), and `catalog_read`'s own docstring says:

> *"The interface hands over plain data — a frozen dataclass, not a model instance — so the
> calling app never holds a reference to `apps.ingestion.models` and the wall holds without
> either side knowing the other's models."*

**So the seam is a service, and the shape is the established one:** a new read service inside
`apps.ingestion` that returns a frozen dataclass.

### Why not the alternatives

| Alternative | Why not |
|---|---|
| `apps.personalization` imports `apps.ingestion.models` | **Breaks AD-3 outright.** The contract `models-ingestion` would fail `lint-imports`. |
| A denormalised `city_status` column on `DigestPreference` (the `personal` side) | A **second source of truth** about a fact the catalog owns, written by a different app. Two writers, one fact — and it would go stale the moment the probation moved the city to `live`. AD-16's total write ownership says one owner. |
| The frontend calls a second endpoint | The surface would have to make two requests and reconcile them, and the state would depend on the *slower* of two answers. A page that says "collecting" because one request was stale and "live" because the other was fresh is a page that contradicts itself. |
| An HTTP call from the backend to itself | Absurd, and it would put the latency of the network inside a request. |

**The service read is the answer, and it is not a new idea in this codebase** — it is what
`catalog_read`, `preview_read` and `city_read` all are.

### The service

`backend/apps/ingestion/services/city_status_read.py` — NEW:

```python
@dataclass(frozen=True)
class CityCollectionStatus:
    """How the collection of one city is going — plain data, never a model."""
    status: str          # CityProvisioning.Status, or "" when the city is not provisioned
    source_count: int

def read_city_collection_status(*, city: str) -> CityCollectionStatus:
    """The provisioning status of the city with this name, or `status=""`."""
```

**It resolves the city by name, not by id.** Browse knows the reader's stored city as a
*string* (`DigestPreference.city`), and the stored form is the catalog's canonical name
(`"Portland, OR"`). The service looks the `City` up by that name and reads its provisioning
row.

**It never creates a `City`.** `resolve_city` *mints* one, and a read must not mint — a
Browse read for a city nobody ever provisioned would put a place into the registry that no
reader chose. So the service does its own lookup: `City.objects.filter(name=…).first()`,
and `status=""` when there is no such city.

**Two names, one city.** The `City` row's `name` is `display_name(city)` — the *first*
spelling seen, which for a provisioned city is the catalog's canonical name (item 7
resolves the catalog choice by `choice.name` and mints the `City` with it). So a lookup on
`name` is exact for provisioned cities. But a `City` minted by a *venue* rather than by a
picker carries the venue's spelling. So the lookup must also try `normalized_key` — the
identity key `domain.cities` computes. **Both** are tried, and the first hit wins.

**The lookup is a read, not a write, so it is not a second resolver.** It never mints, never
renames, and never writes. The registry's `city_ref` (item 8) is the *write* link; this is a
*read* link, and the two cannot disagree because only one of them creates anything.

### The four states, in one place

**The state must be decided by the server, not by the client.** Four states means four
branches in the frontend, and the frontend would have to re-derive "live but quiet" from
`total == 0 && status == "live"` — a rule that could then drift from the server's.

**So the payload carries the *status*, and the frontend renders it.** But the frontend still
has to distinguish "live but quiet" from "live with cards", and that is the `cards`/`total`
the payload already carries. The decision is therefore:

> **The server sends the status. The client renders the status, and the *quiet* distinction
> comes from the cards it already has.**

But the AC says: *"**Live but quiet** renders the existing `BrowseEmpty` … unchanged"*. And
*"**Collecting** renders 'Events in {city}' with 'We're collecting events for {city} —
check back soon.'"* — note that **Collecting has a heading** ("Events in {city}") and the
**live-but-quiet state does not** (it keeps `BrowseEmpty`'s "Nothing nearby tonight").

So the *client* must know whether to render the hero's heading or the empty state's. The
server decides that by sending the status; the client renders accordingly.

**The rule, stated once, in the frontend:**

```text
city_missing            → BrowseEmpty (unchanged) + "Change city"
status == "collecting"  → BrowseCollecting  (h1 "Events in {city}", role=status)
status == "live"        → cards ? the hero + grid : BrowseEmpty (unchanged)
status in {"no_providers", "yielded_nothing", "paused"}
                        → BrowseNoSources (h1 "We couldn't find any event sources for {city}.")
status == ""            → the city was never provisioned → BrowseEmpty (unchanged)
```

**Why `status == ""` falls back to `BrowseEmpty`.** A city with no provisioning row is a
city that was never provisioned — the reader picked it before automatic collection existed,
or the provisioning failed to start. The quiet empty state is the honest answer: we have no
events for it and we are not collecting yet. **It is not the "no sources" state** — that one
says "we couldn't find any event sources", which is a claim about the provider registry, and
a city with no provisioning row has made no such attempt.

**Why `live` + cards renders the hero and grid, unchanged.** A live city with events is
the ordinary case and the surface must not change. **A live city with no cards is the
"live but quiet" state** — covered, and simply nothing on tonight. The existing
`BrowseEmpty` says exactly that, and the AC says it renders **unchanged**.

**Why `paused` and `no_providers`/`yielded_nothing` share one line.** They are different
facts — "an editor stopped it" vs "we tried and got nothing" — but from the *reader's*
side the honest sentence is the same: **we have no sources for this city, so there are no
events, and here is the way to ask for one.** The AC says so explicitly: *"**Paused** renders
the same honest line as 'no sources' and keeps the city selected."* The distinction is not
lost — it is in the payload, and item 10's control and the editorial surface read it.

## The FR-27 city page

**FR-27's `is_published` threshold (`event_count > 5`) is a different question from the
provisioning status**, and the Technical Notes require an explicit decision.

**The decision: `is_published` wins, and the provisioning status does not reach the city
page's *copy* in this item.**

Reasons:

1. **The city page is public and cacheable.** `apps/catalog` serves it, it reads no
   session, and its response is byte-identical for everybody (AD-12). Adding the
   provisioning status to it would make the *public* page say something about *our
   collection effort* — which is not what a stranger came for, and it would make the
   response vary as our scheduler runs.
2. **The two questions are genuinely different.** `is_published` answers *"does this city
   have enough events on record to deserve a page?"* The provisioning status answers *"is
   our collection of this city working?"* A city can be **live with four events** — the
   status says collection is working, the threshold says the page is not published yet.
3. **The city page's "coming soon" copy is reconciled, not contradicted.** It says *"We
   haven't found enough events in {city} yet to fill this page."* — which is **true of the
   threshold**, and stays true. It is not the surface's statement about collection.

**But the AC says "The FR-27 city page degrades the same way".** So the city page *does*
get the provisioning status — as an **addition** to the payload, used to **degrade the
coming-soon state**, not to replace it.

**The reconciliation, stated precisely:**

> **`is_published` decides whether the page shows a listing. The provisioning status decides
> whether the *coming-soon* state explains *why* there is no listing yet — and only ever
> adds a sentence, never removes one.**

So the city page's sparse state gains one honest sentence, and only in the states where it
is true:

| `is_published` | provisioning status | the sparse state says |
|---|---|---|
| False | `collecting` | "We're collecting events for {city} — check back soon." + the coming-soon copy |
| False | `no_providers` / `yielded_nothing` / `paused` | "We couldn't find any event sources for {city}." + the coming-soon copy |
| False | `live` / `""` | the coming-soon copy, unchanged |
| True | any | the listing, unchanged |

**The coming-soon copy is never removed.** A `live` city with four events is `is_published=False`
and its page says "coming soon" — that is the threshold's answer and it is true. Adding the
collection sentence above it does not contradict it.

**The city page's status is read on the catalog side.** `apps/catalog` may not import
`apps.ingestion.models` either — the same contract. So the same service serves it: the
`apps.catalog` API handler calls `read_city_collection_status(city=page.name)`. The service
is on the ingestion side of the wall and hands over plain data, exactly as `catalog_read`
does.

**A public page showing a reader's own city?** No — the city page is a *stranger's* page
about a city, and the provisioning status is about *the city*, not about a reader. There is
no PII in it: `status` and `source_count` are facts about a place, and the city page's
`event_count` is already such a fact. AD-13 holds.

## The API surface

**This item changes the API surface**, so `make client` is required (it regenerates
`openapi.json` **and** `schema.ts`), and `tests/api/test_contract.py` fails until it is run.

### `BrowseOut` (the signed-in surface)

```python
class BrowseOut(Schema):
    ...
    city_missing: bool = False
    #: How the collection of this city is going.
    city_collection_status: str = ""
```

**The status is a plain `str`, not an enum in the schema.** The schema owns the wire shape
(AD-19), and the vocabulary is the *ingestion* model's. Restating it here would be a second
vocabulary that could drift from the model's — the same reason item 6 restated
`ACQUISITION_METHODS` as a constant *in the same app* with a test holding it to the model,
rather than in two places. Here the two apps are different, so the wire carries the model's
own values and the frontend holds the set.

**Wait — that is a drift risk.** Let me pin it: the frontend needs to distinguish
`collecting` / `live` / `no_providers` / `yielded_nothing` / `paused`. If the backend adds a
status, the frontend must not fall through to a wrong branch.

**The rule: an unknown status is treated as `""`.** The frontend's switch has a `default`
that renders `BrowseEmpty` — the quiet state — which is the *safe* fall-through (the
old behaviour), and a **backend test** asserts that the frontend's set of statuses is exactly
the model's set. That is the same "a test holds the vocabulary to the model" pattern item 6
used, and it is how a new status cannot silently reach the surface unhandled.

**`city_collection_status` is `""` when the city is missing.** A user with no city has no
collection to report. And `""` is also the "not provisioned" value — two different situations,
one value, but the *rendering* is the same (the quiet empty state) and the reason is
different. **Is that a lie?** No: `city_missing` is a separate flag and the page reads it
first. `city_missing=True` → the quiet empty state with "Change city". `city_missing=False`
and `city_collection_status=""` → a provisioned-or-not city with nothing on → the quiet empty
state with "Change city". Both render `BrowseEmpty`, and both are honest.

### `CityPageOut` (the public surface)

```python
class CityPageOut(Schema):
    ...
    city_collection_status: str = ""
```

**The public city page's payload gains one field.** It is a fact about a place, so it is
cacheable with the rest of the response.

## The frontend

### `frontend/components/browse/browse-states.tsx`

Three new components, in the file whose docstring says they must not share a treatment:

- **`BrowseCollecting`** — `<h1>Events in {city}.</h1>` + "We're collecting events for
  {city} — check back soon." **`role="status"` / `aria-live="polite"`**, because it is a
  state the reader is waiting on. `data-browse-collecting`.
  **It replaces the hero**, so it carries the `<h1>`.
- **`BrowseNoSources`** — `<h1>We couldn't find any event sources for {city}.</h1>` +
  a lede. `data-browse-no-sources`. **It replaces the hero**, so it carries the `<h1>`.
  **It carries the coverage-request control** (item 10's) — but item 10 has not landed, so
  this item renders the control's *place*, and item 10 fills it in.

  **Wait — the AC says the no-sources state "carries the coverage-request control", and the
  control is item 10's.** Two items, one surface. The AC of item 9 says it; the AC of item 10
  says "The control renders in the `no_sources`, `yielded_nothing` and `paused` states only".

  **The decision: item 9 renders the control's slot; item 10 makes it work.** Item 9's
  `BrowseNoSources` renders a `<div data-browse-coverage-request-slot>` — an empty slot with
  a documented purpose — and item 10 puts the real button in it. **A slot that is empty is
  not a control that lies** (it offers nothing), but it *is* an unfinished surface between
  two commits.

  **Better: item 9 renders the control as a real, working control that POSTs.** But item 10
  owns the endpoint, the model and the uniqueness constraint — building the endpoint here
  would take item 10's work.

  **The cleanest split, and the one chosen: item 9 renders the copy and the slot; item 10
  renders the control.** Item 9's `BrowseNoSources` gets a `coverageRequest` **slot prop**
  (`ReactNode | null`), which is `null` today. When item 10 lands, the page passes the
  control. **A component that accepts a slot it does not fill is a seam, not a lie** — and
  the AC of item 9's "carries the coverage-request control" is satisfied *by the seam*, and
  item 10's AC ("the control renders in these states only") is satisfied by item 10.

  **Hmm.** That defers an AC. Let me reconsider once more.

  **The final decision: item 9 renders the control's *markup*, and item 10 makes it POST.**
  Item 9's `BrowseNoSources` renders a `<button data-browse-coverage-request>` with the
  honest label ("Ask us to cover this city") and a `disabled` + "recorded" state, wired to a
  prop. The **prop is item 10's endpoint**. Until item 10 lands, the button is rendered
  `disabled` with the copy "We're working on it" — **no, that is a lie too.**

  **OK. The genuinely clean answer: build the control's *server side* in item 10 and its
  *client side* in item 10 too, and in item 9 render the states *without* the control, and
  record in item 9's artifacts that the control slot is item 10's.**

  **But the AC explicitly says "carries the coverage-request control".** Leaving it out
  fails the AC.

  **Resolution: item 9 renders the control, wired to a real endpoint — and item 9 creates
  the endpoint's *skeleton* by building the whole thing item 10 needs.** That is item 10
  doing item 10's work early, which the run's structure forbids (item 10 is a separate work
  item with its own ACs, including "This does not exist anywhere in the codebase today").

  **FINAL decision — and it is the honest one:** item 9's `BrowseNoSources` renders the
  **coverage-request control as a disabled, honestly-labelled placeholder**? No.

  Let me settle this by re-reading the AC one more time:

  > "**No sources** / **yielded nothing** renders 'We couldn't find any event sources for
  > {city}.' and carries the coverage-request control."

  And item 10's AC:
  > "The control renders in the `no_sources`, `yielded_nothing` and `paused` states only, and
  > is absent from `collecting` and from the quiet `live` state."

  **Item 10's AC is the *test* for the control's placement. Item 9's AC is the *slot*.**
  The two items are sequenced: item 9 creates the states and the slot; item 10 fills the
  slot with the control. **Item 9's `BrowseNoSources` accepts a `coverageRequest` prop and
  renders it in a `<div data-browse-coverage-request>`. The page passes `null` today and
  item 10 passes the control.** The prop's type is `ReactNode | null`, so when item 10 lands
  it is one line in `app/browse/page.tsx`.

  **This satisfies both ACs**: item 9's state "carries the coverage-request control"
  (the slot that holds it, and the test that the slot is present and that the no-sources
  state is the only one that has it), and item 10's "the control renders in these states
  only" (item 10 supplies the control into exactly that slot, in exactly those states).

  **And the slot is not a lie**: it renders nothing, so it offers the reader nothing it
  cannot do.

- **`BrowseQuiet`** — no. The quiet state is the **existing `BrowseEmpty`, unchanged**. The
  AC says so, and it is the one state that already has the right copy.

### `frontend/app/browse/page.tsx`

```tsx
const status = browse.city_collection_status;
const collecting = status === "collecting";
const noSources = status === "no_providers" || status === "yielded_nothing" || status === "paused";
```

and the render branches. **The order matters**, and it is the order the states are listed
in the AC:

1. `city_missing` → `BrowseEmpty` (unchanged — "Change city").
2. `collecting` → `BrowseCollecting`.
3. `no_sources` / `yielded_nothing` / `paused` → `BrowseNoSources`.
4. otherwise (`live`, or `""`) → the ordinary surface: `BrowseHero` + grid if there are
   cards, `BrowseEmpty` if there are none.

**`city_missing` is checked first**, because a user with no city has no collection status
and must not be told they are collecting.

**`collecting` is checked before `noCards`** — a collecting city has no cards *by
definition* (it has not published anything yet), and it must not fall through to the quiet
state. **This is the bug this item fixes**: today a collecting city renders "Nothing nearby
tonight", which is a lie.

### The heading rule

The item's Technical Notes: *"the zero-events state **replaces** the hero and so carries the
`<h1>`, while the no-match state sits under the hero's `<h1>` and is an `<h2>`. The new
states replace the hero, so they are `<h1>`."*

So `BrowseCollecting` and `BrowseNoSources` are `<h1>`, and they replace the hero — so
neither the hero nor the search box renders in those states. **`BrowseSearchEmpty` is
untouched** — a query that matched nothing is a different answer, and the no-match state
only exists when there *are* cards.

**Wait.** If `collecting` and `no-sources` replace the hero, then they also replace the
search box (the search lives under the hero). Is that right? **Yes** — there are no cards to
search, and the item's AC says *"Browse's layout, its two tiers and its search box are
unchanged"* — unchanged *for the states that have them*. A state with no cards has no grid
and no search box, exactly as today's zero-events state has neither.

## The tests

**Each state has a test that fails if the states are collapsed into one.** That is the
item's headline requirement, and it is enforced by *pairwise* assertions: for each pair of
states, a test asserts the two render **different** headings and **different** data
attributes. A collapse into one treatment fails.

### Backend

`backend/tests/ingestion/test_city_status_read.py` — NEW:

- The status is read for a provisioned city; `""` for a city with no provisioning row.
- The status is `""` for a city that does not exist at all (and **no `City` is minted** —
  the read never writes).
- The lookup finds the city by its canonical name, and by its `normalized_key` (a `City`
  minted by a venue).
- The status is read for a city whose provisioning row says each of the five statuses.
- **AD-13**: the read never writes; no audit row, no log line carrying the city name.
- The service never calls `resolve_city` (a mutation: swap the lookup for `resolve_city`
  and the "no City is minted" test must fail).

`backend/tests/personalization/test_browse_read.py` — extended:

- `BrowsePage.city_collection_status` is `""` when the user has no city.
- It is the city's status when the user has one.
- It is `""` for a city that was never provisioned.

`backend/tests/api/test_browse_api.py` — extended:

- The response carries `city_collection_status`.
- It is `""` when no city is set.

### Frontend

`frontend/tests/browse-states.test.tsx` — NEW:

- **One test per state**, asserting the state renders and says something **specific**.
- **One pairwise test per pair** (6 pairs), asserting the two states render different
  headings — so a collapse fails.
- The collecting state is `role="status"` / `aria-live="polite"`.
- The collecting state's heading is `<h1>`; the no-sources state's heading is `<h1>`.
- The quiet state is the **existing** `BrowseEmpty`, unchanged (asserted against its copy
  and its `data-browse-empty`).
- `city_missing` renders the quiet state with "Change city" and is **not** the collecting
  state.
- The no-sources state carries the coverage-request slot; the collecting state and the quiet
  state do **not**.
- The live-but-quiet state renders `BrowseEmpty` — **not** the no-sources state. (This is
  the "a covered city that is simply quiet must not be told its sources failed" AC.)
- The ordinary surface (live with cards) is **unchanged**: the hero, the two tiers, the
  search box.

`frontend/tests/city-page-states.test.tsx` — NEW:

- The city page's sparse state keeps its "coming soon" copy in every case.
- A `collecting` city adds the collecting sentence.
- A `no_providers` / `yielded_nothing` / `paused` city adds the no-sources sentence.
- A `live` city (or `""`) adds nothing.
- A published city (`is_published=True`) shows the listing and no state sentence.

`frontend/tests/api-contract.test.ts` — the status vocabulary:

- The frontend's set of statuses is exactly the model's set (a **source-level** assertion:
  the frontend file's literals vs the backend model's `Status.choices`).

## The mutation check

The probe lives beside item 8's:
`.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py` — **extended**, not
duplicated, because the probe is already the run's single mutation instrument.

Mutations to apply and revert, one at a time:

| # | Mutation | What it would mean | Caught by |
|---|---|---|---|
| 1 | `collecting` folded into the quiet state | A collecting city is told it is quiet — the exact lie this item fixes | the collecting-state test |
| 2 | `live` with no cards folded into the no-sources state | A covered city is told its sources failed | the live-but-quiet test |
| 3 | `city_missing` folded into the collecting state | A user with no city is told collection is under way | the city-missing test |
| 4 | the collecting state's `aria-live` removed | A state the reader is waiting on is silent | the a11y test |
| 5 | the status not read at all (`""` always) | Every city is quiet | the status test |
| 6 | the read mints a `City` | A read writes to the registry | the no-mint test |

**A mutation that survives is a missing test.**

## Files to change

### New

- `backend/apps/ingestion/services/city_status_read.py` — the read service.
- `backend/tests/ingestion/test_city_status_read.py` — its proof.
- `frontend/tests/browse-states.test.tsx` — the four states.
- `frontend/tests/city-page-states.test.tsx` — the city page's degradation.

### Modified

- `backend/apps/personalization/services/browse_read.py` — read the status, carry it on
  `BrowsePage`.
- `backend/apps/personalization/schemas.py` — `BrowseOut.city_collection_status`.
- `backend/apps/personalization/api.py` — pass it through.
- `backend/apps/ingestion/services/city_read.py` — carry the status on `CityPage`.
- `backend/apps/catalog/schemas.py` — `CityPageOut.city_collection_status`.
- `backend/apps/catalog/api.py` — pass it through.
- `frontend/components/browse/browse-states.tsx` — `BrowseCollecting`, `BrowseNoSources`.
- `frontend/app/browse/page.tsx` — the four branches.
- `frontend/components/city-page/city-page.tsx` — the degraded sparse state.
- `frontend/lib/api/{openapi.json,schema.ts}` — **regenerated by `make client`**.
- `backend/tests/personalization/test_browse_read.py`, `backend/tests/api/test_browse_api.py`
  — extended.

### Unchanged, deliberately

- `backend/apps/ingestion/services/city_provisioning.py` — item 7's, and it is right.
- `backend/apps/ingestion/services/city_probation.py` — item 8's.
- `backend/apps/personalization/models.py` — **no new column.** The status is not
  denormalised onto the personal side.
- `backend/worker/tasks.py` — no new task.
- `frontend/components/browse/browse-hero.tsx`, `browse-search.tsx`, `browse-grid.tsx` —
  **the layout, the two tiers and the search box are unchanged.**
- `frontend/components/browse/browse-states.tsx`'s existing four components — **untouched**,
  including `BrowseEmpty` and `BrowseSearchEmpty`.
- `backend/apps/catalog/public_surface.py` — the city page's cacheability is unchanged.

## Verification

```bash
uv run --directory backend ruff check apps/ingestion apps/personalization apps/catalog shared tests/ingestion tests/personalization tests/api
uv run --directory backend ruff format --check apps/ingestion apps/personalization apps/catalog shared tests/ingestion tests/personalization tests/api
uv run --directory backend lint-imports                                   # 21 kept, 0 broken
uv run --directory backend python manage.py makemigrations --check --dry-run   # No changes detected
uv run --directory backend python manage.py check                        # no issues
uv run --directory backend pytest -q
uv run --directory backend python ../.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py
cd frontend && pnpm test && pnpm typecheck && pnpm lint
make client                                                               # regenerates openapi.json + schema.ts
```

**`ruff format` is scoped to the directories being worked in** — never the repo root.

## What this unblocks

Item 10 (`city-coverage-request`) fills the `coverageRequest` slot this item creates, and
the endpoint it POSTs to.

Item 11 (`home-city-dropdown-catalog`) rewires the dropdown to the catalog — the other
half of the same surface, and it also corrects `home-city.tsx`'s docstring.
