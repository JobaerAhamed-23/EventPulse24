---
id: frontend-public-event-page
title: The front door — the public event page, open to a stranger
intent: public-pages-and-seo
complexity: medium
mode: confirm
status: completed
depends_on:
  - public-event-read-by-slug
  - schema-org-jsonld
created: 2026-11-01
run_id: run-eventpulse24-024
completed_at: 2026-11-02T13:52:50.944Z
---

# Work Item: The front door — the public event page, open to a stranger

## Description

The first route in this codebase that renders for someone with no account. `frontend/app/` has ten routes today and every one sits behind auth, onboarding, or a dev flag.

The page lives at **`/events/{slug}`**, which collides with the existing `/events/[id]` detail screen — Next.js rejects two different dynamic slug names at one level. Rather than move the authed route and rewrite every internal link into it (digest home, timeline, conflicts and the detail conflict prompt all link there), **one route branches on its parameter**: a UUIDv7 is the signed-in detail screen, anything else is a slug and renders the public page.

## Acceptance Criteria

- [x] `app/events/[id]/page.tsx` branches on the parameter: **UUIDv7 → authed detail, otherwise → public page**. The discriminator is a shared, tested predicate, not an inline regex.
- [x] `/events/{id}` and `/events/{id}/reminders` behave **exactly as before**, and every existing link into the detail screen still resolves. Existing tests for those routes pass unchanged.
- [x] The public branch **renders fully with no session** (AD-12) — no redirect, no sign-in wall, no auth check on the render path — and is statically generated or ISR'd.
- [x] The JSON-LD from `schema-org-jsonld` is embedded **verbatim**, not rebuilt on the client. The page and the structured data state the same facts because they come from the same payload.
- [x] A **"Save to Pulse" CTA** — a soft wall. A visitor reads the whole event first; the CTA invites an account, it does not gate the content.
- [x] `generateMetadata` emits **Open Graph and Twitter Card** tags with the real per-event title and description, plus a **branded static image** (FR-28's image, held static this round by decision).
- [x] A **canonical link tag**, so the public URL is the one indexed and the share link never reads as duplicate content.
- [x] An unknown slug renders a proper **404** with the right status code, not a soft 404 page returning 200 — a soft 404 poisons an index.
- [x] A **past event renders normally**, consistent with `public-event-read-by-slug` keeping it addressable.
- [x] Theming and tokens follow `public-event-page-desktop.html`; the page works at phone width.
- [x] Tests: the UUID branch, the slug branch, an unknown slug's status code, a render with no cookies present, the JSON-LD appearing in the server-rendered HTML (not injected client-side), metadata output, and the existing detail-route tests still green.

## Notes on how the criteria were met

**The caching criterion was met one level down, and the reason is forced.** The
criterion says "statically generated or ISR'd"; the segment is **`force-dynamic`**, and
the public page's *facts* are cached in the data cache (`unstable_cache`, tagged with
the event's own path). Two constraints make the literal reading impossible:

1. **One route serves two surfaces.** The segment also serves the personal Detail
   Screen, which reads cookies. A prerendered segment cannot run `cookies()`, and a
   dynamic segment's page is never in the Full Route Cache. **A segment has exactly
   one rendering mode**, so the page cannot be static while the detail screen is
   dynamic.
2. **The prerendered version 500s.** With `generateStaticParams` returning `[]`, the
   route is registered as prerenderable, and Next throws *"Page changed from static to
   dynamic at runtime"* for **both** branches — measured against a running production
   server, not inferred.

What the criteria actually require — *"renders fully with no session, no redirect, no
sign-in wall, and no auth check on the render path"* — **is** met and was measured: a
cookie-free request answers 200, renders the whole page, and sets no cookie. And the
page's facts **are** cached: four requests to a live slug cost **one** API call, while
a not-found is **never** cached and is re-read every time.

**The segment's `loading.tsx` was deleted, deliberately.** A segment-level
`loading.tsx` is a Suspense boundary *above* the page, so the response streams before
`notFound()` can set the status — which turned the unknown slug into a **soft 404**
(a 200). The Detail Screen's skeleton moved *inside* the page as a `<Suspense>` around
only the detail branch, so the public branch is never inside a pending subtree. This
was measured: with the `loading.tsx`, 200; without it, 404.

**A superseded event answers 308, not 404.** The backend carries the successor's slug
in the 404's `details` so the link a crawler already holds resolves forward. The page
redirects to it (308, because the old URL is permanently wrong) and 404s otherwise.

## Technical Notes

The JSON-LD must be in the **server-rendered** HTML. A crawler that does not execute JavaScript sees nothing otherwise, which defeats the entire FR.

`frontend/next.config.ts` is currently an empty config object — any image or revalidation configuration this needs starts there.

Use the generated client only (AD-19); do not hand-write a fetch against the public endpoint.

## Dependencies

- public-event-read-by-slug
- schema-org-jsonld
