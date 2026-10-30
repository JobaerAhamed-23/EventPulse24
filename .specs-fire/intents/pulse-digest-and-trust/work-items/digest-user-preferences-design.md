---
id: digest-user-preferences
title: The user's home city and the personal-events opt-out — design
intent: pulse-digest-and-trust
mode: confirm
created: 2026-10-30
---

# Design: The user's home city and the personal-events opt-out

Two stored preferences in the `personal` schema, written only by `personalization`
(AD-16): the user's **home city** and whether **personal events** appear in the digest.

Both are small to build and decision-heavy to get right, so the decisions are below and
the reasoning for each is recorded.

## Why the item exists at all

The composition service runs in the **worker** (AD-11), where there is no request and
therefore no headers. `GeoPort.resolve_city` takes "a bag of headers, not a request",
by deliberate design — so the city **must already be stored** by the time the job runs.
This is the whole reason the city is a separate work item from composition, and it is
why nothing in this item reads a header at composition time.

## The spine's own words

AD-10: the Relevance Pulse is written "at digest composition" into `personal`, and read
by the card, the detail and the email.

FR-5: the digest is "three cards for the user's beachhead" — the must-know card, the
nearby card, and the card they would not have found.

FR-8: the empty state reads "No qualifying events in **{city}**."

FR-19: "a user can opt out of personal events appearing in the Pulse Digest."

PRD `[ASSUMPTION-7]`: personal events appear **by default**. Open Question #13, owner
Product, still open.

## Decisions

### D1 — The home city joins `DigestPreference`, as a third field

The work item asks the design to decide whether the city joins `DigestPreference` or
stands alone, and quotes `DigestPreference`'s own docstring: "the shape is reconsidered
when a second, genuinely separate preference arrives."

**It joins.** The reasons:

1. **`DigestPreference` is already the "where and when" model.** It holds a delivery
   time and the timezone it is a wall clock in. A city is a third coordinate of the same
   question — *where the user is* — and the two travel together: a user who moves
   changes both, and the digest ranks on the pair.

2. **The docstring's condition is met, and met in the right way.** "A second,
   *genuinely separate* preference" is the test. A home city is not separate from the
   digest — it is a **coordinate of the same delivery**. A separate table would mean a
   second lookup for the same row's worth of information, and a second place a move
   has to update. The docstring is inviting the reconsideration, not forbidding the
   answer.

3. **It is one row per user either way.** `DigestPreference` has a unique constraint on
   `user_id`. A standalone `HomeCity` model would need its own. One row, one
   constraint, one write.

**The counter-argument, and why it loses.** A city could change without the delivery
time changing — "I moved to Chicago but keep 9am". A standalone model would express
that independence. But the independence is already expressible: `update_fields` on the
one column. The independence is a *write-time* concern, not a *storage* concern, and
the command layer owns the write.

### D2 — The city is a **nullable** field on `DigestPreference`, not a required one

This is the decision that most shapes the rest of the item.

`DigestPreference` exists today for users who completed onboarding step 3, and its
`user_id` is unique. If the city were a **required** field on that model, then every
existing row — every user who set a delivery time before this item — would be
invalid, and the city would have to be backfilled before the migration could even
apply. The model is also **created** by the onboarding flow, which sets the delivery
time; a required city would mean the city must exist before the delivery preference
does.

So the city is **nullable**, and its absence is meaningful in exactly one way:
**"we do not know where this user is."** That is different from "the user is in New
York City", and the difference is the whole point of the fallback.

**A nullable field is not a field that may be null.** The city is written by a command
that always writes *something*: either a catalog-covered city or the fallback. The
nullable column is the storage of "not yet set", for the accounts that predate this
item and for the window before the backfill runs.

### D3 — The catalog-coverage rule, and the NYC fallback, are **reused** — not reimplemented

FR-2's rule is already implemented and already tested:

- `list_supported_cities(now=...)` in `apps/ingestion/services/preview_read.py` — "a
  city is supported when it has at least one upcoming, published, non-superseded event
  with a *current* Event Fit".
- `PREVIEW_FALLBACK_CITY = "New York City"` in `shared/constants.py` — FR-2's "falls
  back to the most-popular city (NYC at MVP)".
- `PreviewCities.supports(city)` — the case-insensitive coverage check.

