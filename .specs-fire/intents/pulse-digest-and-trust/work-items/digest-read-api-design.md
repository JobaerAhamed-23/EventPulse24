# Design: The digest read API — persisted rows, and nothing else

**Work item**: `digest-read-api`
**Intent**: `pulse-digest-and-trust`
**Mode**: confirm
**Date**: 2026-10-30

---

## The shape of the problem

`digest-composition-service` wrote the digest. This item serves it.

The endpoint is a **read of persisted rows and nothing else**. That is the whole
design, and it is the design's *value*: AD-10 says an explanation is persisted at
composition time and **never recomputed at render**, and this endpoint is where that
rule either holds or is quietly broken. A read that scored, ranked or generated a tag
would be a read that could disagree with the card the user saw that morning — and the
disagreement would be silent, because the recomputed answer would look perfectly
reasonable.

**So the API's job is to be boring.** It resolves the user from the session, finds the
digest for the user's local date, joins the persisted rows to the display facts, and
projects them onto the wire shape. It computes nothing.

### The three things that are easy to get wrong

1. **The empty state and the not-yet-composed state are different facts.** "We looked
   and there is nothing" and "we have not looked yet" are different, the frontend shows
   different things for them, and collapsing them is the bug this item exists to
   prevent.
2. **The card's display facts live in two places.** A `DigestComposition` row holds the
   *explanation* — the score, the bucket, the tags, the badge. The *name, time and
   location* live in the catalog (for a public event) or in the user's own agenda (for a
   personal one). Neither place holds both.
3. **Three cards must not become three-plus queries per card.** The budget is <500ms
   p95 cached, and an N+1 that lands silently inside a budget is how the budget is
   missed.

---

## D1 — The endpoint is `GET /api/personal/digest`, on the existing personal router

**Decision.** One endpoint on the existing `apps/personalization/api.py` router:

```
GET /api/personal/digest → 200 DigestOut
```

**Why the existing router and not a new one.** The router already declares
`auth=current_user` at the module level, so every endpoint on it is session-authed and
none of them can be added without auth. A new router would have to repeat that
declaration, and the repetition is the risk: a router declared without `auth=` would
serve personal data to anyone. **The personal router has exactly one `auth=` and it is
at the top.** Putting the digest there makes "is the digest behind a session?" a
question with one answer.

**Why `/digest` and not `/digest/today`.** The endpoint serves "the user's current
digest", and the word "today" would be a claim about *whose* today — the user's or the
server's. The path says nothing about the date, and the response carries the
`local_date` it resolved, so the client can see which day it got.

**Why there is no date parameter.** The endpoint reads **today's** digest. A date
parameter would make it a digest *history* endpoint, which is a different surface (the
Timeline, the archive) and not this item's.

**Why no `actor`.** The read writes nothing, so there is no audit row to attribute
(AD-5 records decisions, and reading is not a decision). The service takes `user_id`
and `now`, exactly like `list_personal_events` and `list_saved_events`.

**Why no rate limiting.** The personal router has none, and this is a read of the
user's own row — the throttle exists where an anonymous client can cost the server
work. Adding one here would be the only authed read with a limit, which is a surprise.

---

## D2 — The read is a **service**, not ORM calls in the endpoint

**Decision.** A new module `apps/personalization/services/digest_read.py`, exposing
one function:

```python
def read_digest(*, user_id: UUID, now: datetime) -> DigestRead
```

**Why it is not in `api.py`.** The endpoint layer in this codebase is thin by
convention and by contract: it resolves the user, calls a published service, and
projects the service's plain data onto the wire shape. It never touches the ORM. The
`models-personalization` import contract is what keeps that true — `api.py` may not
import `apps.personalization.models` at all — so the endpoint **cannot** query the
digest without a service that does.

**Why it is not in `digest_composition.py`.** That module is a **command** module: it
opens a transaction, takes an `Actor`, writes an audit row, and is the only writer of
these rows (AD-16). A read in it would be a second kind of thing in a module whose
whole identity is "the writer". `digest_candidates.py` set the precedent for a separate
read module: "These are reads, not commands. They write nothing, audit nothing and log
nothing (AD-13)."

