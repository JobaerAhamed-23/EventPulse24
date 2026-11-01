---
id: share-control
title: Handing it to a friend — the share affordance
intent: public-pages-and-seo
complexity: medium
mode: validate
status: pending
depends_on:
  - frontend-public-event-page
created: 2026-11-01
---

# Work Item: Handing it to a friend — the share affordance

## Description

FR-28's sender side: from a Pulse Card or the Detail screen, turn an event into a URL a friend can open. The link is **not a second URL shape** — it is the FR-26 public page, which is why this item depends on that page existing and adds no new route.

**Raised to `validate` deliberately.** Its raw complexity is medium, which the balanced bias would put at `confirm`, but it is the one item in this intent with **no design to build from**. TRACEABILITY.md flags FR-28 as an *inferred-only gap*: `share-link-desktop.html` is tagged `UJ-5` and shows the **recipient's** landing, not the sender's action. A design doc and Checkpoint 1 land the affordance deliberately rather than inventing it mid-run — which is how the gap arose in the first place.

## Acceptance Criteria

- [ ] A share control on the **Pulse Card** and the **Detail screen**, producing the public `/events/{slug}` URL — no new route, no second link shape, no token.
- [ ] Uses the **Web Share API** where available (EXPERIENCE.md notes it as a platform capability for FR-28), with a **copy-to-clipboard fallback** everywhere else, and visible confirmation that the copy happened.
- [ ] The link opens the public page with its **"Save to Pulse" CTA**, for a recipient with no account — the FR-28 consequence stated in the PRD.
- [ ] Sharing an event the sender can see but the public cannot (`in_review`) is **not offered**, rather than producing a link that 404s for the recipient.
- [ ] The control is **keyboard reachable and screen-reader labelled**; the confirmation is announced, not only shown.
- [ ] Visual language follows the existing design-system tokens and sits consistently on both surfaces.
- [ ] Tests: the share action on both surfaces, the Web Share path and the clipboard fallback, the confirmation state, an unshareable event, and keyboard operation.

## Technical Notes

**Design-doc decisions (Checkpoint 1):**

- **OQ-B — what the sender-side control actually is.** A icon button, a menu item, a long-press — and where exactly it sits on a Pulse Card without crowding the density `Card.PulseDigest` is specified to hold. Nothing in the mockup set answers this.
- **Whether the shared link carries any attribution.** `share-link-desktop.html`'s header distinguishes itself from the public page by having *"shared by" attribution* — but the chosen scope is one URL for both. Decide whether attribution survives as a query parameter the page reads, or is dropped; if it survives, it must not create a second canonical URL.

The branded static OG image and per-event metadata are delivered by `frontend-public-event-page`; this item does not re-implement them, it relies on them for the unfurl.

## Dependencies

- frontend-public-event-page
