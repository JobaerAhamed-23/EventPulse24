# Design: The Detail Screen API and the neighbor count

**Work item**: `event-detail-api`
**Intent**: `pulse-digest-and-trust`
**Mode**: confirm
**Date**: 2026-10-30

---

## The problem

FR-24's Detail Screen needs three things, and they come from three different places:

| What | Where it lives | Why |
|---|---|---|
| the event's public facts | `catalog` | AD-3: the wall |
| the **why-this breakdown** | `personal` | AD-10: the persisted composition |
| the **neighbor count** | `personal` | k-anonymity over other people's behaviour |

And it has to serve **two callers with different rights** (the IA: "Authed + Anon
(read-only)"):

- a signed-in user may see *their own* explanation and their own saved state;
- an anonymous visitor may see the event and **nothing personal at all** (AD-12).

So this endpoint is the first place in the codebase where **one route answers two
audiences**, and the whole design is about making sure the anonymous answer cannot
leak the personal one.

---

## The decisions

### D1 — The endpoint lives in `apps/personalization`, mounted at `/api/events`

**The router is `auth=None`, and the handler resolves the user itself.**

The alternative — extending the existing `GET /api/catalog/events/{event_id}` — is
wrong for a reason that is not obvious. `apps/catalog` is the **session-free** surface
(AD-12): "the public catalog is session-free", its responses stay cacheable, and the
architecture has a whole test file (`test_preview_anonymity.py`) pinning that no session
is read and no cookie is set. This endpoint *does* read a session when there is one.

So there are two routers and two routes:

| Route | Router | Session | Answers |
|---|---|---|---|
| `GET /api/catalog/events/{id}` | `apps.catalog.api` | never | the public facts |
| `GET /api/events/{id}` | `apps.personalization.detail_api` | read, not required | the facts **plus** the signed-in user's own state |

They are not the same resource served twice. The first is a public catalog listing; the
second is *the Detail Screen*, and the Detail Screen is a personal surface that happens
to degrade.

**Why `auth=None` and not `auth=current_user`.** `current_user` raises a 401 for an
anonymous request — correct for `/api/personal/*`, wrong here, because an anonymous
visitor is a normal caller of this route, not a mistake. So the new router is declared
with no `auth=`, and the handler calls `unauthenticated_user(request)`, which is the
project's existing primitive for exactly this ("the signed-in user, or `None` when the
request is anonymous"). It is already used by `GET /api/auth/me`.

**Why the CSRF check still happens on the write.** The router has no `auth=`, so
`current_user` — and therefore `require_csrf` — never runs. But the detail-open signal
is a **write**, and AD-5 says every mutation is a named command behind an audit entry.
A `GET` that writes is exactly the shape CSRF exists to stop: a third-party page can
make a user's browser issue a `GET` that records "this user opened this event". So the
handler calls `require_csrf(request)` itself on the write path.

Wait — a `GET` is a safe method, and `require_csrf` **returns early on a safe method**.
So a CSRF check on a `GET` would be a no-op, and the signal would be forgeable.

**This is the real reason the detail-open signal is a `POST`, not a side effect of the
`GET`.** A `GET` that writes is not just a style question: `require_csrf` will not
protect it, because Django's own rule is that only unsafe methods need the token. A
signal recorded from an unprotected `GET` is a signal anyone can forge.

**So: two endpoints.**

| Route | Method | What it does |
|---|---|---|
| `GET /api/events/{id}` | GET | the Detail Screen's read. Writes nothing. |
| `POST /api/events/{id}/opened` | POST | records the detail-open signal. CSRF-checked. |

The `GET` is a pure read — **it writes nothing at all**, not even the signal. The
frontend calls the `POST` when the screen is actually shown. That is the only shape in
which the signal is protected, and it also keeps the `GET` cacheable and free of side
effects, which is what a read should be.

**The cost.** Two round trips instead of one. The trade is stated rather than hidden:
the alternative is a `GET` that writes, which is unprotected by CSRF and would make the
neighbor count forgeable by anyone who can make a browser issue a `GET`.

### D2 — The public facts come from `catalog_read`, and `PublicEvent` is not widened

A-15/FR-53 say sold-out state flows through "if the event carries it", and
`Event.is_sold_out` exists. But `PublicEvent` does not carry it.

**The problem with adding it to `PublicEvent`.** `EventOut.from_public_event` does
`cls(**vars(event))` — so adding a field to `PublicEvent` **silently changes the public
catalog's wire shape**, and the public catalog's contract is not this item's to change.
FR-24 says the Detail Screen shows sold-out; it does not say the *public catalog
listing* starts showing sold-out.

**So the Detail Screen's facts come from a new published read, not from `PublicEvent`.**
`catalog_read` grows one function:

```python
def get_public_event_detail(*, event_id: UUID, now: datetime | None = None) -> PublicEventDetail
```

`PublicEventDetail` is `PublicEvent`'s fields **plus** `is_sold_out` and `description`.
(The description is on `Event` and is public — the catalog's own `EventOut` does not
carry it, but FR-24 says the Detail Screen shows "full event description".)

**The description is stripped source text.** AD-9 says "no raw source payload is
exposed" and the catalog's `EventOut` docstring says "the Event's stripped
`description` ... never appear here". But `Event.description` is *already* the stripped
field — the ingestion pipeline strips it before storing. Let me verify that: the field
is `description = models.TextField(blank=True)` and the catalog's `EventOut` docstring
says "the Event's **stripped** `description` and the `ExtractedRecord.payload` never
appear here" — so `Event.description` is the stripped one, and it is *not* raw payload.

It is still untrusted source text (AD-13: no untrusted content in logs; AD-9: matching
text belongs to the layer that owns the content). But it is *display* content, and the
Detail Screen has to show it. The rule is: the description may be **served**, and it may
never reach a **log line**, an **audit row**, or a **sort key**. That is the same rule the
catalog's own `EventOut` follows for the title.

### D3 — The why-this breakdown reads the persisted composition, and there is no fallback

AD-10's rule is exact:

> the Detail Screen "is reachable for an Event that is not in today's digest; it reads
> the **most recent composition** for that `(user, event)` pair, and **renders no
> explanation rather than recomputing one if none exists**. An explanation is never
> generated at view time."

So the breakdown is:

- the **most recent** `DigestComposition` for `(user_id, event_id)`, by `composed_at`
  descending — whatever day it was composed;
- its persisted `tags`, `bucket` and `source_badge`;
- and when there is **no** composition, an **explicit absence**, not an empty breakdown,
  not a zero bucket, and not a recomputed one.

**The absence is a shape, not a null.** `why_this: null` and `why_this: {tags: [], bucket:
0}` are different, and the second one is a lie: it says "we looked and the answer was
nothing", where the truth is "we have nothing for you on this event". The wire shape
carries `why_this: WhyThisOut | None`, and `None` is the absence.

**The index already exists.** `DigestComposition` has
`digest_comp_user_event_idx` on `(user_id, event_id, -composed_at)` — the model docstring
says so ("the Detail Screen looks up 'the most recent composition for this `(user,
event)` pair' in a single indexed lookup"), and the descending `composed_at` means the
newest row is the first the index yields. **No migration is needed**, which is worth
saying because the design doc for the models promised this lookup and the index is
already there waiting for it.

**The single most important test in the intent** is that the read never calls
`domain/ranking.py`. It is asserted by monkeypatching the ranking to raise, exactly as
the digest read's test does.

### D4 — The neighbor count is suppressed **before** the number is formed

FR-24 says:

> the count is **bucketed** and rendered as `👥 5–9`, `👥 10–24`, `👥 25–99`, or
> `👥 100+`. Buckets `<5` are suppressed (k-anonymity). **Exact counts are never
> exposed.**

**The cheap version of this check is a trap**, and the work item says so: "computing the
bucket and then suppressing it in the serializer means the exact count existed in the
response-building code and could be logged, cached or leaked by a later change."

So the shape is: **the count is never a number that reaches the response-building code
at all**. The read asks a question whose answer is *a bucket key or nothing*, and the
bucket key is computed inside the service from a count that never leaves it.

Concretely, the service returns:

```python
neighbor_bucket: str | None   # "few" | "some" | "many" | "a_lot" | None
```

There is **no** `neighbor_count` field, anywhere. Not on the dataclass, not on the
schema. A later change cannot leak it because there is nothing to leak.

**The thresholds.**

| Count | Bucket key | The frontend renders |
|---|---|---|
| 0–4 | `None` — suppressed | *(nothing)* |
| 5–9 | `few` | "A few neighbors saved this" |
| 10–24 | `some` | "Some neighbors saved this" |
| 25–99 | `many` | "Many neighbors saved this" |
| 100+ | `a_lot` | "A lot of neighbors saved this" |

**The bucket keys are slugs, not prose.** AD-6/the tag convention: the server states
facts, the client speaks the user's language. A key the frontend renders as "A few"
can be re-worded without a backend deploy.

**The suppression is silent.** Below the threshold there is **no row, no "0 neighbors"
copy**, and no field that says "suppressed". `neighbor_bucket: null` means "there is
nothing to show" — which is what "no signal" means. A separate `neighbor_suppressed:
true` would tell the client *why* it is showing nothing, which is itself a signal about
how many people are near this event.

**The threshold is ≥5, and the PRD's glossary says 1.** The PRD's FR-24 body says "≥5
qualifying users" and the work item says ≥5; the Glossary's "Revealed only when at least
1 qualifying user exists" contradicts it. **The stricter rule governs** — and the reason
is the same one that governs the mockup: the glossary's version would expose a count of
exactly one, which is the identity of one person. k-anonymity at k=1 is not anonymity.

**The count is tier-agnostic.** FR-24's "Privacy floor": "the count aggregates Pro and
Free tier users identically; the badge never differentiates by tier". There is no
subscription entity in this codebase yet, so this is trivially true — and the test pins
it by asserting the count query has no tier filter, which is a statement about the shape
of the query rather than about a filter that does not exist yet.

### D5 — The qualifying signal is a new model, with a retention category and an audit row

FR-24 defines a qualifying user as one who has "either saved OR opened the Detail Screen
for this event **in the last 30 days**".

**The save half already exists.** `SavedEvent` is the user's save of a catalog event, with
`saved_at`. A save within 30 days is a qualifying signal, and the row is already there
with `retention_category = ACCOUNT_CONTENT`.

**The open half does not exist.** There is no model anywhere that records "this user
looked at this event". So this item builds it.

**The shape: a row per `(user, event)`, with the last-opened timestamp.**

```python
class EventDetailOpen(UUIDv7Model):
    user_id = models.UUIDField()
    event_id = models.UUIDField()
    opened_at = models.DateTimeField(default=timezone.now)
```

with a unique constraint on `(user_id, event_id)`.

**Why a row per pair and not an append-only log.** The count asks one question — "has
this user opened this event within 30 days?" — and the answer is a boolean per pair. An
append-only log of every open would answer the same question with a query that counts
rows, and it would store the user's *entire viewing history* of the catalog, which is a
much larger privacy cost than the feature needs. The work item says exactly this: "the
design should consider whether a per-`(user, event)` row with a timestamp is the right
shape or whether something coarser satisfies the count."

A per-pair row with a **last-opened** timestamp satisfies the count and stores the
minimum: one row per pair the user has looked at, holding the most recent time.

**But "last-opened" loses the 30-day window's honesty.** If a user opened an event 60
days ago and again today, the row says "today" and they qualify — correct. If they
opened it 60 days ago and never again, the row says "60 days ago" and they do not
qualify — correct. The window is applied to `opened_at`, and because the row holds the
*most recent* open, the window is exact. There is no case where a stale open survives
the window, because the most recent open is the only one that matters.

**What is NOT stored.** No IP, no user agent, no referrer, no duration, no count of
views. The row answers exactly one question and nothing more. This is the "it stores no
more than it needs" the work item asks for, and it is also what keeps it out of AD-13's
log rules.

**The retention category is `PREFERENCE_SIGNALS`, not `ACCOUNT_CONTENT`.**

This is the privacy decision the work item flags. The choices:

| Category | Window | Argument |
|---|---|---|
| `ACCOUNT_CONTENT` | while the account is active | wrong — a viewing record is not the user's own content |
| `PREFERENCE_SIGNALS` | 12-month rolling | **right** — this is a behavioural signal about the user's interests, and it is exactly what "dwell, swipes, dismissals" means |
| `AUDIT_LOG` | 24 months | wrong — it is not an audit record of a change |

`PREFERENCE_SIGNALS` is the honest category: the row is a signal that this user opened
this kind of event, and the 12-month rolling window is longer than the 30-day
qualifying window, so the window is not what keeps the row around — the category's
retention policy is.

**That gap is worth stating.** The 30-day window is a *query* filter; the 12-month
policy is the *deletion* policy. A row survives for up to 12 months and only counts
for 30 days of it. That is a real privacy cost and it is the cost of the feature as
specified. The alternative — a 30-day category — would mean inventing a category for
one table, and the sweep would have to be exact to the day. **The category is
`PREFERENCE_SIGNALS` and the gap is recorded, not hidden.**

**The write is a named command with an audit row (AD-5).**

```python
def record_detail_open(*, user_id: UUID, event_id: UUID, actor: Actor, now: datetime) -> None
```

It writes the row and the audit entry in one `transaction.atomic(using=PERSONAL)` —
`write_audit` raises outside one, which is the guard that keeps an audit row from
being committed apart from its mutation.

**The audit row carries the event id and nothing else.** AD-13 forbids PII and
untrusted content in logs, and the audit table is a log. The event id is an id, not
content. There is no title, no URL, no city.

**The command does not block the read.** The work item says the write "does not block
the read" — so the `POST` is a separate request that the frontend fires and does not
await before rendering. The `GET` never waits on it.

**Idempotent.** Opening the same event twice updates `opened_at` and does not create a
second row. The count cannot be inflated by a user (or a script) opening a page twice.

### D6 — "Same area" is city equality, and the deviation is named

FR-24 defines "same area" as "haversine distance ≤ 2 km OR same city-zip-cluster".

**Neither is computable.** `Venue` has `name`, `city`, `country_code`, `venue_fingerprint`
and `tz` — **no coordinates and no zip**. This is confirmed three times in the codebase:
the model, `domain/ranking.py` ("`Venue` has no coordinates, so haversine is not
computable"), and `domain/event_fit.py` ("Venue has no coordinates").

FR-24 also says "events outside the user's home country do not count". The country is
knowable — `Venue.country_code` — but the **user's** home country is not: `DigestPreference`
holds a city and a zone and no country.

**What "same area" filters, and what it does not.** FR-24's sentence is about *which
events* count toward the signal, not about comparing each user against the reader: a
user qualifies for **this event** by saving **this event** or opening **this event**.
The event's own city is the area, and a user who saved it is by definition someone who
was interested in an event in that area.

So the "same area" rule collapses into a statement about the **event side**, and the
count needs no per-user city comparison at all: a qualifying user's signal *is* a signal
about this event, and this event is in one city.

**What survives, and what it is used for.** The event's city is still read, and it is
still used for one thing: **an event with no venue has no area, and therefore no
neighbors.** A venue-less event is a row with no city — and "people near you" is
meaningless for an event that is nowhere. The city comparison is exact
(case-insensitive), the way `catalog_read`'s `city` filter does it.

**The deviations are named, not approximated:**

1. **City equality, not ≤2 km.** Two venues two kilometres apart in different cities do
   not count each other. Two venues in the same city count each other however far apart
   they are. Both are wrong against FR-24, and neither can be fixed without coordinates.
2. **No country band.** The user's home country is not recorded, so the country rule
   cannot be applied. The count is not narrowed by country.

**Both are recorded in the endpoint's docstring and in this document**, per the work
item: "The deviation is named in the response's docstring and in the brief, not silently
approximated."

**A note on why this is not a silent lie.** The count is bucketed, so a city that is
slightly too wide produces a bucket that is slightly too wide — and a bucket is a coarse
signal to begin with. It is not a precise distance claim that a user could be misled
by. The precision of the underlying rule is what the buckets hide.

### D7 — Reviews and similar-events do not ship

FR-24 lists "similar events user has attended" and the PRD's Out of Scope says "Public
event ratings/reviews" (ASSUM-6, deferred to Phase 3+).

**Neither has data.** Similar-events needs attendance history, and there is no
attendance record anywhere in this codebase — no `Attendance` model, no
`attendances` table, no past-visited tracking. Reviews need a review entity, and
reviews are explicitly deferred.

**So both are absent from the payload** — not present-and-empty. A `similar_events: []`
field would say "we looked and there are none", and for a user who *has* attended
events the app does not know about, that is a lie. An absent field says "this is not
something we can tell you".

### D8 — The three states of the breakdown are on the response, not implied

The response carries:

| Field | Type | Meaning |
|---|---|---|
| `why_this` | `WhyThisOut \| None` | `None` means **no composition exists** |
| `saved` | `bool` | the signed-in user has saved this event |
| `neighbor_bucket` | `str \| None` | `None` means **suppressed** or **not applicable** |

**`why_this: null` and `saved: false` are different facts and both are needed.** "There
is no explanation" and "you have not saved this" are independent, and a client that
cannot tell them apart will render the wrong thing.

**`neighbor_bucket: null` is ambiguous on purpose.** It means either "below the
threshold" or "this is not a signed-in request" — and the second case is handled by the
anonymous response, which has no `neighbor_bucket` field at all. So on the signed-in
response, `null` means "suppressed", and the whole `personal` block is absent from the
anonymous response.

**The personal block is `null` for an anonymous caller, not empty.** The anonymous
response carries `personal: null`. An empty object would say "there is nothing personal
to show you", which is a different claim from "you are not signed in, so we looked up
nothing".

### D9 — The query count is bounded, and the bound is asserted

The signed-in read costs, at most:

1. the public event detail (one catalog query);
2. the most recent composition (one indexed lookup);
3. the user's save (one lookup);
4. the qualifying count (**two** reads, unioned in Python);
5. the detail-open write is **not** in this path — it is a separate request.

So **five queries**, and the count does not grow with the number of cards or the number
of qualifying users: the qualifying count is a fixed pair of reads, not one query per
neighbour.

**The count is two reads unioned in Python, not one aggregate.** *(Revised by the code
review — the original design said one `COUNT(DISTINCT ...)` over two tables.)* The two
signals live in two tables with two shapes, and a single aggregate across them needs a
`UNION` subquery — raw SQL in an otherwise pure-ORM service. The union is also the
shape that **cannot multiply** a user who both saved and opened: the ids go into a set,
so a user qualifies once, whichever signals they have.

The cost is one extra query, and it is a constant. The bound is asserted at the service,
where it means something: the endpoint path also pays the framework's session and
identity reads, and those are the request's cost, not the read's.

### D10 — The anonymous path never touches `personal`

The strongest possible statement is not "the anonymous path does not return personal
data" but "**the anonymous path never queries `personal` at all**".

**That is the design.** The handler branches:

```python
user = unauthenticated_user(request)
if user is None:
    # the public facts, and nothing else. No personal query is issued.
```

The anonymous branch issues exactly **one** query — the catalog's. There is no
composition read, no save read, no count query. A test asserts that the personal alias
was never queried on an anonymous request, which is the same technique the public
catalog read's test uses.

**And the Event Fit is not reached from either path.** AD-10 forbids substituting the
Event Fit for a missing Relevance Pulse, and this is the surface where that substitution
would be most tempting: an anonymous visitor sees an event with **no** personal
explanation, and the Event Fit is the one explanation an anonymous visitor is allowed
to see. Reaching for it here would be exactly the substitution AD-10 calls
"company-ending".

A test asserts the Event Fit read is not reached. The existing
`test_event_fit_separation.py` already asserts that `personalization` does not import
the Event Fit package at all — so this is a second, path-level guard on the same rule.

### D11 — The detail-open `POST` is session-required, and it is not a public surface

`POST /api/events/{id}/opened` records a signal **about a user**. So it requires a
session: an anonymous `POST` is refused with a 401, exactly as every other personal
mutation in this codebase is.

**The router has no `auth=`, so the handler enforces it.** `current_user` raises the 401
*and* runs the CSRF check — which is exactly what this endpoint needs, because it is an
unsafe method. So the `POST` handler calls `current_user(request)` directly.

**The `GET` handler does not**, because it must serve anonymous callers.

So one router, two handlers, two different auth rules — and the difference is *per
handler*, not per router, because the router's rule would be all-or-nothing.

### D12 — The saved flag travels as a boolean, and it is the user's own

`SavedEvent` holds the user's save of a catalog event. The Detail Screen needs to know
whether *this* user saved *this* event — the frontend needs it to render the save
button's state, and the mockup's "save" action is on the screen.

The check is a single indexed lookup on `saved_event_user_event_uq`. It reads the
user's own row, so it is scoped by the session and cannot be talked out of.

**The saved flag is a boolean, not a tag.** The digest card carries the saved state as
the persisted `saved` Why-this tag, because the card's explanation is the persisted
composition. The Detail Screen is different: it reads the *current* state, and the
current state is the save row, not the composition. A composition made three days ago
may or may not have the `saved` tag, and the save may have happened since.

### D13 — The response's `status` is not a status field; it is `why_this`'s absence

There is no `status` on this response. The three things that could be a status here:

| Candidate | Why not |
|---|---|
| `found` / `not_found` | the 404 already says that |
| `has_explanation` / `no_explanation` | that is `why_this is None` |
| `empty` | there is always at least the event's facts |

The 404 is a 404: `get_public_event_detail` raises `EventNotFoundError` when the event
is not published, is superseded, or has already started. That is the same set the
public catalog's list shows, and the Detail Screen must not show an event the catalog
does not list — a link to a detail page for a hidden event would leak its existence.

---

## The decision table

| # | Decision |
|---|---|
| D1 | The endpoint is `GET /api/events/{id}` in `apps/personalization/detail_api.py`, with `auth=None`; the open-signal write is a separate `POST /api/events/{id}/opened` |
| D2 | The public facts come from a new `catalog_read.get_public_event_detail`, which carries `is_sold_out` and `description` — `PublicEvent` is **not** widened, so the public catalog's wire shape is unchanged |
| D3 | The breakdown is the most recent persisted `DigestComposition` for `(user, event)`; no composition is `why_this: null`; the ranking is never called |
| D4 | The neighbor count is suppressed **before** the number is formed; the wire shape has a bucket key and no count field at all |
| D5 | The detail-open signal is a new `EventDetailOpen` model, one row per `(user, event)`, `PREFERENCE_SIGNALS`, written by a named command with an audit row |
| D6 | "Same area" is city equality; the deviation from FR-24's haversine and country rules is named, not approximated |
| D7 | Reviews and similar-events are absent from the payload — not present and empty |
| D8 | `why_this`, `saved` and `neighbor_bucket` are three independent facts, each carried explicitly |
| D9 | The signed-in read is five queries; the count is two reads unioned in Python, so a user who both saved and opened counts once |
| D10 | The anonymous path issues one query and never touches `personal`; the Event Fit is not reached from either path |
| D11 | The `POST` is session-required and CSRF-checked; the `GET` serves anonymous callers |
| D12 | The saved flag is a boolean read from the user's own save row, not a tag on the composition |
| D13 | There is no `status` field; the 404 is a 404 and the absence of an explanation is `why_this: null` |

---

## What the code review changed

Three substantive changes. The full report is in
`.specs-fire/runs/run-eventpulse24-021/review-report-event-detail-api.md`.

### 1. D2's heading was corrected, and its body was vindicated

**The design's heading said `PublicEvent` grows `is_sold_out`; its body said the
opposite, and the body was right.** `EventOut.from_public_event` does
`cls(**vars(event))` — so adding a field to `PublicEvent` **silently changes the public
catalog's wire shape**, and the catalog's contract is not this item's to change.

`catalog_read` grew a **new** published read — `PublicEventDetail` and
`get_public_event_detail` — carrying `PublicEvent`'s fields plus `is_sold_out` and
`description`. `PublicEvent` is untouched. The heading now reads "and `PublicEvent` is
not widened", because a decision whose title contradicts its body is one a later reader
will get wrong.

### 2. The detail-open signal became a separate `POST` (D5, D11)

**This is the change that most protects the feature's own meaning.** The neighbor count
says "other people near you are interested in this"; a signal anyone can forge inflates
that number, and the count is a *trust* signal.

**A `GET` that writes is exactly the shape CSRF exists to stop.** A third-party page can
make a browser issue a `GET`, and only **unsafe** methods carry the CSRF token — so
`require_csrf` returns early on a `GET` and checks nothing. A signal recorded from an
unprotected `GET` is forgeable.

So the read writes **nothing at all** (a test pins it), and the signal is
`POST /api/events/{id}/opened` — session required, CSRF checked, 401 for an anonymous
caller. The cost is a second round trip, and the trade is stated rather than hidden.

### 3. The count is two unioned reads, not one aggregate (D9)

The design said one `COUNT(DISTINCT ...)` over two tables. The implementation issues two
`values_list` reads and unions the user ids in Python — a single aggregate across two
tables needs a `UNION` subquery, which is raw SQL in an otherwise pure-ORM service.

**The union is also the shape that cannot multiply** a user who both saved and opened:
the ids go into a set, so a user qualifies once. The cost is one extra query, and it is
a constant — the signed-in read is five queries, not four.

---

## What the review checked and left alone

**The 30-day query window and the 12-month deletion policy disagree.** The count looks
back 30 days; `EventDetailOpen` carries `PREFERENCE_SIGNALS`, whose retention policy is
12 months. A row can outlive the window that made it relevant. The shape is right — one
row per `(user, event)` — and the deletion job is a separate concern, so the gap is
**recorded rather than closed**. A 30-day deletion policy on this table would match the
window exactly; that is a one-line change to a policy table, and it belongs to whoever
sets the categories.
