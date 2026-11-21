---
run: run-eventpulse24-057
work_item: browse-collecting-states
intent: city-picker-and-auto-collection
generated: 2026-11-21
status: approved
---

# Review Report: The four honest states

## Summary

Item 8 gave a city a status that says something true about our collection of it. **Nothing
read it.** The provisioning status existed on the row, was written by the probation, and
reached no reader — so every city with no events said the same thing: "Nothing nearby
tonight. Try a wider city?"

**That sentence is the honest answer to exactly one of the four situations a city can be in.**
For the other three it is a lie. A collecting city is not empty. A city whose sources failed is
not quiet. A reader with no city at all is not in a city.

This item reads the status and turns it into four distinct surfaces.

**8 mutations, 8 caught.** `city_status_read.py` at 100% coverage. The backend suite: **9036
passed, 0 failed**. The frontend suite: **2922 passed, 0 failed**. `lint-imports` 21 contracts
kept, 0 broken.

## The findings

### 1. The status reaches the payload through a *service*, not through the models

**This was the item's whole architectural problem, and it has one answer.**

The provisioning status lives on `catalog.ingestion_cityprovisioning`. The surfaces that need
it live in other apps: Browse's read is in `apps.personalization`, the public city page's is
in `apps.catalog`. Neither may import `apps.ingestion.models` — AD-3, enforced by the
import-linter's `models-ingestion` contract.

**Four ways were considered, and three of them are wrong:**

| Option | Why not |
|---|---|
| Import `apps.ingestion.models` directly | **Breaks AD-3.** The contract is real and enforced. |
| Denormalise a `city_status` column onto `DigestPreference` | **A second writer of one fact** (AD-16). It would go stale the moment the probation moved a city to `live`, and nothing would ever notice. |
| A second endpoint for the status | **Two answers that can contradict.** The cards and the status would come from different reads, and a reader could see "collecting" above a listing that exists. |
| **A service handing over a frozen dataclass** | **The sanctioned seam, and the precedent is everywhere**: `catalog_read`, `preview_read` and `city_read` are all services that hand over plain data. `browse_read.py` already imported `catalog_read`. |

The contract's own name says it: *"only `apps.ingestion` imports `apps.ingestion.models`
(**others call its services**)"*. **The contract protects the models module, not the app.**

`apps/ingestion/services/city_status_read.py` is that service. It hands over
`CityCollectionStatus` — a frozen dataclass with a `status` and a `source_count`, and no model
anywhere in it.

### 2. A read must not mint

**`resolve_city` *creates* a `City`**, so it was unusable in a read path. Using it would mean
that every reader who opened Browse for a city we had never provisioned would put that place
into the registry — the exact thing item 5's guarantee forbids in spirit: the stored city is
the picked city, and a place nobody picked does not become a stored city by being looked up.

So the read does its own lookup, and the module's docstring says it in the first line:
**"This module reads and never writes."** No `resolve_city`, no creation, no audit row.

