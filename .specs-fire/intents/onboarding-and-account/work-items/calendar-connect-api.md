---
id: calendar-connect-api
title: Calendar Connect API
intent: onboarding-and-account
complexity: medium
mode: confirm
status: in_progress
depends_on:
  - auth-api-and-session-seam
  - calendar-sync-and-polling
created: 2026-10-29
---

# Work Item: Calendar Connect API

## Description

The HTTP surface over the calendar commands. It is what onboarding step 1 (and, later, Settings → Sources) uses to connect Google, Apple or Outlook by pasting a secret ICS/webcal address. It also lets the user see each connection's status, reconnect a revoked one, and disconnect.

## Acceptance Criteria

- [ ] `GET /api/personal/calendars` lists the user's connections: id, provider, status, last synced time, and a sync-in-progress flag. It **never** includes the address, in full, masked or as a fragment. A test asserts that no response body from any endpoint in this router contains the URL.
- [ ] `POST /api/personal/calendars` connects a provider from `{provider, address}`. It returns the new connection with status and sync state, and the first sync is enqueued, not run inline.
- [ ] **The Free cap.** A second connection attempt returns a calm, typed error whose message follows the UX copy for the in-app upgrade prompt, with no modal semantics in the payload. A test pins the status and code.
- [ ] Invalid addresses get a calm, specific message. These include a bad scheme, an address the SSRF policy refuses, and an address already connected. The message never echoes the address back.
- [ ] `POST /api/personal/calendars/{id}/reconnect` takes a new address for a `needs_reconnect` connection.
- [ ] `DELETE /api/personal/calendars/{id}` disconnects and purges that connection's events.
- [ ] `GET /api/personal/calendars/{id}` (or the list endpoint) exposes the **sync status** so onboarding step 1 can show imported events "without leaving the onboarding flow" (FR-3).
- [ ] All endpoints are authed and scoped to the user. Another user's connection id returns 404, not 403.
- [ ] Request bodies with the address are excluded from any request logging or error reporting. A test proves it with log capture on a failing request.
- [ ] Router registered in `config/api.py`, and client regenerated (`make client`, AD-19).
- [ ] `make lint-imports` passes. The API calls `personalization` services only.
- [ ] Tests cover list, connect, the cap, each invalid-address refusal, reconnect, disconnect, cross-user 404, and that no response or log contains the address.

## Technical Notes

The provider value doesn't change any server behaviour; it only affects UI guidance and the Source Badge's provider tag (FR-3's provider parity contract). Keep provider-specific logic out of the services.

The upgrade copy is in `EXPERIENCE.md` / `DESIGN.md` (look for the calendar-cap and upgrade patterns). Take the wording from there; don't write it fresh.

## Dependencies

- auth-api-and-session-seam
- calendar-sync-and-polling
