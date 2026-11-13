---
id: endpoint-coverage-enforcement
title: The Check That Would Have Caught All of This
intent: unwired-surfaces
complexity: medium
mode: confirm
status: pending
depends_on: []
created: 2026-11-13
---

# Work Item: The Check That Would Have Caught All of This

## Description

Eight gaps, found by a hand-run audit on 2026-11-13, across twelve completed intents and
thirty runs. Nothing in CI was asking the question, so the answer drifted for weeks.

The repo has two adjacent checks and neither covers this:

- `backend/tests/.../test_contract.py` asserts the **committed schema equals the live API**.
- `frontend/tests/ad19-endpoint-coverage.test.ts` asserts that **three named endpoints** from
  one intent are in the schema and in the generated client. Its own docstring explains why
  it is not more: *"a coverage check and not just a drift check"* — but the list is
  hand-maintained and covers one intent's additions.

Both are green while four endpoints have no caller.

This item makes the audit a test: **every endpoint in the generated schema is either called
from the UI, or listed with the reason it is not.** A new endpoint with neither fails CI.

The allow-list is the point. "Uncalled" is not always a bug — the RFC 8058 unsubscribe path
is called by a mail provider, the export links are called from an email, the billing webhook
is called by Stripe, and the public catalog reads are an anonymous API the UI deliberately
does not use. Each of those is a **decision**, and a decision that lives in a reviewable list
is worth more than one that lives in a person's memory.

## Acceptance Criteria

- [ ] A test enumerates every `(method, path)` in the committed schema and partitions them
      into **called** and **declared-uncalled**
- [ ] The declared-uncalled list carries a one-line reason per entry, and the current seven
      are recorded with the reasons established by this intent's audit
- [ ] An endpoint that is neither called nor declared **fails the test**, naming the method
      and path
- [ ] A declared-uncalled entry that **is** called also fails — a stale exemption is a lie in
      the same way a missing one is
- [ ] Call-site detection ignores comments, following the precedent in
      `ad19-endpoint-coverage.test.ts`: its client-break probe showed a `toContain(path)`
      over raw source stayed green after the call site was rewritten, because a **docstring**
      still named the path
- [ ] Test files and the generated `lib/api/` folder are excluded from call-site detection
- [ ] The existing `ad19-endpoint-coverage.test.ts` is reconciled with this test rather than
      left to duplicate it — one of them owns the claim
- [ ] A mutation probe proves the test fails: remove a real call site and watch it name that
      endpoint
- [ ] A second probe proves the stale-exemption half fails too

## Technical Notes

- **The audit's own method is the starting point**, and it is worth repeating because it has
  two traps. Paths must be compared **by method**, not by path alone — `/api/notices/events/
  {event_id}/mute` has a `PUT` and a `DELETE` and the UI happens to use both, but a
  path-only diff would have hidden it if it used one. And a path passed as a **variable**
  reads as uncalled: `onboarding-flow.tsx:115` declares
  `path: "/api/personal/onboarding/step" | "/api/personal/onboarding/step/skip"` and calls
  `advance(path)` at `:202`. Both endpoints are used. A naive regex reports two false gaps.
- **Prefer parsing `lib/api/openapi.json` over `schema.ts`** — it is the committed contract
  and is already read by the existing test.
- **This test says nothing about whether a caller is *reachable*.** The personal-events list
  calls nothing and renders nowhere; a list that called an endpoint from a dead branch would
  satisfy this check. That limit should be stated in the test's own docstring rather than
  discovered later.

## Dependencies

- (none)
