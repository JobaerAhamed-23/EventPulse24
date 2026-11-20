---
id: settings-privacy-data-inventory
title: §10.2's "What we store" has never been built — and its source now exists
intent: spec-debt-and-open-findings
complexity: medium
mode: confirm
status: completed
depends_on:
  - prd-section-10-2-reconciliation
created: 2026-11-20
run_id: run-eventpulse24-056
completed_at: 2026-11-20T12:19:27.941Z
---

# Work Item: The data inventory the PRD has always required

## Description

PRD §10.2, in its own words:

> **User-visible data inventory:** Settings → Privacy → "What we store" displays the
> categories and current retention windows in plain language.

**It does not exist.** `app/settings/privacy/page.tsx` renders FR-22's ranking formula and
the danger zone, and its own header comment has listed this among the route's unkept
commitments since `run-eventpulse24-048`:

> `EXPERIENCE.md` §2 row 9 also commits this route to a data inventory, export (FR-52),
> deletion, a training opt-out, the Amendment A-14 geo-IP consent toggle, the A-13
> amendment-history timeline and a read-only mirror of Settings → Sources. **None of those
> is here.**

**The expensive half is done.** `lib/retention-categories.ts` holds the seven live
categories in plain language, pinned to the enforced registry by
`backend/tests/shared/test_retention_published.py`. This item is a section, not a source.

**That is the whole point of doing it now.** The alternative — a hand-written inventory —
would be a third copy of the retention windows, free to drift from both the database and
the privacy policy. Reading `RETENTION_ROWS` means the settings page, the public policy
and the schema cannot disagree without a test failing.

## Acceptance Criteria

- [ ] A **"What we store"** section on `/settings/privacy`, rendering every row of
      `RETENTION_ROWS`: what it holds, how long it is kept, and what deletion does to it
- [ ] It reads `RETENTION_ROWS`. **No retention window is written as a literal** anywhere
      in the settings page
- [ ] A test asserts every row reaches the DOM, so an import that silently stops rendering
      fails rather than quietly emptying the section
- [ ] The section renders in **all three branches** of the page, as `DangerZone` does — it
      depends on no API read, and a data inventory that disappears when the ranking
      endpoint blinks is one a user cannot rely on
- [ ] It links to `/privacy` for the full policy, and to Settings → Account for export
- [ ] Placement: **between the ranking formula and the danger zone.** Readable things
      together; the irreversible control stays last and separate, which is the layout
      decision A-16 and the page's own comment already made
- [ ] The page's header comment and lede are updated — the lede currently describes the
      page as ranking plus danger zone, and would otherwise under-describe it
- [ ] The header comment's list of unkept §2-row-9 commitments is **corrected**, not left
      saying the inventory is missing
- [ ] Existing privacy-page tests pass unchanged

## Technical Notes

- `RETENTION_ROWS` is already `readonly` and typed; the settings page imports it directly.
  **Do not reshape it for this surface** — if the two surfaces want different wording, the
  row gains a field, so both still come from one place.
- `/privacy` renders the same data as prose with `holds` / `window` / `onDelete`. This
  surface is a signed-in settings screen and should use the settings vocabulary rather
  than copying the public page's markup.
- **This does not close §2 row 9.** Export, the A-14 geo-IP toggle, the A-13
  amendment-history timeline and the Sources mirror remain unbuilt. The header comment must
  still say so, with the inventory struck from the list.

## Dependencies

- prd-section-10-2-reconciliation — the inventory publishes §10.2's categories to users, so
  §10.2 must be true first. A-27 withdraws the two that do not exist.
