# Walkthrough: run-eventpulse24-056

**Intent:** The findings run-055 raised and did not close — plus the About link
**Scope:** wide, 4 items · **Branch:** `feature/broken-links-and-legal-pages` · 2026-11-20

## What this run was for

Run-055 was scoped to 404s. It found six things that were not 404s and raised them rather
than absorbing them. This run closes four of them, and settles the two `#` placeholders
the user asked about.

## 1. The lint errors were a real bug

`pnpm lint` had exited non-zero since `run-eventpulse24-043` — **twelve commits**,
including three in run-055 whose reviews recorded it as pre-existing and moved on.

Two of the three errors were one defect:

```tsx
{expiryLine(expiresAt, Date.now()) !== null ? (
  <p …>{expiryLine(expiresAt, Date.now())}</p>
) : null}
```

**One sentence, two clocks.** The guard reads `T`, the body reads `T + ε`. If the link
expires inside `ε`, the guard sees a live link, lets the paragraph render, and the
paragraph prints *"That link has expired."* Crossing a minute boundary gives the milder
version: a guard that saw 2 minutes above a body that prints 1.

Fixed with one read on mount. **No `eslint-disable`** — the compiler rule was correct.
**No ticking countdown** — that is a different product decision, and it is recorded in the
source so nobody later reads the frozen sentence as an oversight.

The first test asserts the property rather than a symptom: `expected 2 to be less than or
equal to 1`.

**`pnpm lint` now exits 0.**

## 2. The PRD claimed things the code does not do

**A-27 — two retention windows for data that does not exist.** §10.2 published
`EMAIL_DELIVERY_EVENTS` (90 days, *"sent, opened, clicked"*) and `ANALYTICS_AGGREGATES`
(indefinite). **No model declares either**, and there is no analytics vendor in the
repository at all. The product collects *less* than the document said — the right
direction for an error, and still an error, because §10.2 is published to users through
`/privacy`.

**A-28 — an opt-out that was never configured.** §10.2 stated the system is configured to
opt out of the LLM provider's training-data retention. `voyage.py` configures nothing. The
replacement is a stronger claim and a true one: **no personal data reaches the provider at
all.**

Both bullets are struck through in place rather than deleted, so a reader comparing an old
copy can see what moved.

## 3. §10.2's oldest unkept requirement

> **User-visible data inventory:** Settings → Privacy → "What we store" displays the
> categories and current retention windows in plain language.

It predates every FIRE intent in this repository and had no surface. It has one now, and
**it reads `RETENTION_ROWS` rather than restating the windows** — so the schema, the public
policy and the settings screen share one source, pinned to the database by a backend test.

**Run-055 is why this was cheap.** `RETENTION_ROWS` was built to make the *public* policy
true; this is a second consumer. Built first, it would have needed its own source, and
would now be a third copy free to drift.

## 4. About and Contact — what the user asked about

Both rendered as `href="#"` on **eight surfaces**.

**Neither was visible to the link guard.** It resolves hrefs starting with `/`; `#` is a
valid fragment. Right not to call it a 404, wrong to say nothing — so a page §326
explicitly promises stayed unbuilt with nothing going red.

They were not the same case:

- **About is named by §326's canonical footer bullet.** Promised, never built. Copy drawn
  from PRD §1 and §15.2.
- **Contact appears in no section**, like `/how`. Built anyway, because the footer linked
  it on eight surfaces and the legal pages needed somewhere real to point.

The frame was **extracted, not duplicated**: `ProsePage` holds the shared chrome and
`LegalPage` composes it, adding only the draft banner and date. All 15 legal assertions
pass unchanged, which is the evidence the extraction preserved behaviour.

## The guard has now been wrong twice

Once about **where** hrefs live — object literals, which hid `/how`. Once about **what
counts as a dead link** — `#`, which hid About and Contact.

**Both were found by a person, not by the suite.** That is its honest status: good at the
cases it has been taught, and it has needed teaching twice in two days. It now covers JSX
attributes, object literals, `/`-routes, `#`, empty hrefs and `javascript:`. The remaining
known gap is named in its own docstring — a route built at runtime or returned by a helper
is still invisible.

## Results

| Suite | Tests | Result |
|---|---|---|
| Frontend | 2865 (179 files) | pass |
| Backend `tests/shared` + `tests/identity` | 753 | pass |
| `tsc --noEmit` | — | exit 0 |
| `pnpm lint` | — | **exit 0**, first time since run-043 |

## Still open, for a human

1. **Legal review** of `/terms` and `/privacy`. The banner comes off when it is true.
2. **Real contact addresses** replacing the placeholders now marked in three places —
   `/privacy`, `/terms` and `/contact`. One sweep when inboxes exist.
3. **F-8 — CI lint was red for twelve commits and nothing stopped.** The baseline is clean
   now, which is the only cheap moment to make it gating.
4. **§326's remaining promises:** social links, city nav, "Made in [city]" provenance. No
   social accounts are named in the repo, and city nav may be redundant against
   `/events-in/[slug]`.
5. **`EXPERIENCE.md` §2 row 9 is still open** on `/settings/privacy`: the A-14 geo-IP
   consent toggle, the A-13 amendment-history timeline, and the Sources mirror.
