# Plan: fr8-suggest-link-removal

**Run:** run-eventpulse24-055 · **Mode:** confirm · **Complexity:** low
**Checkpoint:** plan approval (this document)

## What this is

`/suggest` has never existed. One link points at it, and clicking it 404s — the bug the
user reported. The code change is a deleted paragraph. **The deliverable is Amendment
A-26**, which records why an MVP FR's element is being withdrawn rather than deferred.

## What the scan changed about the shape of this item

Three things turned up that the work item did not know when it was written.

### 1. The spec promises `/suggest` in three places, not one

| Source | What it promises | Built? |
|---|---|---|
| `prd.md` FR-8 | the empty-state card carries *"a 'Suggest an event' link"* | yes — and it 404s |
| `EXPERIENCE.md` §5 L517 | empty Pulse Digest: `Text.Meta` link opening *"a `/suggest` form (PRD FR-8)"* | yes — same link |
| `EXPERIENCE.md` §5 L522 + §2 L78 | empty **Preview**, SEO referrers only: link to `/suggest?city={city}` | **no — never built** |

`components/preview/preview-section.tsx:242` renders *"No preview available in {city} yet."*
and no link at all. So the preview promise is unkept rather than broken, and it does not
404 today — **but it is live spec**, and a later build picking it up would reintroduce the
same dead link on a second surface. An amendment that withdraws only the digest reference
leaves that loaded.

**§5 L522 is also the strongest argument the product has for ever building `/suggest`**, and
A-26 should say so rather than bury it. Its rationale is specific: a cold visitor arriving
from Google *"events near me {city}"* in a city with no coverage needs a way to express
interest, and the link is shown **only** to search-engine referrers precisely so the No-CTA
Discipline holds for everyone else. That is a real argument, and withdrawing it costs
something. It is withdrawn here because the form it opens does not exist in any layer —
not because the reasoning is bad.

### 2. A link-resolution test already exists, and it already fences `/suggest`

`frontend/tests/digest-home-boundary.test.ts:349` resolves every literal internal `href`
in the home surface's 15 files against `app/**/page.tsx` or `route.ts`. `/suggest` sits in
an `UNBUILT` set with a **reverse assertion** that fails if the route is ever built.

**This item must therefore edit that test, not merely survive it.** Removing the link
makes the exception, its reverse assertion and ~8 lines of comment describe nothing.

It also explains the blind spot: `FILES` covers the digest home only, which is why
`/terms` and `/privacy` were never resolved. **Widening it is re-offered at this
checkpoint** — see *Decision asked for* below.

### 3. Exactly one rendering test asserts the link

`app/page.test.tsx:312-313` — `getByRole("link", { name: "Suggest an event" })` and an
`href` assertion. It flips to an absence assertion.

## Steps

1. **Write Amendment A-26** — withdrawing `/suggest` from all three spec references.
   Content: the link is withdrawn, not deferred; no suggestion feature exists in any layer
   (no FR, model, endpoint, table or admin), so the link can only resolve to a 404; §5
   L522's SEO cold-start rationale is recorded verbatim as the condition under which this
   is revisitable. Lands inline at FR-8 in `prd.md`, in the form A-25 used at `prd.md:773`.
2. **Apply A-26 to `EXPERIENCE.md`** — §5 L517, §5 L522 and the §2 L78 IA row, plus an
   `updated_note` entry in the frontmatter, matching how A-24 was recorded there.
3. **`components/digest/digest-empty.tsx`** — delete the `<p className="mt-1">` wrapper and
   its `Link`; drop the now-unused `import Link from "next/link"`; rewrite the header
   comment, which currently argues at length *for* the link's existence.
4. **`app/page.test.tsx:312-313`** — assert no link is rendered in the empty state.
5. **`tests/digest-home-boundary.test.ts`** — remove `/suggest` from `UNBUILT`, remove the
   now-empty reverse assertion, rewrite the comment block that explains the exception.
6. **Traceability note** — record FR-8's withdrawal against its two matrix rows so the next
   regeneration reads the absence as A-26 rather than as a regression.

## Verification

- `pnpm vitest run app/page.test.tsx tests/digest-home-boundary.test.ts` green
- Full frontend suite green — Node 24 required (`export PATH=$HOME/.nvm/versions/node/v24.22.1/bin:$PATH`)
- `grep -rn "/suggest" frontend/` returns nothing outside `.specs-fire/`
- **Each changed assertion is made to fail once** before it is accepted — the absence
  assertion in step 4 passes trivially against an empty render, so it is proved by
  temporarily restoring the link

## Files

| File | Change |
|---|---|
| `_bmad-output/.../prd.md` | A-26 inline at FR-8 |
| `_bmad-output/.../EXPERIENCE.md` | §5 L517, §5 L522, §2 L78, frontmatter `updated_note` |
| `frontend/components/digest/digest-empty.tsx` | link + import + header comment |
| `frontend/app/page.test.tsx` | presence assertion → absence |
| `frontend/tests/digest-home-boundary.test.ts` | `UNBUILT` exception + comment |
| `_bmad-output/.../TRACEABILITY.md` | FR-8 rows noted |

## Risks

- **Amendment numbering.** A-25 is the highest in use. Numbers are easiest to miss inside
  EXPERIENCE.md's `updated_note`, which is one very long line holding A-9 through A-24.
  Verified A-26 free; re-check before writing.
- **EXPERIENCE.md §5 copy is locked.** This is a subtraction. The headline and the
  `No qualifying events in {city}.` line must come out byte-identical.
- **Scope creep toward `/preview`.** A-26 withdraws the preview promise *in the spec*. It
  does **not** touch `preview-section.tsx`, which has no link to remove.

## Decision taken at checkpoint (2026-11-20) — APPROVED

**Widen `digest-home-boundary.test.ts`'s link resolution to the whole app, in this item?**

The earlier offer of a link test was declined when it was described as new work. That
description was wrong: the test exists, it is well built, and its loop is ~15 lines. The
change is to run it over `app/**` and `components/**` instead of 15 named files — most
likely lifted into its own `tests/internal-links.test.ts` so the home-surface file keeps
its subject.

It would have caught all three links in this intent. Without it, `/terms` and `/privacy`
stay unguarded until `legal-page-routes` builds them, and the next dangling link is found
by a user again.

Cost: roughly one file, plus whatever it turns up — and it may well turn up more than the
three known links, which would be a finding, not a failure.

**Approved: widen it now, inside this item.** The resolving loop is lifted into
`frontend/tests/internal-links.test.ts` covering `app/**` and `components/**`;
`digest-home-boundary.test.ts` keeps its home-surface subject and loses the `/suggest`
exception. Step 5 below is extended accordingly, and step 7 is added:

7. **`frontend/tests/internal-links.test.ts`** — new. Every literal internal `href` under
   `app/**` and `components/**` resolves to a `page.tsx` or `route.ts`. Dynamic segments
   skipped as before. Any route it finds dangling beyond the three known is reported, not
   silently allowed.
