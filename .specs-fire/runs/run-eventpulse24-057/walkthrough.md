# Walkthrough: run-eventpulse24-057

**Intent:** City Picker Over a Curated World List, With Automatic Collection
**Scope:** wide, 11 items · **Branch:** `city-picker-and-auto-collection` · 2026-11-21

## What this run was for

A reader could not choose their city. The picker's options were "the cities that have
events right now" — a mirror of what we happened to have collected — and the stored city
was quietly rewritten to a fallback whenever it was not one of them. So the product asked
a reader to pick a city, and then disagreed with them.

The intent's guarantee is one sentence: **"The stored city is the picked city. Never
silently rewritten to anything else."** This run makes that sentence true, and then makes
the pick *mean* something — a pick provisions a city, the city's collection says what is
true about itself, and a city that yields nothing is told so and given a way out.

Eleven items, in the order the chain demanded: **a world to offer** (the catalog, the
providers, the parser, the endpoint), **the storage rule**, **the provisioning**, **the
honesty about it**, and **the surface**.

## 1. The picker had no world to offer

The first item built the thing the picker was missing: a curated catalog of **166 cities**,
each with its own canonical name, its two spellings, its country, its region and its time
zone.

**The catalog's two forms are different strings on purpose.** `"Portland, OR"` is the
*stored* value — the one a preference holds, the one the server understands. `"Portland,
Oregon"` is the *label* — the one a reader reads, and the one that tells Atlanta from
Tbilisi. Nothing collapses them, and the mutation check holds both apart.

The catalog is hand-verified, not scraped, and its invariants are the dataset's own:
labels and values unique, every city resolvable to a time zone, every city answerable to a
provider set. **A test that a mutation can break** is the only proof of an invariant, so
every one of these has one.

## 2. A source carries its city's zone, so a new city can publish

Nothing could publish an event in a city we had not collected for, because a source had no
way to know the city's time zone — and a time zone is not a guess. A publication without
one is a local time nobody can read.

So a source carries its city's zone, and the city's zone comes from the catalog row, not
from the fetch. **FR-17 puts the API first**, so item 3 gave the API its own parser rather
than letting it borrow the crawler one: an API and a crawl are different shapes wearing
the same coat, and a parser that handles both handles neither cleanly.

## 3. The catalog became an endpoint, and it stayed session-free

`GET /api/public/cities` — every place a reader may pick, as `value`/`label` pairs.

**It carries no session**, because it is a public catalog and a public answer needs no
identity. It carries no query, because the answer is the same to everybody. It is
throttled under its own scope, because a list of 166 places is cheap to serve and
expensive to scrape.

**And for eleven items nothing called it.** That is the hole item 11 closed, and it is
worth naming here because the shape of the hole is the shape of the whole run: an
endpoint existed, was correct, was tested — and was invisible to the surface it was built
for. Nothing failed. The product was simply narrower than it looked.

## 4. The stored city is the picked city

The old rule was a *coverage* rule: if we had no events for the city a reader picked, the
server stored a fallback instead. Silently. So the reader picked Chittagong and the
preference said "Montgomery", and neither the reader nor the product knew.

**The rule is now the catalog's rule.** A city the catalog holds is stored **exactly as
picked** — verbatim, byte for byte, and the whole-dataset proof is 682 cases over the
catalog's cross-product. A city the catalog does **not** hold is **refused**: a 422, and
nothing is stored.

**The refusal is the interesting half.** A quiet substitution is a lie the reader cannot
see; a loud refusal is a message the reader can act on. The rule is unchanged for a *geo
guess* and a *backfill* — those cities were never the reader's choice, so a fallback is
still the honest answer there. **Only a choice is refused.**

## 5. A registry of which providers exist for which cities

Which provider serves which city is a fact about the *provider*, not about the reader,
and it changes on the provider's schedule. So it is a registry: `SourceSpec`,
`ProviderTemplate`, `resolve(city)`.

