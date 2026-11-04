---
work_item: revalidation-signal
intent: public-pages-and-seo
created: 2026-11-02
mode: validate
checkpoint_1: approved
---

# Design: The page goes stale the moment the event changes — the revalidation signal

## Summary

The signal already exists and has no listener. `Event.LIFECYCLE_FIELDS` names the seven
columns whose change means "the public page's facts moved", and the `catalog.guard_event_write`
trigger **requires `event_version + 1` on every change to any of them**. Every fact a public
page states is in that list.

This design connects that bump to a rebuild of the one page it affects. The path is:

```
  a lifecycle write (API runtime or worker)
        │
        ▼
  EventStateChange row  ──►  transaction.on_commit  ──►  Celery task
        (catalog, same txn)      (AD-17's seam)            (revalidate_public_pages)
                                                                   │
                                                                   ▼
                                                        HTTP POST to the frontend's
                                                        revalidation route handler
                                                                   │
                                                                   ▼
                                                        revalidatePath("/events/<slug>")
                                                        revalidatePath("/events-in-<city>")
```

**The edge is a callback, not a pull.** The backend does not ask the frontend "is your page
current?"; it says "this page's facts moved". The frontend answers by rebuilding it.

**The failure mode is stale-but-correct.** A revalidation that cannot be delivered is retried
and surfaced; it never takes a page down and never leaves the system believing a page is fresh
when it is not.

## Scope

**In Scope:**

- A **revalidation port** and its adapter — the backend's one way to reach the frontend
- A **revalidation outbox** — a durable record of "this page needs rebuilding", with its own
  idempotency marker and its own retry bound
- A **worker task** that drains the outbox and delivers the signal
- A **frontend route handler** that receives the signal and rebuilds the named paths
- The **authentication** of the edge — a shared secret, one on each side
- The **cascade rules** — which paths a given event change touches

**Out of Scope:**

- The public event page itself, the city page itself, and any page rendering
  (`frontend-public-event-page`, `frontend-city-page` — both still `pending`)
- `revalidateTag` — see D6
- A time-based ISR floor as a *primary* mechanism — see D9
- The sitemap and robots endpoints (`sitemap-and-robots`)
- The `schema-org-jsonld` work item's payload work

**A hard dependency, stated plainly:** the frontend has **no public event page, no ISR, no
route handler, and no `revalidatePath`/`revalidateTag`/`unstable_cache` anywhere**. The single
`revalidate` hit in the frontend tree is a *negative* assertion in
`app/preview/page.test.tsx:43`. `next.config.ts` is `{}`.

**So this item cannot deliver a working end-to-end revalidation on its own.** It can deliver
the *signal*: the authenticated edge, the durable outbox, the delivery task, the
authentication, the retry bound, the cascade rules, and the route handler that calls
`revalidatePath` on a path it is given. Whether that rebuild produces a correct page depends
on the page existing.

**The work item's own ACs are about the signal, and this design delivers every one of them.**
But the AC *"a change to any `LIFECYCLE_FIELD` … causes that event's public page to be rebuilt"*
is only verifiable once `frontend-public-event-page` lands. This design therefore:
- builds the signal as a **complete, testable unit** against the paths, with the route handler
  tested for the *call it makes* (`revalidatePath` receives the right paths), and
- **honours the ordering** the page item needs: the revalidation route handler, the path
  conventions, and the secret's name are all fixed here, so `frontend-public-event-page`
  consumes them rather than inventing parallel ones.

