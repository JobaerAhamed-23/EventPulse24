# Test Report: settings-privacy-data-inventory

**Run:** run-eventpulse24-056 · **Date:** 2026-11-20 · **Result:** PASS

| Check | Result |
|---|---|
| Frontend suite | 178 files / **2853** tests, pass |
| `tsc --noEmit` | clean |
| `pnpm lint` | **exit 0** |
| New: `data-inventory.test.tsx` | 4 pass |

## What shipped

PRD §10.2's requirement — *"Settings → Privacy → 'What we store' displays the categories
and current retention windows in plain language"* — has existed since the PRD was written
and had no surface. It has one now.

**It reads `RETENTION_ROWS`; it restates nothing.** No retention window appears as a
literal anywhere on the settings surface. The schema, `/privacy` and this page now share
one source, pinned to the database by `backend/tests/shared/test_retention_published.py`.

## Tests, and the proof they fail

Proved by rendering only the first three rows (`RETENTION_ROWS.slice(0, 3)`):

```
× renders every category the registry publishes
× states a window and a deletion outcome for every category
```

Both caught it; restored, 4 pass.

| Test | Asserts |
|---|---|
| renders every category the registry publishes | every row present by `data-retention-row`, **and the count matches** — a duplicated or stale row fails as surely as a missing one |
| states a window and a deletion outcome for every category | §10.2 asks for categories *and* windows; a category without one is half an answer |
| does not publish the two categories that have no models | A-27's withdrawal holds on this surface too |
| points at the full policy and at export | `/privacy` and `/settings/account` |

## A correction to this item's own acceptance criteria

The work item required the section to render in **"all three branches of the page, as
`DangerZone` does."** **`DangerZone` renders in two.** The third branch —
`session.kind !== "signed-in"` — has no user and renders only `SettingsStates`; the route
redirects signed-out visitors before reaching it.

The inventory therefore renders in **the two signed-in branches, matching `DangerZone`
exactly**, which is what the criterion was reaching for. Recorded rather than silently
diverged from.

The reasoning still holds in the branch that matters: the inventory renders in the
`unavailable` branch, because it depends on no API read and a failed *ranking* fetch is no
reason to stop telling someone what is stored about them.

## Acceptance criteria

| Criterion | Status |
|---|---|
| "What we store" renders every `RETENTION_ROWS` row with holds/window/deletion | ✔ |
| No retention window written as a literal | ✔ |
| Test asserts every row reaches the DOM | ✔ plus a count assertion |
| Renders in the branches `DangerZone` does | ✔ two, see correction above |
| Links to `/privacy` and to export | ✔ |
| Placed between the ranking formula and the danger zone | ✔ both branches |
| Lede updated | ✔ now names all three sections |
| Header comment corrected, still listing what is unbuilt | ✔ A-14 toggle, A-13 timeline, Sources mirror remain named |
| Existing privacy-page tests pass unchanged | ✔ |
