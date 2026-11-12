---
id: data-export
title: Download my data — JSON and ICS, off the retention registry
intent: pro-tier-and-monetization
complexity: medium
mode: confirm
status: completed
depends_on:
  - subscription-model-and-entitlement
  - saved-collections-model
created: 2026-11-11
run_id: run-eventpulse24-027
completed_at: 2026-11-11T16:48:21.860Z
---

# Work Item: Download my data — JSON and ICS, off the retention registry

## Description

FR-52 exports a user's saved events, personal events, preference graph and reminder plans as
JSON and ICS. The foundation is already built and already names this requirement:
`shared/retention.py` opens with *"The sweep job, account deletion and **export (FR-52)** all
read `retention_registry()`."* Every model already declares a `RetentionCategory`, enforced
by system checks `eventpulse.E003/E004`.

So this item builds the export **off the registry**, not off a hand-maintained list. A new
model added later is exported because it declared a category, not because someone remembered.

**This item carries an open question that may change its scope** — see Technical Notes.

## Acceptance Criteria

- [ ] Export enumerates what to include by reading `retention_registry()`. There is **no
      second hand-maintained list** of exportable models, and a test proves a newly-registered
      user-data model appears in the export without touching export code.
- [ ] Categories that are not user data are excluded by category, not by name —
      `NOT_USER_DATA` and `ANALYTICS_AGGREGATES` do not appear.
- [ ] JSON includes all user-created records. **Personal-event locations are redacted when the
      user opted out of precise location sharing**, per FR-52's testable consequence.
- [ ] Saved collections from `saved-collections-model` are included — hence this item's
      dependency on it.
- [ ] The ICS export **imports cleanly into Google, Apple and Outlook**. Prove it against the
      ICS the existing `adapters/calendar/ics.py` already parses, so export and import agree.
- [ ] Export runs **asynchronously** as a Celery task and the user receives an **email with
      download links within 24 hours**.
- [ ] Download links expire, and a link cannot be used to fetch another user's export. A test
      covers the cross-user case.
- [ ] Requesting an export twice in quick succession does not queue two jobs.
- [ ] Tests cover: registry-driven enumeration; the redaction branch in both states; link
      expiry; cross-user refusal; and the ICS round-trip.

## Technical Notes

Medium complexity — the registry does the structural work.

**The open question, to settle at this item's checkpoint:** FR-52's own text concedes the
tension — *"export is free for GDPR compliance but UX is in Pro settings for non-EU users."*
GDPR Article 20 is a right, not a feature. If the only export affordance sits behind
$4.99/month, the product arguably fails that obligation for EU users. Three ways out: gate
nothing; gate nothing but surface it only in Pro settings (what the PRD literally says, and
the weakest position legally); or gate the convenience and provide a free request path. **This
is a legal question before it is a product one** and should be answered deliberately rather
than inherited from a pricing bullet. If the answer is "not gated", this item simply loses
its Pro check and nothing else in the intent moves.

The 24-hour SLA echoes the `user_reported` review-item SLA from `trust-loop`; reuse that
pattern rather than inventing a second scheduling idiom. Durations belong in
`shared/constants.py`.

Account deletion also reads the registry and is already specified at 30 days with export
retained for 30 days post-deletion. This item should not implement deletion, but must not
make it harder.

## Dependencies

- subscription-model-and-entitlement
- saved-collections-model