**The Eventbrite template is in the registry and disabled.** Its shape — the only JSON-LD
shape proven by running code — is kept, so enabling it is one constant after a person's
review of the Terms. `seed_dhaka_live.py` already says Eventbrite's Terms restrict
automated access and point at their API; **a disabled template that only hid itself would
be settled by whoever was paying attention.** "Disabled" means *cannot be registered*, not
merely quiet.

## 6. A pick turns into a collection

The pick used to store a string. Now it **provisions a city**: mint the `City` row,
register a `Source` per provider spec, and write a `CityProvisioning` row whose status is
the sentence the surface will read about that city.

**Three things this does not do**, and each is load-bearing:

- **It does not mint a city the reader did not choose.** A city we have never heard of is
  a *pick*, and a pick provisions immediately — a better answer than queueing it.
- **It does not retry.** The row's existence means "provisioned", whatever its status says.
  A reader's pick is not a retry request: they knew nothing failed, and a retry would be
  invisible to them. A retry belongs to a person or to the scheduler.
- **It does not write the reader's city into an audit trail.** The audit row carries the
  city *id*, never the city *name* — a person's city is weak location data about a real
  person (AD-13), while a *source's* city is a public fact about a place.

## 7. A city that yields nothing is told so

A thousand-city dropdown mints sources that fetch every four hours forever — for cities
with one reader and zero yield. The status was `collecting`, forever, whatever happened.

**Four honest statuses, and a probation that earns them.** A run publishes → the city is
`live` (terminal). Three consecutive zero-yield runs → the source is paused, and the city
is `yielded_nothing`. A source paused *by an editor* → the city is `paused`. A city with
no sources at all → never tried, which is not the same as tried and got nothing.

**`unchanged` is yield.** The most consequential line in the run. It is what a *healthy*
source returns on every poll after the first; without it, every healthy source would accrue
a zero-yield run per poll and be paused after twelve hours of doing its job perfectly.

**A 304 leaves the counter alone** — it proves neither emptiness nor content. Resetting
would let a source alternate "empty" / "304" forever and never be condemned. **Only a move
on evidence counts.**

And **publication is narrow**: only `new` and `superseded` make a city `live`. Yield is
not publication — a city that re-affirms old events forever is covered and producing, but
it never *published*, and "live" must mean "there are events in this city's catalogue".

**The probation runs in the ingest path, after the commit.** Not on a scheduler tick: a
city that yields nothing should say so the moment it is known, and the counter moves
*inside* the run's transaction while the city-wide consequence runs *after* it, in its own
transaction — running it inside would deadlock two concurrent runs of one city's two
sources.

## 8. A city says what is true about collecting it

Browse had one way to talk about a city, and it was wrong for three of the four states.
Now it says **one of four honest things**, in **three treatments** across two families:
`quiet` and `noCity` share the quiet treatment; `noSources`, `paused`, `noProviders` and
`failed` share the no-sources treatment.

**The distinction that matters:** state B (covered, quiet) and state C (never produced
anything) are different facts, and a collapse of the *groups* is the failure the item
exists to catch. A collapse *within* a group is the design.

**The vocabulary is read, not written down.** The test reads the model's `Status.choices`
and the components' own `status === "..."` comparisons. A hand-written list would have
missed the sixth status (`failed`), and the surface would have said "Nothing nearby
tonight" about a city whose provisioning had failed.

## 9. A reader can ask us to cover a city we have not covered

The no-sources dead end was a dead end: the reader was told we have nothing, and given
nothing to do about it. Now it offers an ask.

**One row per city, not one per reader.** The editorial question is "how many people want
this city covered?" and the answer to that is a number. "Did *this* reader ask?" has no
use and no reader who could act on it — so the row is on the **catalog** side, and the
uniqueness is a *named* constraint (`city_coverage_request_city_uq`) so a test can assert
it by name.

**The count is on the wire and not on the screen.** A reader told "you are the 47th person
to ask" is being told something about a crowd, and the product's voice is calm.

