---
work_item: state-change-notice-model
run: run-eventpulse24-025
intent: event-state-sync
checkpoint: 1 (design)
created: 2026-11-06
---

# Design: One calm notice, once, and a way to silence it

## Summary

A new `delivery`-owned entity in `personal`, `StateChangeNotice`, plus a per-`(user, event)` mute table. The email is one of the notice's two deliveries, not the notice itself.

Two things were investigated in code before this was written, because the work item recorded both as contradictions:

- **Quiet Hours do apply.** The capture decision and `models.py:334` only *looked* contradictory; the docstring's wording is wrong, not the decision.
- **FR-54's daily cap cannot live in the send key**, and it is not an edge case — one poll already writes several state changes.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | A notice **entity**, with the `ScheduledSend` as one of its deliveries | A send row has no "seen"; the in-app surfaces need one record both can read |
| D2 | Uniqueness is per `(user, state_change_id)`; the **daily cap is separate** | That is what "never repeats" actually forbids — a retry, not a second event |
| D3 | The cap is enforced at mint by **`PRECEDENCE`**, replacing upward | The key must stay AD-7's, or a cancellation collides with a sold-out and is dropped |
| D4 | `seen_at` and `dismissed_at` are **two columns**, not one | Being shown something and closing it are different acts with different consequences |
| D5 | The quiet-hours lead margin is **`REMINDER_SLOT_OFFSET["1hr"]`**, reused | The tree already has an answer to "the last moment a message is still actionable" |
| D6 | The mute is **its own table**, not a column on `ReminderPlan` | A saved event usually has no plan, and an unsave now deletes the plan |
| D7 | A **terminal** change (`cancelled`, `superseded`) overrides both the cap and the mute | Silence about a cancellation is the one failure the user cannot recover from |

---

### D1 — one entity, and the email is a delivery of it

The work item asked whether this is one table or two. It is two rows of two existing kinds: a new `StateChangeNotice`, and the `ScheduledSend` its email already has a key for.

`ScheduledSend` cannot be the notice. It is `delivery`'s send ledger, swept continuously on a `(due_at, status)` index, and it has no vocabulary for *seen* — only `pending`, `sent`, `cancelled`, `failed`. FR-54 asks for "in-app **+** email", and the in-app half outlives the send: the strip is still dismissible after the email went out, and still needed if the email never does.

Hanging `event_id`, `change_kind`, `seen_at` and `dismissed_at` off `ScheduledSend` would also widen the hottest table in the schema for columns only one of its five kinds uses.

So: the notice is the record, and the email is one of its two deliveries. The other is the screen.

### D2 — "never repeats" is about retries, not about a second event

FR-54 says both of these, and the work item is right that they are different rules:

> The notification is one-time per event; never repeats.
> A user receives at most one state-change notification per event per day.

Taken literally the first makes the second meaningless — "at most one per day" presumes there can be a second day. And the four consequence bullets plainly expect distinct notices for cancel, move, relocate and sold-out.

The reading that makes every sentence true: **uniqueness is per state change**, which is exactly AD-7's existing key —

```
user_id · state_notice · state_change_id
```

— so a propagation retried after a partial run raises nothing new. That is the repeat FR-54 is forbidding. The daily cap is then a separate rule (D3), not a restatement of this one.

Recorded as a **PRD amendment**: the opening sentence should read "one-time per state change", alongside the FR-55 amendment already on the brief.

### D3 — the cap is a mint-time rule resolved by precedence, and the key does not move

**It cannot live in the key.** AD-7 fixes the state-notice key in the Spine's own table. Re-keying on `(event, local_date)` would make a cancellation at 14:00 collide with a sold-out minted at 09:00 and be silently dropped as a duplicate — losing the one message FR-54 most requires.

**And the cap is not protecting against a rare burst.** `event_writes.py:245` writes **one `EventStateChange` per kind** in a single poll, versions `v+1..v+k`, ordered by `PRECEDENCE`. A source update that moves the time *and* marks it sold out already produces two notices seconds apart. The cap is the common case for any multi-field change.

So the key stays exactly as AD-7 specifies — **no spine amendment** — and the cap is enforced where the notice is raised, against `(user_id, event_id, local_date)`:

| Existing notice that day | New change | Outcome |
|---|---|---|
| none | any | raise |
| pending, **more or equally** important | any | no notice, no email |
| pending, **less** important | any | cancel its send, replace the notice |
| already **sent** | non-terminal | no notice |
| already **sent** | terminal (`cancelled`, `superseded`) | raise anyway — D7 |

