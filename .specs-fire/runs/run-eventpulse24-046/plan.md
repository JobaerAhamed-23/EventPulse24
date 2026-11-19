---
run: run-eventpulse24-046
work_item: timeline-why-this-tag
intent: traceability-gap-closure
mode: validate
checkpoint: plan
approved_at: pending
---

# Implementation Plan: The Timeline block's Why-this tag — deferred, with the reason

## Approach

**Documentation only. Zero lines of production code.**

The approved design settles `EXPERIENCE.md` §13's promise that a desktop Timeline
event-block adds *location and one Why-this Tag* on hover or focus. The location shipped;
the tag is withdrawn under a new **Amendment A-24**, with the reason recorded in place, and
`TRACEABILITY.md`'s O-2 closes.

Three documents change. Nothing under `backend/` or `frontend/` is touched, so the
generated API client, the contract test and every existing suite are unaffected by
construction.

### Where A-24 is recorded, and why not in the Surface Coverage Map

EXPERIENCE.md records amendments in two different places, and this one goes in the less
obvious of them:

- The **Surface Coverage Map** (rows 1-24, `Amendment A-NN` in the surface's name) is for
  amendments that **add or change a surface and its mockup**. A-24 adds no surface, no
  component and no mockup.
- The **`updated_note` frontmatter field** carries "Spine update" entries for as-built
  corrections that touch only this document — the pattern A-18's `/settings/sources`
  correction established on 2026-11-13.

A-24 is the second kind, so it is prepended to `updated_note` (newest first, matching the
existing order) and the `updated:` date moves to 2026-11-19. Adding a Surface Coverage row
would assert a new surface that does not exist.

## Files to Create

| File | Purpose |
|------|---------|
| (none) | |

## Files to Modify

| File | Changes |
|------|---------|
| `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/EXPERIENCE.md` | §13 Density Modes line 1107: the hover/focus Timeline row drops the Why-this Tag, keeps location, carries `(Amendment A-24)`. Frontmatter: A-24 spine-update entry prepended to `updated_note`; `updated:` → 2026-11-19 |
| `_bmad-output/planning-artifacts/traceability/TRACEABILITY.md` | FR-32 row (line 197): "**O-2 partly closed** — §13's Why-this tag is open as `timeline-why-this-tag`" → O-2 **closed**, §13 amended under A-24, location-only by decision |
| `.specs-fire/intents/traceability-gap-closure/work-items/timeline-why-this-tag.md` | Frontmatter `status: pending` → `completed` (the run-plan reconciliation rule: state.yaml is authoritative, frontmatter follows) |

## Tests

| Test File | Coverage |
|-----------|----------|
| (none added) | Documentation-only change. Verification is a zero-diff check over `backend/` and `frontend/`, plus a grep that no document still lists the tag as open work. |

## Technical Details

### The exact §13 edit

Line 1107 today:

```
| **Hovered / focused (Timeline event-block, desktop)** | Mouse hover or Tab focus | Adds location (`Text.Meta`) and 1 Why-this Tag (read-only at MVP — full Why-this breakdown expansion is on Detail Screen, never on Timeline). |
```

becomes a location-only row tagged `(Amendment A-24)`, stating in the cell that the tag was
considered and withdrawn, and keeping the existing pointer to the Detail Screen for the
full Why-this breakdown.

### What the A-24 note must say

Four things, because each answers an objection a later reader will raise:

1. **The decision** — the Timeline block reveals location only; the Why-this Tag is
   withdrawn, not deferred indefinitely and not silently dropped.
2. **The reason** — every public block on the Timeline *is* a saved event, so `is_saved` is
   universally true; `discovery` needs a digest slot and never fires; the time tags are
   relative to `now` and so never fire on any week but the current one. The single tag §13
   asks for therefore resolves to `nearby` on every block in the user's own city, or to
   `saved` — which, on a surface that shows only saved events, answers "why is this here?"
   with "because you saved it." The one informative tag, `matches_<chip_key>`, sorts last
   in `RANKING_TAG_ORDER` and is unreachable whenever any fixed tag applies.
3. **Why this is not a trust-signal removal** — §13's own anti-pattern ("Adaptive density
   must not hide the trust signals") governs the **Pulse Card**, whose mobile default
   exposes Why-this Tags, Confidence Pulse and Source Badge. The Timeline block's default
   shows none of the three at any density, so nothing is hidden; a promise is withdrawn
   before it was ever kept. §13 already routes the full breakdown to the Detail Screen.
4. **Not a cost decision** — the design doc's measured correction. Building it costs **one
   extra query**, not the "four reads" the work item recorded: `why_this_tags` reads only
   `inputs.city_match` from `RankingInputs`, the user's city rides on the `DigestPreference`
   row the Timeline already reads, and `chip_keys_for` is pure text over columns the batched
   catalog read already selects. Only `_read_interest_keys` is new. Stating this stops the
   deferral being reversed the first time somebody checks the cost claim.

Point 4 matters most for durability: a deferral justified by a cost that turns out to be
wrong is a deferral that gets undone.

### What is deliberately NOT changed

- **`domain/ranking.py`, `why_this_tags`, `RANKING_TAG_ORDER`** — correct as they stand;
  this is about one surface's use of them.
- **`TimelineBlock`, `TimelineBlockOut`, `timeline-block.tsx`** — no field added or removed,
  so no schema change and no `make client` regeneration.
- **The work item's `source` line in `state.yaml`** — "AD-10 bars personalization from the
  Event Fit" is a true statement and an accurate record of the 2026-11-17 split. The
  clarification that AD-10 does **not** bar the `why_this_tags` path lives in the design
  doc, where a reader meets it before writing code.
- **Browse and the Digest** — untouched; they remain the surfaces where the tag is
  computed and where it means something.

### Verification

1. `git diff --stat` shows changes confined to the two planning documents and the work
   item's frontmatter.
2. `git status` shows no modification under `backend/` or `frontend/`.
3. `grep -rn "timeline-why-this-tag"` across `_bmad-output/` returns nothing describing it
   as open work.
4. The A-24 ID is confirmed unused immediately before writing (it was free at planning time;
   `fr22-published-formula` is slated to take A-25, so the check guards against a
   same-session collision).

## Based on Design Doc

Reference: `.specs-fire/intents/traceability-gap-closure/work-items/timeline-why-this-tag-design.md`

---
*Plan approved at checkpoint. Execution follows.*
