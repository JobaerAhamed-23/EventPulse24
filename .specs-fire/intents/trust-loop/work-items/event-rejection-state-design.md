---
work_item: event-rejection-state
intent: trust-loop
created: 2026-11-10
mode: validate
checkpoint_1: approved
---

# Design: A reject that is a state, not a delete

## Summary

An editorial **Reject** writes `Event.publication_status = 'rejected'` and nothing else about the event's lifecycle. The event is never deleted, its `Event.Status` is not touched, and it disappears from every public surface because every public read already filters `publication_status == published` by equality.

Invisibility alone is not enough. `publication_status` is not a lifecycle field, so changing it bumps no version, writes no `EventStateChange` and puts nothing in the AD-17 outbox — which means the reminders of everyone who saved the event keep firing for a listing editorial has ruled bad. So the reject command **also bumps `event_version` deliberately and appends an `EventStateChange` of a new kind, `delisted`**, which rides the existing outbox and consumer to cancel those reminders.

**No email is sent.** That is a decision, not an omission (D4). The saved user's card falls back to "event no longer available" — a state the UI already renders for superseded and unpublished events — and their reminders stop silently.

**Nothing on the personal side is written** (D6). The user's conflict pairs stay open, so an editor's reversal is lossless and the open AD-17/AD-21 reinstated-conflict defect is never reached.

Reversal is `relisted`, the mirror of `delisted`, available only through an editor command.

## Scope

**In Scope:**
- `Event.PublicationStatus.REJECTED` and the migration `ingestion/0009_event_rejected`
- A targeted `catalog.guard_event_write` change: moving **into or out of** `rejected` requires `event_version + 1`
- `EventStateChange.Kind.DELISTED` and `Kind.RELISTED`, and their rows in the two exhaustive behaviour maps
- `apps/ingestion/services/editorial_state.py`: `reject_event` and `reinstate_event`, the only writers of `rejected`
- Closing the ingestion re-entry hole in `IncomingEvent.gating()` (D7)
- Suppressing the notice for both kinds (D4)
- Read-absence tests (one per public read, each failing when its filter is removed), transition tests, propagation tests, and the extended map-parity tests