`PRECEDENCE` is reused, not reinvented: `domain/lifecycle.py:43`, declaration order most to least important, already pinned by `tests/domain/test_lifecycle.py:207`.

Replacing a pending notice cancels its send and mints a new one under the new change's key. The old key stays spent, which AD-7 explicitly contemplates — *"the old key stays spent, so a `1d` reminder already sent for the old date does not block the `1d` reminder for the new one."*

**The worst case is two emails per event per day**, and it is bounded by D7's exception being terminal: once a cancellation has sent, nothing outranks it.

### D4 — `seen_at` and `dismissed_at` are different facts

The work item asked what "seen" means, and the honest answer is that it is two questions:

- **`seen_at`** — the notice has been put in front of the user. Set when the Detail banner or the digest strip renders it. This is what makes a notice stop being *new*.
- **`dismissed_at`** — the user closed the strip. An act, not an observation.

One column cannot be both: a user who opens the Detail screen has seen the notice but has not dismissed anything, and treating that as a dismissal would remove the strip they never looked at.

The surfaces then differ, deliberately:

- the **digest strip** lists notices with `dismissed_at IS NULL` — it is a queue, and closing an item should empty it;
- the **Detail banner** ignores `dismissed_at` — it is about *this* event, which the user has deliberately navigated to. Dismissing a strip should not hide "this event was cancelled" from the event's own page.

### D5 — the lead margin is the `1hr` slot, reused

Decision 8 at capture: Quiet Hours apply, except when deferral would push the notice past the event's own start.

The work item is right that "past the start" is not the real predicate — a notice landing ninety seconds before the doors open is technically in time and useless. It needs a margin, and an invented number would be a threshold with no owner (AD-8).

There is already an answer in the tree. `REMINDER_SLOT_OFFSET["1hr"]` is the project's existing statement of *the last moment a message about an event is still worth sending*: it is the tightest reminder a user can choose. A notice that cannot beat the `1hr` reminder is not actionable either.

```python
due = shift_to_sendable(now, window=settings.quiet_hours, zone=zone)
if due > event_start - REMINDER_SLOT_OFFSET[ReminderSlot.HOUR]:
    due = now          # the deferral would outlast its usefulness
```

Both branches are tested, including an event that starts *inside* the quiet window — where every deferral is too late and the notice always goes immediately.

### D5a — the Quiet-Hours docstring is wrong and gets amended

`models.py:334` and `scheduled_sends.py:473` both say a `state_notice` has *"no slot and no Quiet-Hours arithmetic"*. The first half is right; the second is not, and it is the sentence that made this look like a contradiction.

`shift_to_sendable(instant, *, window, zone)` takes **any** aware instant. Nothing in it is slot-specific. A state notice has no slot because its send time is not an offset from the event's start — it is *now* — but that instant is still shifted out of the quiet window like any other.

`slot_at` stays **null**, and the preference rewrite keeps skipping the row — for a better reason than the one it currently gives. A state notice's pre-shift instant is *the moment the change happened*. That is in the past and never moves, so there is nothing for a later preference change to recompute. The skip is correct; the comment explaining it is not.

Both comments are rewritten as part of this item.

### D6 — the mute is its own table

`EventNoticeMute(user_id, event_id)`, `delivery`-owned, in `personal`. Unique on the pair.

Not on `ReminderPlan`, although FR-11's per-event reminder opt-out lives there. That precedent does not transfer:

- a saved event usually has **no plan at all** — `save_event` does not attach one, which is the whole reason `save_plan_slots` has its attach branch;
- and `unsave_event` now **deletes** the plan, so a mute stored on it would vanish with the save and silently un-mute on a re-save.

Not on `NotificationPreference` either: that is one row per user, and this is a per-event fact. Its own docstring already draws exactly this line — per-user scope there, per-event scope elsewhere.

A muted event raises no notice and sends no email. Its **reminders and digest placement are untouched**: the mute silences the correction, not the event.

### D7 — a terminal change overrides both the cap and the mute

This is the one place the design deliberately departs from the AC's literal wording, so it is stated plainly rather than buried.

A `cancelled` or `superseded` change raises its notice even when the daily cap would suppress it, and even when the event is muted.

