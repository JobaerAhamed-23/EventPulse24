# Review Report: legal-page-routes

**Run:** run-eventpulse24-055 · **Date:** 2026-11-20 · **Verdict:** PASS

## Scope

**Created**

| File | Purpose |
|---|---|
| `app/terms/page.tsx` | `/terms` route |
| `app/privacy/page.tsx` | `/privacy` route |
| `components/legal/legal-page.tsx` | shared frame + `LegalSection` |
| `lib/legal.ts` | `LEGAL_LAST_UPDATED`, one source for both dates |
| `tests/legal-pages.test.tsx` | 11 tests |

**Modified** — `components/pre-auth/pre-auth-footer.tsx` (removed `/how`, added `/terms`),
`tests/internal-links.test.ts` (widened matcher, `UNBUILT` deleted),
`components/brand-topbar.test.tsx`, `app/signin/page.test.tsx`,
`_bmad-output/.../TRACEABILITY.md` (F-1 corrected).

## Checks

| Check | Result |
|---|---|
| Full suite | 177 files / 2843 tests, pass |
| `tsc --noEmit` | clean |
| `pnpm lint` | 5 problems, all pre-existing; new files contribute none |
| Spacing scale | ✔ after fixing `mt-10` → `mt-12` |
| Brownfield rules | ✔ frame structure follows `AuthPageShell`; `PreAuthFooter` and `BrandTopbar` reused, not reimplemented |

## Auto-fixes applied

- **`mt-10` → `mt-12`** in `legal-page.tsx`. Mechanical, caught by `spacing-scale.test.ts`,
  no semantic effect. Tests re-run after.

## Findings

### F-2 (corrected during this run) — my own count of dangling links was wrong

The intent brief, the item-1 commit message and TRACEABILITY F-1 all stated **three**
dangling destinations across five link sites, "and no others". It is **four across six**.

`PreAuthFooter` also links `/privacy`, and links `/how`, which has no route. The miss was
in the first version of `internal-links.test.ts`: its matcher read the JSX attribute form
`href="/x"` and the footer stores its rows in an object literal,
`{ href: "/how", label: "How it works" }`. **A source-matching test is only as good as the
forms it matches, and the first version was blind to the commonest way this codebase holds
a route — in a table.** The matcher now accepts `href` followed by `=` or `:`.

Corrected in `TRACEABILITY.md` rather than left standing. `lib/settings-sections.ts` holds
exactly such a table; every row resolves today, and the widened matcher now reads it.

### F-3 (closed) — the pre-auth footer did not meet §323

`EXPERIENCE.md` §323 requires *"Log in, Privacy, Terms, social links"*. The `LINKS` array
had no Terms row, while the file's own header comment discussed Terms as though it did.
**A comment describing a link that does not exist is worse than no comment**, because it
is read as evidence. Row added, comment corrected.

### F-4 (open, carried from item 1) — three lint errors committed on this branch

Unchanged: two *"Cannot call impure function during render"* in
`components/settings/email-change.tsx` (186, 191) and one unused variable in
`e2e/digest-opt-out.spec.ts:102`. Pre-existing, out of scope, still raised.

## Observations, no action

- **`/privacy` vs `/settings/privacy`.** Two different surfaces with adjacent names: the
  public policy and the signed-in privacy settings screen. Both files' headers say so
  explicitly, which is the cheapest guard against a future edit to the wrong one.
- **The placeholder bodies make only verified claims.** The privacy page states no
  model-training and no data sales; `backend/` contains no training or fine-tuning path,
  and both are PRD §10.2 absolutes. It also says export and deletion are available today —
  `app/settings/account` (FR-52 export) and `app/settings/privacy` (danger zone) both
  exist. **No claim about the LLM provider's own training-retention opt-out was made**,
  because that was not verified; `legal-copy-draft` must check `adapters/llm/` before
  making it.
- **`UNBUILT` is gone and that is worth protecting.** The comment left in its place tells
  a future author to restore the set *with its reverse assertion* rather than deleting an
  entry from `missing`, which is the shortcut that would quietly re-admit a dead link.

## Conclusion

Complete and green. The item exceeded its plan by one step — the §323 Terms row — which is
recorded above rather than absorbed.