**Out of Scope:**
- **The editorial workflow**: the admin actions, closing the `ReviewItem`, recording the resolution and the FR-16 observation. That is `editorial-review-commands`, which depends on this item. This item ships the *state transition*; that item ships the *verdict that calls it*.
- **Approve and Edit.** Only Reject and its reversal are here.
- The `source_reliability` score, the report API, and the admin queue.
- **Resolving the AD-17/AD-21 reinstated-conflict defect.** D6 routes around it rather than fixing it; it stays open and carried.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D1. Rejected is a publication status, not a lifecycle status** | A third `Event.PublicationStatus` value, `rejected`. `Event.Status` is untouched. | Every public read filters `publication_status == PUBLISHED` by **equality** — `catalog_read` (4 sites), `city_read`, `event_fit/reads`, `preview_read`, `url_feed_read` (2), `revalidation` — so a third value is absent from all of them with **no read changes at all**. And the two fields mean different things: `Event.Status` is *the source's* claim about whether the event happens; `rejected` is *our* claim that the listing is bad. A duplicate listing's underlying event still happens, so writing `status = cancelled` would be false — see D3. |
| **D2. The reject command bumps `event_version` itself; `publication_status` does NOT join `LIFECYCLE_FIELDS`** | `reject_event` writes `publication_status` and `event_version + 1` in one update, then appends the change row. | Adding `publication_status` to `LIFECYCLE_FIELDS` looks tidier and is wrong: ingestion already moves events `in_review → published` **silently** on every re-resolution (`IncomingEvent.gating()`, run-015 plan P1), and that transition would suddenly demand version bumps and emit state changes to every saver. The trigger only *requires* a bump when a lifecycle field moved — it never forbids a deliberate one — so an explicit bump is legal today and leaves the ingestion path untouched. |
| **D3. The kind is `delisted` / `relisted`, not `rejected`** | `EventStateChange.Kind.DELISTED` and `RELISTED`. | Three different words for "no" already exist and must not collide: `domain/confidence.py`'s `Gate.REJECT` means "never becomes an Event", and `ReviewItem.resolution` has `withdrawn` for a system close (`review-queue-model` D5). The split is meaningful rather than cosmetic: **`rejected` is the verdict** (and matches FR-57's button), **`delisted` is the consequence that travels** to savers. A reader who sees `delisted` in the outbox is not left wondering whether an `ExtractedRecord` was gated. |
| **D4. No notice email, for either kind** | `raise_state_notice` returns early for `delisted` and `relisted`. | **The user's call (2026-11-10).** It is mechanically available: `_apply_to_user` calls the snapshot, the sends and the notice as three independent steps, and `raise_state_notice` already decides notice-worthiness per change — a `detail_changed` that fixes a typo cancels nothing and emails nobody. The copy is why: FR-54 fixes four subjects verbatim and has no "rejected" wording; `"was cancelled"` is **false** for a duplicate or wrong-venue reject, and inventing "we removed this listing" would be new product copy the PRD never ratified. Silence is the only option that states nothing untrue. |
| **D5. Reminders are cancelled through the AD-17 path, not a new one** | `LIFECYCLE_SEND_BEHAVIOUR`: `delisted → CANCEL`, `relisted → REMINT`. | A rejection touches **every** saver, whose rows are across the schema wall, and the outbox is the only cross-wall fan-out there is — keyset-paged over savers, per-user failure isolation, `propagated_at` set only when all succeed, reconciler re-offer. `cancel_sends_for_targets` is per-user and cannot address a fan-out. Building a second one would duplicate the most delicate machinery in the tree for one caller. |
| **D6. The personal side writes nothing; the conflict pair stays open** | `LIFECYCLE_PERSONAL_BEHAVIOUR`: `delisted → NONE`, `relisted → NONE`. | **The user's call (2026-11-10).** `cancel_saved_event` would close the pairs as `cleared_by_state_change`, but AD-21 D24 makes a closed pair **immutable** and `conflict_pair_pair_uq` forbids a replacement — so an editor reversing the rejection would restore a real clash that `/conflicts` could never mention again. Leaving the pair open costs nothing in the UI: a side whose catalog event is not published already renders `available: false` → "event no longer available", the same path superseded and unpublished events take. Reversal becomes lossless and the open defect is never reached. |
| **D7. The NONE ⟹ KEEP invariant is re-stated, not bypassed** | `test_only_sold_out_and_detail_changed_skip_the_personal_side` and `test_the_kinds_that_skip_the_personal_side_still_keep_their_sends` are **extended**, and a new test pins the real rule: *a kind that skips the personal side must not move the event's time.* | The existing pairing was over-fitted to the only two NONE kinds that existed. Its stated reason is "the snapshot and the sends would disagree about **an event that moved**" — and a visibility change moves no time, so the reason does not reach `delisted`. The sends still cancel correctly with a NONE personal behaviour because `_apply_sends` takes the version from the **change** (`replace(target, version=change.event_version)`), never from the snapshot. Deleting the tests would be bypassing them; narrowing them to their actual invariant is extending them, which is what the AC asks for. |
| **D8. Ingestion can never republish a rejected event** | `IncomingEvent.gating()` omits `publication_status` when the stored event is `rejected`. The `ExtractedRecord` still updates normally. | This is the re-entry hole, and it is live today: `gating()` "follows every new resolution, silently", so the very next poll of the source would overwrite `rejected` back to `published` and the editor's decision would evaporate within the hour. The record still updates so the evidence stays current — only the gate is frozen. |
| **D9. A re-sent rejected item does NOT raise a new review item** | Ingestion sees it, updates the record, and raises nothing. | The source will keep sending it on every poll. Raising an item per poll would re-queue a decision the editor already made, every hour, forever — exactly the queue spam that `review-queue-model` D2's "one open item per (target, reason)" exists to prevent. The editor's verdict is durable; the source's persistence is not news. |
| **D10. `rejected` is reversible and therefore NOT terminal** | The trigger's terminal rule stays exclusive to `superseded`. | `superseded` is terminal because a *different* event replaced it and the identity moved. A rejection is a human judgement about a listing, and the AC requires an editor to be able to undo it. |

## Technical Approach

### The two writes, and why both

```
EDITOR REJECTS
      │
      ├─ Event.publication_status = 'rejected'   ──►  gone from 10 public reads
      │  Event.event_version      = v+1               (no read code changes)
      │
      └─ EventStateChange(kind='delisted', v+1)  ──►  AD-17 outbox
                                                          │
                                        worker.propagation.propagate
                                                          │
                                        list_savers_for_event (keyset-paged)
                                                          │
                                              ┌───────────┴───────────┐
                                              │                       │
                                   personal: NONE (D6)      sends: CANCEL (D5)
                                   pair stays open          reminders stop
                                              │                       │
                                              └───────────┬───────────┘
                                                          │
                                            raise_state_notice → SKIPPED (D4)
                                                          │
                                                     no email
```

Without the first write the event stays visible. Without the second, reminders keep firing. Neither is sufficient alone, and that is the whole finding behind this design.

### Trigger change

One targeted rule added to `catalog.guard_event_write`, leaving every existing rule intact:

```sql
IF (OLD.publication_status = 'rejected') IS DISTINCT FROM (NEW.publication_status = 'rejected')
   AND NEW.event_version <> OLD.event_version + 1 THEN
  RAISE EXCEPTION 'entering or leaving rejected needs event_version + 1'
    USING ERRCODE = 'restrict_violation';
END IF;
```

