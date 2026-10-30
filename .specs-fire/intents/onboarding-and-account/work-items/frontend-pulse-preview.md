---
id: frontend-pulse-preview
title: Frontend Pulse Preview
intent: onboarding-and-account
complexity: medium
mode: confirm
status: in_progress
depends_on:
  - pulse-preview-api-and-geo
  - frontend-auth-surfaces
created: 2026-10-29
---

# Work Item: Frontend Pulse Preview

## Description

Builds `/preview` from `pulse-preview-desktop.html`. It is the anonymous gateway: three Pulse Cards in the visitor's city, with Event Fit's tags and 1–5 indicator shown inline, a geo-IP consent banner, a one-tap city change, and a soft wall that asks for sign-up at the 3rd save (FR-2).

## Acceptance Criteria

- [ ] `/preview` implements its mockup exactly. It uses the pre-auth topbar (brand only), and sign-in and sign-up live in the footer and hero CTAs.
- [ ] **No session dependency (AD-12).** The page renders identically for an anonymous and a signed-in visitor, and is statically generated or ISR'd per city where the platform allows. Any per-viewer behaviour, such as the banner's remembered choice, is client-side only.
- [ ] Each card shows its title, venue, local start time with timezone label, Event Fit tags (13px italic micro-tags, per `DESIGN.md`) and the 1–5 indicator **labelled as Event Fit's meaning**, plus Source Badge if provided. There is no Relevance Pulse wording, because nothing on this page is personal (AD-10).
- [ ] **Consent banner (FR-2):** "Showing events near [city]. Use a different city? [Change] [Use this] [Don't use my location]."
  - The choice persists in a cookie for the session.
  - "Don't use my location" sends the opt-out, so the preview falls back to NYC, and the banner doesn't reappear that session.
  - "Change" opens the one-tap city picker from `/api/public/preview/cities`.
- [ ] **Soft wall:** "Save to Pulse" on the 1st and 2nd cards records the intent client-side, and the 3rd tap requires sign-up and routes to `/signup` (FR-2: "soft-walls at the 3rd card"). The design doc or plan states whether earlier pre-signup saves are carried into the account after sign-up. If they aren't, say so plainly.
- [ ] **States** (`EXPERIENCE.md` `/preview` row):
  - Loading shows 3 card skeletons.
  - Empty shows "No preview available in {city} yet."
  - Error shows "Couldn't load the preview. Refresh."
- [ ] Generated client only, tokens and vanilla components only. The hand-rolled tooltip pattern from `DESIGN.md` is used for any tag explanation.
- [ ] Accessibility: the banner is a labelled region with keyboard-reachable actions, the 1–5 indicator has a text alternative, and nothing relies on colour alone.
- [ ] Vitest tests cover rendering from fixtures, each banner action and its cookie, the opt-out request, the city change, the soft wall on the 3rd save, and the three states. `make lint-web` and `make test-web` pass.

## Technical Notes

The Pulse Card's full rendering belongs to the Pulse Digest intent. Build the preview card as the smallest component the mockup needs, named so the digest intent can extend it rather than fork it. Coordinate with any card-like component the last intent left in `frontend/components/`.

## Dependencies

- pulse-preview-api-and-geo
- frontend-auth-surfaces