**This item reuses all three.** It does not write a second coverage rule and a second
fallback constant. Two rules for "which cities may a user be in" would be two rules
that could disagree, and the disagreement would show up as a digest that ranks on a
city the preview says is not served.

**The import is legal.** The `models-ingestion` contract protects
`apps.ingestion.models` — the *models* module — not the services. `personalization`
already imports `apps.ingestion.services.catalog_read` in three places
(`api.py`, `schemas.py`, `services/saved_events.py`), so this is the established
pattern for reaching across the AD-3 wall: through a published service, never through
a model.

**The canonical spelling is stored.** `list_supported_cities` returns the catalog's own
spelling of each city, and the events are filed under that spelling. A digest that
ranked on `"brooklyn"` while the events are filed under `"Brooklyn"` would find
nothing. So the stored value is the catalog's spelling, matched case-insensitively —
the same `_canonical` rule `preview_api.py` applies.

### D4 — The city is set **without a new question**: the preview choice carries, then the header, then the fallback

FR-1 caps onboarding at 3 steps and every step is skippable. This item adds no fourth
step and no new field to an existing step.

**The order of preference is:**

1. **The visitor's explicit preview choice**, carried across the sign-up boundary.
2. **The geo header**, read at sign-up.
3. **The NYC fallback**, recorded as a fallback and not as a guess.

**Why the preview choice comes first.** A visitor who corrected their city on `/preview`
and then signed up has told us their city more explicitly than any header will. Losing
that at the sign-up boundary and re-inferring from a header would be a small but real
insult — and the work item says so directly.

**The carry is technically constrained, and the constraint is stated here.** The preview
choice lives in a **session cookie** (`ep_preview_city`) that is read and written **in
the browser only** — deliberately, because a server-side choice would make `/preview`
vary per visitor and break AD-12's cacheability. The backend never reads that cookie.
It reaches the backend as the `city=` query parameter (or `use_geo=false`) that
`previewQuery()` builds.

So the carry is: **the frontend reads the cookie at sign-up and sends the city as part
of the sign-up request.** The backend receives an explicit city, and treats it exactly
as it treats the preview's explicit city — the same coverage check, the same
canonicalisation, the same fallback for an uncovered city.

This item owns the **backend** half: the command that accepts an explicit city, checks
it, and stores it. The frontend half — reading the cookie and adding the field to the
sign-up request — belongs to `frontend-onboarding-flow`, and this item's design states
the contract it must satisfy so the two can be built in either order.

### D5 — "Don't use my location" carries as **no city**, not as the fallback city

The preview choice has three shapes: `unasked`, `opted-out`, and `city`.

**A visitor who chose "don't use my location" has declined location inference.** The
work item asks for a decision rather than a default here, and asks specifically whether
"silently storing an inferred city for someone who declined inference" is acceptable.
It is not.

So `opted-out` carries as **an absent city** — and an absent city means the fallback
is **not** applied at sign-up, because the fallback *is* an inferred city. The user
declined inference; the NYC fallback is inference with a different source.

**What the digest then ranks on.** This is the honest question, and it has an honest
answer: **nothing, until the user picks a city.** A digest that ranked on NYC for a
user who declined location would be showing them a city's events under a city they did
not choose.

But a digest has to show *something*. FR-8's empty state reads "No qualifying events
in **{city}**" — which needs a city to name.

**The resolution:** the opt-out does not carry a city at sign-up, and the user's
`DigestPreference` has **no city** until they choose one. The digest for such a user
renders the empty state **without a city in it**, and the **nearby** slot falls back to
the user's **timezone** — which the onboarding flow already collects, and which the
user consented to explicitly as a delivery preference.

**This is recorded as an open decision, not a settled one.** PRD Open Question #13 is
still open with Product, and the question "what does a user who declined geo see?" is
adjacent to it. The behaviour this item implements is the *conservative* one — no city
stored, no inference — and it is a placeholder that Product can change without a
migration, because a city that is `NULL` is exactly "we do not know", and that state is
already reachable.

**What is not negotiable:** storing an inferred city for a user who declined inference.
That would be storing location data the user refused to provide.

### D6 — The personal-events opt-out is a **stored flag on `DigestPreference`**, defaulting to included

