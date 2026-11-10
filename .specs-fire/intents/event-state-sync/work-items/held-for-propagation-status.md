---
id: held-for-propagation-status
title: The sweep will send a reminder for an event that already moved — the
  propagation hold
intent: event-state-sync
complexity: high
mode: validate
status: completed
depends_on: []
created: 2026-11-04
run_id: run-eventpulse24-025
completed_at: 2026-11-05T06:10:24.975Z
---

# Work Item: The sweep will send a reminder for an event that already moved — the propagation hold

## Description

AD-17 specifies a guard that was never built. Its words:

> *"Every event-bound `SCHEDULED_SEND` carries the `event_version` it was scheduled against. After claiming a row, the sweep reads the Event's current `event_version` through `ingestion`'s read interface — a separate, non-transactional read. If the catalog version is newer, the row goes to `held_for_propagation` and is not sent; propagation then releases, rewrites or cancels it."*

`apps/delivery/services/delivery_sweep.py` contains no version check of any kind — the only match for "propagat" in the file is a comment quoting AD-17's outbox rule. And there is nowhere for a held row to go: `ScheduledSend.Status` (`apps/delivery/models.py:286-297`) is `pending`, `sent`, `cancelled`, `failed`, with `TERMINAL_STATUSES = frozenset({SENT, CANCELLED, FAILED})`.

So today the sweep claims a row, does not ask whether the event moved, and sends. That is the exact race AD-17 was written to prevent, and it is live independently of whether propagation exists — a reminder for a cancelled event goes out on schedule right now.

**This item needs a design doc (Checkpoint 1) before any code.** It adds a status to a continuously-swept table and makes a deliberate exception to an invariant the model documents in prose.

## Acceptance Criteria

- [ ] A **new non-terminal `held_for_propagation` status** on `ScheduledSend`, with a migration safe to run against a table the sweep is actively claiming from.
- [ ] `TERMINAL_STATUSES` is unchanged, and the docstring at `models.py:287` — *"`pending` is a promise; the other three are terminal and never reopened"* — is **rewritten, not left to rot**. A held row is non-terminal and explicitly re-openable, and the next reader must not have to infer that from the frozenset.
- [ ] After claiming a row, the sweep reads the event's current `event_version` through `ingestion`'s published read as a **separate, non-transactional read**. The claim transaction stays `personal`-only (AD-3).
- [ ] When the catalog's version is newer, the row is **held, not sent**, and not re-claimed on the next tick.
- [ ] **A held row is never stranded.** A test proves every held row either returns to `pending` or reaches a terminal state once propagation runs — including the case where propagation itself fails and retries.
- [ ] The guard applies only to **event-bound** sends. Personal-event reminders and the digest/Pulse Ping are keyed differently and must not be held by it.
- [ ] A held row's **send key is not consumed**. AD-7: the key is never derived from `due_at`, and a hold is not a send — re-minting after propagation must not find the key spent.
- [ ] **The accepted residual window is tested as accepted**, not silently tolerated. AD-17 concedes "a change that commits between that version read and the provider call can still send one reminder for the old time." A test documents that window and asserts the FR-54 notice is what corrects it.
- [ ] The sweep's throughput does not regress into a per-row catalog query. Version reads are batched across a claim.

## Technical Notes

**Design-doc decisions (Checkpoint 1):**

- **Batched version read vs. per-row.** The sweep claims in batches; one read per row would put a cross-module call on the hottest path in the system. The design states the batch shape and what happens to a row whose event is missing from the result.
- **Whether a hold is a status or a column.** A status is the Spine's own word. A nullable `held_at` alongside `pending` would avoid touching the status set at all and might age better — the design should consider it and say why it chose otherwise.
- **Who releases a held row, and what if nobody does.** Propagation releases it. If propagation is broken, held rows accumulate silently and reminders stop going out — a failure mode that is quieter and worse than sending a stale one. The design names the alarm.
- **Interaction with the attempt bound.** A held row that was previously attempted keeps its attempt count; the design states whether a hold resets it.

**Ordering note:** this item has no dependency on the propagation consumer and should land before it. The guard is the thing that makes the consumer safe to turn on, and it is independently valuable — it stops a wrong send today even while `propagate_state_change` is still a stub.
