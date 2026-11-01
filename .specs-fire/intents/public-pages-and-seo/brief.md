---
id: public-pages-and-seo
title: Public Pages, SEO & Share Links
status: in_progress
created: 2026-11-01
---

# Intent: Public Pages, SEO & Share Links

## Goal

Give EventPulse24 a **front door**. Every six intents so far have served people who were already inside — onboarding assumed someone arrived, the digest assumed an account, delivery assumed an address to write to. Nothing in this repository has ever been reachable by a stranger. `frontend/app/` holds ten routes and every one of them sits behind auth, onboarding, or a dev flag.

This intent builds the surface that brings people in: a crawlable public page for every published Event carrying Schema.org `Event` JSON-LD, an "Events in [city]" landing page for every real city, a sitemap, and a share link a user can hand to a friend. It closes **FR-26** (public event pages with structured data), **FR-27** (SEO city pages) and **FR-28** (share-card public link), and it gives `EventFit` its first consumer.

The PRD names the stake plainly (§4.8): *"Growth comes through SEO and shareability. SEO is the cold-start unlock."*

## Users

- **The stranger searching "events in Brooklyn"** (UJ-3), who has never heard of this product. Today there is nothing to find — a grep for `sitemap` across the whole repository returns zero hits.
- **The friend who was sent a link** (UJ-5), who must see the event in full with no account, no modal, and no sign-in wall — and be offered "Save to Pulse" as an invitation rather than a toll.
- **The user who wants to share** (Flow: Pulse Card → share, Detail → share), who has an event on screen and no way to turn it into a URL.
- **Search crawlers**, which need stable URLs, a sitemap, and structured data that agrees with what the page renders — AD-12: *"Schema.org `Event` JSON-LD is emitted from the same data the page renders."*

## Problem

- **No public surface exists at all.** `frontend/app/` has `conflicts`, `dev`, `events`, `onboarding`, `preview`, `reset-password`, `settings`, `signin`, `signup`, `timeline` — and no `sitemap.ts`, no `robots.ts`, and no route that renders without a session. `next.config.ts` is an empty config object.
- **The one event read that exists is wrong for SEO on two counts.** `apps/catalog/api.py:70` is `get_event(request, event_id: UUID)`, and its own description states an event *"that is not public — **or that has already started** — reads as not found."* Reading by UUID cannot serve a slug URL, and 404-ing the instant an event begins discards every bit of search ranking the page earned. The public surface needs its own read: **by slug, and inclusive of past events.**
- **`EventFit`'s read is built but capped for a preview, not a page.** `apps/ingestion/event_fit/reads.py:63` `list_event_fit_for_city` already serves the Pulse Preview and already does the hard parts: it skips a row whose `event_version` no longer matches its Event (AD-10 staleness), filters to `published` and non-`superseded`, orders by score then start time, and matches `city__iexact` on a stripped string. What it does **not** do is page: it is bounded by `MAX_PREVIEW_SIZE` and returns a top-N preview. The city page needs the same rules over an unbounded, paged result — an extension of this read, not a second one.
- **City is free text, so cities fragment — though less than it first appears.** `Venue.city` is `CharField(max_length=100)` with no normalization and `EventFit.city` copies it verbatim, but the existing read matches `city__iexact` on a stripped string, so **case and surrounding whitespace are already one city**. What still fragments is punctuation and region suffixes — "Brooklyn" and "Brooklyn, NY" remain two cities — and there is no canonical display name or URL slug for any of them. FR-27's rule, a page per city with **>5 events**, would be counted over those split buckets and would mint a URL from an unnormalized string.
- **Nothing can tell the frontend a page went stale.** `Event.LIFECYCLE_FIELDS` and the `catalog.guard_event_write` trigger already bump `event_version` on every change to `status`, `is_sold_out`, `venue` or the times — the signal exists and has no listener. A cached page showing "tickets available" for a cancelled show is a trust failure, and trust is this product's whole proposition.

## Success Criteria

### Public event pages (FR-26)

- A session-free page at **`/events/{slug}`** for every `published` Event, statically generated or ISR'd per **AD-12**, rendering fully with no account and setting no session.
- Served by a **new public read keyed on `slug`**, separate from `catalog.get_event`'s UUID+not-yet-started rule. A **past event still resolves** — its page stays up and indexed.
- An Event whose `publication_status` is `in_review` is **never publicly listed and never addressable**, matching the model's own comment ("not digest-eligible, not publicly listed").
- Valid Schema.org `Event` JSON-LD **emitted from the same data the page renders** (AD-12), including the IANA timezone per ARCHITECTURE-SPINE.md line 565, with `eventStatus` and `offers.availability` derived from `Event.status` and `is_sold_out` rather than hardcoded.
- A **"Save to Pulse" CTA** on every public page — a soft wall, never a hard one.
- Because `mint_slug` (`services/slugs.py`) mints once at creation and **never re-mints on retitle**, a public URL is permanent by construction. Nothing in this intent may introduce a path that rewrites a slug.

