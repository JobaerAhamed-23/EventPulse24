---
run: run-eventpulse24-038
work_item: timeline-hover-detail
intent: traceability-gap-closure
date: 2026-11-17
---

# Test Report: Reveal the Timeline block's detail on hover and focus — FR-32 (UI)

## New tests

`frontend/components/timeline/timeline-block-place.test.tsx` — **8 tests.**

| Group | Holds |
|---|---|
| `the place the server sent` | it renders; **it is in the `aria-label`**; nothing renders when the server sent none; a personal block with no location names no place; a personal block carries its own |
| `the reveal adds and never removes` | the name, the category label, the conflict indicator and the place all co-exist; `group-hover` and `group-focus-within` are both present on the same element; `group` is on the block |

**The accessible-name test is the one that matters most.** `aria-label` overrides inner
text in the accessible-name computation, so the revealed line is invisible to assistive
technology unless the place is named in the label — and "reveal on hover" means nothing to
a reader who cannot hover. Without that assertion the feature would look complete and be
unreachable for screen-reader users.

The two class-name assertions are deliberately shallow — jsdom does not apply hover or
focus-within — but they pin the **pairing**: a `group-hover` without its
`group-focus-within` is a hover-only affordance, which is the rule this project has
written down twice.

## Suite results

| Suite | Result |
|---|---|
| Frontend | **2649 passed, 161 files, 0 failed** (2641 + the 8 added) |

Existing timeline suites — `components/timeline`, `tests/timeline-a11y.test.tsx`,
`app/timeline` — all still pass untouched: 38 tests.

## Gates

| Gate | Result |
|---|---|
| `pnpm test` | 2649 passed, 0 failed |
| `pnpm typecheck` | clean |
| `eslint` / `prettier` (touched files) | clean |

## Not covered

- **No visual confirmation.** Docker and the API are down, so nobody has seen the reveal.
  jsdom cannot evaluate `:hover`, so the reveal is proven structurally — the element, its
  content, its name and its class pairing — not visually.
- **The height change is unverified by eye.** Growth was chosen over an overlay with the
  reasoning recorded in the component; whether it feels right in a packed day column is a
  judgement that needs the running app.
