# Review report: `event-detail-api`

**Work item**: `event-detail-api`
**Intent**: `pulse-digest-and-trust`
**Mode**: confirm
**Date**: 2026-10-31

---

## The verdict

**Approved.** The endpoint does what the item asked, and it does it by reading persisted
rows and nothing else — which is the whole point of the item. The design's central claim
survived contact with the implementation: **the ranking is never called on this path**,
and the test that proves it is a monkeypatch that makes `domain/ranking.py` raise.

The review changed three substantive things: the **public facts** moved off `PublicEvent`
onto a new published read (D2), the **detail-open signal** became a separate `POST`
(D5, D11), and the **neighbor count** became two unioned reads rather than one aggregate
(D9).

---

## What the review checked

| Property | How | Result |
|---|---|---|
| the read computes nothing | `domain/ranking.py` is monkeypatched to raise; the endpoint is exercised against a composed digest | green |
| the read writes nothing | the `GET` is asserted to write no row — the signal is a separate request | green |
| the anonymous path never queries `personal` | the personal alias is wrapped and the query count asserted to be **zero** | green |
| the Event Fit is not reached | `list_event_fit_for_city` is monkeypatched to raise, on **both** paths | green |
| the count is suppressed before the number is formed | there is no count field on the dataclass or on the schema; the payload's key set is asserted exactly | green |
| the count is tier-agnostic | the assertion is on the SQL that runs, not on the prose | green |
| the count does not grow with the neighbour count | 40 neighbours and 150 neighbours cost the same queries | green |
| the endpoint never imports the models | the `models-ingestion` and `models-personalization` contracts | green |
| the wall holds | the catalog read is `get_public_event_detail`, a lookup on the `catalog` alias | green |
| the `POST` is session-required | an anonymous `POST` is a 401 | green |
| the signal is recorded once per `(user, event)` | the unique constraint, and the row count compared across two opens | green |
| the contract is regenerated | `make client`, and the diff is in the commit | green |

---

## The three changes the review made

### 1. The public facts moved off `PublicEvent` onto a new published read (D2)

**The design's heading said `PublicEvent` grows `is_sold_out`; its body said the
opposite, and the body was right.** `EventOut.from_public_event` does
`cls(**vars(event))` — so adding a field to `PublicEvent` **silently changes the public
catalog's wire shape**, and the public catalog's contract is not this item's to change.
FR-24 says the Detail Screen shows sold-out; it does not say the public catalog listing
starts showing it.

So `catalog_read` grew a **new** published read — `PublicEventDetail` and
`get_public_event_detail` — carrying `PublicEvent`'s fields plus `is_sold_out` and
`description`. `PublicEvent` is untouched, and the catalog listing's contract is
unchanged.

**The description is on the Detail Screen and nowhere else.** The catalog's own
`EventOut` deliberately omits it; FR-24 says the Detail Screen shows the "full event
description". `Event.description` is *already* the stripped field — the ingestion
pipeline strips it before storing — so it is not raw payload (AD-9). It is untrusted
source text that is **display content**: it may be served, and it may never reach a log
line, an audit row or a sort key. The same rule the catalog's `EventOut` already follows
for the title.

**The heading was corrected.** The design's D2 title now reads "and `PublicEvent` is not
widened", because a decision whose title contradicts its body is a decision a later
reader will get wrong.

### 2. The detail-open signal is a separate `POST`, not a side effect of the `GET` (D5, D11)

**This is the change that most protects the feature's own meaning.** The neighbor count
says "other people near you are interested in this". A signal anyone can forge inflates
that number, and the count is a *trust* signal — the feature is the opposite of the
attack it would be.

**A `GET` that writes is exactly the shape CSRF exists to stop.** A third-party page can
make a browser issue a `GET`, and Django's own rule is that only **unsafe** methods carry
the CSRF token — so `require_csrf` returns early on a `GET` and checks nothing. A signal
recorded from an unprotected `GET` is forgeable.

So the read writes **nothing at all** — a test pins it — and the signal is
`POST /api/events/{id}/opened`, which runs the shared `current_user` seam: session
required, CSRF checked, 401 for an anonymous caller.

**The cost is a second round trip, and the trade is stated rather than hidden.** The
frontend fires the `POST` when the screen is actually shown; the `GET` is the read.

**The router has no `auth=`, and that is deliberate.** This route serves two audiences,
and a router's `auth=` is all-or-nothing. The read calls `unauthenticated_user(request)`
and branches; the write calls `current_user(request)`. The two rules live in the two
handlers, because the route genuinely needs both answers.

**The signal is a new model, `EventDetailOpen`.** One row per `(user, event)`, holding
the most recent open — so the 30-day query window is exact, and a user who opened the
screen ten times is still one row. Retention is `PREFERENCE_SIGNALS`: it is a behavioural
signal, not account content and not an audit row.

**The write is a named command with an audit row, in the same transaction** (AD-5). The
row stores nothing but the pair and the time — a test asserts that.

### 3. The neighbor count is two unioned reads, not one aggregate (D9)

**The design said one `COUNT(DISTINCT ...)` over two tables.** The implementation issues
**two** `values_list` reads and unions the user ids in Python.

