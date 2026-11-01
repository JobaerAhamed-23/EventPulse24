---
id: city-page-read-api
title: The city read — the preview's rules, unbounded and paged
intent: public-pages-and-seo
complexity: medium
mode: confirm
status: pending
depends_on:
  - city-canonicalization
created: 2026-11-01
---

# Work Item: The city read — the preview's rules, unbounded and paged

## Description

What `/events-in-{city-slug}` renders from. Most of this read already exists: `apps/ingestion/event_fit/reads.py:63` `list_event_fit_for_city` serves the Pulse Preview and already does the parts that are easy to get wrong — it **skips a stale row** whose `event_version` no longer matches its Event (AD-10), filters to `published` and non-`superseded`, orders by score descending then start time ascending, and matches `city__iexact` on a stripped string.

What it does not do is **page**. It is clamped by `MAX_PREVIEW_SIZE` and returns a top-N preview by design. A city page is a different thing: an unbounded, paged listing. This item extends that read rather than writing a second one, so the staleness rule and the publication filters have exactly one implementation.

## Acceptance Criteria

- [ ] A city listing read that **reuses `list_event_fit_for_city`'s rules** — staleness skip, `published`-only, non-`superseded`, score-then-start ordering — with paging in place of the preview clamp. The preview's own call site keeps working unchanged; `/preview` is live today.
- [ ] The read is keyed on the **canonical City** from `city-canonicalization`, not a raw query string, so `Brooklyn` and `Brooklyn, NY` resolve to one page.
- [ ] Rows are **served as stored** (AD-10): the score and tags are never recomputed at render, and a stale row is absent rather than wrong.
- [ ] The **>5 events** threshold (FR-27) is applied as a documented, single-sourced constant, and the count is computed by the same filters the listing uses — a city cannot show 3 events on a page that claimed it qualified.
- [ ] A city **below the threshold or empty** returns a well-formed empty result the page renders as "coming soon" — **not a 404 and not an error**. FR-27 requires graceful degradation.
- [ ] **No session is read and none is set** (AD-12). The response does not vary by cookie.
- [ ] Paging is bounded: a page-size ceiling, and a request beyond the last page returns empty rather than erroring.
- [ ] Schemas and regenerated client (AD-19).
- [ ] Tests: a city above threshold across two pages, a city at exactly 5 and at exactly 6 events, an empty city, a city whose only fits are stale, an unknown city slug, ordering with tied scores, and a request with a session cookie proving the response is identical without it.

## Technical Notes

**OQ-D is still open and this item decides it:** does `>5 events` count **upcoming only** or all-time? `list_event_fit_for_city` filters `start_time_utc >= now`, so inheriting its behaviour means a city page can wink out of existence once its events pass — an SEO regression, since a URL that 404s after ranking is worse than one that never ranked. Recommended resolution: **list upcoming events, but qualify the city on a broader window**, so the page persists and shows "coming soon" between seasons rather than disappearing. Confirm during the run.

`event_fit_city_score_idx` on `(city, score)` already serves this access path — check the paged query still uses it rather than falling back to a sort.

## Dependencies

- city-canonicalization
