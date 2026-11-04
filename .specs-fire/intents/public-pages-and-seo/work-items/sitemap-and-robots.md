---
id: sitemap-and-robots
title: Discoverable, not merely reachable — the sitemap and robots
intent: public-pages-and-seo
complexity: medium
mode: confirm
status: completed
depends_on:
  - public-event-read-by-slug
  - city-page-read-api
created: 2026-11-01
run_id: run-eventpulse24-024
completed_at: 2026-11-04T06:18:38.155Z
---

# Work Item: Discoverable, not merely reachable — the sitemap and robots

## Description

Pages that exist and cannot be found are not an SEO surface. A grep for `sitemap` across this repository returns **zero hits**, and `frontend/app/` has neither `sitemap.ts` nor `robots.ts`. This item makes the public pages discoverable: a sitemap enumerating every public event and qualifying city page, and a robots policy that invites crawlers to the public surface and keeps them out of the authed one.

## Acceptance Criteria

- [x] A **backend URL feed** listing public event slugs and qualifying city slugs with their last-modified times. It is **paged and bounded** — this read grows with the catalog and must never be an unbounded scan.
- [x] `lastmod` is **derived from the event's real last change**, so a crawler is told the truth about what moved. `event_version` already increments on every lifecycle change and is the honest basis for it.
- [x] `frontend/app/sitemap.ts` emits a valid sitemap covering both page types, **split into a sitemap index** if the catalog exceeds the 50,000-URL / 50MB limit — chosen now rather than discovered at scale.
- [x] Only publicly addressable URLs appear: **no `in_review`, no `superseded`, no below-threshold city**, matching exactly what the two read items serve. A sitemap that lists a 404 is a crawl-budget leak.
- [x] `frontend/app/robots.ts` allows the public surface, **disallows the authed and dev routes** (`/settings`, `/timeline`, `/conflicts`, `/onboarding`, `/dev`, `/events/{uuid}`), and points at the sitemap.
- [x] The sitemap is generated, **never hand-maintained** — a static list would be stale the first time the pipeline runs.
- [x] The feed is session-free (AD-12) and uses the generated client (AD-19).
- [x] Tests: a feed page boundary, exclusion of `in_review` / superseded / below-threshold entries, sitemap validity, the index split at threshold, and robots disallowing the authed routes while allowing `/events/{slug}` and `/events-in-{city}`.

## Technical Notes

Disallowing `/events/{uuid}` while allowing `/events/{slug}` is awkward precisely because of the branching route — both live under one path segment. Resolve it with an explicit pattern rather than hoping crawlers never guess a UUID; a crawler that indexes the authed branch gets a sign-in redirect recorded as the page's content.

## Dependencies

- public-event-read-by-slug
- city-page-read-api