FR-19's third consequence is "a user can opt out of personal events appearing in the
Pulse Digest", and `[ASSUMPTION-7]` makes it opt-out, not opt-in.

**It joins `DigestPreference` too**, for the same reason the city does: it is a
**digest** preference, not a general one. It says what goes *into this user's digest*,
and it travels with the other two digest coordinates.

**It is a boolean that defaults to `True`** — personal events **are** included. That is
`[ASSUMPTION-7]`, and the default is the assumption itself: an opt-out default is
"include", so the row's default *is* the assumption.

**The flag is stored, not derived.** There is nothing to derive it from — no other
table records the user's wish — so a stored boolean is the only shape it can have.

**`[ASSUMPTION-7]` is recorded as an assumption, and the assumption is visible.** The
model's docstring says the default is `[ASSUMPTION-7]` and that Open Question #13 may
change it. A reader who changes the default is changing the product's default
behaviour, and the docstring says so where they will see it.

### D7 — A separate model is **not** introduced for either value

Both values are columns on `DigestPreference`. No new table, no new migration for a
new model, no new unique constraint, no new ownership entry in
`tests/architecture/test_write_ownership.py`.

**The rule that decided it:** a new table is a thing with an owner, a retention
category, a retention window, a backfill, and a place a future reader must look. Both
of these values have **one** row per user, they are **read together** (the composition
service needs the city, the slot assignment and the opt-out in one go), and they are
**written together** (a user who moves and opts out in the same settings visit).

**The counter-argument, recorded.** `DigestPreference`'s docstring warns that a
"delivery time and a zone" is "a single value with two parts, read as a unit and written
as a unit", and that "a graph would add a node type, an edge type and a traversal for
one row". The same argument now applies to *three* parts. The warning is about not
over-engineering into a graph — and three columns is not a graph. The shape stays
deliberately small, and the docstring is updated to say what it now holds and why the
reconsideration still does not call for a graph.

### D8 — Both values are written by **named commands** with audit entries (AD-5)

FR-7's "user in a new timezone" case and a plain move both need a path, and the
*settings surface* is out of scope — the **command** is not.

**The commands live in `apps/personalization/services/`**, beside `onboarding.py`'s
`set_digest_preference`, and follow its exact shape:

- the user's advisory lock (`_lock_user`), so two concurrent writers cannot both find
  no row and both insert;
- `transaction.atomic(using=PERSONAL)`;
- an upsert on the one row;
- `write_audit(...)` **inside** the transaction — an audit row committed apart from its
  mutation could record a change that rolled back;
- the read-back through the published read function.

**The audit rows carry the city — or do they?** AD-13's discipline is that a city is
"weak location data about a real person" and belongs alongside the email address, not in
a log line. The audit table is a `retention_category = AUDIT_LOG` table, i.e. it *is*
a log.

**The city is not written to the audit `details`.** The audit row records **that** the
city changed, and the action name says which. The *value* stays out of the log. The
audit row is for "what changed", and "the home city changed" answers that completely;
the new value is one read of the row away and is available to whoever needs it under
the same access control as the row itself.

**The opt-out flag is written to the audit `details`.** It is a boolean, it is not
location data, and "did they opt in or out" is exactly the question an audit row
should answer.

### D9 — The **backfill** is an idempotent management command, and it writes the **fallback**

Accounts created by the onboarding intent have no city at all. The backfill is
`config/management/commands/backfill_digest_cities.py`, modelled on
`backfill_event_fit.py`:

- **idempotent** — running it twice writes the same value twice, not two rows;
- **`--dry-run`** — reports the count and writes nothing;
- it holds **no model query of its own**: `apps.personalization.models` is importable
  only from `apps.personalization` (AD-2), so the query lives in the service and the
  command calls it;
- it runs on the `PERSONAL` alias.

**What it writes: the fallback city.** The backfill has no better information than the
NYC fallback — there is no geo header in a management command, and the accounts it
fills were created before this item existed. Writing the fallback is honest: it is
recorded as a fallback, and the user can change it.

**It does not overwrite a city that is already set.** A user who has already picked a
city keeps it. That is what makes it idempotent *and* what makes it safe to run after
the sign-up path is live.

### D10 — Neither value is **ever** logged, and the city is not in `__str__`

AD-13's discipline, carried from `DigestPreference`'s existing code.

