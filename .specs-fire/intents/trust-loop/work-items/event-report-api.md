---
id: event-report-api
title: A user can say "this is wrong" — EventReport and its endpoint
intent: trust-loop
complexity: medium
mode: confirm
status: completed
depends_on:
  - review-queue-model
created: 2026-11-10
run_id: run-eventpulse24-026
completed_at: 2026-11-10T17:10:12.757Z
---

# Work Item: A user can say "this is wrong" — EventReport and its endpoint

## Description

FR-59 (Amendment A-4) gives the signed-in user a one-tap report with four categories. `apps/personalization/__init__.py:4` lists `EventReport` as owned, and the Spine puts it in `personal` "because it is attributable to a user". The `REVIEW_ITEM` it raises lives in `catalog` "and carries no user identity across the wall (AD-3)".

## Acceptance Criteria

- [ ] `EventReport` lives in `personal`: user, event id (no FK across the wall, per AD-3), category, and created timestamp. The category is exactly one of `wrong_date_time`, `wrong_venue`, `does_not_exist`, `duplicate`. There is **no free-text field**. A retention category is declared (AD-15).
- [ ] `POST` to a report endpoint on the personalization router. It is session-scoped and CSRF-protected like the other writes. It takes `{event_id, category}`, and the response gives the client what it needs for the toast and nothing more.
- [ ] **Rate limit: 5 per user per day**, declared through the throttle port (the Spine's rate-limiting row), not hand-rolled. The sixth report answers with a distinct, documented error the UI can render calmly.
- [ ] The plan defines what a repeat report from the same user on the same event does: a no-op, an update or a second row. It must not let one user inflate the `ReviewItem` count, and a test pins it.
- [ ] Each accepted report calls `ingestion`'s published `raise_review_item(event, reason=user_reported, category=…)`. This raises a new item or bumps the open one. It passes the event id and category, never the user.
- [ ] **The event's visibility never changes on a report.** A test proves a reported event is still in the digest candidates and the public read.
- [ ] A report on an unknown event, or on one that isn't publicly visible, is refused the way the existing Detail read refuses it (not found), so the endpoint can't be used to probe hidden events.
- [ ] The report also exists as an observation candidate for FR-16. Whether it counts depends on the editor's later verdict ("upheld"), which `reliability-recompute-and-escalation` defines. This item stores the facts that definition will need.
- [ ] OpenAPI is regenerated and `frontend/lib/api/schema.ts` is rebuilt in the same change (AD-19).
- [ ] Contract tests cover the shape, each category, an invalid category, the rate limit, a signed-out request, an unknown or hidden event, and the AD-3 property (no user identity in the `ReviewItem` row).

## Technical Notes

`apps/catalog/preview_api.py:59` shows the existing use of `get_throttle_port`. The cross-wall call follows how `personalization` already calls into `ingestion` published services (`catalog_read`). The two writes happen in different databases (`personal` and `catalog`), so the plan must state the ordering and what happens if the second write fails. The precedent is the AD-17 outbox, and the plan should say whether a report needs one.

## Dependencies

- review-queue-model
