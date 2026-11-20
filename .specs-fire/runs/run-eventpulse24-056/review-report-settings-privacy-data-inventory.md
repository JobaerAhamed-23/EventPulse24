# Review Report: settings-privacy-data-inventory

**Run:** run-eventpulse24-056 · **Verdict:** PASS

## Scope

**Created** — `components/settings/data-inventory.tsx`,
`components/settings/data-inventory.test.tsx`.
**Modified** — `app/settings/privacy/page.tsx` (import, both signed-in branches, lede,
header comment).

## Checks

| Check | Result |
|---|---|
| Frontend suite | 2853 pass (178 files) |
| `tsc --noEmit` | exit 0 |
| `pnpm lint` | exit 0 |

## Auto-fixes applied

**None.**

## Findings

### §10.2's inventory requirement — closed

The oldest open requirement touched in these two runs. It predates every FIRE intent in
this repository and was never scheduled, because it reads as documentation rather than a
feature.

**What made it cheap was run-055.** `RETENTION_ROWS` was built to make the *public* policy
true; the settings surface is a second consumer of the same table. Had this been built
first, it would have needed its own source — and would now be a third copy of the windows,
free to drift.

### F-10 (observation) — `EXPERIENCE.md` §2 row 9 is still not closed

The route still owes the A-14 geo-IP consent toggle, the A-13 amendment-history timeline,
and the read-only mirror of `Settings → Sources`. The header comment now says so
precisely, with the inventory struck from the list rather than the whole list deleted.

**Deliberately not folded in.** Each is its own surface with its own decisions, and this
item owned the inventory.

## Observations, no action

- **The count assertion is the one that earns its place.** Asserting each row is present
  would pass against a page that rendered every row twice, or that rendered a stale
  eighth. The count is what makes the mirror exact.
- **`data-retention-row` keys the rows by category id**, not by index, so a reordering of
  `RETENTION_ROWS` does not churn the tests.
- **The two withdrawn categories are asserted absent here as well as on `/privacy`.** The
  backend time bomb catches the day either gains a model; these two assertions catch a
  hand-edit that adds a row to the UI without one.
- **The lede was updated.** It described a page of two sections and the page now has
  three; leaving it would have under-described the surface on the screen whose purpose is
  to describe things accurately.

## Conclusion

Complete and green.
