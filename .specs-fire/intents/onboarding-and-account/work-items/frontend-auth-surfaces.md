---
id: frontend-auth-surfaces
title: Frontend Auth Surfaces & Signed-in Home
intent: onboarding-and-account
complexity: medium
mode: confirm
status: pending
depends_on:
  - auth-api-and-session-seam
created: 2026-10-29
---

# Work Item: Frontend Auth Surfaces & Signed-in Home

## Description

Builds the account surfaces from the UX spine and makes routing aware of who is signed in:

- **`/signup`** and **`/signin`** from `signup-desktop.html` and `signin-desktop.html`.
- **`/reset-password`**, covering both the request form and the set-a-new-password form reached from the email link.
- **`/`** becomes the **calm signed-in placeholder home**. In the route map, `/` is the Pulse Digest, which the Pulse Digest intent builds. Until then it shows a quiet "your Pulse is being prepared" state and links to personal and saved events. The existing personal-events section currently on `/` moves into or under it.
- **An anonymous visitor to `/`** goes to `/preview`. A signed-in user who hasn't finished onboarding goes to `/onboarding`.

## Acceptance Criteria

- [ ] `/signup` and `/signin` implement their mockups exactly, using the pre-auth topbar (brand only, topbar-quiet rule, `EXPERIENCE.md`). Footer and section CTAs are as drawn.
- [ ] **Space for OIDC buttons.** The layout includes the equal-weight provider stack's position as drawn, but nothing is wired to it in this intent. The design doc for a later intent wires it up. Do **not** render dead, clickable buttons; render the position in a way the mockup and the intent decision both allow, and record the choice.
- [ ] Error states use the API's calm messages verbatim. Because the API is enumeration-safe, the UI never adds wording that reveals whether an account exists.
- [ ] `/reset-password` covers the request state, the email-sent state ("We've sent a reset link to {email}." per `EXPERIENCE.md`), the set-new-password state from the link token, and the expired or used token state.
- [ ] **Routing:**
  - Anonymous `/` goes to `/preview`.
  - Signed in but not onboarded, `/` goes to `/onboarding`.
  - Signed in and onboarded, `/` shows the placeholder home.
  - A signed-in user visiting `/signin` gets the silent redirect to `/` (`EXPERIENCE.md`: "Returns the user to session if the cookie is still valid").
- [ ] **The placeholder home** is calm and follows the voice and tone rules (PRD §13.2). It has no fake digest cards and no fake data. It reuses the existing personal-events components, and it has sign-out.
- [ ] CSRF tokens are sent on every state-changing call, as `auth-api-and-session-seam` documents.
- [ ] Only the generated client is used; there are no hand-written API types (AD-19).
- [ ] Design tokens and vanilla components only, with no component library ("UI system: None" is binding). WCAG: labelled inputs, visible focus, and errors announced to assistive tech.
- [ ] Vitest tests cover each form's success and error rendering, enumeration-neutral copy, each routing branch, and the expired-token state. `make lint-web` and `make test-web` pass.

## Technical Notes

The route decision for `/` needs the session. Decide whether it happens in the Next proxy or middleware (a cookie-presence check plus `GET /api/auth/me`) or in the page. Keep `/preview` itself free of any session dependency (AD-12). It must render identically for a signed-in visitor.

`app/page.tsx` is currently `force-dynamic` because it shows per-session personal events. Keep that property for `/`.

## Dependencies

- auth-api-and-session-seam
