# Walkthrough: run-eventpulse24-055

**Intent:** The links that lead nowhere — `/suggest`, `/terms`, `/privacy`
**Scope:** wide, 3 items · **Branch:** `feature/broken-links-and-legal-pages`
**2026-11-20**

## How this started

> *"i see some page give me 404 when no digest exist it show a suggest event button when
> i click it give 404."*

One user, one dead link. The scan that followed found **four** dangling destinations
across **six** link sites, two of them under a sentence asking people to agree to
documents the product then refused to show them.

## What shipped

| Commit | Item |
|---|---|
| `049ce62` | `fr8-suggest-link-removal` |
| `9f3f295` | `legal-page-routes` |
| *(this)* | `legal-copy-draft` |

### 1. The reported bug — `/suggest`

Withdrawn, not built. **Amendment A-26.** `/suggest` existed in no layer: no FR, no model,
no endpoint, no table, no admin. The route was never built because it was never specified
beyond the word "link".

`digest-empty.tsx` had argued in its own header that a real link beats a disabled control
and beats an inert button. On those three options it was right. **The fourth — not making
the promise — was never on the list.**

A-26 withdrew it from all three places the spec named it, including an unbuilt
`/preview` SEO-referrer placement, so a later build could not plant the same dead link on
a second surface. §5's rationale for that placement is preserved verbatim: it is the
revisit condition, and it is **unfunded rather than refuted**.

### 2. The compliance gap — `/terms` and `/privacy`

Both routes built, pre-auth chrome, visible draft banner above the first clause, citable
section ids, one shared `lastUpdated`.

They are pre-auth surfaces **by specification**: `EXPERIENCE.md` §323 names this footer's
affordances as *"Log in, Privacy, Terms, social links."*

### 3. The words

Written from running code, not from the PRD. Ten sections on `/privacy`, nine on `/terms`,
with a claim-to-evidence table in the test report for every factual statement.

## What the run found that nobody was looking for

### `/how` — the furthest-reaching dead link in the product

The pre-auth footer linked "How it works" to a route that never existed, on **eight
surfaces**. **No spec asks for it** — §323 does not list it, and names it only as something
that must not sit in the topbar. Removed, not built.

### The footer did not meet §323

Terms was named in `pre-auth-footer.tsx`'s own header prose and **absent from its link
array**. The footer had fallen short of §323 for as long as it existed, and the comment
described a link that was never there. Row added.

### PRD §10.2 publishes two windows for data that does not exist

`EMAIL_DELIVERY_EVENTS` (90 days, "sent, opened, clicked") and `ANALYTICS_AGGREGATES`
(indefinite) **have no models**, and there is no analytics vendor anywhere. The product
does not track opens or clicks. Omitted from the published table; a time bomb fails if
either gains a model.

### §10.2 claims a training-opt-out configuration that does not exist

`adapters/llm/voyage.py` configures none. Voyage receives only public event text, so the
exposure is small — but the claim is wrong, and a due-diligence answer drawn from §10.2
would be wrong with it. Not repeated on the page, and a test asserts the silence.

## Two corrections to my own work, recorded rather than quietly fixed

**1. "Nothing guards against dangling links" was false.**
`tests/digest-home-boundary.test.ts` had resolved hrefs against the app directory for some
time, and even fenced `/suggest` with a reverse assertion. What it lacked was **reach** —
fifteen files. The user had declined a link test offered as new work; it was re-offered
with the real cost and approved.

**2. "Three dangling destinations, and no others" was wrong — it is four.**
The test written to catch this class **missed `/how` on its first pass**: its matcher read
the JSX form `href="/x"`, and the footer stores links in an object literal. A
source-matching test is only as good as the forms it matches, and the first version was
blind to the commonest way this codebase holds a route — in a table. Matcher widened,
`TRACEABILITY.md` F-1 corrected.

**3. A bug in the seam test itself.** `test_every_category_in_use_is_published` never
subtracted the published rows. Loud, so caught in seconds — but reversed it would have
passed while asserting nothing, guarding a legal page nobody checks by hand.

## The guards left behind

- **`tests/internal-links.test.ts`** — every literal internal `href` under `app/**` and
  `components/**` resolves to a real route. **Zero exceptions**; `UNBUILT` was deleted
  once the last gap closed, and the comment in its place tells a future author to restore
  the set *with its reverse assertion* rather than delete an entry from `missing`.
- **`backend/tests/shared/test_retention_published.py`** — the published retention table
  must match the enforced registry, in both directions, plus a time bomb on the two
  unimplemented categories.
- **`tests/legal-pages.test.tsx`** — the draft banner, its position above the first
  clause, the 30-day figure, the surviving categories, and the absence of a
  training-opt-out claim.

**Every new or flipped assertion was proved to fail on purpose.**

## Results

| Suite | Tests | Result |
|---|---|---|
| Frontend | 2847 (177 files) | pass |
| Backend | 7666 | pass (877s) |

`tsc --noEmit` clean · `ruff check` clean · `pnpm lint` unchanged at 5 pre-existing problems

## Still open, for a human

1. **Three lint errors committed on this branch** (F-4) — two *"Cannot call impure
   function during render"* in `components/settings/email-change.tsx`, one unused variable
   in `e2e/digest-opt-out.spec.ts`. Pre-existing, out of scope all three times it was
   raised. **CI lint is either red here or not gating.**
2. **PRD §10.2 needs amending** to drop the two unimplemented retention categories, or the
   stores need building. (F-6)
3. **§10.2's training-opt-out sentence** describes configuration that does not exist. (F-7)
4. **Legal review** of both documents. The banner says so; it should come off only when it
   is true.
5. **Real contact addresses** replacing the two marked placeholders.
6. **`Settings → Privacy → "What we store"`** — §10.2 requires a data inventory in plain
   language on that route and it is unbuilt. `RETENTION_ROWS` now exists and is exactly
   what it needs; the remaining work is a section, not a source.