**This is a deliberate sequencing decision, and it is the one thing worth arguing about.**
The alternative — defer the whole item until the page exists — means the signal is designed
twice: once now, in ignorance of the page's paths, and once after, in the light of them.
Fixing the path conventions now means the page item has a contract to build against.

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **OQ-C — how the backend reaches the frontend** | **An authenticated HTTP callback from the backend to a Next.js route handler** | See "OQ-C" below, in full. |
| **Who fires it — API runtime or worker** | **One signal path, fired from the worker.** The API runtime never calls the frontend. | See "Who fires it" below. |
| **What happens when the frontend is unreachable** | **A durable outbox row with a bounded retry, plus a bounded staleness floor** | See "Failure" below. |
| **The transport** | **A new `RevalidationPort` + a new adapter** | The `http-client` import contract confines `httpx` to `adapters.crawl`, and `SourceFetchPort` is **GET-only** — it cannot POST, and it is semantically wrong (a source fetch retrieves *untrusted public content*; this call carries *our* secret to *our* deploy). |
| **The route handler's path** | **`/revalidate`, outside `/api/*`** | `frontend/proxy.ts:28` declares `matcher: "/api/:path*"` and rewrites every such request to Django. A handler at `/api/revalidate` would be **unreachable** — the proxy eats it. `/revalidate` is outside the matcher and therefore reaches Next. |
| **The secret** | **A new `REVALIDATION_SECRET`, on both sides; no reuse of `CALENDAR_CREDENTIAL_KEY`** | `CALENDAR_CREDENTIAL_KEY` is protected by the `credential-key` and `crypto-library` import contracts, and it is *encrypted at rest* per AD-18 — a key you cannot read at boot time cannot authenticate an outbound request. The new secret is compared in **constant time** — `secrets.compare_digest` on the Python side, `timingSafeEqual` on the TypeScript side. |
| **The outbox** | **A new `RevalidationRequest` table**, not a column on `EventStateChange` | `EventStateChange.append_only_mutable = frozenset({"propagated_at"})` — the architecture guard allows **exactly one** mutable column on that table, and `propagated_at` is already AD-17's personal-propagation marker. The revalidation signal needs its **own** marker with its **own** lifecycle, and it must not occupy the reserved `worker.tasks.propagate_state_change` slot (see D4). |
| **Idempotency** | **The signal is a *request to rebuild*, not a *command to apply*. Rebuilding twice is harmless; the second rebuild is a no-op if nothing changed.** | The AC says *"the same bump delivered twice rebuilds once more, harmlessly."* This is why the frontend's side needs no dedup table: `revalidatePath` is idempotent by construction. The backend's side dedups at the **enqueue** boundary (one open request per event), not at the delivery boundary. |
| **Post-commit** | **`transaction.on_commit(..., using=CATALOG, robust=True)`** — the same seam `_record_change` already uses | The AC: *"a rebuild fired from an uncommitted write can read the old row back and re-cache exactly the stale page it was meant to fix."* `event_writes.py:176` already does this for AD-17's propagation. **This is not a new mechanism; it is a second `on_commit` callback on the same site.** |
| **`revalidatePath` vs `revalidateTag`** | **`revalidatePath`** | `revalidateTag` needs a shared cache tag that the page's fetch call declares. The frontend has no public page, no fetch layer for one, and no tag convention. `revalidatePath` takes a path and needs nothing else — and the signal's payload is naturally a **path list**, because the cascade rules are path rules. D6 records the cost: a path rebuild invalidates the whole route, not a fragment. |
| **The cascade** | **Computed on the backend, at enqueue time, from the Event's state** | The affected paths are derivable from the Event row alone (its slug, its venue's city, and — for a move — the *old* city's slug). Computing them at enqueue time means the delivered payload is a **concrete list of paths**, and the frontend does no lookup and no inference. |
| **The city-membership problem** | **The old city's slug is captured from the `EventStateChange`'s `before` facts — which requires one model change** | See "City membership" below. This is the design's one genuine data-model consequence. |
| **The route handler's response** | **`204 No Content` on success; `4xx`/`5xx` on failure** | The backend needs to distinguish "the frontend refused (bad secret — do not retry)" from "the frontend is down (retry)". See "Failure". |

### OQ-C — how the backend reaches the frontend

**The question.** AD-19 has made the frontend/backend relationship strictly one-directional:
*"the Next.js frontend is a client — it holds no domain logic and reaches the backend only
through the generated API client."* Nothing has ever called the other way. What is this new
edge, how is it secured, and why does it not erode AD-19's boundary?

**The answer, in three parts.**

**1. The edge is a cache-invalidation callback, and it is not a domain edge.**

AD-19 protects the frontend's *domain* independence: the frontend holds no domain logic and
derives nothing the backend has not given it. The revalidation callback is the opposite
direction, and it carries **no domain facts at all** — it carries a list of *paths* and a
version number. The frontend is told "rebuild this URL"; it re-reads the backend's public
read and renders it exactly as it would have on a cold request.

**The direction of data flow is unchanged: the backend still holds every fact.** The callback
carries no event data, no status, no time, no title — only *which pages to rebuild*. A
compromised frontend learn nothing it could not get from the public page itself.

**2. The security is a shared secret, and the secret is scoped to exactly one capability.**

The request carries `Authorization: Bearer <REVALIDATION_SECRET>`. The frontend compares it
in **constant time** — `timingSafeEqual` from Node's `crypto` (a timing side channel on a
secret comparison is a real leak, and a plain `===` returns at the first differing
character). The Python side uses `secrets.compare_digest` for the same reason.

**Why a shared secret and not something fancier:** the caller is *our own* backend and the
receiver is *our own* frontend deploy. There is one trust boundary, and it is crossed once per
lifecycle change at most. A JWT with an expiry would add a signing key, a clock dependency and
a token format to solve a problem that one secret solves: proving the caller is us.

**The secret is deliberately narrow.** It authorises **exactly one thing**: "rebuild the paths
in the body". It grants no read access to the API, no write access to the catalog, no
administrative capability. The frontend's route handler does not consult the secret for
anything else, and there is no other endpoint that accepts it.

**3. Why this does not erode AD-19.**

| AD-19 says | This design | Why it is compatible |
|---|---|---|
| "The frontend is a client" | Still true | The frontend's *domain* knowledge is unchanged. It still holds no domain logic. |
| "It reaches the backend only through the generated API client" | Still true for **data** | The callback carries no data. Every fact on the rebuilt page still arrives through the generated client, exactly as before. |
| "The OpenAPI schema Django Ninja emits is the single source of truth" | Still true | The revalidation route handler is a **Next.js** route, not a Django endpoint. It is **not** in the OpenAPI schema, because it is not part of the API contract — it is a deployment-internal callback between two of our own deploys. No API surface is added, so no schema change, no client regeneration. |

**The important distinction, stated precisely:** AD-19 says the frontend reaches the backend
*only through the generated API client*. That is a rule about **where the frontend's data comes
from**, not a rule that forbids the backend from ever calling the frontend. The frontend's data
still comes from exactly one place — the generated client. The callback adds a *cache
instruction*, not a *data source*.

**Would a pull be better?** A pull — the frontend asks "is my copy of event X current?" —
would need the frontend to poll, or to check on every request, and it would put a backend
round-trip on the hot path of a public page. The push costs one outbound HTTP call per
lifecycle change, which is a rare event. **The push is right.**

### Who fires it — API runtime or worker

