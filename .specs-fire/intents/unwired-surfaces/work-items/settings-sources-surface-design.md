---
id: settings-sources-surface-design
work_item: settings-sources-surface
intent: unwired-surfaces
run_id: run-eventpulse24-031
status: approved
decision: split-into-own-intent
created: 2026-11-13
---

# Design: Settings → Sources — and why it also leaves this intent

## The checkpoint's question

Same as FR-25's: does this belong in `unwired-surfaces`, or in an intent of its own?

## Finding 1 — it is the same category as FR-25, by this intent's own definition

`unwired-surfaces` is about **endpoints that exist and have no caller**. That is the
sentence the brief opens with and the rule `endpoint-coverage-enforcement` now enforces.

Settings → Sources has **no endpoints at all**:

| Piece | State |
|---|---|
| `reliability_score()` — `domain/reliability.py:148` | **built** |
| `SourceReliabilityScore` model, one row per (source, week) | **built** |
| `Source` registry (FR-13), 7 acquisition methods, 7 types | **built** |
| An endpoint exposing any of it to a signed-in user | **none** |
| A per-user source-mute model | **none** |
| Any effect of a mute on composition or ranking | **none** |
| `/settings/sources` | **none** |

It was listed here because the **audit** found it, and the audit was looking for
designed-but-absent surfaces. But it needs a new model, a migration, three endpoints and a
composition behaviour change before a screen can call anything. That is a feature, not a
wiring gap, and it is larger than the two items remaining in this intent combined.

## Finding 2 — the mockup's taxonomy exists nowhere in the model

`settings-sources-desktop.html` specifies *"4 grouped sections (Official / Community /
Aggregator / Crawled)"*. The code has three different taxonomies, and **none of them is
that one**:

| Where | Values |
|---|---|
| `Source.SourceType` | venue, promoter, ticketing, community, government, media, other (**7**) |
| `AcquisitionMethod` | api, partnership, jsonld, rss, ics, email_ics, crawl (**7**) |
| `domain/sources.py` priority | high, lower (**2**, derived from method) |

"Official" maps cleanly — `source_priority` says *"The high tier is the official
sources — the API and partnership methods"*. "Crawled" maps to `CRAWL`. **"Community" and
"Aggregator" map to nothing**: `community` is a `SourceType` while the other three groups
are acquisition concepts, so the mockup's four groups mix two taxonomies and leave
jsonld/rss/ics/email_ics unassigned.

Inventing the mapping is a **product decision about how sources are described to users**,
not an implementation detail. Making it silently inside a feature item is how a UI ends up
asserting a taxonomy the system does not have.

## Finding 3 — the reliability copy conflicts with the domain, and this is already written down

`domain/reliability.py:49`: *"FR-16 asks for 'a 3x week-over-week drop in reliability
score'. **That cannot happen**"*. A screen that renders a number the domain says is
impossible is the explanation drift AD-10 exists to prevent. The new intent must decide
what the dots actually show before drawing them.

## Finding 4 — where the mute lives is an AD-3 question with a known precedent

A per-user mute is personal state about a catalog object. AD-3 forbids relating the two
schemas, and the product already solves exactly this: `SavedEvent` is a `personal` row
carrying `event_id` **by value, no foreign key**, and `CollectionEventOut` documents the
rule. So the answer is probably "the same way saves do it" — but *probably* is not a
migration, and the new intent should state it.

## Decision

**Split into its own intent: `source-transparency-and-mute`.**

The line is the same one FR-25 was split on, applied consistently: this intent closes gaps
where a built endpoint has no caller. Both FR-25 and this have no endpoint to call. Keeping
one and splitting the other would make the intent's scope mean two different things.

## What this intent keeps

Nothing is built here. `unwired-surfaces` finishes with the two items that are genuinely
in scope: the traceability section, and the e2e proof of the four gaps it actually closed.