It fires only on the boundary into or out of `rejected`, so ingestion's silent `in_review ↔ published` transitions are untouched (D2).

**Legal:** `published → rejected` with `v+1`; `in_review → rejected` with `v+1`; `rejected → published` with `v+1`; `rejected → in_review` with `v+1`.
**Illegal:** any of those four without the bump; a `rejected` row deleted (the existing grants already forbid it).

### Commands

`apps/ingestion/services/editorial_state.py`, the only writers of `rejected`:

- `reject_event(*, event_id, actor, now) -> RejectResult` — guards the current status, writes both halves in one `CATALOG` transaction, appends the audit entry (AD-5), and enqueues propagation and revalidation.
- `reinstate_event(*, event_id, actor, now) -> RejectResult` — the mirror, kind `relisted`.

Both require a **user** actor: `Actor.system(...)` is refused, because AD-14 says every editorial action is attributed and a job must not be able to reverse an editor.

## Integration Points

| Surface | What changes |
|---|---|
| The 10 public reads | **Nothing.** Equality on `published` already excludes the new value. Each gets an absence test that fails when its filter is removed. |
| `revalidation.py:88` | `is_public` goes False on reject, so the public pages rebuild and the event's URL 404s. The reject command enqueues the revalidation in the same transaction. |
| `editorial-review-commands` | Calls `reject_event` / `reinstate_event`; owns closing the `ReviewItem` and recording the resolution. **Every open item on the event closes on one verdict** (`review-queue-model` D2). |
| `reliability-recompute-and-escalation` | A reject is an FR-16 negative observation. This item raises no observation; that item reads the audit entries. |
| `frontend` | **Nothing.** `available: false`, `catalog_event_missing: true`, `public_slug: None` and `status: None` are already rendered. |

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Extending `EventStateChange.Kind` breaks the exhaustive maps | **High** — a missing key is a `KeyError` in a worker, for every saver of one event at once | That is precisely what `test_every_lifecycle_kind_is_mapped` and `test_every_lifecycle_kind_has_a_personal_behaviour` catch. Both maps and both tests are updated in the same commit, and `domain/notices.py` raises on an unknown kind by design. |
| A reject lands while a save is in flight | Medium — a snapshot stamped at the old version | Already handled: AD-21's save-race protocol re-reads the version after commit and requests re-propagation (`personalization-write-services` D27). |
| The conflict pair left open looks like a bug to a reader | Low | D6 is written into the map's comment beside the entry, not only here, so the next reader meets the reason where they meet the code. |
| `relisted → REMINT` silently re-creates reminders | Low | Correct: the user saved it and it is back. Symmetric with the silent cancellation the user chose, and the `ReminderPlan` row was never deleted, so the slots are still theirs. |
| A long-rejected event is reinstated after its start time | Medium — reminders minted for a past instant | `mint_for_plan` already returns no rows for a past `due_at`; a test pins it. |

## Implementation Checklist

1. `Event.PublicationStatus.REJECTED`; `EventStateChange.Kind.DELISTED` and `RELISTED`
2. Migration `ingestion/0009_event_rejected`: the choices and the `guard_event_write` replacement (forward and reverse)
3. `LIFECYCLE_SEND_BEHAVIOUR` += `delisted: CANCEL`, `relisted: REMINT`; `LIFECYCLE_PERSONAL_BEHAVIOUR` += both as `NONE`, each with its D5/D6 comment
4. Extend the two map-parity tests and add the "skips personal ⟹ moves no time" test (D7)
5. `raise_state_notice`: skip both kinds, with a test asserting no `ScheduledSend` notice row and no email
6. `apps/ingestion/services/editorial_state.py`: `reject_event`, `reinstate_event`, audit, propagation and revalidation enqueue
7. `IncomingEvent.gating()`: freeze `publication_status` on a rejected event (D8); test that a re-poll does not republish and raises no new review item (D9)
8. Trigger tests: the four legal transitions, and each one refused without the version bump
9. One absence test per public read, each proven to fail when its filter is removed
10. End-to-end: save → reject → assert no email, reminders cancelled, conflict pair still open and rendering unavailable, event absent from all public reads → reinstate → assert reminders re-minted and the pair intact
11. Full gate set: ruff, ruff format, `lint-imports`, `manage.py check`, `makemigrations --check`, coverage (80% overall / 100% `domain/`), the OpenAPI client contract, frontend lint and typecheck

## PRD Amendment Owed

FR-57's "Reject (deletes from registry)" must be amended to: *Reject moves the event to a non-public `rejected` publication state. It is never deleted, it is absent from every public surface, saved users' reminders are cancelled without an email, and only an editor can reverse it.*
