---
id: fr8-suggest-link-removal
title: FR-8's "Suggest an event" link points at a route that was never built —
  withdraw it
intent: broken-links-and-legal-pages
complexity: low
mode: confirm
status: completed
depends_on: []
created: 2026-11-20
run_id: run-eventpulse24-055
completed_at: 2026-11-20T10:51:10.598Z
---

# Work Item: Withdraw FR-8's "Suggest an event" link

## Description

The empty Pulse Digest links to `/suggest`. **No such route has ever existed**, and nothing
in the product backs one: no FR defines a suggestion feature, and there is no model, no
endpoint, no table and no admin for user-submitted events anywhere in `backend/`.

The link was shipped knowingly. `digest-empty.tsx`'s header comment argues that a real link
beats a disabled control or an inert button, and on those three options it is right. **The
fourth option — not making the promise — was never on the list.** That is the one this work
item takes.

**The decision is the deliverable; the code change is three lines.** FR-8 says in its own
text that the empty state card carries *"a 'Suggest an event' link"*. Deleting it is a
deviation from an MVP FR, and this repo has twice now recorded exactly this kind of
withdrawal as a numbered amendment with its reasoning attached (A-24 withdrew the Timeline
Why-this tag; A-25 pinned FR-22's formula). **A-26 is the next number** and this follows
their form: the amendment is written and dated first, then the code moves.

## Acceptance Criteria

- [ ] **Amendment A-26 is written before the component is touched**, recording: that FR-8's
      link is withdrawn, not deferred; that the withdrawal is because no suggestion feature
      exists or is planned, so the link can only ever resolve to a 404 or to a page that
      apologises for itself; and that it is revisitable if a suggestion feature is ever
      specified
- [ ] A-26 lands in `prd.md` at FR-8, in the inline form A-25 used at `prd.md:773`
- [ ] `EXPERIENCE.md` §5 is updated if and only if it names the link; the **locked copy is
      otherwise untouched**
- [ ] `digest-empty.tsx` no longer imports or renders a `Link`, and `/suggest` appears
      nowhere in `frontend/`
- [ ] The locked headline *"Nothing on the pulse today. The calendar is yours."* and the
      `No qualifying events in {city}.` meta line render exactly as before
- [ ] The component's header comment is rewritten — **it currently argues for the link's
      existence**, and leaving that reasoning in place above code that no longer does it is
      how a comment becomes a lie
- [ ] Existing `digest-empty` tests pass; any test asserting the link's presence is updated
      to assert its absence, and **that updated test must be able to fail**
- [ ] FR-8's traceability row is re-scored with a note that the link is withdrawn by A-26,
      so the next matrix regeneration does not read the absence as a regression

## Technical Notes

- `components/digest/digest-empty.tsx:50` — the single `<Link href="/suggest">`, inside the
  final `<p className="mt-1">`. The whole paragraph goes with it; an empty `<p>` left behind
  would hold margin the layout no longer wants.
- The `import Link from "next/link"` at line 1 becomes unused.
- EXPERIENCE.md §5 is the canonical source for this state and its copy is explicitly locked.
  Read it before editing; the goal is a *subtraction*, not a redesign.
- The highest amendment currently in use is **A-25**. Verify nothing else has claimed A-26
  before writing it — the EXPERIENCE.md `updated_note` block is where amendment numbers are
  most easily missed.

## Dependencies

(none)
