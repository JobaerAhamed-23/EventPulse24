---
id: city-page-read-api
title: The city read — the preview's rules, unbounded and paged
intent: public-pages-and-seo
complexity: medium
mode: confirm
status: completed
depends_on:
  - city-canonicalization
created: 2026-11-01
run_id: run-eventpulse24-024
completed_at: 2026-11-02T07:46:42.703Z
---

# Work Item: The city read — the preview's rules, unbounded and paged

## Description

What `/events-in-{city-slug}` renders from. Most of this read already exists: `apps/ingestion/event_fit/reads.py:63` `list_event_fit_for_city` serves the Pulse Preview and already does the parts that are easy to get wrong — it **skips a stale row** whose `event_version` no longer matches its Event (AD-10), filters to `published` and non-`superseded`, orders by score descending then start time ascending, and matches `city__iexact` on a stripped string.

What it does not do is **page**. It is clamped by `MAX_PREVIEW_SIZE` and returns a top-N preview by design. A city page is a different thing: an unbounded, paged listing. This item extends that read rather than writing a second one, so the staleness rule and the publication filters have exactly one implementation.

## Acceptance Criteria

- [x] A city listing read that **reuses `list_event_fit_for_city`'s rules** — staleness skip, `published`-only, non-`superseded`, score-then-start ordering — with paging in place of the preview clamp. The preview's own call site keeps working unchanged; `/preview` is live today.
- [x] The read is keyed on the **canonical City** from `city-canonicalization`, not a raw query string, so `Brooklyn` and `Brooklyn, NY` resolve to one page.
- [x] Rows are **served as stored** (AD-10): the score and tags are never recomputed at render, and a stale row is absent rather than wrong.
- [x] The **>5 events** threshold (FR-27) is applied as a documented, single-sourced constant, and the count is computed by the same filters the listing uses — a city cannot show 3 events on a page that claimed it qualified.
- [x] A city **below the threshold or empty** returns a well-formed empty result the page renders as "coming soon" — **not a 404 and not an error**. FR-27 requires graceful degradation.
- [x] **No session is read and none is set** (AD-12). The response does not vary by cookie.
- [x] Paging is bounded: a page-size ceiling, and a request beyond the last page returns empty rather than erroring.
- [x] Schemas and regenerated client (AD-19).
- [x] Tests: a city above threshold across two pages, a city at exactly 5 and at exactly 6 events, an empty city, a city whose only fits are stale, an unknown city slug, ordering with tied scores, and a request with a session cookie proving the response is identical without it.

## Technical Notes

**OQ-D is still open and this item decides it:** does `>5 events` count **upcoming only** or all-time? `list_event_fit_for_city` filters `start_time_utc >= now`, so inheriting its behaviour means a city page can wink out of existence once its events pass — an SEO regression, since a URL that 404s after ranking is worse than one that never ranked. Recommended resolution: **list upcoming events, but qualify the city on a broader window**, so the page persists and shows "coming soon" between seasons rather than disappearing. Confirm during the run.

> **Resolved during the run, as recommended.** The listing shows upcoming events; the
> qualification counts over `CITY_PAGE_QUALIFICATION_WINDOW` (365 days). The two counts
> answer different questions and are measured separately:
>
> - **`event_count`** — the *qualifying* count, over the window. It is what
>   `is_published` is decided on, and it is why the page persists between seasons.
> - **`has_next`** — measured against the *listing's* total (upcoming only), **not**
>   `event_count`. This distinction was caught in code review: measuring `has_next`
>   against the qualifying count makes an off-season city (six qualifying events, empty
>   listing) advertise a next page it does not have, and a crawler follows it forever.
>
> `test_a_city_that_has_had_events_keeps_its_page_between_seasons` holds the window
> down; `test_the_qualification_window_has_a_boundary` pins its edge.

`event_fit_city_score_idx` on `(city, score)` already serves this access path — check the paged query still uses it rather than falling back to a sort.

## Dependencies

- city-canonicalization
