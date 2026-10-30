---
id: auth-api-and-session-seam
title: Auth API & Session Seam Replacement
intent: onboarding-and-account
complexity: medium
mode: confirm
status: completed
depends_on:
  - account-auth-core
created: 2026-10-29
run_id: run-eventpulse24-020
completed_at: 2026-10-29T15:19:57.280Z
---

# Work Item: Auth API & Session Seam Replacement

## Description

Puts the HTTP surface over `account-auth-core` and makes the session real everywhere.

There are two halves:

1. **`/api/auth/*` endpoints:** sign-up, sign-in, sign-out, the current user (`me`), password-reset request and password-reset confirm.
2. **Replace the seam.** `apps/personalization/auth.py` holds the deliberate one-function `current_user` seam. Its docstring says "the onboarding intent replaces it in one place". This item does that. `identity` publishes the authenticated-actor resolver, and every authed router uses it. The personal-event and saved-event endpoints built last intent then work for a real signed-in user without changing a single endpoint.

## Acceptance Criteria

- [ ] `POST /api/auth/signup`, `POST /api/auth/signin`, `POST /api/auth/signout`, `GET /api/auth/me`, `POST /api/auth/password-reset` and `POST /api/auth/password-reset/confirm` exist, registered in `config/api.py`.
- [ ] Sign-up and sign-in establish a session. The session cookie is first-party, because the browser only calls `/api/*` on the site's own origin through `frontend/proxy.ts`.
- [ ] `GET /api/auth/me` returns the signed-in user's id, email and onboarding status, or 401 when anonymous. It never returns the password hash or other internal fields.
- [ ] **Enumeration safety holds at the HTTP edge.** For sign-up, sign-in and reset-request, an unknown email and a known email produce **byte-identical response bodies and the same status code**. The tests compare the full response.
- [ ] Throttled requests return 429 with the project's error shape (`config/errors.py`).
- [ ] CSRF is enforced on every state-changing endpoint, and the frontend has a documented way to obtain and send the token.
- [ ] **The seam is replaced in one place.** `identity` publishes the resolver, and `apps/personalization/auth.py` either delegates to it or is removed with its call sites updated. Nothing else in `personalization` changes.
- [ ] **The existing personal endpoints work with a real session.** Tests sign in through the real endpoint and then exercise `/api/personal/*` and the save endpoints. An anonymous request still gets 401 with "Please sign in to continue."
- [ ] Services still receive an explicit actor, never `request` (spine: Auth row).
- [ ] The OpenAPI schema regenerates and the TypeScript client is regenerated with `make client`, never hand-edited (AD-19).
- [ ] The import contracts pass: `personalization` reaches `identity` through its published interface, never through `apps.identity.models`.
- [ ] Tests cover each endpoint's success and failure paths, byte-identical enumeration responses, CSRF refusal, 429, sign-out ending the session, and a 7-day-old session being expired using a fixed clock.

## Technical Notes

Look at how `apps/personalization/api.py` uses `Router(auth=current_user)` and `request.user.pk`. The replacement should keep that shape, so the diff to existing routers is at most an import change.

Django Ninja's `django_auth` plus Django's CSRF middleware is the conventional path. Check what Ninja does with CSRF for session auth in the installed version before relying on it.

Onboarding status in `me` is read through `personalization`'s published interface once `onboarding-state-and-interests` exists. Until then, `me` can omit it. Do not make this item depend on that one; add the field in that item.

## Dependencies

- account-auth-core
