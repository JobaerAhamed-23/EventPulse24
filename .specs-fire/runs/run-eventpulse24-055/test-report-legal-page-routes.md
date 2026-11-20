# Test Report: legal-page-routes

**Run:** run-eventpulse24-055 · **Date:** 2026-11-20 · **Result:** PASS

## Suite

| Scope | Files | Tests | Result |
|---|---|---|---|
| Full frontend suite | 177 | 2843 | **all pass** |
| New: `tests/legal-pages.test.tsx` | 1 | 11 | all pass |

`tsc --noEmit` clean. `pnpm lint` unchanged at 5 pre-existing problems; the new files
contribute none.

## The fence did its job, and that is the headline

`internal-links.test.ts` carried `/terms` and `/privacy` in `UNBUILT` with a reverse
assertion. The moment the two routes were created, **it failed on its own exception**:

```
AssertionError: expected [ '/terms', '/privacy' ] to deeply equal []
```

That is the mechanism working exactly as designed — the fence could not outlive the gap
it covered, and the removal could not be forgotten.

**`UNBUILT` is now gone entirely.** `/how` left it too: with the footer row removed,
nothing links there, so there is no exception left to hold. **Every internal link in the
app resolves, with no allow-list.**

## Tests added

| Test | Asserts |
|---|---|
| renders, with its own title | both routes render an `h1` |
| says it is an unreviewed draft, above the first clause | the banner exists, names "unreviewed draft" and "not been reviewed by a lawyer", **and precedes the first `section` in source order** |
| dates itself from the one shared constant | both read `LEGAL_LAST_UPDATED` |
| gives every clause an id | every `article section` has a non-empty `id` |
| carries the pre-auth footer and marks its own row | the page's own footer row has `aria-current="page"` |
| does not offer a route that was never specified | no "How it works" link |

**The banner assertion was proved by deleting the banner** and re-running: both pages
failed, then passed on restore. It is the one element whose removal would change what the
page claims about itself, so a test that could not fail on it would be worthless.

## Three existing tests failed, and all three were right to

**None was a flake, and none was "fixed" by weakening it.**

### 1. `tests/spacing-scale.test.ts` — `mt-10` is not on the scale

```
components/legal/legal-page.tsx:85 mt-10
```

`styles/tokens.css` declares 0, 1, 2, 3, 4, 6, 8, 12, 16, 20, 30. **This is the design
system catching an invented spacing value**, which is what it is for. Changed to `mt-12`.
The guardrail was right and the code was wrong.

### 2. `components/brand-topbar.test.tsx` — required the "How it works" link

```ts
expect(screen.getByRole("link", { name: "How it works" })).toHaveAttribute("href", "/how");
```

**The test was pinning a 404 in place**, exactly as `app/page.test.tsx` had been pinning
`/suggest`. Flipped to `queryByRole(...)).toBeNull()`, with the reasoning recorded inline.

### 3. `app/signin/page.test.tsx` — ambiguous "Terms" link

`getByRole("link", { name: "Terms" })` began matching **two** elements once the footer
gained its Terms row. Scoped to `within(screen.getByRole("main"))`, because the assertion
is about the consent footnote under the form, not the footer. **The ambiguity was real
information**, not noise: it is how the test told us the page now has two Terms links.

## A spec gap found while testing, and closed

`EXPERIENCE.md` §323 names the pre-auth footer's secondary affordances as *"Log in,
Privacy, **Terms**, social links."* **The footer had no Terms row.** It was named in
`pre-auth-footer.tsx`'s own header prose — *"'How it works', Privacy and Terms point at
routes that do not exist yet"* — and absent from the `LINKS` array, so the footer has
fallen short of §323 for as long as it has existed, and the comment described a link that
was never there.

The row was added next to Privacy, where §323 puts it. **This is a scope addition beyond
the plan's eight steps**, taken because the spec is explicit, the route now exists, and
the test written for this item surfaced it directly.

## Acceptance criteria

| Criterion | Status |
|---|---|
| `/terms` and `/privacy` exist; all links resolve | ✔ six link sites across three files |
| Pre-auth chrome | ✔ `BrandTopbar` + `PreAuthFooter`, per §323 |
| No session read; no redirect to onboarding | ✔ static routes, no `getSession` import |
| Visible draft banner above the first clause | ✔ asserted, including source order |
| Last-updated from a single source | ✔ `lib/legal.ts` |
| Reading measure, heading hierarchy, anchor ids | ✔ `--layout-container-reading`, `h1`/`h2`, `id` per section |
| Keyboard/screen-reader reachable | ✔ semantic `article`/`section`/`aside`, labelled notice |
| Route-level test with a failable banner assertion | ✔ proved |
| `UNBUILT` entries removed | ✔ set deleted entirely |
| sitemap/robots reviewed | ✔ no change — reasoning recorded below |

## Indexability — reviewed, deliberately unchanged

`robots.ts` allows `/` and disallows only the authed and dev prefixes, so both routes are
crawlable, which is correct for legal documents. `app/sitemap.xml/route.ts` is a **sitemap
index over event children** and carries no static marketing routes — `/pricing` and
`/preview` are absent too, so adding only the legal pages would be inconsistent with the
file's shape. **No change is the decision, not the default.**