**One signal path, and it lives in the worker.**

Lifecycle changes arrive from two places:

- **the API runtime** — a user-facing write (an editorial action, an API-triggered change);
- **the worker** — the ingest pipeline and state polling.

The instinct is to wire both. **The right answer is that the *decision* to revalidate is made in
the write path in both cases, and the *delivery* happens in the worker in both cases.** The two
are separated:

| Stage | Where | What it does |
|---|---|---|
| **Decide** | the write path (API runtime *or* worker), inside the transaction | Writes the `RevalidationRequest` row and registers the `on_commit` callback |
| **Deliver** | the worker, always | Drains open requests and POSTs to the frontend |

**Why the API runtime must not deliver.** Three reasons, in order of weight:

1. **AD-11**: *"No long work inside a request… A request handler's job is to validate, enqueue,
   and return."* An outbound HTTP call to another deploy, with its own timeouts and its own
   failure modes, is exactly the long work AD-11 forbids in a request. A request that blocks
   on the frontend's availability is a request whose latency is the *sum* of two deploys'.
2. **The user-facing write must not fail because a cache rebuild failed.** If the API runtime
   delivered the signal inline, a frontend outage would turn a successful catalogue write into
   a failed request — the user would see an error for a change that was actually saved. The
   AC forbids exactly this: *"it never takes a page down."*
3. **The failure mode would be a 500 on an unrelated surface.** An editorial action failing
   because the marketing site's CDN was down is a bug, not a design.

**Why "one signal path" is not two.** Both the API runtime and the worker reach the **same**
`apps/ingestion/services/revalidation.py` service, which writes the same row and registers the
same `on_commit` callback. There is no "API version" of the signal and no "worker version" of
the signal. The only difference is *which process the callback's enqueue lands in* — and since
the callback is `transaction.on_commit`, it lands in **whichever process committed the
transaction**. That is the whole subtlety, and it is handled below.

**The subtlety: `on_commit` runs in the committing process.** `transaction.on_commit` executes
the callback **in the thread that committed the transaction**. So an API-runtime write would
run the enqueue *in the API runtime*.

**That is fine, because the enqueue is only a Celery `send_task`.** `apps/ingestion/services/outbox.py`'s
`_send` is `current_app.send_task(task_name, args=args)` — it hands the job to the broker and
returns. It does no network work of its own beyond the broker round trip, and it is already
used from the API runtime today for AD-17's propagation. The **delivery** — the HTTP call to
the frontend — happens in the worker, always.

**So: one signal path, two stages, and the stage boundary is the point.** The API runtime
writes a row and hands a job to the broker. The worker makes the call.

### Failure

**The requirement: stale-but-correct, never wrong.**

| Situation | Behaviour |
|---|---|
| The frontend is down | The request row stays **open**. The next drain re-delivers it. The page keeps serving its **stale but correct** cached copy — it was correct when it was built, and the fact it missed is a time change, not a corruption. |
| The secret is wrong | The frontend answers **401**. The request row is marked **permanently failed** — retrying with a wrong secret forever is noise, and the condition is a deployment misconfiguration, not a transient fault. It is **surfaced** (logged at `error`, and counted). |
| The frontend answers 5xx | The request row's attempt count goes up and it is **re-delivered** on the next drain, up to the bound. |
| The frontend answers 2xx | The request row is **closed**. |
| The broker is down at enqueue time | `on_commit(..., robust=True)` logs the failure and the item stays committed — the **row is already written**, so the reconciler finds it. This is AD-17's exact guarantee: *"A Redis loss or a crash between commit and enqueue therefore delays propagation; it never loses it."* |
| The backend crashes between commit and enqueue | Same as above — the row is committed, and the reconciler picks it up. |

**The bound.** A request row carries `attempts`. After `REVALIDATION_MAX_ATTEMPTS` failed
deliveries it is marked **exhausted** and no longer retried. It is not deleted — it is kept
and surfaced, because an exhausted request means "this page is stale and we gave up", and
that is a fact an operator needs to see.

**The floor (D9).** The user chose on-demand over a timer "precisely to avoid a stale window".
But a signal that can be exhausted, against a frontend that can be down for hours, against a
row that can be lost — an on-demand signal with no floor is a page that is **stale forever**.

**The floor is kept, as a backstop, and it is explicitly secondary.** `PUBLIC_PAGE_CACHE_CONTROL`
already declares `stale-while-revalidate=86400` — a day of serving-stale-then-refreshing. So
the CDN is *already* a floor for the page's bytes.

**The design's floor is the reconciler.** The reconciler re-enqueues **open** request rows on a
cadence (every 5 minutes, matching `OUTBOX_RECONCILE_EVERY_MINUTES`), independently of the
worker tick's 60-second schedule. That is the same shape as AD-17's reconciler, and it means
a delivery that failed is retried **without waiting for the next lifecycle change**.

**And a time-based page rebuild is NOT added here.** Two reasons:

1. **There is no page to rebuild.** No ISR, no `revalidate`, no public route exists in the
   frontend yet. A time-based floor would be a timer with nothing to fire.
2. **The page item owns the page's caching.** `frontend-public-event-page` decides whether its
   route uses `revalidate` (a time floor), `revalidateTag` (a tag floor), or neither. If that
   item later chooses `revalidate = 3600`, the floor exists — and it is **the page's** choice,
   made where the page is, not decided here on the page's behalf.