**The throttle runs before the idempotence shortcut** — a repeat still spends an attempt; a
limit a repeat could slip past is not a limit. And **a request never mints a city**: a
city we have never heard of is a pick, and a pick provisions immediately.

## 10. The picker finally offers the world

The last hole. The picker read the *preview's* list — the cities with events right now — so
a reader in a city the catalog holds and nothing has been collected for **was not offered
their own city**. The picker's whole purpose is to let them pick one.

**The guarantee was hollow until this item.** "The stored city is the picked city" is only
meaningful if the picker offers the picked city.

**The label is read; the value is stored, and nothing translates between them** — a native
`<select>` already separates an option's text from its value. "Atlanta, Georgia" and
"Tbilisi, Georgia" differ only in the first word, so a control that showed the value would
offer two near-identical entries, and one that submitted the label would store a string the
server refuses.

**The stored city is matched by its *value*, never its label** — the stored city is
"Portland, OR" and its label is "Portland, Oregon"; matching on the label would not find
it, would synthesise a second option, and would offer the reader the same city twice under
two spellings.

And the **docstring's false reason is gone**. It said the control is a select because the
server silently replaces a city with a fallback — **no longer true of a chosen city**,
which is now refused. The real reason replaced it: the catalog's size and the catalog's
canonical spellings. A docstring that explains a decision with a false reason sends the
next reader looking for a rewrite that no longer happens.

## The mutation check is the run's spine

**39 mutations, 39 caught, 0 survived.** Each item's whole-dataset invariants were
mutation-checked before its test report was written — **a mutation that survives is a
missing test**, and finding one is the point of the exercise.

**The two that had to be written before the code was.** "The stored city is matched by its
label rather than its value" — the mutation that would have offered a reader the same city
twice, caught by one test that exists because the plan's decision 3 said so before the code
was written. And "the picker goes back to the preview's city list" — caught by the
*endpoint-coverage* test rather than a component test, because the component would still
have worked perfectly with fewer cities. **The coverage test is the only thing that
notices the picker's source of truth changed**, and it notices in both directions: an
endpoint with no caller and no declaration is an orphan, and a declaration with a caller is
a stale exemption.

## Results

| Suite | Tests | Result |
|---|---|---|
| Backend | 9091 | pass, 1 warning |
| Frontend | 2957 (184 files) | pass |
| `tsc --noEmit` | — | exit 0 |
| `pnpm lint` | — | 0 errors, 2 pre-existing warnings |
| `pnpm format:check` | — | 44 unformatted — one *fewer* than the branch started with |
| Mutation probe | 39 | **39 caught, 0 survived** |
| import-linter | 21 contracts | 21 kept, 0 broken |

`make client` ran three times (items 4, 10, and the API surface of item 3), regenerating
both `openapi.json` and `schema.ts`.

## Still open, for a human

1. **The Eventbrite template is disabled and waits for a person.** Its Terms restrict
   automated access and point at their API. The shape is kept in the registry, so enabling
   it is one constant — but it is a review of someone's terms, not a code change.
2. **The catalog is hand-verified and hand-maintained.** 166 cities is a snapshot. Widening
   it, or correcting a row, is a deliberate edit with a whole-dataset test behind it.
3. **A city's sources are audited, never deleted.** A paused or `yielded_nothing` city's
   sources stay in the registry, paused, with their reason on the row. **The pause reason
   is a column and not the audit trail** — the trail is retained 24 months, and after that
   the answer disappears; the column is state, and the trail is accountability.
4. **The coverage-request queue has no editor UI.** The row and the counter exist, the
   admin is read-only, and the endpoint is throttled — but *acting* on the queue is a
   person's job and nothing surfaces it to them yet.
5. **A reader's coverage request never mints a city.** By design: a city we have never
   heard of is a pick, and a pick provisions immediately. If that rule is ever wrong, it is
   wrong here, in `coverage_requests.py`, in one place.
6. **The pre-existing formatting drift** — 44 files unformatted, down from 45 because
   item 11's `home-city.tsx` was in the set and was formatted here. The rest is not this
   run's to fix.