**Why it is not in `digest_candidates.py`.** That module's reads are *candidate* reads —
the pools the composition ranks from. This read is the *composed* read: the digest and
its rows, already decided. Mixing them would put "what might be ranked" and "what was
ranked" in one file, and the two answer different questions about the same day.

**Why it is not in the API layer at all.** AD-19: the wire shape lives with the surface
that owns the contract. The *read* lives in the service, and the *shape* lives in
`schemas.py`.

---

## D3 — The three states, and they are three distinct responses

**Decision.** The endpoint always answers **200**, and the body's `status` field says
which state it is:

| State | `status` | `cards` | `city` |
|---|---|---|---|
| composed | `"composed"` | 1–3 cards | the user's city |
| composed and empty | `"empty"` | `[]` | the user's city |
| not composed yet | `"not_composed"` | `[]` | the user's city |

**Why 200 for all three, and not a 404.** A 404 would mean "there is no such digest",
which is true of the not-yet-composed state and false of the empty one — and the
frontend would have to map a status code onto "nothing happening" versus "not ready",
which is exactly the interpretation the API is supposed to remove. **Three explicit
states, one status code, and the state is named in the body.**

**Why `not_composed` is not the empty state.** They are different facts and the
frontend shows different things:

- **empty** — "Nothing on the pulse today. The calendar is yours." (FR-8's copy)
- **not composed** — the digest has not been built yet. The composition is worker work
  (AD-11), and the user may arrive before it has run. Showing them "nothing on the
  pulse today" would be **a lie**: something might be on the pulse, and the system just
  has not looked yet.

**Why the empty state still carries the city.** FR-8's copy is "No qualifying events in
**{city}**", so the city is part of the message, and the API cannot send a message. The
city comes from the `DigestPreference`, and it is `None` for a user who has not chosen
one — in which case the client omits the sentence's city rather than inventing one.

**Why `is_empty` is on the row.** The composition service already stores it (D5 of the
composition design), and the reader must be able to tell "a deliberate empty digest"
from "a composition that never ran" **without counting children** — and without a
second query.

---

## D4 — The local date is resolved the same way the composition resolved it

**Decision.** The read resolves the user's local date the way the composition did:

```python
zone_name = preference.timezone if preference else DEFAULT_DIGEST_TIMEZONE
local_date = now.astimezone(ZoneInfo(zone_name)).date()
```

**Why this matters, and why it is not a detail.** The composition wrote the digest
*under a date*. If the read computed a different date, the read would look for a digest
that does not exist and report `not_composed` on a day that has three cards on it. The
two must agree exactly.

**The rule, stated once.** The local date is a function of `(now, the preference's
zone)` and of nothing else. Both sides call **the same function** — the read imports
the composition's `_local_date` rather than reimplementing it — so the two cannot
drift. (A private helper being imported across modules is a smell; the fix is to
**promote it to a shared, named helper** rather than to copy it. See D4b.)

**Why the preference is read at all.** The digest row stores the `timezone` it was
composed in, but the read needs the zone **now** to know which day "now" is in. If the
user moved, the zone changed, and the day may have changed with it — and the digest
for the new day has not been composed. Reading the *current* preference is right, and
the digest's own stored zone is what the response reports, so a mismatch is visible.

### D4b — The local-date helper is shared, not copied

**Decision.** `_local_date` moves out of `digest_composition.py` into a small shared
module, and both the composition and the read import it.

**Why.** Two copies of "the user's local day" is two rules that can disagree about a
boundary — and the boundary is exactly what the DST test pins. A copy is a future
bug; a shared helper is a future no-op.

**Where it goes.** `apps/personalization/services/digest_dates.py` — a leaf module
with no imports beyond the stdlib and `shared.constants`. It is not `domain/`: the
`domain/` package is "stdlib only, pure" and knows nothing about a preference, so a
function that reads a `DigestPreference` does not belong there. And it is not
`shared/`: `shared/` is the layer both apps read, and this one is the personalization
app's own rule.

**The signature.** `local_date_for(*, now: datetime, zone_name: str) -> date` — it takes
the zone as a string, not the preference, so it is a pure function of the two things it
needs and can be tested without a database.

---

## D5 — The card's display facts come from the catalog and the user's own agenda

**Decision.** The response's cards carry the name, time and location. Those are **not**
on the `DigestComposition` row, and they come from two places depending on the kind:

| Kind | The display facts come from | How |
|---|---|---|
| `public` | the catalog | one batched `get_public_events(event_ids=...)` |
| `personal` | the user's own agenda | one query over `PersonalEvent` |

**Why the explanation is not enough.** A `DigestComposition` holds `event_id`,
`score`, `bucket`, `tags`, `source_badge` and `event_version`. It does not hold a title
— and it must not, because a title is untrusted source content and the composition row
is a durable account of *why* the event was chosen, not a copy of the event.

**Why the catalog lookup is batched.** `get_public_events` is one query with an `IN`
clause. Three cards must not become three round-trips to the catalog. The catalog read
is a *lookup*, not a join: it runs against the `catalog` alias and returns plain data,
so the wall holds (AD-3).

**What happens when the catalog no longer holds the event.** A public card whose event
has been superseded or unpublished since the composition **still appears** — with the
explanation the composition persisted, and with the catalog's facts marked unavailable.
The reason is AD-10: the composition is a fact about the day, and the explanation on it
must not change because a source moved. The card shows what it showed that morning,
plus a flag saying the catalog has moved on.

**The flag is `catalog_event_missing: bool`.** It is a **fact about the catalog**, not
an error: the card is still valid, still explained, and still saved. The frontend can
mark it ("this event was updated by its source") without the card disappearing.

**And the display facts are optional, because there is nothing to show.** The
composition row does not hold a title, a time or a venue — it must not, because a title
is untrusted source content and the composition is an explanation, not a copy of the
event. So when the catalog has dropped the event there is no title, no time and no venue
to send, and the card's `title`, `start_time_utc`, `end_time_utc` and `start_time_tz`
are all `null`. The card does not invent a placeholder: a card showing "Untitled
event" at the epoch would be a lie about a day, and the flag already says the facts are
gone.

**The same holds for a personal card whose agenda row is gone.** The user may delete
the event after the composition, and the same flag marks it.

**Why the personal card's facts are not in the catalog.** A personal event is the user's
own row. There is no catalog event, and there must not be one — `DigestComposition`
holds the personal event's id *by value* (OQ-8), and the personal event's own row is
where its name, time and location live.

**Why a personal card's `venue_name` is its `location`.** The personal event's
`location` is free text ("2 Example Street") and is not a venue. The wire field is
`location`, and for a personal card it carries that free text verbatim. It is **not**
matched against a city and it is **not** turned into a venue — the codebase refuses
guesses of that kind (the same call the composition service makes for the personal
event's city band).

---

## D6 — The card carries the bucket, not the score

**Decision.** The wire shape carries `bucket: int` (1–5) and **not** `score`.

**Why.** FR-22's raw `relevance_score` is an internal number; the card shows 1–5 dots.
Sending the raw score would invite the frontend to re-bucket it — which is the
"recomputed at render" failure wearing a different hat. It would also break the
no-flicker rule: the bucket the user saw this morning is a **persisted fact about
their day**, and a frontend that re-bucketed `0.84` might land on a different bucket
than the one persisted.

**But the score is on the row and it is useful.** The Detail Screen's "why this?"
breakdown needs the contributing factors, and those come from the **persisted tags**,
not from the score. The score stays internal.

**Why this is not a loss.** The score is a `Decimal` on the row, and the row is there
for the Detail Screen's own read (`event-detail-api`), which has a different contract
and can carry more. The card's contract is the card's.

---

## D7 — The persisted tags are sent as keys, and the score is not

**Decision.** `tags: list[str]` — the persisted Why-this Tag **keys**, in the persisted
order.

**Why keys and not labels.** The same reasoning as the Source Badge: the label is the
frontend's. `domain/ranking.py` stores the keys ("nearby", "tonight",
"matches_music"), and the design system owns the copy.

**Why the persisted order and not a re-sorted one.** The order is the **priority
order** — `RANKING_TAG_ORDER` first, then the chip tags in sorted key order — and it
is what the card and the Detail Screen must agree on. Re-sorting here would be a
second ordering rule, and a second ordering rule is one more thing that can disagree
with the other surfaces.

**Why the tags are not recomputed.** This is AD-10's whole point, and it is asserted
by a test: the endpoint path never calls `domain/ranking.py`.

---

## D8 — The Source Badge travels as a variant key

**Decision.** `source_badge: str | None` — the persisted badge *type*
("official_site", "community_site", "aggregator", "crawled"), or `None` for a personal
event.

**Why `None` and not a default.** A personal event has no source, so it has no badge.
`digest_composition_kind_shape_ck` already says so — a `public` composition has a
non-null badge and a `personal` one has a null badge — and the schema cannot invent a
badge the row does not have. `None` here is not "unknown"; it is "there is no source".

**Why the key and not the label.** FR-23's five variants map to labels and tooltip copy
in the design system. The API sends the variant key; the client renders it.

**Why the badge travels with the card and not with the event.** The badge is a fact
about **how this source's facts were obtained**, and it is persisted *per composition* —
because the same event composed on two different days could have been composed from
different sources' facts. Reading it from the catalog at render would answer a
different question than the one the composition answered.

---

## D9 — The query count is bounded, and the bound is asserted

**Decision.** The read issues **at most six queries**:

| # | Query | Alias |
|---|---|---|
| 1 | the preference (for the zone and the city) | `personal` |
| 2 | the digest for `(user_id, local_date)` | `personal` |
| 3 | the compositions for that digest | `personal` |
| 4 | the open conflict pairs | `personal` |
| 5 | the user's saves of the public cards (the bridge to a pair's side) | `personal` |
| 6 | the display facts — the public events in one batch, or the personal events in one query | `catalog` or `personal` |

