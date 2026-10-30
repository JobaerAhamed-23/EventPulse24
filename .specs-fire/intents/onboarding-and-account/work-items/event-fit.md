---
id: event-fit
title: Event Fit (session-free score and tags)
intent: onboarding-and-account
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-10-29
run_id: run-eventpulse24-020
completed_at: 2026-10-30T01:38:21.917Z
---

# Work Item: Event Fit (session-free score and tags)

## Description

Builds **Event Fit**, the session-free half of AD-10. It is a non-personalized 1–5 score plus generic Why-this tags per `(event, city)`. It is computed when an event is ingested or refreshed, persisted on the catalog side, and owned by `ingestion` (AD-16's table lists `EVENT_FIT` under `ingestion`).

Pulse Preview needs it because AD-12 forbids the public surface from depending on a session, and AD-10 forbids it from borrowing a personal explanation. Event Fit is the only indicator a visitor without an account is allowed to see.

The intent decided the rules are **deterministic, with no LLM**, and use only **inputs that already exist on an Event**: start-time proximity and extraction confidence. There is no price field and FR-16 source reliability isn't built, so "Free" tags and reliability weighting wait until those exist.

## Acceptance Criteria

- [ ] A **pure function** in `domain/event_fit.py` (stdlib only, AD-2) takes the event's start, end, timezone, extraction confidence, city, and the "now" reference. It returns a score (an integer 1–5) and an ordered tuple of tag keys. The thresholds and weights are named constants in `shared/constants.py`.
- [ ] **Tags are generic, time- and place-based,** for example "Tonight", "Tomorrow", "This weekend" and "In <city>". The day boundaries are computed **in the event's own IANA timezone**, not UTC: an event at 23:30 local on Friday is "Tonight" on Friday, not on Saturday. A test pins a DST transition and a date-line case.
- [ ] **The score is deterministic.** The same inputs always give the same output, there is no randomness, and nothing is computed at render time. `domain/` coverage stays at 100%.
- [ ] An `EventFit` model on the catalog side is keyed by `(event, city)`, with score, tags, `computed_at` and the input `event_version`. It has an AD-15 retention category and is written **only by `ingestion`**.
- [ ] Event Fit is **recomputed when the event is created or changes** (new `event_version`), inside the existing ingest path and transaction discipline. A stale row (an `event_version` that doesn't match) is never served.
- [ ] Time-relative tags like "Tonight" go stale as time passes, not only when the event changes. The design in the plan states how this is handled, for example a periodic refresh due from the existing tick, or tags stored as absolute date anchors and rendered relative at read. AD-10 says never *computed* at render, so state why the choice complies.
- [ ] A management command **backfills** Event Fit for existing published events and is idempotent.
- [ ] **A published read in `ingestion`'s catalog read interface** returns the top N (default 3) upcoming public events for a city, ordered by Event Fit score and then by start time, with their persisted score and tags. It never reads `personal`.
- [ ] Event Fit never feeds an authenticated surface as a Relevance Pulse substitute (AD-10 "never cross them"). An architecture test asserts `personalization` doesn't import the Event Fit read. The digest intent will need it to hold.
- [ ] `make lint-imports`, `manage.py check` and the coverage gates pass.
- [ ] Tests cover each tag rule at its boundaries, the score bands, local-day computation across DST, recompute on version change, no stale row served, the backfill being idempotent, and the top-N ordering.

## Technical Notes

The 1–5 indicator shares its visual vocabulary with the Confidence Pulse (FR-22). Check `DESIGN.md` for how the Pulse Preview's dots are labelled, so the score's meaning isn't confused with extraction confidence. They are different things that happen to share an input.

City is the venue's city (`Venue.city`). An event without a venue city gets no Event Fit row and doesn't appear in the preview, rather than being guessed.

Mind the refresh cost. Recomputing all published events is cheap at MVP scale, but bound it in batches as `schedule_sources` does.

## Dependencies

(none)