### City pages (FR-27)

- A **canonical `City`** noun with a stable slug and display name, which Venues resolve to — so "Brooklyn", "brooklyn" and "Brooklyn, NY" are one city with one page. Includes a **backfill** over existing Venue rows.
- A page at **`/events-in-{city-slug}`** for every city with **>5 events**, served by **extending `list_event_fit_for_city`** rather than writing a second read — keeping its staleness skip, its published/non-superseded filters and its score-then-start ordering, and adding paging beyond `MAX_PREVIEW_SIZE`. Rows are **served as stored** (AD-10: never recomputed at render).
- A sparse or empty city **degrades gracefully to "coming soon" copy** rather than 404-ing or rendering an empty grid.
- A **sitemap** covering event and city pages, plus `robots.ts`, so the pages are discoverable rather than merely reachable.

### Share links (FR-28)

- A share control on the Pulse Card and the Detail screen that produces the **FR-26 public URL** — the share link is not a second URL shape, it is the same page.
- Open Graph and Twitter Card metadata per event: **real title and description**, with a **branded static image** for this round.
- The link opens the public page with its "Save to Pulse" CTA, for a recipient with no account.

### Freshness

- Revalidation is **triggered by the existing `event_version` bump**, not by a timer — the lifecycle guard trigger is the signal, and this intent gives it its first listener.
- A cancelled or sold-out event's public page reflects that **without waiting for a cache window to lapse**.

## Constraints

- **AD-12 — the public surface never depends on a session.** Pages render fully without one; any personalized content arrives only via a separate client-side request. Binds all three FRs.
- **AD-19 — the API contract is generated, never hand-written.** The frontend reaches the backend only through the generated client; `frontend/lib/api/` is never hand-edited.
- **AD-10 — Event Fit is served as stored.** Never recomputed at render; a stale row (mismatched `event_version`) is never served.
- **AD-16 — module ownership.** The City model gets exactly one owning module, and no second write path.
- **ASSUMPTION-9** (PRD §4.7) — public event pages are **not user-generated content**; they reflect the registry's source of truth only. No reviews, no UGC, on either page type.
- **PRD §10.4** — 99.9% SEO uptime is the standard these pages are held to.
- **Out of scope by PRD:** per-event Open Graph tuned for SEO (Phase 2), UGC reviews on public pages, user-generated content on city pages, paid placements.

## Notes

### Decisions taken at intent capture

| Decision | Choice | Rationale |
|---|---|---|
| Event URL shape | `/events/{slug}` | Reuses the existing public-facing segment; `Event.slug` is already globally unique (`event_slug_uq`). |
| City URL shape | `/events-in-{city-slug}` | Matches the long-tail query "events in [city]" directly. |
| Route collision | One `app/events/[id]/` route, branching on UUIDv7-vs-slug | Next.js rejects two different dynamic slug names at one level. Branching keeps `/events/{id}` and `/events/{id}/reminders` and every internal link into the detail screen unchanged. |
| Freshness | On-demand revalidation on `event_version` bump | `LIFECYCLE_FIELDS` + `guard_event_write` already emit the signal; a timer would leave a cancelled event showing as scheduled for the length of the window. |
| City identity | A canonical `City` model + venue backfill | Free-text `Venue.city` fragments FR-27's >5-event threshold and yields thin duplicate pages. |
| OG image | Branded **static** image, per-event title/description | Dynamic per-event image generation is a substantial work item with no design to build from; deferred rather than guessed at. |

### Open questions for decomposition and design

- **OQ-A — Where does `City` live?** `Event`, `Venue` and `EventFit` are all in `apps/ingestion/models.py`, but ARCHITECTURE-SPINE.md's Capability Map assigns FR-26–28 to **`catalog`** — and `apps/catalog/models.py` is **0 lines**, the app being read-side only (`api.py`, `preview_api.py`, `services/`). Ownership must be settled under AD-16 in the City work item's design doc, not assumed.
- **OQ-B — FR-28 has no design.** TRACEABILITY.md flags the share affordance as an **inferred-only gap**: `share-link-desktop.html` is tagged `UJ-5` (the recipient's landing), not `FR-28` (the sender's action). The sender-side control needs a design pass inside this intent.
- **OQ-C — How does the backend reach the frontend to revalidate?** This is a new outbound direction — until now the frontend has been a pure client of the API (AD-19). The call path, its shared secret, and its failure behaviour need deciding; a missed revalidation must degrade to stale-but-correct, never to a wrong page.
- **OQ-D — Does the `>5 events` threshold count upcoming events only, or all-time?** Affects whether a city page can wink out of existence after its events pass, which would be an SEO regression.

### Mockups available

- `public-event-page-desktop.html` — self-tagged `FR-26`, contains real `application/ld+json`
- `city-page-desktop.html` — self-tagged `FR-27`, includes the "coming soon" sparse state
- `share-link-desktop.html` — tagged `UJ-5`, covers the **recipient** landing only (see OQ-B)
