---
id: editorial-admin-queue
title: Where an editor actually works — the review queue in Django admin
intent: trust-loop
complexity: medium
mode: confirm
status: pending
depends_on:
  - editorial-review-commands
created: 2026-11-10
---

# Work Item: Where an editor actually works — the review queue in Django admin

## Description

AD-14 makes Django admin the MVP surface for FR-57. `apps/editorial/admin.py` is empty, and `apps/editorial/__init__.py` already says it "owns nothing; acts only through ingestion commands". This item fills it, following the conventions of the existing `apps/ingestion/admin.py`: every write goes through a command, `save_model` never calls `obj.save()`, delete is disabled, and the admin's `LogEntry` is off.

## Acceptance Criteria

- [ ] A `ReviewItem` changelist, **open items first**, then ordered by priority and `due_at`. `user_reported` items past their 24h SLA are visibly marked. The list can be filtered by reason, status and source.
- [ ] Each item's page shows what an editor needs to decide: the event's current facts (or the source's score history, for a source item), the source and its badge, the report count with category tallies, and **no reporter identities**.
- [ ] Approve, Edit and Reject (and Dismiss, for source items) call the `editorial-review-commands` services. A command's refusal (a stale version or an already-closed item) shows on the form, not as a 500. Edit uses a form limited to the editable fields, and its `clean()` runs the command's own checks, as the ingestion admin does.
- [ ] **Delete is disabled** on every editorial model view, and no admin action bypasses a command.
- [ ] A summary at the top of the changelist shows the **queue size**, the **age of the oldest open item**, and the **count of SLA breaches**. These are the FR-57 metrics that FR-29's dashboard will later read, computed by an `ingestion` read service, not in the template.
- [ ] **Access:** a member of the editorial group can see and act. A signed-in user who isn't staff, or is staff without the group, is refused. Superuser is not required. Each case is tested, including the negative ones.
- [ ] Tests drive the admin through the Django test client: list ordering, the SLA mark, each action, a refusal shown on the form, the summary numbers, delete returning 403, and the access matrix.

## Technical Notes

Copy the patterns rather than reinventing them: `_add_domain_error` and `_actor_names` in `apps/ingestion/admin.py`, and the actor construction (`shared.actor.Actor`, `ActorKind`). Actor names are read from `personal` for display (AD-3), by id only.

## Dependencies

- editorial-review-commands
