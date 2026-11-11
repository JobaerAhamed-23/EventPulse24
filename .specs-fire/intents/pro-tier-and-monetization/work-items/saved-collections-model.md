---
id: saved-collections-model
title: Named collections — the model FR-49 never got
intent: pro-tier-and-monetization
complexity: medium
mode: confirm
status: pending
depends_on: [subscription-model-and-entitlement]
created: 2026-11-11
---

# Work Item: Named collections — the model FR-49 never got

## Description

FR-49 is **the only MVP functional requirement with no work item anywhere on disk**.
TRACEABILITY.md:59 marks it MISSING and explains why: *"Nothing designed. 'Named collections'
exists only as a marketing bullet on the FR-48-tagged pricing pages — no screen shows
creating, viewing, or managing a collection."* It notes EXPERIENCE.md's coverage table claims
`settings-desktop.html` covers FR-49, and that the mockup contains zero collection content.

This item builds the storage: a named, user-owned, orderable grouping over `SavedEvent`.

## Acceptance Criteria

- [ ] `SavedCollection` lives in `apps/personalization/models.py`, in `personal`, owned by
      `personalization` — which already declares ownership of `SavedEvent`.
- [ ] It declares `retention_category = RetentionCategory.ACCOUNT_CONTENT`, matching
      `SavedEvent`.
- [ ] **Membership is explicit**, so one saved event can belong to more than one collection,
      and a collection can be empty. A save is never silently filed somewhere.
- [ ] **AD-3 holds throughout.** Nothing here relates to `catalog`. Membership references the
      user's `SavedEvent`, which already holds the catalog event id by value with no foreign
      key.
- [ ] **Ordering is persisted and explicit**, not derived from creation time — FR-49 requires
      reorder as a user action. Reordering is stable and total: no two collections of one
      user share a position, and a reorder leaves no gaps that later break ordering.
- [ ] A collection name is **unique per user**, enforced by a constraint rather than by
      application code.
- [ ] Deleting a collection **does not delete the saves inside it**. They return to being
      uncollected. This is the one place a delete is permitted, and it deletes a grouping,
      not user content.
- [ ] Writes go through named `personalization` commands with a `PersonalizationAuditEntry`
      (AD-5).
- [ ] Tests cover: the per-user name constraint; membership in two collections at once; an
      empty collection; reorder stability under concurrent reorders; and that deleting a
      collection leaves its `SavedEvent` rows intact.

## Technical Notes

Medium complexity — the shape is conventional, and the decisions are small but real:

- **Ordering representation.** An integer position needs renumbering on insert; a fractional
  or lexicographic rank avoids it. Either is fine; pick one and make the concurrent-reorder
  test prove it.
- **Membership table vs. array column.** A join table is the conventional answer and makes
  "which collections is this save in?" queryable. Postgres arrays would be denser but harder
  to constrain.

No Pro gate lives here. Gating is the API's job (`saved-collections-api`), because the model
must still be readable by a lapsed Pro user whose collections must not vanish — see the
open downgrade question in the brief.

Follow `SavedEvent` (`personalization/models.py:273`) for conventions: `UUIDv7Model`,
retention category, constraints named explicitly, and a docstring that says *why* the shape
is what it is.

## Dependencies

- subscription-model-and-entitlement