- **`__str__` names the delivery time and the timezone** — it already does, and it does
  **not** name the city. The city is weak location data about a real person; putting it
  in `__str__` puts it in every log line and every admin list column.
- **The audit `details` carries no city** (D8).
- The **audit row's `target_id`** is the `DigestPreference`'s id, not the user id — so
  the audit row does not become a per-user index of where people live. (The existing
  `onboarding.digest_preference_set` audit already uses the preference's id.)

**The city is stored as a plain `CharField`, not encrypted.** This is a deliberate
departure from `ACCOUNT_IDENTITY`, and it is worth saying why: the email address is
encrypted because it is a **credential** — it authenticates. A city is not a credential
and it does not authenticate anything; it is a preference, and `DigestPreference` is
already `PREFERENCE_SIGNALS`. Encrypting it would make it unqueryable and unindexable
for no gain. The protection it gets is the same as every other preference's: it is in
the `personal` schema, readable only by `ep_personal`, and purged with the account.

### D11 — The retention category is **`PREFERENCE_SIGNALS`**, unchanged

`DigestPreference` already declares `RetentionCategory.PREFERENCE_SIGNALS`, and it
keeps it. A city and an opt-out flag are preferences — the inputs to what the digest
shows — and PRD §10.2's 12-month rolling window is the category PRD assigns to
preference signals.

**The 12-month window does not break anything here**, which is the contrast with
`DigestComposition` (D4 of the digest-composition-models design, where
`PREFERENCE_SIGNALS` would have broken AD-10's "most recent composition" promise).
The difference is real and worth stating: a **composition** is the *output* — a record
of what the user was shown — and must outlive the day it was shown. A **city** is an
*input* and may be refreshed.

**A user whose city row expires falls back to the NYC fallback** rather than to "no
city" — because the digest must have a city to rank on and to name in the empty state.
That is the same fallback the sign-up path uses, and it is why the fallback lives in
one place.

### D12 — The API surface is **two endpoints on the existing router**, and the values reach the frontend through the generated contract

The values are exposed, because the digest header shows "Brooklyn, NY" (UJ-1) and the
empty state names the city (FR-8).

**Two endpoints**, on the existing `personalization` router, which already carries
`auth=current_user`:

- `GET /personal/digest-preference` — the current values. This **already exists** as
  part of the onboarding state read (`read_onboarding`), so the city and the opt-out
  are added to that response rather than to a new endpoint.
- `PUT /personal/digest-preference` — the change command. This **already exists**
  (`put_digest_preference`), so the city and the opt-out are added to that body.

**The body change is additive and backward-compatible.** The city and the opt-out are
optional in the request body: an existing client that sends only `delivery_time` and
`timezone` keeps working, and a command that omits them **does not clear** the stored
values.

**This endpoint cannot clear the city, and that is a shape limitation, not an
oversight.** A `null` city and an omitted city are the *same value* in Pydantic, so
"leave it alone" and "clear it" cannot be told apart in this body. A shape that cannot
say which one it means must not guess: guessing "clear" would wipe the city of every
client that sends the field as `null`, and guessing "leave alone" would make the value
unreachable. So `null` means **leave it alone**, and clearing is not offered here at
all — the service can clear it (`set_home_city(city=None)`), and a future settings
endpoint may expose it through a shape that *can* distinguish the two.

**AD-19: the values reach the frontend through the generated contract** — the OpenAPI
schema is exported and the TypeScript client regenerated (`make openapi && make
client`). Nothing is hand-written on the frontend side. This item's frontend half is
the settings surface, which is out of scope; the contract is updated so the next item
can use it.

### D13 — The **sign-up** path: where the city is first written

The city must exist before the composition worker runs, and the earliest moment the
backend has an identity for the user is **sign-up**.

**The sign-up command accepts an optional explicit city** and runs the coverage check
(D3). If the client sends a city that the catalog covers, it is stored canonically. If
it sends one that the catalog does not cover, the **fallback** is stored — because at
sign-up the city was *inferred* by the client, and the preview's rule is explicit: an
unsupported *geo* city falls back, because the visitor did not choose it.

**This asymmetry is the preview's rule, and it is inherited, not invented:**

| Where the city came from | The visitor chose it? | Unsupported city → |
|---|---|---|
| The preview's explicit `?city=` | yes | **empty preview, city named** — the truth |
| The geo header | no | **the fallback** — the edge guessed |
| The sign-up body, from the preview choice | yes | **the fallback** (D14) |

### D14 — The sign-up body's city is treated as **inferred**, not as an explicit choice

This is the one place where the design departs from the preview's rule, and it departs
**deliberately**, so it is argued here.

At the preview, an explicit `?city=` that the catalog does not cover yields an **empty
preview carrying that city's name** — because "showing the fallback's events under the
requested name is a heading that lies", and at that point the visitor is still on the
page and will see the empty state.

At **sign-up**, there is no page to show an empty result on. The user has created an
account; the digest will be composed for them overnight. Storing a city the catalog
does not cover would produce a digest that ranks on nothing and names a city in its
empty state — "No qualifying events in Springfield" — where Springfield was a place
the client inferred and the catalog has no events for.

**So an unsupported city at sign-up stores the fallback**, exactly as an unsupported
geo city does at the preview. The user's account is not blocked by a city the catalog
cannot serve, and the digest says something true.

**The rule for the value the user *actually* chose is different, and the difference is
recorded rather than lost.** The preview choice carries an explicit city. If that city
is not covered, storing the fallback loses what the user said. The design therefore
records the *rejected* city alongside the fallback, in the audit row's action name — no,
not in the audit details (D8 says no city goes there).

**The resolution is that the choice is preserved at the point it was made, not at
sign-up.** The preview already answers the unsupported-city case correctly, in the
preview itself: an empty preview carrying the requested city's name. The user sees
"no preview available in Springfield yet" and can pick another city. By the time they
sign up, the cookie holds a city they saw working — or one they chose deliberately
and the client can pass through.

**The concrete rule, stated once:**

- An unsupported city from the **geo header** → the fallback.
- An unsupported city from the **preview choice** → the fallback, and the fallback is
  recorded as a fallback (`city_source`), so the digest can tell the user "we are
  showing New York City because we do not have your city yet" rather than silently
  implying New York City is their city.

**The `city_source` flag.** `DigestPreference` carries a **`city_source`** column
alongside the city, with values `geo`, `choice`, `fallback`, `backfill`. This is what
makes "recorded as a fallback rather than a guess" — which the work item explicitly
requires — actually true and observable. The digest can say *"showing New York City —
we don't have your city yet"* when the source is `fallback`, and the user is not lied
to.

### D15 — Where the transaction boundaries fall

Two writes in this item could join a transaction, and the two answers are **not** the
same, so both are argued here.

**The digest-preference endpoint: one transaction.** A request that sets the delivery
time *and* the city is one decision by one user. If the city write failed after the
delivery time had been written and the two were separate commits, the row would say
"8am" while the city said nothing changed — and neither half would be wrong on its
own, which is the worst kind of half-applied state. So the city is written **inside**
the delivery-time transaction.

**The sign-up path: the city is outside the account's transaction.** The account is the
thing that must not be half-made. An account that exists without its audit row is a
hole; an account that exists without a city is merely a user whose city we do not know
yet — a state the digest already handles (D5) and one the backfill fills (D9). So if
the city write fails, the account stands and the city is missing. The opposite trade —
rolling the account back because a city could not be stored — would lose a real
sign-up over a preference, and would leave the caller with a 500 for an account that
might or might not exist.

**The duplicate sign-up never touches the real holder's city.** The duplicate path
returns before the city is written, and the duplicate path is the one an attacker
reaches. A duplicate must not be able to change another account's stored preferences.

This costs one column and it is the difference between a fallback that is honest and
one that is invisible.

## The model

### `DigestPreference` (modified)

| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDField` (pk, UUIDv7) | from `UUIDv7Model` |
| `user_id` | `UUIDField` | by value (OQ-8) — unchanged |
| `delivery_time` | `TimeField` | the local wall clock — unchanged |
| `timezone` | `CharField(max_length=64)` | the IANA zone — unchanged |
| **`city`** | **`CharField(max_length=64, null=True, blank=True)`** | **the catalog's spelling of the user's home city; null = "not known"** |
| **`city_source`** | **`CharField(max_length=16, null=True, blank=True, choices=CitySource.choices)`** | **how the city was arrived at: `geo`, `choice`, `fallback`, `backfill`** |
| **`include_personal_events`** | **`BooleanField(default=True)`** | **`[ASSUMPTION-7]`: personal events are included unless the user opts out** |
| `created_at` | `DateTimeField(auto_now_add=True)` | unchanged |
| `updated_at` | `DateTimeField(auto_now=True)` | unchanged |

**No new table.** D7.

**`city_source` is nullable for the same reason `city` is.** A row written before this
item has neither. The pair means the same thing: "we do not know where this user is".

**`city_source` is constrained to agree with `city`.** A city with no source, or a
source with no city, is a state nothing should produce. The check constraint is the
database holding it, so a bug in the command layer cannot leave a row claiming a
fallback that never happened.

**`include_personal_events` is not nullable and has no check constraint.** It is a
boolean with a default; there is no invalid state for a boolean.

## What this item does not decide

- **The settings surface.** The command exists; the screen that calls it is out of
  scope (the work item says so explicitly).
- **The frontend's half of the sign-up carry.** This item defines the backend contract
  — the sign-up body accepts an optional city — and `frontend-onboarding-flow` reads
  the preview cookie and sends it.
- **How the composition service reads these values.** It reads them; this item owns
  storing them and the commands that write them.
- **What the digest shows for a user with no city.** The city is absent, the nearby
  slot falls back to the timezone, and the empty state names no city. The *wording* of
  that state is `frontend-digest-home`'s.
- **Open Question #13.** `[ASSUMPTION-7]` is recorded as an assumption, and the
  default is the assumption. If Product changes it, the default changes — and the
  opt-out flag's name stays, because a flag that stores "include personal events" is
  correct whether the default is true or false.

## Decisions summary

| # | Decision | Why |
|---|---|---|
| D1 | The city joins `DigestPreference` | It is a third coordinate of "where and when the digest arrives", read and written together; `DigestPreference`'s docstring asks for the reconsideration, and the answer is one row, not two |
| D2 | The city is **nullable** | A required field would invalidate every existing row and force the backfill before the migration could apply; `NULL` means "not known", which is a real state |
| D3 | The coverage rule and the NYC fallback are **reused** | Two rules for "which cities may a user be in" would disagree; the service is the legal cross-wall import (`models` are protected, services are not) |
| D4 | The preview choice carries, then the header, then the fallback | An explicit choice beats an inferred one; the carry is a request field, because the cookie is browser-only by design (AD-12's cacheability) |
| D5 | "Don't use my location" carries as **no city** | Storing an inferred city for a user who declined inference is not acceptable; the digest falls back to the timezone instead |
| D6 | The opt-out is a **boolean on the same row, defaulting to included** | `[ASSUMPTION-7]` is opt-out; it is a digest preference, so it belongs with the digest's other coordinates |
| D7 | **No new model** | One row per user, read and written together; a new table means an owner, a retention category, a backfill and a second lookup for the same information |
| D8 | Named commands with audit entries; the **city is not in the audit details** | AD-13: a city is weak location data; the audit row says *that* it changed, and the value stays out of the log. The boolean is in the details — it is not location data |
| D9 | An idempotent backfill command writing the fallback | It has no better information than the fallback; it never overwrites a city already set |
| D10 | The city is **not** in `__str__` and **not** encrypted | A city is not a credential; it cannot authenticate. Encrypting it would make it unqueryable for no gain |
| D11 | Retention stays **`PREFERENCE_SIGNALS`** | A city is an *input*, and may be refreshed — the contrast with a composition, which is an *output* and must outlive its day |
| D12 | Two existing endpoints, additive bodies, generated contract | The read and the write already exist; AD-19 says the frontend never hand-writes the shape |
| D13 | Sign-up accepts an optional city and runs the coverage check | The city must exist before the worker runs; sign-up is the earliest moment the backend has an identity |
| D14 | An unsupported sign-up city stores the fallback, and `city_source` records it | At sign-up there is no page to show an empty result on; the fallback must be honest, and `city_source` is what makes it honest |
| D15 | The delivery time and the city land in **one transaction**; the sign-up city is **outside** the account's | A request that sets both is one decision, and a half-applied decision is worse than a failed one. But an account is the thing that must not be half-made: an account with no city is a state the digest handles, and one without its audit row is a hole |
