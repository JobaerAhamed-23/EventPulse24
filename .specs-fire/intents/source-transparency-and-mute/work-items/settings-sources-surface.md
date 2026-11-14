---
id: settings-sources-surface
title: Settings → Sources — A Designed Screen With No Endpoints
intent: source-transparency-and-mute
complexity: high
mode: validate
status: completed
design_doc: settings-sources-surface-design.md
checkpoint_1: approved
depends_on: []
created: 2026-11-13
run_id: run-eventpulse24-033
completed_at: 2026-11-13T17:02:07.888Z
---

# Work Item: Settings → Sources — A Designed Screen With No Endpoints

## Description

`settings-sources-desktop.html` (Amendment A-18) specifies a complete screen:

> - 4 grouped sections (Official / Community / Aggregator / Crawled) with reliability-badge
>   leading text; 10 illustrative sources spanning all 4 types.
> - Each row: source-name + reliability dots (1–5) + 3-state source-mute control
>   (Mute / Show less / Default).
> - Footer ghost button: "Restore all defaults" — bulk reset confirmation lives behind this
>   tap (per §10.4 bulk-action safeguard).

Its header records that the spec was locked and the mockup was missing: *"EXPERIENCE.md §2
IA row 8 spec is locked (grouped source list + reliability badge + 3-state mute) but no
`mockups/settings-sources-desktop.html` existed prior to this amendment."*

**The score is built. The screen is not, and neither is any way to reach it.**

| Piece | State |
|---|---|
| `reliability_score()` — `domain/reliability.py:148` | **built** |
| `SourceReliabilityScore` model + guard trigger — `ingestion/migrations/0011_*` | **built** |
| An endpoint exposing per-source reliability to a signed-in user | **does not exist** |
| An endpoint storing a per-user source mute | **does not exist** |
| `/settings/sources` route | **does not exist** |

This is also where `calendar-connect-api.md:20` expected the calendar controls to live
("…and, later, Settings → Sources") — though `settings-desktop.html` puts calendar sync in
its own `#calendar-sync` section, which is why `calendar-connection-controls` is a separate
item and does not wait on this one.

**Like `less-like-this-adjustment`, this is large enough to be its own intent.** The design
checkpoint decides.

## Acceptance Criteria

- [ ] **The design checkpoint decides scope before any code**, including whether the 3-state
      mute is the same control FR-25's prompt reverses
- [ ] A signed-in user can see the sources behind their events, grouped by acquisition type,
      with each source's reliability
- [ ] A source can be set to Mute / Show less / Default, and the setting persists
- [ ] The setting **changes what the user is shown** — proven against the composition or
      ranking path, not only by a test that the row was written
- [ ] "Restore all defaults" exists and is **confirmed before it completes** (§10.4
      bulk-action safeguard)
- [ ] Reliability is rendered as the mockup specifies — 1–5 ink-primary dots, **not** the
      terracotta confidence pulse, and no new tokens
- [ ] The route follows the five-step settings house pattern and is linked from an existing
      settings page (there is no `/settings` index and no sub-nav)
- [ ] New endpoints go through the generated client (AD-19) with `make client` output
      committed
- [ ] Every test is verified by a mutation probe that makes it fail

## Technical Notes

- **FR-16's matrix status is a documentation problem, not this item's.** The matrix scores
  FR-16 `PARTIAL (inferred only)` because *nothing cites it* — not because the reliability
  dots are missing. Open item #1 says one line in `EXPERIENCE.md` or a tag in this mockup's
  header closes it. **Do not edit the matrix or the mockup to improve the score as a side
  effect of building this**; the matrix's own rule is that editing a document to improve the
  score in the same pass that measures it is how a matrix stops being trustworthy.
- **Read `domain/reliability.py` before designing the badge.** It documents a real conflict:
  *"FR-16 asks for 'a 3x week-over-week drop in reliability score'. **That cannot happen**"*
  (`:49`). A screen that renders a number the domain says is impossible is explanation drift
  of the kind AD-10 forbids.
- **The mute is per-user state over a global catalog object.** Which schema owns that table
  is an architecture question (AD-3's composition separation) and belongs in the design doc,
  not in a migration written on the way past.
- **`settings-sources-desktop.html` shows 10 illustrative sources.** The real set comes from
  the source registry (FR-13). Render what exists; an empty registry gets
  `component.emptystate.quiet`, which the mockup already provides for.

## Dependencies

- (none)
