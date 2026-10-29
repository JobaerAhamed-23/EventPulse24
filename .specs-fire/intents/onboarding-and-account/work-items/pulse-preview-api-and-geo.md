---
id: pulse-preview-api-and-geo
title: Pulse Preview API & Geo Port
intent: onboarding-and-account
complexity: medium
mode: confirm
status: pending
depends_on:
  - event-fit
created: 2026-10-29
---

# Work Item: Pulse Preview API & Geo Port

## Description

The backend for `/preview` (FR-2):

- **A geo port** that turns the hosting edge's geo header into a city, with a fake for local and CI.
- **A list of supported cities** drawn from what the catalog actually covers.
- **An anonymous, cacheable endpoint** that returns three Pulse Cards for a city from persisted Event Fit.

AD-12: "Public event pages render fully without a session … Personalized content on a public page arrives only via a separate client-side request." The preview endpoint reads **no session and no `personal` data**.

## Acceptance Criteria

- [ ] **The geo port** (`ports/geo.py`, or a similar name chosen in the plan) maps a request's edge geo header, such as Vercel's `x-vercel-ip-city`, to a city name or nothing.
  - A fake adapter is the local and CI default, configurable to return a chosen city.
  - The real adapter only reads a header. It does no database lookup and calls no vendor.
  - The decoded header is treated as untrusted input: length-bounded and URL-decoded once.
- [ ] **Supported cities** are the cities with at least one upcoming public event that has Event Fit. A geo city outside that set falls back to **NYC** (FR-2: "falls back to the most-popular city (NYC at MVP)"). NYC is a named constant.
- [ ] `GET /api/public/preview?city=<city>` returns up to 3 cards. Each card has its title, venue, local start time with timezone, Event Fit score and tags, and Source Badge inputs, if the read interface provides them. It also returns the resolved city and whether it came from geo, the query or the fallback.
  - With no `city` parameter, it uses the geo port.
  - An explicit `city` overrides geo (the "Change" action).
  - An unsupported explicit city returns an empty preview with the resolved city, so the frontend shows "No preview available in {city} yet." (`EXPERIENCE.md` `/preview` empty state). It never returns another city's events under that name.
- [ ] `GET /api/public/preview/cities` lists the supported cities for the one-tap city picker.
- [ ] **No session.** A test calls both endpoints with a signed-in session and without one, and gets **identical** responses. The endpoint doesn't touch `request.user` or `personal`.
- [ ] **Cacheable.** The response sets cache headers suited to a public, per-city response, and varies on the city input and nothing session-related.
- [ ] **Rate-limited per IP** (PRD §11.2).
- [ ] The "Don't use my location" choice is honoured. The frontend sends an explicit opt-out, and the endpoint then ignores geo and uses the fallback. A test proves geo isn't consulted.
- [ ] Router registered, and client regenerated (AD-19). `make lint-imports` passes. The endpoint reads `catalog` only through `ingestion`'s published read interface.
- [ ] Tests cover the geo hit, the geo miss falling back to NYC, an explicit override, an unsupported city returning empty, opt-out skipping geo, identical responses with and without a session, the per-IP limit, and fewer than 3 events.

## Technical Notes

**Where the header is read.** The browser calls Next.js, and `frontend/proxy.ts` rewrites `/api/*` to Django. Check whether the platform's geo header survives that rewrite. If it doesn't, the Next side reads it and forwards it as a parameter. Either way, Django sees only the port's input, and the code doesn't depend on the host (AD-1).

Geo-IP is a privacy-relevant choice (PRD §10.2, FR-2's consent banner). Never store the resolved city server-side for an anonymous visitor, and never log it with the IP.

## Dependencies

- event-fit
