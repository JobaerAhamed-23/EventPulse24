---
id: digest-scheduling
title: Composition scheduling from the single tick
intent: pulse-digest-and-trust
complexity: medium
mode: confirm
status: pending
depends_on: [digest-composition-service]
created: 2026-10-30
---

# Work Item: Composition scheduling from the single tick

## Description

Gets the composition job run, from the one 60s beat entry this project has. `config/celery.py` has exactly one `beat_schedule` entry — `tick` — and `backend/tests/worker/test_tick.py` pins it. Everything periodic hangs off that tick as due-time work: `schedule_sources`, `schedule_calendars`, `reconcile_outbox` every 5 minutes, `refresh_event_fits` every 15. Digest composition joins them.

It also covers the **first digest**: FR-1 promises an authenticated Pulse Digest within 30 seconds of sign-up, "rendered from a pre-computed cached composition (city + time-of-day hash); the live personalized composition replaces it on the second digest." A user who finishes onboarding must not land on an empty home waiting for tomorrow's tick.

## Acceptance Criteria

- [ ] **`beat_schedule` still has exactly one entry.** `tests/worker/test_tick.py` passes unchanged, with no new beat entry and no platform cron (AD-7: "the sweep must not be a platform cron").
- [ ] **A claiming dispatcher**, following the shape `schedule_sources` and `schedule_calendars` already use: find users whose digest is due, claim them with `SELECT … FOR UPDATE SKIP LOCKED`, enqueue one composition job per claim, and **release the claim whatever happens** — the run-016 pattern the existing tasks already follow.
- [ ] **Horizontal worker replicas are safe by construction.** Two workers ticking at once must not compose the same user's digest twice; the claim and the `(user_id, local_date)` uniqueness together make the second attempt a no-op. A test exercises the concurrent path rather than assuming the constraint covers it.
- [ ] **Due time respects the user's stored delivery time and timezone.** `DigestPreference` already holds a local wall clock paired with an IANA zone, and its docstring says `delivery` "will read it when it computes the next send time". This item composes *at or before* that local time so the digest exists when the user arrives — **it does not send anything.** The send is the delivery intent's.
- [ ] **The first digest is composed immediately on onboarding completion**, so the signed-in home is never empty for a new user. The job is enqueued from the existing onboarding-completion path, not polled for.
- [ ] **The job is idempotent.** Re-running it for a user whose digest already exists for that local date is a no-op, which falls out of the composition service's determinism rather than being re-implemented here.
- [ ] **A failed composition does not wedge the user.** A claim that errors is released, the failure is logged with its job name and no PII (AD-13), and the next tick retries. A permanently failing user does not block any other user's digest.
- [ ] **A management command composes on demand** for one user or a backfill set, idempotent, for operating and for local development.
- [ ] **Nothing long happens in a request** (AD-11). A test asserts no request handler calls the composition service directly.
- [ ] Tests cover: the tick enqueueing the dispatcher without changing the pinned beat schedule; the claim/release cycle including the error path; two concurrent dispatchers producing one digest; the due-time computation across a DST transition; the first-digest enqueue on onboarding completion; and the management command's idempotency.

## Technical Notes

**Cadence is a real decision, not a copy of the Event Fit refresh.** `refresh_event_fits` runs every 15 minutes over all published events because "tonight" goes stale. Digest composition is once per user per local day at a user-chosen time — a completely different shape. Reusing the minute-modulo trick would compose everyone at the same moment, which is the opposite of what the per-user delivery time means. The design should state the dispatcher's selection rule and what "due" means precisely.

**FR-1's "city + time-of-day hash" cached composition is a different thing from this.** It describes a *pre-computed, shared* composition used for first paint — closer to the Pulse Preview's city cache than to a per-user digest. The brief keeps the 30-second promise's delivery half out of scope; what this item owes is only that a new user's own digest exists quickly. If the design wants the shared-cache approach, it must say how a shared composition becomes a per-user `DIGEST_COMPOSITION` without violating AD-10's "persisted per user" rule — and the simpler answer, composing their real digest on the spot, is probably right at MVP scale.

The tick's docstring documents its own nesting carefully ("the two cadences nest — every multiple of 15 is also a multiple of 5 … if the two are ever made independent, the tick test that pins the enqueue order will say so"). Whatever this item adds to the tick, extend that docstring in the same spirit.

## Dependencies

- digest-composition-service