**What this design guarantees without the floor:** the *signal* is delivered, retried and
bounded; the *page* is rebuilt on delivery. If the delivery is exhausted, the page keeps
serving a stale copy until the page's own caching policy refreshes it. **Stale, never wrong.**

## Data Models Affected

### Creates

- **`RevalidationRequest`** (`apps/ingestion/models.py`) — the revalidation outbox

  | Column | Type | Notes |
  |---|---|---|
  | `id` | UUIDv7 | Primary key |
  | `event` | FK → `Event`, `PROTECT` | The event whose pages moved |
  | `event_version` | PositiveInteger | The version the signal is about — the **write-side** version |
  | `paths` | JSONField (list[str]) | The concrete paths to rebuild, computed at enqueue time |
  | `state` | CharField | `open` / `delivered` / `exhausted` / `failed` |
  | `attempts` | PositiveInteger | Failed delivery attempts |
  | `last_error` | CharField, blank | A reason slug — **never a URL, never a body** (AD-13) |
  | `requested_at` / `closed_at` | DateTime | |
  | `created_at` / `updated_at` | DateTime | |

  **One open request per event.** A partial unique index on `(event)` where `state = 'open'`.
  Two lifecycle changes in quick succession produce **one** open request, not two — and the
  second change **updates** the open row's `event_version` and `paths`. This is the enqueue-side
  idempotency the AC asks for, and it is why the AC's *"the same bump delivered twice rebuilds
  once more, harmlessly"* is a property of the **frontend**, not of a dedup table.

  **`event_version` is recorded for a reason beyond bookkeeping.** `PublicEventPage` carries
  `event_version` expressly so *"the revalidation work item compares it against a cached copy
  to decide whether a page is current."* The delivered signal carries the version; the
  frontend's rebuild reads the current version; a version **lower** than the signal's means
  the page was rebuilt from an older read (a race), and the rebuild is **skipped** rather than
  caching an older page over a newer one. This is D8.

### Modifies

- **`EventStateChange`** — **no change.** It is append-only with exactly one mutable column
  (`propagated_at`), which belongs to AD-17's personal propagation. The revalidation signal
  gets its own table for that reason.

- **`Event`** — **no change.** No column is added to the Event.

### The city-membership problem, and the one model change it forces

**The AC:** *"A change to a city's membership (an event published, superseded, or moved between
cities) revalidates the affected city page(s)."*

**The problem.** The affected city pages are **not** derivable from the `EventStateChange` row
alone. `_KIND_FACTS[ChangeKind.DETAIL_CHANGED]` captures `venue_fingerprint` — *not* the
venue's id, and therefore **not** its city. A venue change that moves an event from Brooklyn to
Queens records a fingerprint, and a fingerprint is a hash: it cannot be reversed to "the old
city was Brooklyn".

**Three sources of truth for the old city, and which one is used:**

| Source | Availability | Verdict |
|---|---|---|
| `EventStateChange.before["venue_fingerprint"]` | present for `DETAIL_CHANGED` | **unusable** — a hash does not name a city |
| `EventStateChange.before["venue"]` | **absent today** | **needs one model change** |
| The Event's own `venue` row at read time | only the **new** city | insufficient alone |

**The change: `venue_id` joins the recorded facts.** `EventFacts` (in `domain/lifecycle.py`)
carries `venue_fingerprint` but not the venue id; `Event` has `venue_id` and `Venue` has
`city_ref`. Recording the venue's **id** in the state change's `before`/`after` facts makes the
old city **nameable**: `venue_id → Venue.city_ref → City.slug` → the city page's path.

