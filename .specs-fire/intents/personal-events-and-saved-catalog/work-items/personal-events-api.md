---
id: personal-events-api
title: Personal Events API
intent: personal-events-and-saved-catalog
complexity: medium
mode: confirm
status: in_progress
depends_on:
  - personalization-write-services
created: 2026-10-29
---

# Work Item: Personal Events API

## Description

Exposes the personal event commands over HTTP: create, edit, delete and list the signed-in user's own personal events.

These endpoints are **session-based and user-scoped**. Unlike the public catalog, they are not session-free (AD-12 applies to the *public* surface only), and every request resolves exactly one user. No endpoint may read or write another user's records.

The contract is generated, never hand-written (AD-19): the wire shapes live in `apps/personalization/schemas.py` as Pydantic schemas, and the frontend's TypeScript client is generated from the OpenAPI schema in CI.

The interesting part of this endpoint is the conflict response. A create that detects a conflict does not complete — it returns a payload describing the conflict and the three actions, and the client must send back one of them. That round trip is the whole of FR-58's forced-choice contract at the HTTP level.

## Acceptance Criteria

- [ ] Wire schemas live in `apps/personalization/schemas.py` as Pydantic schemas, following `apps/catalog/schemas.py`'s conventions. No ad-hoc dicts in responses.
- [ ] Times cross the wire as **UTC plus an explicit IANA timezone** — the same shape `EventOut` uses (`start_time_utc` + `start_time_tz`). Display conversion is the frontend's job (AD-6).
- [ ] `POST /api/personal/events` creates a personal event. Required fields: name, start time, and the explicit IANA timezone. Optional: end time, location, notes.
- [ ] A create **without** an explicit IANA timezone is refused with the standard `{code, message, details?}` shape — a 4xx through the single error handler in `config/errors.py`, never a 500.
- [ ] `POST /api/personal/events` returns **409** (or the project's chosen conflict code) with the conflict payload when a conflict is detected. The event is **not** created in that case, or is created in a state that requires the resolution — either way, the response carries the conflicting event(s) and the three available actions.
- [ ] The conflict payload names exactly the three actions — `keep_both`, `edit_new`/`update_existing`, `delete_new` — and exposes no dismiss option. The schema makes a `dismiss` value impossible to express.
- [ ] `PATCH /api/personal/events/{id}` edits an event and re-runs conflict detection. A conflicting edit returns the same conflict payload.
- [ ] `DELETE /api/personal/events/{id}` deletes an event.
- [ ] `GET /api/personal/events` lists the signed-in user's personal events, and `GET /api/personal/events/{id}` returns one.
- [ ] Every endpoint is scoped to the authenticated user. A user cannot read, edit or delete another user's personal event — an attempt returns 404, not 403, so the endpoint does not confirm the record exists.
- [ ] Every endpoint is **authenticated**. An unauthenticated request returns 401.
- [ ] The router is registered in `config/api.py` under a `/personal` prefix, and the OpenAPI schema regenerates cleanly (`make client`).
- [ ] The generated TypeScript client in `frontend/lib/api/` is regenerated from the committed `openapi.json`. It is **never** hand-edited (AD-19).
- [ ] The `models-personalization` and `models-ingestion` import contracts keep passing: the API module must not import `apps.personalization.models` directly, and must not import `apps.ingestion.models`. The API calls the published services.
- [ ] Tests cover: create succeeds with a valid timezone; create refused without one; create returning the conflict payload and creating nothing; each of the three resolutions completing the flow; edit re-running detection; delete; list scoping to the user; and a cross-user access attempt returning 404.
- [ ] No endpoint returns a raw source payload or an unstripped internal field (AD-9 discipline applied to personal data).

## Technical Notes

`apps/catalog/api.py` is the reference for the router shape. Note how it keeps the wire shapes and the query separate:

```python
from apps.catalog.schemas import EventListOut, EventOut, EventPage
from apps.ingestion.services.catalog_read import get_public_event, list_public_events

router = Router(tags=["catalog"])
```

The catalog router is registered in `config/api.py` with a comment explaining *why* it is session-free. The personal router gets the opposite comment: it is session-based by design.

**Authentication.** The project has no auth implementation yet — `apps/identity/models.py` has only the `User` model extending `AbstractUser`, and `apps/identity/api.py` is an empty router. FR-1–FR-4 (onboarding and account) are a later intent. So this work item needs a **minimal** way to identify the requesting user.

Keep it minimal and honest: a session or token mechanism sufficient for these endpoints, clearly marked as the seam the later onboarding intent will replace. Do not build the full 30-second onboarding flow, calendar connect, or the account surface here. The critical property is that the user id is resolved from the request and is **never** taken from the request body — a user-supplied user id in a payload is the classic way this goes wrong.

If the identity app cannot yet authenticate, an explicit, clearly-labelled interim mechanism is acceptable **provided** the tests prove the scoping property holds. The scoping test (one user's events are invisible to another) is the real deliverable; the auth mechanism is replaceable.

**Error codes.** `config/errors.py` installs the single handler. Domain errors in `domain/errors.py` map to HTTP there. Add the new error types there rather than raising ad-hoc exceptions from the API layer, so the `{code, message, details?}` shape stays in one place and the messages follow the calm UX voice ("We couldn't find that event." style, no exclamation marks).

**AD-19.** `openapi.json` is committed and the frontend client is generated from it by `make client`. Regenerate it in this work item and commit the result, so the frontend work item builds against a current client.

## Dependencies

- personalization-write-services
