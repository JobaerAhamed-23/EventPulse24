---
id: public-event-read-by-slug
title: The public event read — by slug, and the past still counts
intent: public-pages-and-seo
complexity: medium
mode: confirm
status: in_progress
depends_on: []
created: 2026-11-01
---

# Work Item: The public event read — by slug, and the past still counts

## Description

The surface that serves `/events/{slug}` to a stranger with no session. It is a **new read**, not a reuse: `apps/catalog/api.py:70` `get_event(request, event_id: UUID)` is keyed on a UUID a crawler never sees, and its own description says an event *"that is not public — **or that has already started** — reads as not found."* That rule is correct for a digest and fatal for SEO. A page that 404s the moment the doors open throws away every bit of ranking it spent months earning, and a Schema.org page for a concert last month is legitimate content, not an error.

## Acceptance Criteria

- [ ] `GET` one published event **by `slug`**, in `catalog`'s public router. **No session is read and none is set** (AD-12).
- [ ] **A past event resolves.** Unlike `get_event`, there is no `start_time_utc >= now` filter. The page for an event that already happened stays addressable and stays indexed.
- [ ] An event whose `publication_status` is `in_review` is **404, not 200** — never publicly addressable, matching the model's own comment ("not digest-eligible, not publicly listed") and AD-6/AD-8.
- [ ] A **`superseded`** event is 404 at its own slug; where `superseded_by` names a live Event, the response directs to that event's slug so the link a crawler already has resolves forward rather than dying.
- [ ] The payload carries everything the page and its JSON-LD need from one read: title, description, `start_time_utc`, `end_time_utc`, `start_time_tz` (the IANA name — ARCHITECTURE-SPINE.md:565 requires the timezone in the public JSON-LD), venue name and address parts, city, `canonical_url`, `status`, `is_sold_out`, and `event_version`.
- [ ] `event_version` is in the payload — the revalidation work item needs it to prove a cached page is current.
- [ ] An unknown slug is a clean 404, not a 500, and is cacheable as such.
- [ ] Schemas and **regenerated client** (AD-19) — `frontend/lib/api/` is never hand-edited.
- [ ] Tests: a published upcoming event, a published **past** event (the case `get_event` deliberately refuses), an `in_review` event, a superseded event with and without a live successor, an unknown slug, an event with no venue, and a request carrying a session cookie proving the response does not vary by it.

## Technical Notes

Read-side shape follows `apps/ingestion/services/catalog_read.py`, which already projects `slug` onto its DTOs at three call sites — the projection pattern exists, the key and the time filter are what change.

`Event.slug` carries `event_slug_uq`, a **global** unique constraint, so the slug alone addresses an event with no city or date segment needed. `mint_slug` (`services/slugs.py`) mints once at creation and does not re-mint on retitle, so these URLs are permanent by construction. **Nothing in this item may introduce a path that rewrites a slug.**

## Dependencies

(none)
