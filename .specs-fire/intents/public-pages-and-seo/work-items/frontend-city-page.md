---
id: frontend-city-page
title: Events in [city] — the landing page that answers the search
intent: public-pages-and-seo
complexity: medium
mode: confirm
status: completed
depends_on:
  - city-page-read-api
  - frontend-public-event-page
created: 2026-11-01
run_id: run-eventpulse24-024
completed_at: 2026-11-03T10:31:00.858Z
---

# Work Item: Events in [city] — the landing page that answers the search

## Description

The page a stranger lands on after typing "events in Brooklyn" — the long-tail query FR-27 exists to capture. It renders the paged city listing as a grid of events, each linking to its public event page, with the sparse case handled honestly rather than as an empty screen.

## Acceptance Criteria

- [x] A route at **`/events-in-{city-slug}`** rendering the paged city listing, statically generated or ISR'd, **fully without a session** (AD-12).
- [x] Event Fit's **score and tags are displayed as served** (AD-10) — never recomputed, never re-ranked on the client.
- [x] A city **below the >5 threshold or with no upcoming events** renders the **"coming soon"** state from `city-page-desktop.html` — not an empty grid, not a 404. FR-27 requires graceful degradation.
- [x] Each card links to the public event page at `/events/{slug}`.
- [x] Title and meta description are **per-city and descriptive** (`Events in Brooklyn · This week and next · EventPulse24`), with a canonical link tag.
- [x] Paging is **crawlable** — reachable by link, not only by a client-side control a crawler cannot operate.
- [x] An **unknown city slug** returns a real 404 status, not a soft 404.
- [x] Theming, filter chips and the city pill follow `city-page-desktop.html`; works at phone width.
- [x] Tests: a populated city across two pages, a city in the sparse state, an unknown slug's status code, a render with no cookies, and the crawlable paging links present in server-rendered HTML.

## Technical Notes

Reuse the public event card presentation from `frontend-public-event-page` rather than building a second card — the two pages show the same noun and should not drift.

`city-page-desktop.html` is self-tagged `FR-27` and already includes the sparse "coming soon" state; build from it.

## Dependencies

- city-page-read-api
- frontend-public-event-page
