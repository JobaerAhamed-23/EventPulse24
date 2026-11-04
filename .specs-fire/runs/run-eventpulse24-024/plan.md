---
run: run-eventpulse24-024
work_item: e2e-proof-and-contract-tests
intent: public-pages-and-seo
mode: confirm
checkpoint: plan
approved_at: 2026-11-04
---

# Implementation Plan: Prove a stranger can get in — and that the proof can fail

## Approach

**The shape of the work.** Nine work items built this intent's public surface. Each was
tested in isolation: the read, the projection, the page, the route, the sitemap, the
share control. **None of them was tested as a journey.** This item is the journey, and
it is walked by the one visitor whose case nobody has proved: **someone with no account
and no cookie.**

**Why the stranger is the subject.** Every other item's proof could assume a session.
A sign-in wall that creeps onto a public page is invisible to every test that logs in
first — the test would be green, the crawler would be redirected, and the page would be
unindexable. So this proof is written **from the outside in**: the city landing, then
the event page, then the CTA — with no cookie jar anywhere.

**The proof is in three languages, and each language proves one thing the others cannot.**

1. **The backend speaks the truth** (`backend/tests/e2e/test_public_pages_proof.py`).
   The catalog's three public endpoints, the city page's staleness rule, the
   `in_review` invisibility, the past event that still resolves, the revalidation
   signal's paths, and the URL feed's membership — asserted against a real database.
   This is the layer that decides *what is public*.
2. **The frontend renders it, server-side, with JavaScript off**
   (`frontend/tests/public-crawl-proof.test.tsx`). The crawler does not run React; it
   reads bytes. So the crawl is proved with **`renderToStaticMarkup`** over the route
   functions themselves, with `next/headers`'s `cookies` mocked to **throw** — so any
   attempt to read a session fails loudly instead of silently rendering an empty jar.
3. **The contract holds** (`backend/tests/e2e/test_public_pages_contract.py`). The
   generated client is in sync (AD-19), the import contracts hold, and the public reads
   are structurally session-free — asserted on the source, because "no session" is a
   property of the module, not of one rendered page.

**And every one of those assertions is shown able to fail.** The mutation probes
(`backend/tests/e2e/mutation_probe_public_pages_e2e.py`) plant one real bug at a time —
a stale fit rendered instead of dropped, an `in_review` event leaking into the feed, a
`sessionHeaders()` call creeping into a public read — and require the matching suite to
go red. A test that cannot fail proves nothing, and the walkthrough records the probe
output.

**Order of work, and why:**

