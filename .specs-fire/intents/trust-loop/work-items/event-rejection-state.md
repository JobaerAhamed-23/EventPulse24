---
id: event-rejection-state
title: A reject that is a state, not a delete
intent: trust-loop
complexity: high
mode: validate
status: in_progress
depends_on: []
created: 2026-11-10
---

# Work Item: A reject that is a state, not a delete

## Description

FR-57 says an editor's Reject "deletes from registry". During capture this intent decided on a **soft reject** instead, matching a codebase that never deletes catalog rows: sources are paused, events are versioned, and `EventStateChange` is append-only. The question this item answers is *where* "rejected" lives. There are two candidates, and they behave very differently downstream:

- **A third `Event.PublicationStatus` value** (`published`, `in_review`, `rejected`). Every public read already filters on `published`, so a rejected event disappears with almost no read changes. However, publication status is not a lifecycle field, so **saved users are told nothing**. Their reminders keep firing for an event that editorial has ruled doesn't exist.
- **A lifecycle change**: a new `EventStateChange.Kind`, or reuse of `cancelled`. The change travels through the outbox, consumer, notice and send path that `event-state-sync` built, so saved users get notified and reminders get cancelled. However, it widens tables that are mapped exhaustively (`LIFECYCLE_SEND_BEHAVIOUR`, `LifecyclePersonalBehaviour`, the notice copy and the Pulse Card state), and it is a change to the `guard_event_write` trigger.

## Acceptance Criteria

- [ ] The design picks one representation and records why. If it picks a combination (for example, publication `rejected` **plus** a `cancelled`-shaped lifecycle change), it also states what a saved user sees and in what words. FR-54's copy has no "rejected" wording, and "cancelled" may be a lie when the event was a duplicate.
- [ ] A rejected event is **never deleted**. It is absent from every public read: the catalog read, the city pages, the sitemap, the public Event URL, Event Fit, the digest candidates and the share links. One test per read proves it, and each test must fail when the filter is removed.
- [ ] A rejected event **cannot re-enter by ingestion**. A later poll of the same source item does not silently republish it, and the design states whether a source re-sending it raises a new review item or is ignored.
- [ ] A rejected event is **reversible only by an editor**, through a command. Ingestion never reverses it.
- [ ] Saved users are handled as the design decides, and an end-to-end test proves it: notice, cancelled sends, and the Timeline and conflict behaviour, including the interaction with the open AD-17/AD-21 reinstated-conflict defect.
- [ ] Migration and trigger changes come with tests for the legal and illegal transitions.
- [ ] Any change to the exhaustive lifecycle maps comes with the existing "every kind is mapped" tests extended, not bypassed.

## Technical Notes

`Event.PublicationStatus` is at `apps/ingestion/models.py:257`, `Event.Status` at :261, `EventStateChange.Kind` at :493, and `LIFECYCLE_SEND_BEHAVIOUR` at `shared/constants.py:983`. `domain/confidence.py`'s `Gate.REJECT` means "never becomes an Event". That is a different thing, and the naming must not collide.

**PRD amendment owed:** FR-57's "Reject (deletes from registry)" should be amended to match whatever this item ships.

## Dependencies

(none)