**The union is the more honest shape.** The two signals live in two tables with two
shapes, and a single `COUNT(DISTINCT)` across them needs a `UNION` subquery — raw SQL in
an otherwise pure-ORM service. The union also **cannot multiply** a user who both saved
and opened: the ids go into a set, so a user qualifies once, whichever signals they have.
A `JOIN` would multiply that user; a `COUNT(DISTINCT)` would not, but a `UNION` of two
reads cannot either.

**The cost is one extra query, and it is a constant.** The signed-in read is now five
queries in total — one catalog, one composition, one save, and the count's two signal
reads — against the design's four. The count does not grow with the number of cards or
the number of qualifying users, and a test asserts that at 40 neighbours and at 150.

**The bound is asserted at the service, where it means something.** The endpoint path
also carries the framework's session and identity reads, which are the request's cost
and not the read's; those are excluded, and the remainder is asserted to be at most four.

---

## The four things the review checked and found correct

**The count is suppressed before the number is formed.** This is the item's "beware the
cheap version" warning, and the implementation answers it structurally rather than by
discipline. `NeighborCount` holds a `bucket` field and **no `count` field**; the
schema has `neighbor_bucket` and no count; there is nothing for a later change to log,
cache or leak, because there is nothing to leak. The test asserts the whole `personal`
key set is exactly `{"why_this", "saved", "neighbor_bucket"}` — so a later change that
adds `neighbor_count` fails the test rather than shipping.

**The threshold is 5, and the reason is stated.** FR-24's body says "≥5 qualifying
users"; the PRD's glossary says "at least 1". The stricter rule governs, and not out of
deference to the body text: **k-anonymity at k=1 is not anonymity**. A count of exactly
one is the identity of one person, and the whole point of the signal is that it says
"other people near you are interested in this" rather than "one specific person is".

**The three states are independent facts.** "There is no explanation" and "you have not
saved this" are different claims, and a client that cannot tell them apart renders the
wrong thing. `why_this`, `saved` and `neighbor_bucket` are three separate fields, each
carried explicitly.

**"Same area" is city equality, and the deviation is named.** FR-24 defines it as
"≤2 km or same city-zip-cluster", and neither is computable — `Venue` has no coordinates
and there is no zip data anywhere in the schema. The clause filters on the **event side**:
a user qualifies for *this* event by saving *this* event, so there is no per-user city to
compare against, and the event's own city is the area. The event's city is still read,
for one reason: **an event with no venue has no area, and therefore no neighbours.**

---

## The one thing the review would still change, and did not

**The 30-day query window and the 12-month deletion policy disagree.** The count looks
back 30 days; `EventDetailOpen` carries `PREFERENCE_SIGNALS`, whose retention policy is
12 months. So a row can outlive the window that made it relevant, holding a record of
what a named person looked at, for eleven and a half months longer than anything reads
it.

**It was left alone, deliberately, and recorded instead.** The shape is right — one row
per `(user, event)`, so the row count is bounded by the number of events a user opened,
not by the number of times — and the deletion job is a separate concern from this
item's. But the gap is a real one and it is named in D5, so whoever owns the retention
work inherits it with the fact in hand rather than having to rediscover it.

**A shorter signal retention would close it** — the window is 30 days, so a 30-day
deletion policy on this table would match it exactly. That is a one-line change to a
policy table, and it belongs to whoever sets the categories, not to this item.

---

## The three test failures that were real defects

Recorded here because each was a genuine correction, and the last two are the kind of
test bug that hides a real bug.

**The endpoint returned a 500 on every `POST`.** `Status.HTTP_204_NO_CONTENT` does not
exist in Django Ninja; the codebase's convention is `Status(204, None)`. A plain mistake,
caught by the test that asserted a 204.

**The window's boundary was untestable at the endpoint.** The endpoint resolves `now`
from the wall clock, so a timestamp pinned at import time is a few milliseconds older
than the service's own `now`, and an *inclusive* boundary that should have qualified was
one hair outside the window. **The boundary is now pinned at the service**, where `now`
is a parameter and the instant is exactly expressible — plus a second test one second
inside it. This is the same lesson the `digest-read-api` item learned about its own
`NOW`: the surface decides whether "now" is a parameter or a wall clock, and the test
has to follow it.

**The tier-agnostic test asserted on prose.** It read the module's source and asserted
the word "pro" was absent — and the module's own docstring says "Pro and Free users
count identically", so it failed on its own explanation. The assertion is now on **the
SQL that actually runs**: the two signal queries are located in the captured query log
and asserted to carry no tier predicate. A prose grep was never a meaningful test of a
query's shape, and it would have passed on a query that *did* filter on a tier if the
docstring had been worded differently.

---

## A note on the neighbouring sources' contradictions

`EXPERIENCE.md` §12's own example breakdown line says "12 of your neighbors saved this",
and `event-detail-desktop.html` renders "12 neighbors tracking this in Brooklyn" — both
exposing an exact count that FR-24 and §12's "Neighbor Count Privacy" subsection
explicitly forbid. **The bucketed prose governs, and both examples are wrong.** Recorded
here because the mockup is the more persuasive artifact, and a later reader looking at
the mockup will find an exact count and think the implementation is missing it.

---

## The gate, one more time

```
3802 passed · 99.17% coverage · 19/19 import contracts · domain 100% · no migrations
ruff check clean · ruff format clean · frontend typecheck, lint and format clean
```
