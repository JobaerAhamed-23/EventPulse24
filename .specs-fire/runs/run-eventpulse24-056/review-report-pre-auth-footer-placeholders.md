# Review Report: pre-auth-footer-placeholders

**Run:** run-eventpulse24-056 · **Verdict:** PASS

## Scope

**Created** — `app/about/page.tsx`, `app/contact/page.tsx`,
`components/pre-auth/prose-page.tsx`, `tests/prose-pages.test.tsx`.
**Modified** — `components/pre-auth/pre-auth-footer.tsx`,
`components/legal/legal-page.tsx` (now composes `ProsePage`),
`tests/internal-links.test.ts` (+ placeholder rule).

## Checks

| Check | Result |
|---|---|
| Frontend suite | 2865 pass (179 files) |
| `tsc --noEmit` | exit 0 |
| `pnpm lint` | exit 0 |
| Legal page tests after refactor | 15 pass, **unchanged** |

## Auto-fixes applied

**None.**

## Findings

### F-11 — the link guard's second blind spot, now closed

`#` was invisible to a test written to find exactly this class of problem. **The guard has
now been wrong twice**: once about where hrefs live (object literals, which hid `/how`),
once about what counts as a dead link (`#`, which hid About and Contact).

**Both were found by a person, not by the suite.** That is the honest status of this
guard: it is good at the cases it has been taught and has needed teaching twice in two
days. It now covers JSX attributes, object literals, `/`-routes, `#`, empty hrefs and
`javascript:`, and the remaining known gap is named in its own docstring — a route built
at runtime or returned by a helper is still invisible.

### F-12 (closed) — About was promised by §326 and never built

Unlike `/how`, which was removed because no section asked for it, About is named in the
canonical footer bullet. It needed a page, not an amendment, and now has one.

### §326 remains partly unmet — recorded, not closed

Social links, city nav and the "Made in [city]" provenance line. Product decisions: no
social accounts are named anywhere in the repo, and city nav may be redundant against the
existing `/events-in/[slug]` surface.

## Observations, no action

- **`LegalPage` composing `ProsePage` is the right seam.** The alternative — a second
  frame for About and Contact — would have duplicated the topbar, reading column and
  footer, and the two would have drifted. That the 15 legal assertions pass unchanged,
  including the banner's source-order check, is the evidence the extraction preserved
  behaviour.
- **Contact's content is mostly links back into the product**, deliberately. A contact
  page whose first answer is "export it yourself, here" serves the reader better than one
  that routes everything through an inbox — and it is the only honest shape while the
  addresses are still placeholders.
- **The placeholder addresses are now stated in three places** — `/privacy`, `/terms` and
  `/contact` — each marked. Replacing them is a single sweep when real inboxes exist, and
  a test asserts Contact's marking survives.
- **About makes no claim the product does not keep.** One notification a day, three cards,
  no open tracking, no data sales: each is either implemented or documented in the privacy
  policy, which was itself written from the code.

## Conclusion

Complete and green. The pre-auth footer now has no link that goes nowhere, and the guard
can see the kind that hid.