**Why the bound is a test and not a comment.** A card count that grows with the query
count is an N+1 waiting to land, and an N+1 that lands inside a <500ms budget is how the
budget gets missed. The test records the SQL on **both** connections and asserts the
count, so the next person to add a per-card lookup sees the test fail.

**The bound is six, and it was four until D10 changed.** The two extra queries are the
conflict read and the save lookup that bridges a public card to a conflict pair. They
are **not** per-card: one query for all the pairs, one for all the saves. And the save
lookup is only reached once a pair exists to look for — a user with no open conflicts
pays one fewer.

**The bound is on the read, and the read is counted directly.** The endpoint's request
path also carries the auth seam's two queries — the session row and the user row — and
every endpoint on the personal router pays those. They are the framework's cost, not the
read's, and a bound that counted them would be a bound on the login machinery rather
than on the digest.

**Why the personal events are one query and not one per card.** A personal card's
display facts are the user's own rows. `PersonalEvent.objects.filter(id__in=[...])` is
one query — and there is at most one personal card anyway, since Slot 1 is the only
slot that holds one.

**Why there is no query for the saves *of the flag*.** The `saved` flag is **not** in
the card as a separate field. It is in the composition's **tags** —
`why_this_tags(is_saved=True)` put `saved` there — and the tags are persisted. Reading
the saves to recompute the flag would be recomputing an explanation, which is the thing
this endpoint must not do. (The save lookup in query 5 exists for the *conflict*, not
for the flag: it is the bridge from a catalog event id to a pair's side.)

**Why the queries are not in one transaction.** A read does not need one, and a
transaction spanning the two aliases would break AD-3. The queries are independent, and
the only consistency requirement — "the compositions belong to the digest I found" — is
satisfied by the `digest_id` foreign key.

---

## D10 — The card carries every flag the criteria list, and the conflict flag is read live

**The work item's acceptance criteria** ask for "the slot, the personal/public kind,
the conflict flag, `tz_review_pending`, and whether the event is already saved."

**Decision, per field:**

| Field | Carried? | Why |
|---|---|---|
| the slot | **yes** — `slot` | It is the persisted row's own column, and the frontend renders the three cards differently by slot. |
| the personal/public kind | **yes** — `event_kind` | It is the persisted row's own column, and FR-19 requires the "Personal" text label. |
| `tz_review_pending` | **yes** | The frontend marks an approximated time. It comes from the catalog, **at read time** — it is a live fact about the event, not an explanation. |
| whether the event is already saved | **yes, as a tag** | The `saved` Why-this tag is already persisted in `tags`. The endpoint does not query the saves to recompute it. |
| the conflict flag | **yes** — `conflict` | See below. |

**Why the conflict flag is on the card.** FR-58's indicator "renders on a card whose
event is in a `CONFLICT_PAIR`" — the brief says it explicitly, and the work item asks
for the flag. A card that could not show the indicator would be a card missing one of
the six trust signals, and "adaptive density never hides a trust signal" is the locked
rule.

**Why it is read live and not persisted on the composition.** A conflict is a **live
condition of the user's own calendar**: two things clash *now*. A conflict that arises
at 3pm on a digest composed at 7am did not exist when the digest was composed, and a
conflict resolved at noon is gone — so a flag persisted at 7am would be stale in one
direction or the other. The flag is therefore read from the **persisted `ConflictPair`
rows** at request time, and **never computed** (AD-21: conflict detection happens
"never at render"). An overlap computed here would produce a *different* answer from
the persisted pair whenever the two disagreed, and they disagree the moment an event
moves without the propagation running.

**Why the flag is not on the composition row.** The composition is a durable account of
*why* the event was chosen. A conflict is not part of that answer, and putting it there
would mean a row that is wrong within hours.

**The bridge, and why it costs a query.** A conflict pair's two sides are the
`personal` rows — a `PersonalEvent`'s id and a `SavedEvent`'s id — while a public card
names the **catalog** event's id. So a public card's conflict is found through the
user's save of it: one query for the saves of the public cards' event ids, and the
pair's `saved_event` side is matched against them. A personal card's `event_id` **is**
the `PersonalEvent`'s id, so it matches a pair's `personal_event` side directly.

**Only `ACTIVE` pairs count.** A `RESOLVED` pair is answered and a
`CLEARED_BY_STATE_CHANGE` one is over; neither is an open conflict, and showing either
would put a conflict prompt on a card for a conflict the user has already settled.

---

## D11 — The response carries the city's *source*, because the fallback city is not the user's city

**Decision.** The response carries `city: str | None` and `city_source: str | None` —
the same pair the onboarding endpoint already returns.

**Why.** The city is the user's home city, and `city_source` says how it was
resolved: `choice` (the user picked it), `fallback` (the server chose `PREVIEW_FALLBACK_CITY`
because the catalog does not cover the user's city), or `None` (the user has no city).

FR-8's copy is "No qualifying events in **{city}**" — and if the city is the server's
fallback rather than the user's, the copy is misleading. The `city_source` is what lets
the frontend say "we don't have your city yet" instead of implying New York is the
user's city.

**Why the same pair and not a new shape.** `DigestPreferenceOut` already carries
`city` and `city_source`, and `city_source` was built for exactly this reason. A second
shape for the same two facts would be two shapes that could disagree.

---

## D12 — The wire shapes are Pydantic schemas in `schemas.py`

**Decision.** Two new schemas in `apps/personalization/schemas.py`, plus one `Literal`:

```python
#: The three states a digest read can report, as a closed set.
DigestStatus = Literal["composed", "empty", "not_composed"]


class DigestCardOut(Schema):
    """One Pulse Card on the digest."""

    event_id: UUID
    slot: str
    event_kind: str
    title: str | None = None
    canonical_url: str | None = None
    start_time_utc: datetime | None = None
    end_time_utc: datetime | None = None
    start_time_tz: str | None = None
    venue_name: str | None = None
    venue_city: str | None = None
    location: str | None = None
    tags: list[str] = []
    bucket: int
    source_badge: str | None = None
    tz_review_pending: bool = False
    catalog_event_missing: bool = False
    conflict: bool = False


class DigestOut(Schema):
    """The user's Pulse Digest for their local day."""

    status: DigestStatus
    local_date: date
    timezone: str
    city: str | None = None
    city_source: str | None = None
    cards: list[DigestCardOut] = []
```

**Why `title` is optional but `bucket` is not.** The bucket is the explanation, and the
explanation is always there — AD-10 says it is persisted and never recomputed, so it
cannot be missing. The title is a *display fact* that lives in the catalog or in the
user's own agenda, and either place may have moved on since the composition (D5). The
one required display fact is the one the composition itself holds.

**Why `location` sits beside `venue_name`.** A public event's place is a venue; a
personal event's is a free-text location. One wire field per kind, both present, one of
them `None` — rather than one overloaded field that means different things for
different cards.

**Why `timezone` is on the response.** The digest row stores the zone it was composed
in, and the client needs it to render the local date it was given. Without it, a client
showing "Wednesday" has no way to know which Wednesday.

**Why the datetimes are `datetime` and not a pre-formatted string.** AD-6:
"display-time conversion happens at the presentation edge, never in domain logic". The
API sends the instant and the IANA zone; the client converts.

**Why `status` is a `Literal`.** The three states are a **closed set the read
produces**, and a `Literal` is exactly what a closed set is for. The codebase's own
convention for such sets (`ConflictAction`, `ConflictResolutionValue`) is `Literal`, so
this is the place the convention wins — and the frontend's generated type then carries
the three states, which is worth more than the convenience of a plain string.

**Why `cards` and not `items`.** `items` is the convention for a *list of things*, and
these are not a list of things — they are the three slots of a digest, and `cards` says
what they are. The empty state is `cards: []`.

## D13 — The endpoint never touches the models, and never imports the ranking

**Decision.** `api.py` imports `read_digest` from the new service and the schemas from
`schemas.py`. It imports neither `apps.personalization.models` nor
`apps.ingestion.models`, and it does not import `domain.ranking`.

**Why this is a test and not a convention.** "Nothing is computed" is the item's
central acceptance criterion, and a convention is not an assertion. Two tests:

1. **The endpoint path never calls `domain/ranking.py`.** A monkeypatch on
   `domain.ranking.score_slot_1`, `score_slot_2`, `score_slot_3` and
   `why_this_tags` that raises if called, and the endpoint is exercised against a
   composed digest.
2. **The endpoint path never writes a row.** Every table in both schemas is counted
   before and after, and the counts must be identical.

**Why the second test is worth its cost.** A read that writes is a read that is not a
read, and it would show up as an audit row the user did not ask for. Counting the rows
is the only way to be sure.

---

## D14 — The response is scoped to the session user, and no user id is an input

**Decision.** The endpoint takes no body, no path parameter and no query parameter. The
user comes from `request.user.pk` and nowhere else.

**Why.** The scoping comes from the session, so it cannot be talked out of by a
payload. This is the same rule every endpoint on the router already follows, and there
is a test for it.

**Why an anonymous request gets a 401 and not a preview.** The preview is the public
catalog's anonymous surface (`apps/catalog/preview_api.py`), and it shows *catalog*
events, not the user's digest. A digest is the user's own — their city, their interests,
their personal events — so an anonymous request for it has no answer that is not a leak.
`current_user` raises a 401 before the endpoint runs.

---

## D15 — The endpoint is in the OpenAPI schema, and the TypeScript client is regenerated

**Decision.** The endpoint appears in `/api/openapi.json`, and
`frontend/lib/api/openapi.json` and `frontend/lib/api/schema.ts` are regenerated.

**Why.** AD-19: "the new endpoints reach the frontend through the generated contract,
never hand-written." The regeneration is part of the item, not a follow-up — a
contract that is not regenerated is a contract the frontend cannot use.

**Why the OpenAPI test matters.** The endpoint being *absent* from the schema is a
failure mode that no runtime test catches: the endpoint works, the frontend just cannot
call it. A test that asserts the path is in the schema catches it.

---

## The decision table

| # | Decision | The alternative | Why this one |
|---|---|---|---|
| D1 | `GET /api/personal/digest` on the existing personal router | A new router; a date parameter | One `auth=` on the personal router; a date parameter is a history endpoint |
| D2 | A new read service, `digest_read.py` | ORM in the endpoint; a read in the command module | The endpoint may not import the models; the command module is the writer (AD-16) |
| D3 | Three named states, all 200 | A 404 for "not composed" | A status code the client has to interpret is the thing this item removes |
| D4 | The local date is resolved the same way the composition resolved it | Compute it again in the read | Two copies of a boundary rule is two rules that can disagree |
| D4b | The local-date helper is shared, not copied | Copy `_local_date` | A copy is a future bug; the DST test pins the boundary |
| D5 | The display facts come from the catalog (batched) and the user's own agenda, and are optional | Put the title on the composition row | A title is untrusted content; a composition is an explanation, not a copy |
| D6 | The card carries the bucket, not the score | Send the raw score | A frontend that re-buckets breaks the no-flicker rule |
| D7 | The persisted tag keys, in the persisted order | Recompute the tags; re-sort them | AD-10; a second ordering rule is one more thing that can disagree |
| D8 | The Source Badge travels as a variant key, `None` for a personal event | A default badge; a label | The label is the frontend's; a personal event has no source |
| D9 | At most six queries, asserted by a test | Whatever the implementation does | An N+1 inside a <500ms budget is how the budget is missed |
| D10 | Every flag the criteria list is carried; the conflict flag is read live from the persisted pairs | Persist the conflict flag on the composition | FR-58's indicator renders on the card; a conflict is live, so it is read, not stored |
| D11 | The city carries its `city_source` | Just the city | The fallback city is not the user's city, and the copy must not imply it is |
| D12 | Two Pydantic schemas and one `Literal` in `schemas.py` | Ad-hoc dicts | AD-19; a closed set is what a `Literal` is for |
| D13 | The endpoint never imports the models and never calls the ranking | Rely on convention | "Nothing is computed" is the item's central criterion, and a convention is not an assertion |
| D14 | No user id is an input | A `user_id` parameter | The scoping comes from the session and cannot be talked out of by a payload |
| D15 | The endpoint is in the OpenAPI schema and the client is regenerated | Hand-write the client | AD-19 |

---

## What the code review changed

**Two decisions were reversed, and both reversals were the design being wrong.**

**1. D10 — the conflict flag is on the card, read live.** The design said no: a conflict
is a *live* condition of the user's own calendar while the composition is a *fact about
a day*, so the flag belonged on the Timeline and not on the card. The reasoning about
staleness was right and it survives the change — the flag is read from the **persisted
`ConflictPair` rows** at request time and never computed (AD-21), exactly as
`tz_review_pending` is read live from the catalog.

What the review found is that the design's alternative **does not exist**: there is no
conflict read endpoint. `list_conflict_pairs` is a service, and nothing publishes it, so
a card that left the flag off would have had no indicator at all — and FR-58's indicator
renders on a card, and "adaptive density never hides a trust signal" is the locked rule.
The work item's acceptance criteria ask for the flag too.

It costs **two** queries, so D9's bound moved from four to six: the open pairs, and the
user's saves of the public cards (the bridge from a catalog event id to a pair's
`saved_event` side). The `saved` *flag* is still not a separate field — it travels as the
persisted `saved` tag, and the save lookup exists for the conflict, not for the flag.

**2. D5 — the card's display facts are optional.** The design had `title` and
`start_time_utc` required, and the first implementation papered over the gap with a
sentinel — an epoch instant and an empty title for a card whose catalog event had been
dropped. **A card showing an empty title at 1970-01-01 is a lie about a day**, and the
sentinel would have been invisible in the schema: every consumer would have had to know
that the epoch means "gone".

The display facts are now `None` when they are gone, with `catalog_event_missing=True`
saying why. The card still appears, still carries its bucket, its tags and its badge, and
the client marks it rather than hiding it. The **required** fields are now exactly the
ones the composition itself holds — AD-10 guarantees the *explanation* is persisted, so
it can never be missing; the *display facts* live elsewhere and may have moved on. The
same rule was applied to a personal card whose agenda row the user deleted after the
composition.

**3. D9 — the bound is on the read, and the read is counted directly.** The first test
counted the endpoint's queries and measured six: two of them were the auth seam's
(session row, user row), which every endpoint on the personal router pays. The bound
moved onto the service, where it means something, and the endpoint path got its own
test — the count must not grow with the number of cards.

**4. D12 — two schemas and one `Literal`, not four schemas.** The design said "four new
schemas" and showed two. The two missing ones were never needed: the `DigestStatus`
`Literal` is a type alias rather than a schema, and the service's own `DigestCard` and
`DigestRead` are plain frozen dataclasses in the service layer, where the codebase
already keeps them.

---

## What this item does not build

- **The digest's email delivery.** Not in this intent's item list.
- **The Detail Screen's read.** `event-detail-api` reads the most recent composition for
  a `(user, event)` pair — a different query, a different contract, and it *does* need
  the score, which the card does not carry.
- **The Timeline's conflict state.** Already built; the digest card deliberately does
  not duplicate it (D10).
- **The frontend.** `frontend-pulse-card` and `frontend-digest-home` consume this
  endpoint.
- **A digest history.** A date-parameterised endpoint is a different surface.
- **Composing on demand.** If no digest exists for today, the endpoint says so. It does
  not compose one — AD-11 says composition is worker work, and a read that composes
  would be a write from a request path.