1. **Backend proof first**, because the backend decides what "public" means and every
   other assertion is downstream of it. It also needs the one new fixture the item
   requires: a city with **six** current fits (FR-27's threshold is strictly `> 5`),
   each with `city_ref` set — which `VenueFactory` does **not** provide.
2. **The frontend crawl**, because it is the item's centrepiece and it is the layer
   nobody has touched.
3. **The contract file**, because it is the cheapest file and it catches drift.
4. **The probes**, last, because a probe's job is to break the code the other three
   files just wrote.

**Three facts the implementation must not lose:**

- **"No session" must be structural, not incidental.** The proof's client must have *no
  cookie jar at all* — not "a client that happens not to log in". A later change can
  silently restore a login step; a later change cannot silently restore a cookie jar
  that the harness refuses to carry.
- **The JSON-LD is asserted on the *server-rendered* markup.** A DOM test with
  JavaScript enabled proves nothing about a crawler. The assertion is on the bytes
  `renderToStaticMarkup` produces, and the JSON-LD is parsed out of the markup.
- **A stale `EventFit` row is *absent*, not rendered wrong.** The rule is a skip, not a
  correction. The proof asserts the row's absence from the listing — and the probe
  proves the assertion goes red when the skip is removed.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/tests/e2e/public_pages_fixtures.py` | The shared fixtures: a canonical city, a venue with `city_ref`, six current fits, one stale fit, one `in_review` event, one past event. Written as functions, not factories, because the trigger and the threshold make several of these impossible to build with `factory_boy` alone. |
| `backend/tests/e2e/test_public_pages_proof.py` | The backend half of the proof: the anonymous crawl's first hop (the city endpoint), the event endpoint, the past event, the stale fit, `in_review` invisibility, the URL feed's membership, the revalidation signal's paths, and the visible-status ↔ `eventStatus` agreement. |
| `backend/tests/e2e/test_public_pages_contract.py` | The contract half: the generated client is in sync (AD-19), the import contracts hold, the three public reads are structurally session-free, and the public pages' metadata is indexable while the Detail Screen's is not. |
| `backend/tests/e2e/mutation_probe_public_pages_e2e.py` | The mutation probes: one real bug at a time, each naming the suite that must go red. |
| `frontend/tests/public-crawl-proof.test.tsx` | The crawl proof: `/events-in-{city}` → `/events/{slug}` → the "Save to Pulse" CTA, with no cookie jar at any hop, and the JSON-LD parsed out of the server-rendered markup. |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/tests/e2e/conftest.py` | **Patch `revalidation._send` as well.** The file already patches `tasks._enqueue` and `outbox._send`; the revalidation outbox has its own seam (`apps/ingestion/services/revalidation.py`'s `_send`), and until it is patched the enqueue reaches a broker the test does not own. The new fixture is `revalidation_sent`, and it records `(task_name, args)`. |
| `backend/tests/e2e/test_public_pages_proof.py` | *(created above — listed here for the conftest coupling)* The proof uses `revalidation_sent` to observe the signal's enqueue. |
| `frontend/lib/api/openapi.json` | **Not changed.** This item adds tests, not endpoints — so the committed document must stay *exactly* as it is, and the contract test asserts it is unchanged. That is itself the AD-19 claim. |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/e2e/test_public_pages_proof.py` | The city endpoint answers a stranger with the listing; the event endpoint answers with the full page and its JSON-LD; a **past** event still answers 200 with content; a **stale** `EventFit` is absent from the city page; an **`in_review`** event is absent from its own slug, from the city page and from the URL feed; the visible status and the `eventStatus` agree; a cancellation writes **one** revalidation request naming the event's path and the city's path; the feed carries exactly the public URLs. |
| `backend/tests/e2e/test_public_pages_contract.py` | The committed OpenAPI matches the live API and the generated TypeScript matches the document (AD-19 — a drifted client fails); the 19 import contracts hold; `public-event-read.ts`, `city-page-read.ts` and `url-feed-read.ts` carry no `sessionHeaders`, no `getSession` and no `cookies(`; the public branches' metadata is indexable and the Detail Screen's is not. |
| `frontend/tests/public-crawl-proof.test.tsx` | The city landing renders server-side and links to the event; the event page renders server-side with its title, its description and the "Save to Pulse" CTA; **no hop reads a cookie** (`cookies` throws if called); the JSON-LD is in the server-rendered markup and parses as a Schema.org `Event`; the CTA is a plain link to `/signup`; the authed surfaces still branch — `/events/{uuid}` reads the detail endpoint and `/events/{uuid}/reminders` reads the plan. |
| `backend/tests/e2e/mutation_probe_public_pages_e2e.py` | *(not a test — the probe harness)* Each probe plants a bug and requires the named suite to go red. The output is recorded in the walkthrough. |

## Technical Details

**The crawl is proved with `renderToStaticMarkup`, in a `// @vitest-environment node`
file.** The crawler reads bytes; React's DOM renderer never runs on a crawler. Two
things make this work, and both were verified live before the plan was written:

- `renderToStaticMarkup` over a `next/link` produces a plain `<a href="…">`, and over
  the route functions produces the whole document — the city page's markup contains the
  event's `/events/{slug}` link and the brand's `<img>`.
- The route functions are **awaited** by the test, exactly as Next awaits them, and
  `next/navigation`'s `notFound`/`permanentRedirect` are mocked to throw — which is
  what Next does with them, and what makes a 404 assertable.

**"No session" is enforced by making the cookie jar unreachable.** `next/headers`'s
`cookies` is mocked to **throw**. A public page that called it would not render a page
with an empty session — it would fail loudly, and the crawl would go red. That is
stronger than asserting `cookies` was not called, because it removes the possibility
of a call that returns a session and is then ignored.

**The JSON-LD is asserted on the markup, and the agreement is asserted together.** The
structured data and the visible state come from the same `status` field, so the proof
cancels an event and asserts **both** in one place: the rendered `data-public-status`
line says it is cancelled, and the JSON-LD's `eventStatus` is
`https://schema.org/EventCancelled`. Asserted separately, the two could drift — one
test would pass while the page lied.

**The revalidation round trip is driven from the write path, not from a timer.**
`apply_lifecycle_change` — a real lifecycle change — bumps the version, writes one
`EventStateChange`, and requests **one** `RevalidationRequest` whose `paths` are
`["/events/{slug}", "/events-in-{city}"]`. The proof asserts the paths, the version and
the enqueue, and it does so **with the clock frozen** (`now` is an argument everywhere
in this codebase) and **without waiting**: the promise is that the *signal* names the
paths, and the frontend's half of the round trip — `revalidatePath` **and**
`revalidateTag(path, { expire: 0 })` — is asserted by the existing
`app/revalidate/route.test.ts` and re-asserted here against the paths the backend
actually produced. **No test sleeps.** A test that waits for a timer is a test whose
answer depends on the machine it ran on.

**The past event is proved against `get_public_event_by_slug`'s own rule.** That read
has **no time bound** — unlike `list_public_events` and `get_public_event(event_id,
now=…)` — so a page for an event that already happened stays addressable. The proof
asserts a real 200 **with content** (the title, the slug, the JSON-LD), not merely a
200: an endpoint that answered 200 with an empty body would pass a status-only
assertion.

**The stale `EventFit` is absent, not wrong.** The staleness rule is
`row.event_version == row.event.event_version`; a row that fails it describes an event
that no longer exists, so it is **skipped** — in Python by `city_read._current_rows`,
and in SQL by the URL feed's `event_version=F("event__event_version")`. The proof
writes a fit whose `event_version` is stale and asserts the event is **not in the
listing**, and that the city's qualifying count did not count it.

**`in_review` is invisible from all three directions, and each has its own reason.**
Its own slug is a 404 (`get_public_event_by_slug` refuses any non-published row); the
city page omits it (`_published_upcoming_fits` filters on `publication_status`); the
feed omits it (`_event_queryset` filters on the same field). Three different
mechanisms, one promise — so the proof asserts all three, and the probes break all
three.

**The sitemap's no-404 promise is proved by fetching every `<loc>`.** The feed is the
source of truth for the sitemap, so the proof reads the feed, walks every path, and
asserts that each one resolves — the event paths through the event endpoint, the city
paths through the city endpoint. A path in the sitemap that 404s is a crawl-budget
leak, and it is the one failure the sitemap item cannot see from inside.

**The robots rules are asserted against the rules the file declares.** `robots.ts`
returns a typed object, and the object *is* the policy — the rendered `/robots.txt` is
Next's business. The existing `frontend/tests/sitemap-robots.test.ts` already covers
the rules in isolation; the contract file re-asserts the **pairing** that matters here:
the authed prefixes are disallowed, the public prefixes are not, and `/events` is *not*
disallowed (because it holds the public pages) while the Detail Screen's own metadata
carries the noindex.

**The authed surfaces are proven unbroken by running them.** `/events/{uuid}` and
`/events/{uuid}/reminders` are asserted through their own reads, with a signed-in
session — the point being that the branching route did not regress the signed-in
Detail Screen. The proof asserts the **detail** read is made for a UUID and **not** for
a slug, and that the reminders route reads the plan with the session's cookies.

**The contract file regenerates rather than compares.** The committed `openapi.json`
is compared to the **live** schema (the backend's own `test_contract.py` does this too,
and the new file asserts it holds from the e2e side), and the generated TypeScript is
compared to what `openapi-typescript` produces **now** — with the file restored
afterwards, so the check is a measurement and not a rewrite. **CI's `contract` job does
the same thing as a `git diff`**, so a drifted client fails the build; the e2e file
proves the same property locally.

**Two seams the research surfaced, and both are handled in the implementation:**

- **`backend/tests/e2e/conftest.py` does not patch `revalidation._send`.** The revalidation
  outbox has its own seam, and the enqueue would reach Celery. The conftest gains the
  patch and a `revalidation_sent` fixture.
- **The city page needs six qualifying fits with `city_ref` set.** `VenueFactory` does
  not set `city_ref`, and `write_event_fit` copies it from the venue — so the fixture
  writes the `City`, the `Venue` (with `city_ref`), the `Event`s and the `EventFit`s
  explicitly, exactly as `tests/api/test_city_page_api.py` does. **A city with five is
  not published; a city with six is.** The proof builds six, and the probe breaks the
  staleness skip to show the count can go wrong.

**No test sleeps, and no test reaches the network.** The whole proof runs offline against
the test database, with `now` passed explicitly. A proof whose answer depends on the
wall clock, or on a network, is a proof whose answer is not about this system.

## Based on Design Doc

Reference: `.specs-fire/intents/public-pages-and-seo/work-items/e2e-proof-and-contract-tests.md`
(the work item itself; there is no separate design doc for this item, and the run's
precedent is the delivery intent's `e2e-proof-and-contract-tests`).

---
*Plan approved at checkpoint. Execution follows.*
