---
id: fr-28-share-affordance
title: FR-28 — design the share action itself, not the page it lands on
intent: traceability-reconciliation
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-11-12
run_id: run-eventpulse24-028
completed_at: 2026-11-12T05:31:37.933Z
---

# Work Item: FR-28 — design the share action itself, not the page it lands on

## Description

FR-28 is the **sender's** action: *"From any Pulse Card or Detail Screen, the user can
generate a public share-link URL with pre-filled metadata."* The matrix caught a subtle
mis-attribution here that is worth preserving as the point of this item.

`share-link-desktop.html` exists and looks like FR-28's design, but its header tags it
`UJ-5` — the journey where a **recipient** lands on a shared link. That is the other end of
the interaction. The sender's affordance — where the control lives on a Pulse Card and on
the Detail Screen, what it looks like mid-share, what confirms the link was copied, what
happens where the Web Share API is unavailable — is designed nowhere. EXPERIENCE.md:964 has
a single line: *"**Web Share API:** for outbound shares (Pulse share-link, PRD FR-28)"* — a
platform-capability footnote, not a design.

The code shipped: `frontend/lib/share-link.ts` and `frontend/components/share/share-control.tsx`.

## Acceptance Criteria

- [ ] A mockup exists, self-tagged `FR-28`, showing the sender's share control **in place on
      both surfaces** the PRD names — a Pulse Card and the Detail Screen — with its resting,
      active and confirmed states.
- [ ] The design states the **Web Share API fallback**: what a browser without `navigator.share`
      shows instead. This is the detail a one-line capability footnote cannot carry.
- [ ] `share-link-desktop.html` keeps its `UJ-5` tag and is **not** repurposed. If it also
      serves FR-28's landing consequence, that is added explicitly rather than assumed.
- [ ] A named DESIGN.md or EXPERIENCE.md section cites `FR-28` and names the component per the
      UX spine's naming convention.
- [ ] A test asserts the generated share-link resolves to the public Event URL in FR-26's form
      and that the landing page carries a "Save to Pulse" CTA.
- [ ] A test asserts the Open Graph tags — title, description, image — are present and
      populated, not empty defaults. This is FR-28's second testable consequence and the one
      that silently degrades: an unfurl with a blank image still "works".
- [ ] The share-link contains no session-dependent data, per AD-12 (*the public surface never
      depends on a session*).
- [ ] Tests name `FR-28`.

## Technical Notes

`migrations/0015_digestpreference_share_precise_location` suggests a precise-location opt-out
interacts with sharing. Check whether it gates the share-link's metadata; if it does, the
design must show both states and a test must cover the redacted one. FR-52's export has the
same redaction rule, so there is a precedent to follow rather than a decision to make.

Check whether the share control appears on the Timeline event-block too. FR-28 says "any
Pulse Card or Detail Screen"; the Timeline is read-only per Amendment A-8, so the honest
answer is probably no — but the design should say so rather than leave it open.