The reason is asymmetry of harm. Every other notice is a convenience — knowing a venue moved, or that it sold out. A cancellation is the one where silence costs the user the evening, and FR-55 has *already removed the event from their digest*, so there is no second channel that would have told them. A mute means "stop telling me about tweaks to this event"; reading it as "do not tell me it is off" turns a preference into a trap.

It also bounds the cap honestly: at most two emails per event per day, because nothing outranks a terminal change.

**If this is not wanted, the alternative is a strict cap and a strict mute** — in which case a user who mutes a sold-out notice in the morning is never told the event was cancelled that afternoon. That consequence should be accepted deliberately, not arrived at.

## Data Models Affected

Two new models, both `delivery`-owned in `personal`, one migration.

**`StateChangeNotice`** — `retention_category = ACCOUNT_CONTENT` (it is about the user's own saved event, and dies with it).

| Column | Note |
|---|---|
| `user_id` | by value (OQ-8) |
| `event_id` | the **catalog** event's id, by value — no FK across the wall (AD-3) |
| `state_change_id` | the `EVENT_STATE_CHANGE` this was raised for, by value |
| `change_kind` | the `ChangeKind` value; the vocabulary is `domain.lifecycle`'s, not a second one |
| `event_version` | the version the change carried, for the AD-17 gate |
| `local_date` | the user's local date — what the daily cap is keyed on |
| `seen_at`, `dismissed_at` | nullable; D4 |
| `created_at`, `updated_at` | |

Constraints: unique `(user_id, state_change_id)` — D2's "never repeats", at the database rather than in a service. Index `(user_id, local_date)` for the cap lookup and the strip; index `(user_id, event_id)` for the Detail banner.

**`EventNoticeMute`** — `retention_category = PREFERENCE_SIGNALS` (it is a preference, and matches `NotificationPreference`).

`user_id`, `event_id`, `created_at`. Unique on `(user_id, event_id)`.

## Affected Files

| File | Action | Purpose |
|---|---|---|
| `backend/apps/delivery/models.py` | Modify | The two models; amend the `slot_at` comment (D5a) |
| `backend/apps/delivery/migrations/0007_*.py` | Create | Both tables, one migration (one per PR) |
| `backend/apps/delivery/services/state_notices.py` | Create | `raise_state_notice`, the cap, the reads |
| `backend/apps/delivery/services/mutes.py` | Create | `mute_event_notices`, `unmute_event_notices`, `is_muted` |
| `backend/apps/delivery/services/scheduled_sends.py` | Modify | `mint_state_notice`; amend the rewrite comment (D5a) |
| `backend/shared/constants.py` | Modify | The lead margin, if it needs its own name |
| `backend/tests/delivery/test_state_notices.py` | Create | |
| `backend/tests/delivery/test_notice_mutes.py` | Create | |

No API in this item — `notice-and-mute-api` (item 8) is where the surface lands.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| The cap's "already sent today" read is per user per event per day | A query on every propagated user | Covered by the `(user_id, local_date)` index; the read is one indexed row lookup inside the transaction that was already open |
| `local_date` is stored, so a user who changes zone has notices dated in the old one | The cap could allow or suppress one extra notice around the change | Accepted. The alternative — recomputing the date at read time — would make the cap depend on when it is asked, which is worse. The digest already stores a local date for the same reason |
| D7 widens the cap beyond FR-54's wording | Two emails in a day instead of one | Bounded, deliberate, and recorded as a PRD amendment rather than a silent departure |
| Replacing a pending notice cancels a send and mints another | Two rows per replaced notice | The old key stays spent, which AD-7 names as the intended pattern |

## Implementation Checklist

- [ ] `StateChangeNotice` and `EventNoticeMute`, one migration, forward-only
- [ ] `raise_state_notice` — AD-17-gated, unique per state change, cap by `PRECEDENCE`, mute-aware, D7 exception
- [ ] `mint_state_notice` — transactional stream, no unsubscribe URL, `slot_at` null, Quiet Hours with the D5 margin
- [ ] `mute_event_notices` / `unmute_event_notices`, with audit rows
- [ ] Amend the two `slot_at` comments (D5a)
- [ ] Tests: the cap at the boundary; a muted event raising nothing while its reminders still fire; both sides of the margin, including an event starting inside the quiet window; a repeated propagation raising exactly one notice; a terminal change overriding cap and mute
- [ ] Full suite, `import-linter`, `ruff`, `makemigrations --check`

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: pending*