**Why the id and not the city slug.** The slug is a *derived* fact; the id is the row's
identity. Recording the id keeps the state-change row faithful to what happened ("the event
moved to venue V") and lets the **cascade rules** turn it into a path at enqueue time, where
the rules live in one place. Recording the slug would bake a routing decision into an audit
row.

**But the venue id is not enough on its own.** `Venue.city_ref` is **nullable** — a venue with
no city resolves to no City. So the old city may be unnameable, and the design says so: **an
event that leaves a city with no canonical city does not revalidate a city page, because there
is no city page to revalidate.** The event's own page is still revalidated.

**A second, smaller gap: `apply_silent_update`.** It changes `title`, `description` and
`canonical_url` with **no version bump and no state change**. Those are page-visible facts. A
signal keyed purely on `event_version` would **miss them entirely**.

**The decision:** `apply_silent_update` **is** a page-visible change, and the design covers it.
But it is not a *lifecycle* change and the AC is written in lifecycle terms, so this design
**does not silently widen the trigger**. Instead:

- `apply_silent_update` **does** enqueue a revalidation request, using the **current**
  `event_version` (unchanged — the version did not move) and the event's current paths. The
  signal says "rebuild this page", and the rebuild re-reads the current row — which **does**
  carry the new title. **The version need not move for the page to be rebuilt**; the version
  only guards *ordering*.
- **The version guard's rule is therefore "the rebuild must not be older than the signal",
  not "the version must have changed".** A signal at version N may be satisfied by a rebuild at
  version N.

This is the honest resolution of a gap the AC did not name. It is called out here so the next
reader does not mistake it for an oversight.

## Technical Approach

### Architecture

```
  ┌──────────────────── backend ────────────────────┐        ┌──── frontend ────┐
  │                                                     │        │                  │
  │  API runtime write ──┐                              │        │                  │
  │                      │                              │        │                  │
  │  worker ingest ──────┼─► apps/ingestion/services/   │        │                  │
  │                      │     event_writes.py          │        │                  │
  │                      │       _record_change()       │        │                  │
  │                      │              │               │        │                  │
  │                      │              ▼               │        │                  │
  │                      │     EventStateChange row      │        │                  │
  │                      │     (catalog, same txn)      │        │                  │
  │                      │              │               │        │                  │
  │                      │   transaction.on_commit ──────┼──┐     │                  │
  │                      │              │               │  │     │                  │
  │                      │              ▼               │  │     │                  │
  │                      │   RevalidationRequest row     │  │     │                  │
  │                      │   (open, paths computed)     │  │     │                  │
  │                      └──────────────────────────────┼──┼─────┼──────────────────┘
  │                                                     │  │     │
  │                          Celery ──► worker task ────┼──┼─────┤
  │                                          │          │  │     │
  │                                          ▼          │  │     │
  │                             RevalidationPort ──HTTP─▶│  │     ▼
  │                             (adapters.revalidation)  │  │   POST /revalidate
  │                                          │          │  │   Authorization: Bearer …
  │                                          ▼          │  │        │
  │                                   mark_delivered ───┼──┼──▶ revalidatePath(...)
  │                                                     │  │
  │   reconciler (every 5 min) ──► re-deliver open ─────┘  │
  └─────────────────────────────────────────────────────────┴──────────────────┘
```

### The cascade rules — which paths a change touches

**Computed on the backend, at enqueue time.** The payload is a concrete list of paths; the
frontend performs no lookups and draws no conclusions.

| The event… | Paths revalidated |
|---|---|
| exists and is `published`, non-`superseded` | `/events/<slug>` |
| has a canonical city | `/events-in-<city-slug>` |
| was `in_review` and is now `published` | `/events/<slug>`, `/events-in-<city-slug>` |
| was `published` and is now `in_review` | `/events/<slug>` — the page must **remove** or 404 it |
| was `published` and is now `superseded` | `/events/<slug>` — the page must **remove** or 404 it, **and** `/events-in-<city-slug>` (it left the city's listing) |
| moved from city A to city B | `/events/<slug>`, `/events-in-<a-slug>`, `/events-in-<b-slug>` |
| changed time, status, sold-out, or venue | `/events/<slug>`, `/events-in-<city-slug>` |

**The event's own page path is `/events/<slug>`.** This is a **fixed convention**, decided here
and consumed by `frontend-public-event-page`. The existing `/events/[id]` route is the
**personal** event detail route (it takes a UUID and is session-bearing); the public page is a
different URL space. The public page item owns its own slug route — the convention fixed here
is `/events/<slug>`.

**The city page path is `/events-in-<city-slug>`.** The FR-27 wording is
`/events-in-{city-slug}`.

**A city page that does not qualify is not revalidated.** The threshold (`>5 events`) is
enforced on the read; a city below it has no page. Revalidating a path that has no page is
harmless (`revalidatePath` on a non-existent route is a no-op), so the rule is **not** worth
enforcing — but it is recorded here so nobody later adds a threshold check and thinks it was
required.

### The `in_review` / `superseded` rule — "removes or 404s its page"

**The AC:** *"An `in_review` or newly-`superseded` event removes or 404s its page rather than
leaving a live page for content that is no longer public."*

**The signal says "rebuild `/events/<slug>`"; the page's own read decides what the rebuild
produces.** `get_public_event_by_slug` already answers correctly: an `in_review` event raises
`EventNotFoundError`, and a superseded event raises with its successor's slug. So a rebuild of
a page whose event has become non-public yields a **404**, and the 404 **replaces the cached
200** — because `revalidatePath` invalidates the route's cache, so the next request renders
the 404.

**The route handler therefore does not need a "remove" concept.** It revalidates the path; the
page's own data source refuses to serve a non-public event; the cache now holds the refusal.
That is the same path the page takes on a cold request, which is the definition of correct.

**The superseded successor is not revalidated by this signal.** `supersede_event` creates a
**new** Event with a new slug; the new event's page has never been built, so there is nothing
stale to fix. The signal revalidates the **old** path (so it stops serving) and the **city**
path (so the listing drops it).

### The path computation, and where it lives

**A pure function.** Path derivation is string work over plain data — no database, no clock, no
Django. It belongs in `domain/`, where `domain-pure` guarantees it is testable standalone and
where `domain/cities.py` already sets the precedent.

```
domain/revalidation.py
  paths_for_event(...)  -> tuple[str, ...]
```

**It takes plain data and returns plain data.** The *caller* (`apps/ingestion/services/revalidation.py`)
does the database reads — the Event, its venue, its old venue, the cities — and hands the
pure function the facts it needs. This is the same split `domain/event_fit.py` and
`domain/lifecycle.py` use.

### The delivery path, in detail

**1. Enqueue (in the write path, inside the transaction).**

```python
# apps/ingestion/services/revalidation.py
def request_revalidation(*, event_id: UUID, now: datetime) -> None:
    """Write the revalidation request and register its post-commit enqueue."""
```

Called from `event_writes._record_change` — the same site that registers AD-17's
`enqueue_propagation` — and from `apply_silent_update`, and from the publish/unpublish path.

The row is written with `using(CATALOG)`, inside the caller's transaction. The `on_commit`
callback is registered with `using=CATALOG, robust=True`.

**2. The `on_commit` callback enqueues a Celery task** — `worker.tasks.revalidate_public_pages`
— carrying the request id. The callback is `robust=True`, so a broker outage does not break
the write: the **row is already committed**, and the reconciler finds it.

**3. The worker task delivers.**

```python
@shared_task(name="worker.tasks.revalidate_public_pages")
def revalidate_public_pages(request_id: str) -> None:
    """Deliver one revalidation signal to the frontend."""
```

It reads the open request, computes the paths (or reads them from the row — they are stored,
so the computation happens once, at enqueue time), and POSTs to the frontend through the
`RevalidationPort`.

**4. The reconciler re-delivers.** Every `REVALIDATION_RECONCILE_EVERY_MINUTES` (5, matching
`OUTBOX_RECONCILE_EVERY_MINUTES`), the reconciler finds open rows whose `requested_at` is
older than `REVALIDATION_RECONCILE_AFTER` and re-delivers them.

### The port and the adapter

**A new port, `ports/revalidation.py`.**

```
ports/revalidation.py
  class RevalidationPort(ABC):
      @abstractmethod
      def revalidate(self, *, paths: Sequence[str], event_version: int) -> RevalidationResult: ...
```

**Why not `SourceFetchPort`.** Three reasons, each disqualifying on its own:

1. **It is GET-only.** `SourceFetchPort.fetch` has no method, verb or body parameter. Revalidation
   is a POST with a JSON body and a bearer token.
2. **It is the wrong semantics.** `SourceFetchPort` retrieves *untrusted public content* from a
   *third party*, under a *source budget* (size, time, ports, redirects). Revalidation posts
   *our* secret to *our own* deploy. Reusing it would mean the secret rides a transport whose
   entire design is about handling untrusted input — and whose `FetchLimits` default to
   `allowed_ports={80,443}`, which a self-hosted frontend on :3000 would fail.
3. **The `http-client` contract forbids the app from importing `httpx` anyway.** A port is the
   only way an app may reach an HTTP client.

**A new adapter, `adapters/revalidation/http.py`.** It holds the `httpx` call, the timeout, the
bearer header, and the URL. It is registered in `settings.ADAPTERS` under the key `revalidation`,
and `ports/registry.py` gains `get_revalidation_port()`.

**The `http-client` import contract must be amended.** Its `source_modules` list names every
package except `adapters.crawl`. The new adapter must be added to that list — or, better, the
contract's `source_modules` should be restructured so **"the adapters that may import an HTTP
client"** is a list that includes `adapters.revalidation`.

**This amendment is visible, and deliberately so.** `tests/architecture/test_import_contracts.py`
has `test_every_adapter_is_covered_by_the_sdk_contracts`, which asserts every adapter is covered
by the `llm-sdk` / `stripe-sdk` / `http-client` contracts. A new adapter **must** be added to
`http-client`'s source list or that test fails. **The architecture test refuses to let a new
HTTP-capable adapter appear without the contract being widened in the same commit.** That is
the project's own mechanism for making an architectural change deliberate, and this design uses
it rather than working around it.

**The `adapters-independent` contract** forbids adapters importing each other. The new adapter
imports only `httpx` and stdlib. Fine.

### The frontend route handler

**`frontend/app/revalidate/route.ts`.**

```
POST /revalidate
Authorization: Bearer <REVALIDATION_SECRET>
Content-Type: application/json

{ "paths": ["/events/some-slug", "/events-in-brooklyn"], "event_version": 7 }
```

- **Path: `/revalidate`** — deliberately **outside** `/api/*`, because `frontend/proxy.ts:28`
  rewrites every `/api/:path*` request to Django. A handler under `/api/` would be unreachable.
- **Auth**: `timingSafeEqual` against `process.env.REVALIDATION_SECRET`. Wrong or missing →
  **401**, and **no revalidation happens**. **Unconfigured** (no secret at all) → **503**,
  because a deployment with no secret must fail **closed** rather than accept every request.
- **Body**: a JSON object with `paths` (a non-empty array of strings, each beginning with `/`)
  and `event_version` (an integer).
- **Action**: `revalidatePath(path)` for each path, from `next/cache`.
- **Response**: **200** on success (with the count and the version). **400** on a malformed
  body. **401** on a bad secret. **503** when unconfigured.
- **Never a session**: the handler reads no cookie and sets none. The public pages are
  session-free by AD-12, and the revalidation route is not part of the user-facing surface.

**The handler revalidates what it is told and infers nothing.** It does not look up an event,
does not know what a slug is, does not compute a city path. The cascade rules live on the
backend, in one place, and are tested there.

**The version guard (D8).** The handler compares the signal's `event_version` against the
version the page's own read returns. If the page's data is **older** than the signal, the
rebuild is skipped — caching an older page over a newer one would be *wrong*, and that is the
one outcome the AC forbids. This check lives in the page's fetch layer (where the version is
known), and the handler passes the version down through the path revalidation. **The
`frontend-public-event-page` item owns this check**; this item delivers the version, and the
page item consumes it.

**Why the handler cannot take a page down.** `revalidatePath` **invalidates** a cache entry; it
does not render anything. The next request re-renders from the backend's public read. If the
backend's read fails, the page's own error handling applies — which is the same handling a
cold request gets. The revalidation path adds no new failure mode to the page.

### The secret — one env var on each side

**`REVALIDATION_SECRET`** — read by the backend from `config/env.py`, and by the frontend from
`process.env.REVALIDATION_SECRET`.

**Why not `CALENDAR_CREDENTIAL_KEY`.** Three reasons:

1. **The `credential-key` import contract** forbids `apps.ingestion`, `worker`, `shared` and
   `ports` from importing `apps.personalization.credentials`. The backend needs to *read* the
   secret, and the credential module is not reachable.
2. **AD-18**: *"every credential is a credential, encrypted at rest."* The calendar key is
   encrypted at rest with AES-GCM, and `shared/credential_key.py` only *parses* its format.
   A key that is encrypted at rest cannot be compared in plaintext at request time.
3. **It is a different credential.** One key per capability. A single leaked key that could
   both decrypt stored calendar credentials *and* force page rebuilds is two capabilities in
   one secret.

**The secret is required with no default**, exactly like `calendar_credential_key`. A missing
value aborts the boot rather than leaving an app that boots healthy and fails later.

**But the frontend cannot abort a boot on a missing secret the way Django can.** The Next
route handler reads it per request. If it is missing, the handler answers **503** — "the
revalidation endpoint is not configured" — which is a *different* answer from 401 ("the secret
is wrong"). The backend treats 503 as retryable and 401 as permanent, so a misconfigured
frontend is retried (and eventually exhausted) while a wrong secret fails fast.

### Why the outbox is a table and not a Celery-only path

**The AC:** *"A revalidation that cannot be delivered is retried and surfaced."*

Celery's own retry is possible but the project **does not use it anywhere** — there is no
`self.retry` in the codebase. The house pattern is AD-17's: *"record it on the row, retry at
the next cadence."* This design follows the house pattern:

- The **row** is the record. It carries `state`, `attempts`, `last_error`.
- The **reconciler** is the retry. It runs on a cadence and re-delivers open rows.
- The **bound** is `REVALIDATION_MAX_ATTEMPTS`.
- The **surfacing** is the log line at `error` when a request is exhausted, plus the row's own
  `state` and `attempts` for an operator to query.

**Why not reuse `EventStateChange.propagated_at`:** the append-only guard allows exactly one
mutable column on that table and it is spoken for. A second marker on the same table would
need the guard widened — and the two markers have genuinely different lifecycles (AD-17's
propagation is *per-user* and may happen after any number of state changes; a revalidation is
*per-event* and must happen after a specific one).

### Why `worker.tasks.propagate_state_change` is not reused

**It is a reserved slot.** Its docstring says so explicitly: *"AD-17 placeholder consumer: no
propagation into `personal` exists yet (FR-53-55). It deliberately leaves `propagated_at` NULL:
marking the row would claim a propagation that never happened, and the real consumer would
then skip it."* It is **reserved for the personal-propagation consumer** that FR-53/54 will
land.

**Reusing it would break that reservation.** If the revalidation consumer occupied it, the
future personal-propagation consumer would find a slot already taken, and — worse — a
revalidation task that set `propagated_at` would claim a propagation that never happened. The
slot gets its own task: `worker.tasks.revalidate_public_pages`.

## Affected Files

| File | Action | Purpose |
|---|---|---|
| `backend/domain/revalidation.py` | create | `paths_for_event()` — the pure path rules |
| `backend/domain/lifecycle.py` | modify | `EventFacts` gains `venue_id` |
| `backend/apps/ingestion/models.py` | modify | `RevalidationRequest` |
| `backend/apps/ingestion/migrations/0007_revalidation_request.py` | create | The table |
| `backend/apps/ingestion/services/revalidation.py` | create | The write-path service: request, mark, reconcile |
| `backend/apps/ingestion/services/event_writes.py` | modify | The `on_commit` registration; `apply_silent_update` |
| `backend/ports/revalidation.py` | create | `RevalidationPort` |
| `backend/ports/registry.py` | modify | `get_revalidation_port()` |
| `backend/adapters/revalidation/http.py` | create | The httpx adapter |
| `backend/adapters/revalidation/fake.py` | create | The fake adapter (the project's `adapter_mode=fake` default) |
| `backend/config/env.py` | modify | `revalidation_secret`, `frontend_revalidation_url`, `revalidation_*` constants |
| `backend/config/adapters.py` | modify | Register the `revalidation` adapter |
| `backend/config/settings.py` | modify | `ADAPTERS["revalidation"]` |
| `backend/worker/tasks.py` | modify | `revalidate_public_pages` + the reconciler |
| `backend/shared/constants.py` | modify | The retry bound, the cadence, the path prefixes |
| `backend/pyproject.toml` | modify | **Amend the `http-client` contract** to include `adapters.revalidation` |
| `backend/tests/domain/test_revalidation.py` | create | The path rules, pure |
| `backend/tests/ingestion/test_revalidation_service.py` | create | The outbox, the enqueue, the idempotency |
| `backend/tests/worker/test_revalidate_task.py` | create | The delivery, the failure, the retry, the bound |
| `backend/tests/architecture/test_import_contracts.py` | modify | The contract amendment is asserted |
| `frontend/app/revalidate/route.ts` | create | The route handler |
| `frontend/app/revalidate/route.test.ts` | create | The handler's contract |
| `frontend/lib/revalidation.ts` | create | The secret comparison + the shared body shape |

**Not changed: any OpenAPI schema.** The revalidation route is a Next.js route, not a Django
endpoint. No API surface is added, so `frontend/lib/api/openapi.json` and
`frontend/lib/api/schema.ts` are **not** regenerated. AD-19 is untouched because AD-19 governs
the API contract, and this is not the API contract.

**Not changed: `EventStateChange`.** Its append-only guard permits one mutable column and it
belongs to AD-17.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **The frontend deploy is down when a change lands** | The page serves a stale copy until the retry succeeds | The request row stays open; the reconciler re-delivers on a 5-minute cadence; `stale-while-revalidate=86400` in `PUBLIC_PAGE_CACHE_CONTROL` is the page-level floor. **Stale, never wrong.** |
| **The secret is wrong in one deploy** | Every signal is refused | The frontend answers 401; the backend marks the request **permanently failed** (not retried) and logs at `error`. A wrong secret is a deployment misconfiguration, not a transient fault, and retrying it forever is noise. |
| **The backend calls the frontend and the frontend is slow** | A slow frontend delays the worker, not the user | The adapter has a bounded timeout (`REVALIDATION_TIMEOUT_SECONDS`, default 5). The delivery is on the worker; the user-facing write already returned. |
| **A lifecycle change is committed but the enqueue is lost** | The page never rebuilds | `on_commit(robust=True)` + the durable row. The row is committed with the change; the reconciler finds it. **AD-17's exact guarantee.** |
| **The rebuild caches an older page over a newer one** | **The page is wrong.** | The version guard (D8): the rebuild is skipped when the page's data is older than the signal's version. |
| **The `http-client` contract is widened by accident** | Any module could grow an HTTP client | The architecture test `test_every_adapter_is_covered_by_the_sdk_contracts` fails unless the new adapter is **named** in the contract — so the widening is a deliberate, visible edit to `pyproject.toml`, in the same commit as the adapter. |
| **The signal is sent to the wrong host** | A credential leaves our infrastructure | The URL comes from configuration (`FRONTEND_REVALIDATION_URL`), never from the request. The adapter does not follow redirects to a different host, and it validates the scheme is `https` in production. |
| **The city path is wrong because the old city is unnameable** | A city page keeps a stale listing | The old city is captured by the `venue_id` fact. A venue with no `city_ref` has no city page, so there is nothing to revalidate. |
| **`apply_silent_update` misses the signal** | A title change never reaches the page | `apply_silent_update` enqueues a revalidation request too, at the current version. See "The city-membership problem" → the silent-update gap. |
| **The version guard adds a coupling the page item does not want** | The page item must implement a version check | Documented as the contract between the two items, and **the version is already on `PublicEventPage`** for exactly this purpose. If the page item decides it does not want the check, it says so and the version is simply unused. |
| **The frontend has no public page yet, so the signal rebuilds nothing** | The end-to-end behaviour is unobservable | Stated in **Scope**. The signal's *own* contract — which paths, when, authenticated, idempotent, retried, bounded — is fully testable without a page. The route handler is tested for the `revalidatePath` calls it makes. |

## Implementation Checklist

- [ ] `domain/revalidation.py` — `paths_for_event()`, pure, stdlib only
- [ ] `domain/lifecycle.py` — `EventFacts` gains `venue_id`; `facts_of()` and `IncomingEvent.facts()` populate it
- [ ] `RevalidationRequest` model + migration, with the partial unique index on `(event)` where `state='open'`
- [ ] `services/revalidation.py` — `request_revalidation()`, `mark_delivered()`, `mark_failed()`, `reconcile_revalidation()`
- [ ] The `on_commit` registration in `event_writes._record_change` — `using=CATALOG, robust=True`
- [ ] `apply_silent_update` enqueues a revalidation too
- [ ] `ports/revalidation.py` — `RevalidationPort` + `RevalidationResult`
- [ ] `ports/registry.py` — `get_revalidation_port()`
- [ ] `adapters/revalidation/http.py` + `adapters/revalidation/fake.py`
- [ ] **`pyproject.toml` — the `http-client` contract amended to name `adapters.revalidation`**
- [ ] `config/env.py` — `revalidation_secret` (required, no default), `frontend_revalidation_url`, the timeout
- [ ] `worker/tasks.py` — `revalidate_public_pages` + `reconcile_revalidation`
- [ ] `shared/constants.py` — the retry bound, the cadence, the path prefixes
- [ ] `frontend/app/revalidate/route.ts` — the handler
- [ ] `frontend/lib/revalidation.ts` — the secret comparison and the body shape
- [ ] **Test: a status change to cancelled revalidates the event's page**
- [ ] **Test: a sold-out flip revalidates the event's page**
- [ ] **Test: a venue change revalidates the event's page and both city pages**
- [ ] **Test: a time change revalidates the event's page**
- [ ] **Test: a publish revalidates the event's page and the city page**
- [ ] **Test: an unpublish revalidates the event's page** (the page must 404)
- [ ] **Test: a supersede revalidates the old page and the city page**
- [ ] **Test: a delivery failure is retried and the retry succeeds**
- [ ] **Test: a double delivery is harmless** (the request is closed after the first)
- [ ] **Test: the trigger fires post-commit** (the callback does not run inside the transaction)
- [ ] **Test: a 401 is not retried; a 5xx is**
- [ ] **Test: the attempts bound exhausts the request and surfaces it**
- [ ] **Test: the reconciler re-delivers an open request**
- [ ] **Test: two lifecycle changes produce one open request**
- [ ] **Test: the route handler refuses a wrong secret and never revalidates**
- [ ] **Test: the route handler rejects a malformed body**
- [ ] **Test: the route handler calls `revalidatePath` for every path it is given**
- [ ] `lint-imports` clean — the `http-client` amendment is deliberate
- [ ] The architecture test names the new adapter in `http-client`
- [ ] `manage.py check` clean; `makemigrations --check` shows no drift
- [ ] **The existing `propagate_state_change` slot is untouched**

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-11-02*
