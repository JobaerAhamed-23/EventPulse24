---
id: source-transparency-and-mute
title: Source Transparency & Mute — Settings → Sources, and What the Dots Mean
status: completed
created: 2026-11-13
split_from: unwired-surfaces
completed_at: 2026-11-13T17:02:07.892Z
---

# Intent: Source Transparency & Mute

## Goal

Build Settings → Sources (Amendment A-18): the grouped source list, the reliability badge,
the 3-state mute (Mute / Show less / Default) and "Restore all defaults".

## Why it is its own intent

Split out of `unwired-surfaces` at its design checkpoint (2026-11-13,
`run-eventpulse24-031`), on the same line FR-25 was split on. That intent closes gaps where
a **built endpoint has no caller**; this has no endpoints at all. The full finding is in
`unwired-surfaces/work-items/settings-sources-surface-design.md`.

## What exists, verified 2026-11-13

| Piece | State |
|---|---|
| `reliability_score()` — `domain/reliability.py:148` | **built** |
| `SourceReliabilityScore`, one row per (source, week), append-only | **built** |
| `Source` registry (FR-13) | **built** |
| `settings-sources-desktop.html` (Amendment A-18) | **designed** |
| An endpoint exposing reliability to a signed-in user | **none** |
| A per-user source-mute model | **none** |
| Any effect of a mute on composition or ranking | **none** |
| `/settings/sources` | **none** |

## Three questions to settle before any code

### 1. The mockup's four groups do not exist in the model

It specifies *Official / Community / Aggregator / Crawled*. The code has
`SourceType` (7 values), `AcquisitionMethod` (7 values) and a derived `high`/`lower`
priority (2). "Official" maps to the high tier — `source_priority`: *"The high tier is the
official sources — the API and partnership methods"* — and "Crawled" to `CRAWL`.
**"Community" and "Aggregator" map to nothing**, and the four groups mix two taxonomies,
leaving jsonld/rss/ics/email_ics unassigned.

This is a product decision about how sources are described to users. Settle it in writing.

### 2. What the reliability dots actually show

`domain/reliability.py:49` already records a conflict with FR-16's text: *"FR-16 asks for
'a 3x week-over-week drop in reliability score'. **That cannot happen**"*. Rendering a
number the domain says is impossible is the explanation drift AD-10 exists to prevent.

### 3. Where a per-user mute lives, under AD-3

Personal state about a catalog object. The product already solves this: `SavedEvent` is a
`personal` row carrying `event_id` **by value, with no foreign key**. The answer is
probably the same shape — but state it rather than discovering it in a migration.

## Constraints

- **No new tokens.** The mockup is explicit: reliability dots reuse the 1–5 ink-primary
  dots pattern in its *uncoloured* form — **not** the terracotta confidence pulse.
- **"Restore all defaults" is confirmed before it completes** (§10.4 bulk-action safeguard).
- **A mute must change what the user is shown**, proven against composition or ranking —
  not only by a test that a row was written.
- **No `/settings` index and no new nav rows.** Link from an existing settings page.
- The generated client is the contract (AD-19); `make client` output is committed.
- **Do not edit `TRACEABILITY.md` or the mockup header to close FR-16's `PARTIAL` score as
  a side effect.** The matrix's own rule: editing a document to improve the score in the
  same pass that measures it is how a matrix stops being trustworthy.

## Related

`relevance-feedback-loop` (FR-25) needs a reversal surface, and this intent's 3-state mute
may be it. Decide once, here, rather than building two mute controls.

## Not decomposed yet

This brief is the capture. Decomposition is the planner's next pass and should start from
the three questions above.
