---
id: digest-candidate-reads
title: Eligible-candidate reads, on both sides of the wall
intent: pulse-digest-and-trust
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-10-30
completed_at: 2026-10-30T17:30:00Z
run_id: run-eventpulse24-021
---

# Work Item: Eligible-candidate reads, on both sides of the wall

## Description

Gives the composition service its candidates: the public events a user may legally be shown, and the personal events eligible for Slot 1. These are two reads on two sides of the AD-3 wall, and keeping them separate is the point — AD-3 means no query can ever return both, so the join happens in the application layer or not at all.

The public read extends `apps/ingestion/services/catalog_read.py`, which is already "the published read interface over the catalog" and the only legal path for another app to see an `Event`. It must **not** go anywhere near `apps/ingestion/event_fit/` — that package is walled off from `personalization` by an import-linter contract written specifically to stop the Relevance Pulse borrowing the Event Fit, and the contract's own comment records that an earlier name-based version of the wall was bypassable by a two-line re-export file.

## Acceptance Criteria

- [ ] **A public-candidate read in `catalog_read.py`** returns upcoming, published, non-superseded events for a city as plain frozen dataclasses — never model instances — matching the existing `PublicEvent` discipline so the caller never holds a reference to `apps.ingestion.models`.
- [ ] **Every eligibility gate is the existing constant, reused and not restated** (AD-8: "the threshold lives in one shared module"):
  - `extraction_confidence` ≥ `EXTRACTION_CONFIDENCE_PUBLISH` — below it an event is "never published to a Pulse Digest";
  - `tz_inference_confidence` ≥ `TZ_INFERENCE_CONFIDENCE_DIGEST` — AD-6: "an Event with `tz_inference_confidence` <0.7 is **not eligible for any Pulse Digest** until editorial review completes";
  - `publication_status` published, `superseded_by` null, start in the future.
- [ ] **Staleness is honored (FR-14):** an event older than **2× its source's `freshness_ttl_hours`** is not surfaced in a fresh digest. `Source.freshness_ttl_hours` exists and defaults to 24; the multiplier is a named constant.
- [ ] The read carries each event's **Source Badge input** — the `Source.source_type` that maps to the five badge variants — because the badge is persisted on the composition and must come from the same read that justified the card.
- [ ] A **`tz_review_pending`** event is eligible (it is published and above the digest gate) and carries the flag through, so the frontend can mark its time as approximated — the treatment `catalog_read` already applies.
- [ ] **A personal-candidate read in `personalization`** returns the user's `PERSONAL_EVENT`s starting within the next **48 hours** (FR-5 / FR-19's eligibility window, as a named constant), including imported calendar events, with their conflict state available.
- [ ] **A saved-event read** supplies the user's `SAVED_EVENT` rows so composition can respect them — at minimum so the digest can tell a saved event from an unsaved one on the card. Saved events read their **personal-side snapshot**, never a catalog join (AD-21).
- [ ] **Conflict state comes from persisted `CONFLICT_PAIR` rows**, never computed at render — AD-21 is explicit that conflict detection happens "never at render", and `domain/conflict.py` is already the one overlap function.
- [ ] **`personalization` still cannot import `apps.ingestion.event_fit`.** `make lint-imports` passes unchanged, and the existing `tests/architecture/test_event_fit_separation.py` stays green with no edits to relax it.
- [ ] **No query touches both schemas.** A test asserts the public read runs on the `catalog` alias and the personal reads on `default`, and that no code path attempts a cross-alias join.
- [ ] `now` is an explicit parameter on every read, as it is throughout `catalog_read.py` — no time-freezing library, each boundary testable at the exact second.
- [ ] Tests cover each gate at its exact threshold (an event one hundredth below the confidence gate is excluded, one at it is included), the 2× staleness boundary, the 48-hour personal window at the exact second, a superseded event being excluded in favor of its replacement, and the city filter.

## Technical Notes

**The page size is not the digest size.** `catalog_read` has `DEFAULT_PAGE_SIZE = 20` / `MAX_PAGE_SIZE = 100`; composition needs a *candidate pool* large enough that three slots can be filled with distinct events after scoring, which is a different number from three. The design should say how many candidates are fetched and why, and bound it — this read runs once per user per day, so a pool that is cheap for one user is not automatically cheap for all of them.

**City matching is equality, not distance.** `Venue` has `city` and `country_code` and no coordinates, so "nearby" is a band: same city, same country, elsewhere. The brief records this as a named deviation from FR-5's haversine curve. Do not invent a centroid table here; if coordinates arrive later, this read is where they land.

An event with no venue city cannot be matched to a user's city. `event-fit` made the same call and chose to give such events no row at all rather than guess — worth following, and worth stating either way.

## Dependencies

(none)
