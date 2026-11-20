# Test Report: pre-auth-footer-placeholders

**Run:** run-eventpulse24-056 · **Date:** 2026-11-20 · **Result:** PASS

| Check | Result |
|---|---|
| Frontend suite | 179 files / **2865** tests, pass |
| `tsc --noEmit` | exit 0 |
| `pnpm lint` | exit 0 |
| New: `tests/prose-pages.test.tsx` | 11 pass |
| `tests/internal-links.test.ts` | 2 pass (was 1) |

## What was wrong

`pre-auth-footer.tsx` rendered **About** and **Contact** as `href="#"` on **eight
surfaces** — both auth screens, `/preview`, `/pricing`, the public event and city pages,
and both not-found pages.

**Neither was visible to the link guard.** It resolves hrefs beginning with `/`; a `#` is
a valid fragment, not a broken route. So the guard was right not to call it a 404 and
wrong to say nothing — and a page `EXPERIENCE.md` §326 explicitly promises stayed unbuilt
with nothing going red, until a user asked what the About link did.

**This is the second blind spot in that guard in two runs.** The first was object-literal
hrefs, which hid `/how`. Both were found by a human looking, not by the test.

## Both pages built

| Page | Spec | Why built |
|---|---|---|
| `/about` | **§326 canonical:** *"Login, Privacy, Terms, **About**, social links, city nav"* | promised and never built |
| `/contact` | **none** — in neither §323 nor §326 | the footer linked it on eight surfaces, and `/privacy` and `/terms` needed a real destination for their placeholder addresses |

About's copy comes from PRD §1 (calm-intelligence positioning) and §15.2 (*"No ads. No
commissions. No data sales."*). Contact's shape is deliberately mostly in-product routes:
reporting a listing, exporting data and deleting an account are all things a user can do
immediately, which is more useful than an address that answers in three days.

## The frame was extracted rather than duplicated

`components/pre-auth/prose-page.tsx` now holds the chrome every pre-auth prose surface
shares, and **`LegalPage` composes it**, adding only the draft banner and the last-updated
date — a legal document's contract, not a general one's. An About page carrying "not
reviewed by a lawyer" would be a category error.

**The refactor is verified by the existing tests**: all 15 `legal-pages.test.tsx`
assertions pass **unchanged**, including the one asserting the banner precedes the first
section in source order.

## Tests, and the proof they fail

### The placeholder guard

Restored `href="#"` on About:

```
× links to no placeholder, either
+ ["components/pre-auth/pre-auth-footer.tsx → #"]
```

It rejects `#`, empty hrefs and `javascript:`. The comment directs a future author who
needs a deliberate placeholder to add an allow-set **with a reverse assertion**, rather
than dropping the entry — the idiom that forced `/terms` and `/privacy` to be built.

### The page tests

| Test | Asserts |
|---|---|
| renders with its own heading | both pages |
| carries the pre-auth footer and marks its own row | `aria-current="page"` on each page's own row |
| gives every section an id | citable sections |
| **carries no draft banner** | `ProsePage` vs `LegalPage` — the distinction the refactor exists to hold |
| about states the business model | §15.2's line, because the calm bet is only credible if the money is not from attention |
| contact points at in-product routes | `/settings/account`, `/settings/privacy` |
| contact marks its addresses as placeholders | the same honesty the legal banner carries |

## Acceptance criteria

| Criterion | Status |
|---|---|
| About resolves | ✔ built — no amendment needed, §326 asked for it |
| Contact resolves | ✔ built |
| No `href="#"` in the pre-auth footer | ✔ |
| Guard extended to `#`, empty and `javascript:` | ✔ across `app/**` and `components/**` |
| Extension proved to fail | ✔ |
| Legal pages point at a real contact route | ✔ `/contact` is linked from the footer on both; their addresses stay marked placeholders |
| §326's further unmet promises recorded | ✔ below |

## §326's three remaining unmet promises

Recorded, **not built and not dropped**: **social links**, **city nav**, and the
**"Made in [city]" provenance** line. All three are product decisions — there are no
social accounts named anywhere in the repo, and city nav overlaps `/events-in/[slug]`,
which already exists and may make it redundant.
