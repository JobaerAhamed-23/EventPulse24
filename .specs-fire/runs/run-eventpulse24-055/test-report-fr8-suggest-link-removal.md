# Test Report: fr8-suggest-link-removal

**Run:** run-eventpulse24-055 · **Date:** 2026-11-20 · **Result:** PASS

## Suite

| Scope | Files | Tests | Result |
|---|---|---|---|
| Full frontend suite | 176 | 2832 | **all pass** |
| Directly affected | 3 | 80 | all pass |

Node 24 (`v24.22.1`) per the repo's `.nvmrc`. No backend tests were run — this item
touches no Python; the spec files it edits are planning artifacts.

## Tests changed, and the proof each can fail

**Every assertion written or flipped here was made to fail once**, by restoring the
withdrawn link and re-running. All four failed, then passed again on restore. A test that
asserts an *absence* passes trivially against an empty render, so this is the only thing
that distinguishes it from a test that asserts nothing.

| Test | Was | Is | Failed when link restored |
|---|---|---|---|
| `app/page.test.tsx` → "offers nothing to click" | required a `link` named "Suggest an event" with `href="/suggest"`; `<a>` count 1 | asserts the link is absent; `<a>` and `<button>` counts both **0** | ✔ |
| `tests/digest-home-boundary.test.ts` → "gives the empty state nothing to click" | `<Link` count 1 | `<Link` count **0**, and no `href` at all | ✔ |
| `tests/digest-home-boundary.test.ts` → "links nowhere that does not exist" | `/suggest` fenced in `UNBUILT` with a reverse assertion | exception removed; resolves every href unconditionally | ✔ (caught `/suggest`) |
| `tests/internal-links.test.ts` | **new** | resolves every literal internal `href` under `app/**` + `components/**` | ✔ (caught `/suggest`) |

## What the new test found on first run

Before its exception was added, `internal-links` failed with exactly four entries and no
others:

```
app/signin/page.tsx → /terms
app/signin/page.tsx → /privacy
components/auth/signup-form.tsx → /terms
components/auth/signup-form.tsx → /privacy
```

**This is the independent confirmation that the intent's scan was complete** — three
dangling destinations across five link sites, and no fourth. It also proves the test is
not vacuous: it was written, it failed, and it failed on the right things.

### The exception it now carries, and why it must not survive

`UNBUILT = new Set(["/terms", "/privacy"])`, with the reverse assertion
`expect([...UNBUILT].filter((route) => routeTarget(route) !== null)).toEqual([])`.

**The exception removes itself.** The moment `legal-page-routes` creates either route, that
assertion fails and the next item cannot land until the fence comes out. This is the same
idiom `digest-home-boundary.test.ts` used to hold `/suggest` honest, and it is the reason
that link was a known quantity rather than a surprise.

## Guards on the new test itself

A sweep that silently matches nothing is worse than no sweep. Two floors:

- `expect(files.length).toBeGreaterThan(50)` — fails if the directories move or the glob
  stops matching
- `expect(checked).toBeGreaterThan(10)` — fails if a refactor to a route helper leaves no
  literal `href`s to resolve

## Acceptance criteria

| Criterion | Status |
|---|---|
| A-26 written before the component was touched | ✔ prd.md FR-8, then code |
| A-26 in `prd.md` in A-25's inline form | ✔ |
| EXPERIENCE.md updated where it names the link | ✔ §5 L517, §5 L522, §2 IA row, frontmatter `updated_note` |
| `digest-empty.tsx` renders no `Link`; `/suggest` gone from `frontend/` | ✔ remaining mentions are comments explaining the withdrawal |
| Locked copy byte-identical | ✔ headline + `No qualifying events in {city}.` unchanged |
| Header comment rewritten | ✔ it argued *for* the link; it now records why there is none |
| Updated tests can fail | ✔ all four proved |
| FR-8 traceability re-scored | ✔ Sections A and C annotated; finding **F-1** added |

## Deviation from plan

The plan listed six steps; **seven were executed.** Step 7 — the repo-wide
`internal-links.test.ts` — was added at the checkpoint on the user's approval, after the
earlier offer of a link test was found to have been made on a false premise: a resolving
check already existed and was good, and only its reach was missing.
