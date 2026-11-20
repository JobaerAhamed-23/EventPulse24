---
id: pre-auth-footer-placeholders
title: About is promised by §326 and goes nowhere; Contact is in no spec at all
intent: spec-debt-and-open-findings
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-11-20
run_id: run-eventpulse24-056
completed_at: 2026-11-20T12:23:48.600Z
---

# Work Item: The two links that go to `#`

## Description

`components/pre-auth/pre-auth-footer.tsx` renders two rows as `href="#"`:

```ts
{ href: "#", label: "About" },
{ href: "#", label: "Contact" },
```

Both render on **eight surfaces** — both auth screens, `/preview`, `/pricing`, the public
event and city pages, and both not-found pages.

**They are invisible to the link guard, and that is its second blind spot.**
`internal-links.test.ts` resolves `href` values beginning with `/`. A `#` is a valid
fragment, not a broken route, so the test is right not to flag it as a 404 — and wrong to
say nothing at all. The first blind spot was object-literal hrefs, found when `/how`
slipped through; this is the same class.

**The two links are not the same case.**

| Link | Spec | Status |
|---|---|---|
| **About** | **§326, canonical:** *"Login, Privacy, Terms, **About**, social links, city nav, 'Made in [city]' provenance"* | **promised and unbuilt** |
| **Contact** | absent from §323 and §326 | **invented** — it came from the mockups, like `/how` |

This is the same split the last intent found: `/privacy` was owed, `/how` was not.

**Contact has a second claim on attention.** `/privacy` and `/terms` both ship
`privacy@eventpulse24.example` and `legal@eventpulse24.example` with a visible note saying
they are placeholders. A real Contact destination would close that too — and a privacy
policy whose only contact route is a placeholder is weaker than one that points at a page.

## Acceptance Criteria

- [ ] **About resolves or is removed**, and the choice is recorded. If removed, it needs an
      amendment — §326 names it, unlike `/how`
- [ ] **Contact resolves or is removed**, and the choice is recorded. No amendment is
      needed to remove it; no section asks for it
- [ ] **No `href="#"` remains in the pre-auth footer**
- [ ] `internal-links.test.ts` is extended to flag placeholder hrefs — `#`, empty, and
      `javascript:` — in `app/**` and `components/**`, with any deliberate survivor named
      in an allow-set carrying a reverse assertion, as `UNBUILT` did
- [ ] That extension is **proved to fail** by restoring a `#` link
- [ ] If a Contact route is built, `/privacy` and `/terms` point at it and their
      placeholder-address notes are updated to match
- [ ] §326's three further unmet promises — social links, city nav, "Made in [city]"
      provenance — are **recorded in the run**, not silently built or silently dropped

## Technical Notes

- **If About is built**, it is a pre-auth surface and uses the same frame as the legal
  pages (`components/legal/legal-page.tsx` is close, but an About page is not a legal
  document and should not carry the draft banner). There is no mockup and no copy; the
  content is a product decision, so a checkpoint belongs before writing prose.
- **If About is removed**, the amendment is small but real: §326 is the canonical footer
  bullet and this is a withdrawal from it, in the form A-26 took for FR-8.
- The footer's header comment has been rewritten twice in two days. **Whatever is decided,
  the comment must end up describing the array**, which is exactly where it went wrong
  before: it discussed a Terms link the array did not contain.

## Dependencies

(none)
