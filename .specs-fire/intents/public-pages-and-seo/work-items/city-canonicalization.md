---
id: city-canonicalization
title: A city is one place — the canonical City noun and the venue backfill
intent: public-pages-and-seo
complexity: high
mode: validate
status: completed
depends_on: []
created: 2026-11-01
run_id: run-eventpulse24-024
completed_at: 2026-11-01T15:50:23.894Z
---

# Work Item: A city is one place — the canonical City noun and the venue backfill

## Description

FR-27 wants one page per city. The database does not have a city — it has a string copied onto `Venue.city` and again onto `EventFit.city`, unnormalized, 100 characters wide. The existing read (`list_event_fit_for_city`) matches `city__iexact` on a stripped value, so **case and whitespace are already one city**; what is still two cities is `Brooklyn` and `Brooklyn, NY`, and neither of them has a URL slug or a display name anyone chose.

This item introduces the **City** noun: a canonical row with a stable slug and a display name, a pure domain normalizer that maps a free-text venue string onto it, and a backfill over existing `Venue` rows.

**This item needs a design doc (Checkpoint 1) before any code.** Two decisions are open and neither should be made inside a build run.

## Acceptance Criteria

- [ ] A `City` model with a **stable slug** (the FR-27 URL segment, minted once and never re-minted — the same discipline `mint_slug` follows for events, so a city page URL cannot move) and a human display name (`Brooklyn`, not `brooklyn, ny`).
- [ ] A **pure domain normalizer** — no Django import, no database — that maps a free-text venue city string to a canonical key, in the shape of `domain/conflict.py` and `domain/event_fit.py`. It handles case, surrounding whitespace, internal punctuation, and a trailing region/country suffix (`Brooklyn, NY` → `Brooklyn`). It is tested on its own.
- [ ] The normalizer **never guesses across genuinely different places**: a string it cannot resolve confidently stays its own city rather than being merged into a near match. Under-merging is recoverable; a wrong merge publishes an SEO page about two different cities.
- [ ] A **backfill** over existing `Venue` rows that is **idempotent** and re-runnable, in the shape of `config/management/commands/backfill_event_fit.py`, attributed to a system `Actor`.
- [ ] A venue with an **empty city** resolves to no City and is not invented — matching the rule `EventFit` already follows ("an event without a venue city gets no Event Fit row ... rather than being guessed").
- [ ] New venues resolve to a City on write, so the backfill is a one-time catch-up and not a recurring repair.
- [ ] Tests: the normalizer's table of inputs including region suffixes, a non-Latin city name, an empty string, two venues in differently-spelled forms of one city, and a re-run of the backfill proving idempotence.

## Technical Notes

**Design-doc decisions (Checkpoint 1):**

- **OQ-A — which module owns `City`.** `Event`, `Venue` and `EventFit` all live in `apps/ingestion/models.py`, but ARCHITECTURE-SPINE.md's Capability Map assigns FR-26–28 to **`catalog`** — and `apps/catalog/models.py` is **0 lines**, the app being read-side only (`api.py`, `preview_api.py`, `services/`). AD-16 requires exactly one owning module and no second write path. Settle this explicitly; do not infer it from where the file was easiest to add.
- **Whether `EventFit` takes a `City` FK or keeps its string.** An FK is cleaner and makes the `>5 events` count trivial; it is also a migration over an existing populated table with an `event_fit_city_score_idx` the preview read depends on, and `EventFit.city` is documented as "the venue's city, **as written on the Venue row**". Keeping the string and resolving at read is cheaper and preserves that provenance. Decide with the index and the preview read in view.

**Constraint:** whatever the design chooses, `list_event_fit_for_city` must keep working for the Pulse Preview unchanged — it is live on `/preview` today.

## Dependencies

(none)
