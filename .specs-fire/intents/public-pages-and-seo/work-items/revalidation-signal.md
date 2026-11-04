---
id: revalidation-signal
title: The page goes stale the moment the event changes — the revalidation signal
intent: public-pages-and-seo
complexity: high
mode: validate
status: completed
depends_on:
  - public-event-read-by-slug
created: 2026-11-01
run_id: run-eventpulse24-024
completed_at: 2026-11-02T10:30:01.208Z
---

# Work Item: The page goes stale the moment the event changes — the revalidation signal

## Description

A cached public page showing "tickets available" for a cancelled show is not a cosmetic bug — it is the product's one promise failing in public, on the surface strangers judge it by first.

The signal already exists and has no listener. `Event.LIFECYCLE_FIELDS` names `start_time_utc`, `end_time_utc`, `start_time_tz`, `status`, `is_sold_out`, `venue` and `superseded_by`, and the `catalog.guard_event_write` trigger **requires `event_version + 1` on every change to any of them**. Every fact a public page states is in that list. This item connects that bump to a rebuild of the one page it affects.

**This item needs a design doc (Checkpoint 1) before any code.** It opens a new direction of call between the two deploys and that is an architectural decision, not an implementation detail.

## Acceptance Criteria

- [x] A change to any `LIFECYCLE_FIELD` on a published Event causes **that event's public page** to be rebuilt — not the whole site, and not on a timer.
- [x] A change to a **city's** membership (an event published, superseded, or moved between cities) revalidates the affected city page(s).
- [x] **Failure degrades to stale-but-correct, never to wrong.** A revalidation that cannot be delivered is retried and surfaced; it never leaves the system believing a page is fresh when it is not, and it never takes a page down.
- [x] The signal is **authenticated** — the rebuild endpoint is not an open door that any caller can use to force work on the frontend deploy.
- [x] The signal is **idempotent and safe to repeat**: the same bump delivered twice rebuilds once more, harmlessly.
- [x] Revalidation is triggered **after the transaction commits**, never inside it — a rebuild fired from an uncommitted write can read the old row back and re-cache exactly the stale page it was meant to fix.
- [x] An `in_review` or newly-`superseded` event **removes or 404s its page** rather than leaving a live page for content that is no longer public.
- [x] Tests: a status change to cancelled, a sold-out flip, a venue change, a time change, a publish and an unpublish, a delivery failure and its retry, a double delivery, and a test proving the trigger fires post-commit.

## Technical Notes

**Design-doc decisions (Checkpoint 1):**

- **OQ-C — how the backend reaches the frontend.** Until now AD-19 has made this strictly one-directional: *"the Next.js frontend is a client — it holds no domain logic and reaches the backend only through the generated API client."* Nothing has ever called the other way. The design must state what this new edge is, how it is secured, and why it does not erode AD-19's boundary.
- **Who fires it — API runtime or worker.** Lifecycle changes arrive from both: user-facing writes on the API runtime, and the ingest pipeline and state polling on the worker. One signal path must serve both, or the design must say why two is right.
- **What happens when the frontend deploy is unreachable.** A queue, a retry policy, and a bound — plus whether a time-based ISR floor is worth keeping purely as a backstop, given the user chose on-demand over a timer precisely to avoid a stale window.

`worker/tasks.py` runs a 60s tick with an established `_enqueue` pattern; `propagate_state_change` already fans out on lifecycle changes and is the natural attachment point to examine first.

## Dependencies

- public-event-read-by-slug