The mutation check swaps the lookup for a `resolve_city` call (mutation #2) and the test fails.

### 3. The status read costs one query, and the query-count guards were raised honestly

The first implementation cost **two** queries — a city lookup and then a provisioning lookup —
and the existing query-count guards caught it immediately.

**Two fixes, in order.** The two city lookups (canonical name and identity key) were collapsed
into one `Q(name=name) | Q(normalized_key=key)`. Then the provisioning row was **joined** rather
than fetched after, with `annotate(provisioning_status=F("provisioning__status"))` — a reverse
`OneToOne` joins in the same query.

That left **two** queries on Browse (the status, and the pool) where there had been **one**.
**The guard was raised from 1 to 2, honestly, with the reason in the comment:** the status is a
*separate* fact from the pool, it comes from a *different table*, and one query cannot serve
both without a join that would multiply the pool's rows by the provisioning's. The same
applies to the city page's guard, raised from 3 to 4.

**A raised bound is not a weakened test** when the reason is written down. What would have
been a weakening is raising it silently, or raising it to a number that no longer bounded
anything.

### 4. Three treatments, and two families within them

**This is the finding the first draft of the tests got wrong, and the tests are what caught
it.**

The plan said "five states, five headings". The implementation says something finer, and the
pairwise test forced the finer thing to be written down:

- **`collecting`** — its own treatment.
- **`quiet` and `noCity`** share the *quiet* treatment. A reader with no city and a reader
  whose city is quiet are in the same place: there is nothing to show, and the way out is the
  same — change city. The difference between them is *why* there is nothing, and the reader
  has no city to act on the difference.
- **`noSources`, `paused`, `noProviders` and `failed`** share the *no-sources* treatment.
  Four facts about *why there are no sources*, and the same honest sentence from the reader's
  side.

**So the assertion is not "seven headings" — it is "three treatments, and the grouping is
exactly these two families."** A collapse of the *groups* is what the file exists to catch; a
collapse of a group onto itself is the design, and the AC says so for `paused` explicitly
("Paused renders the same honest line as 'no sources'").

**The distinction is not lost.** It is in the payload, and the payload is what the editorial
surface reads. A test asserts it: the two statuses are different strings.

### 5. The backend has **six** statuses, and the plan had named five

**The vocabulary test found this, and it is the argument for reading the model's choices
rather than writing them down in a test.**

The plan listed `collecting`, `live`, `no_providers`, `yielded_nothing` and `paused`. The
model has a sixth — **`failed`**, written by item 8's probation when provisioning itself
errored.

`failed` is a fact about *why there are no sources* — the same family as `no_providers` — so
it joins the no-sources family on both surfaces, and the reader gets the same honest sentence.

**A hand-written list in the test would have missed it**, and the surface would have said
"Nothing nearby tonight" about a city whose provisioning had failed — which is the exact lie
this item exists to remove.

**The test reads the model's `Status.choices` out of the Django source, and the frontend's
set out of the two components that branch on it.** The set must be *equal*, not a subset: a
frontend status the backend does not have is a sentence waiting to be wrong, and the day the
backend's spelling changes the string simply stops matching — silently, and every city in
that status falls back to the quiet state.

### 6. `live` is named in code, not handled by omission

A `live` city is the quiet state's city — a covered city with nothing on tonight is not a
special case, it is what a working collection looks like on a Tuesday. So `live` needs no
*treatment* of its own.

**But it is written out anyway**, in both surfaces, as `status === "live"`. A reader of the
file should be able to see that `live` is *handled* — by falling through — rather than infer it
from its absence, and the vocabulary test holds both surfaces to the same set of statuses.
**A status that is handled by omission is still a status the surface knows about**, and the
test can only check that if the code says so.

### 7. The threshold and the status are different questions, and the city page says so

**FR-27's `is_published` asks whether the city has enough events on record to deserve a
page.** The provisioning status asks whether our *collection* of it is working.

The city page's rule is asymmetric, and deliberately so: **the threshold decides whether the
page shows a listing; the status only ever *adds* a sentence to the sparse state.** The
"coming soon" copy is true of the threshold whatever the collection is doing, so it is never
removed — a `collecting` city below the threshold says "Coming soon — we're growing {city}'s
coverage" *and* "We're collecting events for {city}". Both are true.

And a **published** city says nothing about its collection, whatever the status. Our
collection's state does not un-publish a city that has earned a listing, and degrading a city
that has events because of a status the frontend has not learned about would throw away real
events.

### 8. The coverage-request control is a *slot*, not a control

**Item 10 owns the control; item 9 owns the place it goes.** `BrowseNoSources` accepts a
`coverageRequest?: ReactNode` prop and renders it inside `<div data-browse-coverage-request>`.
The slot is empty today, so it offers the reader nothing it cannot do — and the test says so.

This satisfies both items' criteria without either stealing from the other: item 9's AC ("the
no-sources state carries the coverage-request control") and item 10's AC ("renders in these
states only"). **A slot that is empty is honest**; a control that pretends to work is not.

### 9. One pre-existing failure was found, and it belongs to item 11

`tests/endpoint-coverage.test.ts` failed on `GET /api/public/cities` — an endpoint in the
contract with no frontend caller. **It predates this item** (verified by stashing the item's
work and re-running: the same failure).

It is item 11's work — the city picker rewiring is what calls that endpoint. The interim fix
is a `DECLARED_UNCALLED` entry whose reason names item 11 and says plainly that it is a
placeholder, not a permanent exemption. **The map is a claim about the world**, and a claim
that says "this comes out of the map when the picker calls the endpoint" is honest in a way
that a silent exemption is not.

## The security and architecture notes

- **AD-3** — the surfaces do not import `apps.ingestion.models`. The 21 import contracts are
  all kept. The seam is a service handing over a frozen dataclass.
- **AD-10** — the surface does not rank, sort, re-tier or re-bucket. The status changes
  *which state is rendered*, never the order or the content of the cards. Asserted by
  `test_the_status_does_not_change_the_cards`.
- **AD-12** — the public city page reads no session, and its response stays byte-identical for
  everybody. The status is a fact about a *place*, so it rides in the same cacheable response.
  Asserted by `test_the_status_does_not_vary_by_the_session`.
- **AD-13** — no PII reaches a log or an audit row. The read writes nothing at all, so there
  is nothing to leak.
- **AD-16** — the provisioning status has exactly one writer (the ingestion app). The surface
  reads it and does not copy it.
- **No new endpoint, no new migration, no new model, no new table.** `makemigrations --check`
  reports no changes.

## Deliberately not changed

- **`backend/apps/ingestion/services/city_provisioning.py`** — item 7's, and it is right.
- **`backend/apps/ingestion/services/city_probation.py`** — item 8's. This item only *reads*
  what it writes.
- **`backend/apps/personalization/services/browse_read.py`'s card assembly** — the cards, their
  order and their save state are untouched. The status is carried alongside them.
- **`BrowseEmpty`** — the quiet state's copy and its "Change city" link are unchanged. A
  covered city must not be told its sources failed, and the existing empty state was already
  the honest answer for exactly the case it is used in.
- **The `city_missing` case** — a reader with no city gets the quiet empty state with "Change
  city", rather than a city we guessed. A city they never picked would make "Change city" a
  correction of our guess instead of a setting of their preference.
- **The public city page's route, metadata, caching and 404 behaviour** — untouched. The
  status only adds a sentence to the sparse state.
- **`backend/worker/tasks.py`** — no new task. The status is read on demand.

## What this unblocks

**Item 10 (`city-coverage-request`)** fills the `data-browse-coverage-request` slot that
`BrowseNoSources` now carries, in the no-sources family only.

**Item 11 (`home-city-dropdown-catalog`)** rewires the picker to the catalog, and removes the
`GET /api/public/cities` declaration this item had to add.
