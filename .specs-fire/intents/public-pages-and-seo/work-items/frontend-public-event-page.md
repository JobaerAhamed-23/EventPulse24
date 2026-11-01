---
id: frontend-public-event-page
title: The front door — the public event page, open to a stranger
intent: public-pages-and-seo
complexity: medium
mode: confirm
status: pending
depends_on:
  - public-event-read-by-slug
  - schema-org-jsonld
created: 2026-11-01
---

# Work Item: The front door — the public event page, open to a stranger

## Description

The first route in this codebase that renders for someone with no account. `frontend/app/` has ten routes today and every one sits behind auth, onboarding, or a dev flag.

The page lives at **`/events/{slug}`**, which collides with the existing `/events/[id]` detail screen — Next.js rejects two different dynamic slug names at one level. Rather than move the authed route and rewrite every internal link into it (digest home, timeline, conflicts and the detail conflict prompt all link there), **one route branches on its parameter**: a UUIDv7 is the signed-in detail screen, anything else is a slug and renders the public page.

## Acceptance Criteria

- [ ] `app/events/[id]/page.tsx` branches on the parameter: **UUIDv7 → authed detail, otherwise → public page**. The discriminator is a shared, tested predicate, not an inline regex.
- [ ] `/events/{id}` and `/events/{id}/reminders` behave **exactly as before**, and every existing link into the detail screen still resolves. Existing tests for those routes pass unchanged.
- [ ] The public branch **renders fully with no session** (AD-12) — no redirect, no sign-in wall, no auth check on the render path — and is statically generated or ISR'd.
- [ ] The JSON-LD from `schema-org-jsonld` is embedded **verbatim**, not rebuilt on the client. The page and the structured data state the same facts because they come from the same payload.
- [ ] A **"Save to Pulse" CTA** — a soft wall. A visitor reads the whole event first; the CTA invites an account, it does not gate the content.
- [ ] `generateMetadata` emits **Open Graph and Twitter Card** tags with the real per-event title and description, plus a **branded static image** (FR-28's image, held static this round by decision).
- [ ] A **canonical link tag**, so the public URL is the one indexed and the share link never reads as duplicate content.
- [ ] An unknown slug renders a proper **404** with the right status code, not a soft 404 page returning 200 — a soft 404 poisons an index.
- [ ] A **past event renders normally**, consistent with `public-event-read-by-slug` keeping it addressable.
- [ ] Theming and tokens follow `public-event-page-desktop.html`; the page works at phone width.
- [ ] Tests: the UUID branch, the slug branch, an unknown slug's status code, a render with no cookies present, the JSON-LD appearing in the server-rendered HTML (not injected client-side), metadata output, and the existing detail-route tests still green.

## Technical Notes

The JSON-LD must be in the **server-rendered** HTML. A crawler that does not execute JavaScript sees nothing otherwise, which defeats the entire FR.

`frontend/next.config.ts` is currently an empty config object — any image or revalidation configuration this needs starts there.

Use the generated client only (AD-19); do not hand-write a fetch against the public endpoint.

## Dependencies

- public-event-read-by-slug
- schema-org-jsonld
