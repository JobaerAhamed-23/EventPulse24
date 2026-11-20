---
id: spec-debt-and-open-findings
title: The findings run-055 raised and did not close — plus the About link
status: completed
created: 2026-11-20
follows: broken-links-and-legal-pages
completed_at: 2026-11-20T12:23:48.608Z
---

# Intent: The findings run-055 raised and did not close

## Goal

Close every open finding `run-eventpulse24-055` recorded but kept out of scope, and settle
the two remaining `#` placeholders in the pre-auth footer.

## Why it is its own intent

`broken-links-and-legal-pages` was scoped to 404s. It found six things that were not
404s and raised them rather than absorbing them — a settings bug, two PRD divergences, an
unmet §10.2 requirement, and a footer that does not match its own spec. Each was correct
to defer; none is correct to leave.

## The findings, verified 2026-11-20

### F-4 — three lint errors are committed on this branch

`pnpm lint` has exited non-zero for the whole of run-055, unchanged by any of its three
commits. **Two of the three are a real bug, not style.**

`components/settings/email-change.tsx` calls `Date.now()` **twice during render**, at
lines 186 and 191:

```tsx
{expiryLine(expiresAt, Date.now()) !== null ? (
  <p …>{expiryLine(expiresAt, Date.now())}</p>
) : null}
```

**The guard and the value are computed from two different clocks.** A render that
straddles the boundary where `expiryLine` flips to `null` — the moment the link expires —
passes the guard and then renders `null` into the paragraph, producing an empty element
where a sentence should be. The window is small and the failure is silent, which is the
combination that keeps a bug alive.

It is also why React's compiler flags it: `Date.now()` in render is impure, so the value
is not stable across a re-render and never updates on its own.

The third error is dead code: `e2e/digest-opt-out.spec.ts:102` defines a `digest()` helper
that nothing calls.

**It also means CI lint is red on this branch or is not gating**, which is worth knowing
separately from the errors.

### F-6 — PRD §10.2 publishes two retention windows for data that does not exist

`EMAIL_DELIVERY_EVENTS` (90 days, *"sent, opened, clicked"*) and `ANALYTICS_AGGREGATES`
(indefinite) are declared in `RetentionCategory` and **used by no model**. There is no
open-and-click store — `apps/delivery/email_api.py` says so — and no analytics vendor
anywhere in the codebase.

`/privacy` already omits them, and `test_the_unimplemented_categories_are_still_unimplemented`
fails if either gains a model. **The PRD still publishes both.** The document and the
product disagree, and the document is the one that is wrong.

### F-7 — §10.2 claims a training-opt-out configuration that does not exist

> *"Where the LLM provider's terms permit opt-out of training-data retention, the system
> is configured to opt out at the API level."*

`adapters/llm/voyage.py` configures nothing of the kind. **The exposure is small** — the
adapter only ever sends public event title and description, so no personal data is at
stake — **but the sentence is false as written**, and anyone answering a due-diligence
questionnaire from §10.2 would answer wrongly.

### The §10.2 requirement that has never been built

> *"Settings → Privacy → 'What we store' displays the categories and current retention
> windows in plain language."*

`app/settings/privacy/page.tsx` renders the FR-22 ranking formula and the danger zone.
**There is no data inventory**, and the page's own header comment has said so since
`run-eventpulse24-048`.

**The expensive half is now done.** `lib/retention-categories.ts` holds the categories in
plain language, pinned to the enforced registry by a backend test. What remains is a
section, not a source.

### The About link — and what else §326 promises

`components/pre-auth/pre-auth-footer.tsx` renders **About** and **Contact** as
`href="#"`. Neither goes anywhere. They are not 404s, so `internal-links.test.ts` does not
see them — `#` is a valid fragment — which is a second blind spot in that guard worth
naming.

**They are not the same case as each other.**

| Link | In the spec? |
|---|---|
| **About** | **Yes.** §326, the canonical footer bullet: *"Login, Privacy, Terms, **About**, social links, city nav, 'Made in [city]' provenance."* |
| **Contact** | **No.** It appears in neither §323 nor §326. Like `/how`, it came from the mockups' chrome. |

So About is an unkept promise and Contact is an invention — the same split `/privacy` and
`/how` turned out to have.

**§326 promises three more things the footer does not have**: social links, city nav, and
"Made in [city]" provenance. Recorded here; whether they are wanted is a product decision,
not a bug to fix quietly.

**Contact is also what the legal pages need.** `/privacy` and `/terms` both ship a
placeholder address with a visible note saying so. A real Contact route, or a real
address, closes that at the same time.

## Success Criteria

- `pnpm lint` exits zero
- The `email-change.tsx` expiry line is computed from one clock, and a test covers the
  boundary it currently renders wrongly
- PRD §10.2 matches the code: the two unimplemented categories are withdrawn or built, and
  the training-opt-out sentence is corrected or implemented — by amendment, with reasoning
- `Settings → Privacy` carries the §10.2 data inventory, built from `RETENTION_ROWS`
- About and Contact each resolve, or are removed, with the choice recorded
- `internal-links.test.ts` is extended to see `href="#"`, so the next placeholder is not
  invisible to it

## Constraints

- **Amendments precede code**, as A-26 did.
- **The data inventory must not restate the retention windows independently.** It reads
  `RETENTION_ROWS`, so the settings page, the privacy policy and the database cannot
  disagree. A second hand-written copy would be a third thing to drift.
- **`email-change.tsx` is a fix, not a redesign.** It shipped in `run-eventpulse24-043`
  and its behaviour is otherwise correct.
- The inventory renders in **all three branches** of the privacy page, as the danger zone
  does: it does not depend on the ranking read, and a section that vanishes when an
  unrelated API blinks is a section that cannot be relied on.

## Out of scope — these need a human, not a run

- **Legal review** of `/terms` and `/privacy`. The draft banner comes off when it is true,
  and not before.
- **Real contact addresses** replacing `privacy@eventpulse24.example` and
  `legal@eventpulse24.example`.
- **§326's social links, city nav and provenance line** — product decisions.
