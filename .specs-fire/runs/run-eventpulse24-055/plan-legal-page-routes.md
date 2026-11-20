# Plan: legal-page-routes

**Run:** run-eventpulse24-055 · **Mode:** confirm · **Complexity:** medium
**Depends on:** none · **Checkpoint:** plan approval (this document)

## What this is

`/terms` and `/privacy` are linked and do not exist. This item builds the two routes, the
chrome, the typography and the draft notice. **The words are `legal-copy-draft`** — kept
separate so plumbing is reviewed as plumbing and claims are reviewed as claims.

## The link count was wrong, and the correction widens this item

The work item said four link sites. **It is six, across two components**, and the sixth is
the one that matters most for where these pages live.

| File | Links |
|---|---|
| `components/auth/signup-form.tsx` | `/terms`, `/privacy` |
| `app/signin/page.tsx` | `/terms`, `/privacy` |
| **`components/pre-auth/pre-auth-footer.tsx`** | **`/privacy`** |

`PreAuthFooter` renders on **eight surfaces**: both auth screens (via `AuthPageShell`),
`/preview`, `/pricing`, `/events/[id]`, `/events-in/[slug]`, and both of those routes'
`not-found.tsx`. So `/privacy` 404s from the footer of every public page, not only at
signup — and `EXPERIENCE.md` §323 **specifies** that footer: *"the page footer carries
secondary affordances (Log in, Privacy, Terms, social links)."*

**That settles the chrome question.** These are pre-auth surfaces by spec, not by
inference: the footer that links them is the pre-auth footer, and the page it links to
has to belong to the same family.

## A fourth dangling route, found and fenced: `/how`

The same footer links **"How it works" → `/how`**, which does not exist.

**It was missed by the first version of `internal-links.test.ts`** — the matcher read the
JSX form `href="/x"`, and the footer holds its links in an object literal
(`{ href: "/how", label: "How it works" }`). The matcher now accepts `href` followed by
either `=` or `:`, and `/how` is the only route the widened pass adds. The correction is
recorded in TRACEABILITY F-1 rather than quietly folded in.

**`/how` has no requirement behind it.** §323 lists the footer's affordances as *"Log in,
Privacy, Terms, social links"* — "How it works" appears in that section only as something
that must **not** be in the topbar. The footer's own comment says the list came from the
mockups.

It is **fenced in `UNBUILT` and undecided**, not scheduled — see *Decision asked for*.

## Steps

1. **`app/terms/page.tsx`** and **`app/privacy/page.tsx`** — static, public, no session
   read, no `force-dynamic`. Neither may redirect to onboarding; `lib/session.ts` routes
   unauthenticated visitors to `/preview` or `/onboarding` and these routes must not
   participate in that.
2. **A shared `components/legal/legal-page.tsx`** — `BrandTopbar`, the draft banner, a
   reading-width article, `PreAuthFooter current={...}` so the footer marks its own row
   with `aria-current="page"`. Reuses `AuthPageShell`'s frame structure but **not**
   `AuthPageShell` itself: that component centres a 480 px card for *"single-decision, not
   content-rich"* forms, which is the opposite of a long document.
3. **The draft banner** — a visible block above the first clause stating the text is an
   unreviewed draft describing current behaviour, not legal advice, and not reviewed by
   counsel. Not a footnote.
4. **`lastUpdated`** — one exported constant consumed by both pages. Two hand-typed dates
   drift, and a stale date on a policy is a factual claim that is wrong.
5. **Typography and anchors** — `--layout-container-reading`, real `h2`/`h3` hierarchy,
   `id` on each section so a clause can be cited.
6. **Placeholder body** — one honest paragraph per page until `legal-copy-draft` lands.
   **Not lorem, not empty.** A blank page reads as broken; a page that says what it is
   reads as honest. These routes ship in the same run, so this state is short-lived, but
   it must be correct on its own.
7. **`tests/internal-links.test.ts`** — remove `/terms` and `/privacy` from `UNBUILT`.
   **The reverse assertion forces this**: it fails the moment either route exists, so this
   step cannot be forgotten.
8. **Tests** — both routes render; the draft banner is present; the footer's `/privacy`
   row carries `aria-current`; no session is read.

## Verification

- `pnpm vitest run` green, full suite
- `tsc --noEmit` clean
- The banner assertion proved by removing the banner once and watching it fail
- Routes reachable with no cookie — asserted, not assumed

## Indexability

`robots.ts` allows `/` and disallows only the authed and dev prefixes, so both routes are
crawlable by default, which is right for legal pages. `app/sitemap.xml/route.ts` is a
**sitemap index** over event children and carries no static marketing routes — `/pricing`
and `/preview` are absent too. So **no sitemap change**, and the existing default is the
deliberate choice, recorded here.

## Risks

- **`AuthPageShell` reuse would be wrong.** Its 480 px card is spec'd for auth forms; a
  policy rendered into it would be a column of legal text 480 px wide.
- **The footer links `/privacy`, so these pages link to themselves.** `current` must be
  passed or the footer row on `/privacy` will look like any other link.
- **No mockup exists** for either page, and `/settings/privacy` is a different surface
  entirely (privacy *settings*, built by run-048). Do not borrow its layout.

## Decision asked for

**What happens to `/how`?** It is a dead link on eight surfaces, with no spec requirement.
Same three options FR-8's link had: build it, remove it, or leave it fenced and decide
later. Removing it needs no amendment — unlike `/suggest`, no FR or §-section asks for it.
