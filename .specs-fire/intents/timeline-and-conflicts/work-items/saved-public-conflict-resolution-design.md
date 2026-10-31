---
id: saved-public-conflict-resolution-design
title: Design — resolving a conflict that involves a saved public event
intent: timeline-and-conflicts
work_item: saved-public-conflict-resolution
status: proposed
created: 2026-10-31
---

# Design: Resolving a conflict that involves a saved public event

This work item is `validate` mode: it changes a **stored enum**, relaxes a **deliberate
safety rule** ("a client cannot name a saved event's id and have it deleted"), and makes a
button **delete a user's save**. Each of those is a decision that is expensive to undo
once rows exist in the field. This document resolves them before code.

Four decisions are open. Each is stated with the options, the reasoning, and the choice.

| # | Decision | Choice |
|---|----------|--------|
| D1 | New `Resolution` value vs reuse `delete_new` | **New value: `skip_public`** |
| D2 | "new side" vs "side" in the request | **New field: `side`** |
| D3 | Duplicate-kind pairs with a saved side | **Same three actions as time pairs** |
| D4 | The 409 payload shape | **Widen `ConflictOut`; the 409 already carries both sides** |

---

## D1 — A new `Resolution` value: `skip_public`

### Options

1. **New value `skip_public`** — a fifth `ConflictPair.Resolution`.
2. **Reuse `delete_new`**, interpreted per side kind (delete a personal event, un-save a saved one).

### Choice: **new value `skip_public`**

The stored word must mean one thing. `delete_new` means "the record named by the new side
was removed". If it also meant "the save was released", then a reader of the row could not
tell what happened without knowing the side's kind — and the kind is *not* in the row in a
convenient place (it is, in `left_kind`/`right_kind`, but only for the two sides the
request named).

The concrete cost of reuse shows up in the two places the resolution is read:

- **`/conflicts`' Resolved list.** The row would have to render "Deleted · Poetry
  reading" for a personal side and "Deleted · Poetry reading" for a saved side — two
  different meanings of the same word, distinguished only by a kind the list *does*
  carry. So reuse would not actually save the list any work; it would push the
  disambiguation into the presentation layer, where it is easiest to get wrong.
- **The audit trail.** `conflict.resolved` records `{"resolution": "delete_new",
  "deleted": true}`. Under reuse, `deleted` would mean "a personal event was deleted" in
  one row and "a save was released" in another. The audit is the thing operators read to
  answer "what did this user do?" — and a word that means two things makes that a
  judgement call rather than a lookup.

The cost of a new value is a migration, and the AC already budgets for one ("it changes a
stored enum (a migration and its check constraint)"). So the migration is not an
avoided cost — it is a budgeted one, and a new value spends it better.

**`skip_public` is the name, not `un_save` or `release`.** The word "skip" is what the
button says to the user ("Skip {public event}"), and a stored value should be
recognisable as the thing the user chose. `unsave` would name the *mechanism*; the
user's choice is to skip the event, and the mechanism is a side effect.

### The enum and its constraint

```python
class Resolution(models.TextChoices):
    KEEP_BOTH = "keep_both"
    EDIT_NEW = "edit_new"
    DELETE_NEW = "delete_new"
    UPDATE_EXISTING = "update_existing"
    SKIP_PUBLIC = "skip_public"   # new
```

The `conflict_pair_resolution_kind_ck` constraint currently ties a *kind* to a *set of
resolutions*:

```python
models.Q(kind="time")     & (resolution__isnull=True) | resolution__in=["keep_both", "edit_new", "delete_new"])
models.Q(kind="duplicate") & (resolution__isnull=True) | resolution__in=["keep_both", "update_existing", "delete_new"])
```

The new value joins the `time` set only. D3 explains why a duplicate pair never gets
`skip_public`.

**A note on what the constraint cannot express.** The constraint says which resolutions
are legal *for a kind*. It cannot say which are legal *for a side shape* — a
`skip_public` on a personal-vs-personal pair is legal by kind but has nothing to act on.
That is enforced in the **service**, not the database, because the side shape is only
knowable by joining the two sides. The database constraint stays coarse (kind → set) and
the service narrows it (shape → set). This is the same division the existing code already
uses: `RESOLUTIONS_BY_KIND` is the coarse map, and `_is_imported_personal_event` is a
service-level narrowing of `delete_new`.

### The migration

`conflict_pair_resolution_kind_ck` is dropped and re-added with `skip_public` in the
`time` set. The `conflict_pair_status_ck` is **unchanged** — a resolved pair carries a
non-NULL resolution and a non-NULL `resolved_at` whichever resolution it is, and that
constraint never named a resolution value.

**The migration is forwards-only and safe on a database with existing resolved pairs.**
It changes a `CHECK` constraint, not a column, so no row is rewritten and no value is
narrowed. Existing rows keep their resolutions and satisfy the new constraint, because
the new set is a **superset** of the old one for both kinds. There is nothing to
backfill. The migration must be tested against a database holding rows in all three
statuses — the AC requires this ("the migration (forwards on a database with existing
resolved pairs)").

---

## D2 — The request names the **side** the action is about

### Options

1. Keep `new_side_id`, and add a `new_side_kind` so the server can tell a saved side from
   a personal one.
2. Replace `new_side_id` with a `side` object `{kind, id}`.

### Choice: **`side: {kind, id}`** — the side the action is about

The field is renamed because the *concept* changes, not just the type.

`new_side` means "the event the user just created". That was true when the only writable
side was a personal event the user had just created. It stops being true in two places:

- **The save → 409 → resolve round trip.** The user saves a public event; it clashes; the
  409 names a pair. The saved event is the side the action is about — but it was not
  "new" in the sense of "just made by the user", it is a save.
- **`/conflicts`.** A pair can be listed days later. There is no "new" side at all —
  there are two sides, and the user picks one to act on. "New" would be a lie in the
  vocabulary.

Keeping the name `new_side_id` while widening its meaning would be worse than either
option: a client written against the old meaning ("the id of the personal event I just
created") would keep compiling and start behaving differently. **The name has to change
so the break is loud.**

`side` is a two-field object rather than two flat fields because the pair stores a side
as exactly `(kind, id)` — that is the model's own representation (`left_kind`/`left_id`).
Matching the stored shape means the server can compare the request against the row
without a translation, and it means the client cannot send a kind that contradicts a
usage of the id.

### The safety rule this relaxes, and what replaces it

The old rule was: **"The body carries the id only, not the kind: this endpoint resolves
conflicts on personal events, so the new side is a personal event by definition. That
keeps the shape narrow — a client cannot name a saved event's id and have it deleted."**

That rule was sound *given the actions available*. With only `delete_new` as a mutating
action, naming a saved side would have meant deleting a save — a destructive action on
the wrong kind of record. That is precisely the abuse the rule prevented.

The new safety property is stated in terms of **what an action can touch**, not **what
kind a side may name**:

> A resolution can only ever affect the caller's own rows, and only in the way its
> action is defined:
>
> - `skip_public` un-saves a **saved** side. It refuses a personal side — there is
>   nothing to un-save.
> - `delete_new` deletes a **personal** side, and only through
>   `delete_personal_event`. It refuses a saved side.
> - `keep_both` mutates nothing on either side.
> - `edit_new` / `update_existing` mutate nothing; they tell the client which side to
>   open.

The rule is now **per-action**, and each action's reach is stated in one place — the
action table below. The narrow shape is preserved where it still matters: a client cannot
cause a personal event to be deleted by naming a saved side, because `delete_new` only
accepts a personal side, and `skip_public` only accepts a saved side. **The kind is
enforced against the action, not against the endpoint.**

### Ownership

Every side lookup is scoped to `user_id` — the same rule the conflict list now enforces
after the leak found in the previous work item. A `side` naming another user's record is
**not found**, and the pair is rejected as not-the-caller's.

### The action table

This table is the single source of truth for what each action does, and it is what the
service and the endpoint description are both written from.

| Action | Side kind accepted | What it changes | Audit |
|---|---|---|---|
| `keep_both` | either | nothing on either side; the indicator stays (FR-58) | `conflict.resolved` |
| `edit_new` | personal | nothing; the client opens that side in the edit sheet | `conflict.resolved` |
| `update_existing` | personal | nothing; the client opens that side in the edit sheet | `conflict.resolved` |
| `delete_new` | personal | deletes that personal event, through `delete_personal_event` | `conflict.resolved` + `personal_event.deleted` |
| `skip_public` | **saved** | un-saves that saved event, through `unsave_event` | `conflict.resolved` + `saved_event.unsaved` |

**"through `unsave_event`" is the point.** The AC says "un-saves the caller's own saved
event through the existing saved-events command, with its audit entry". There is already
one path to remove a save — `unsave_event` — which closes the pairs the save took part in
and writes `saved_event.unsaved`. A second path would be a second audit trail for the
same fact.

**But `unsave_event` closes the pair it is asked to close**, as
`cleared_by_state_change`. That is right for an *unsolicited* unsave and **wrong here**:
the user is answering a prompt, so the pair's status is `resolved` with a resolution. See
D2a below.

### D2a — Ordering: resolve the pair *after* the un-save, or before?

`resolve_conflict` currently records the resolution on the pair **before** the action it
names ("the resolution is recorded on the pair *before* the action it names, so the audit
trail shows what the user chose even if the follow-up edit lands later").

But `unsave_event` calls `close_pairs_for_side`, which sets the pair's status to
`cleared_by_state_change` and its resolution to NULL — overwriting the resolution the
service just wrote, and violating `conflict_pair_status_ck` (a cleared pair must carry a
NULL resolution, and the row would then hold a status of `cleared_by_state_change` with a
non-NULL resolution).

So for `skip_public` the order must be:

1. Record the resolution on the pair (`status = resolved`, `resolution = skip_public`,
   `resolved_at = now`).
2. Un-save **without** letting the unsave close this pair.

`unsave_event` does not currently offer "don't close this pair" — it closes every pair
the save took part in. The design adds a parameter to `unsave_event`:

```python
def unsave_event(*, user_id, event_id, actor, now, keep_pair: UUID | None = None) -> None
```

`keep_pair` names one pair to **exclude** from `close_pairs_for_side`. The pair is
already `resolved` by then, and `close_pairs_for_side` only touches `active` pairs
(closing an already-resolved pair would be a no-op — but it would also *overwrite* it if
it did not filter). The exclusion makes the intent explicit rather than relying on the
ordering's side effects.

**Why not the other order** (un-save first, then resolve)? Because the unsave closes the
pair as `cleared_by_state_change`, and a `cleared_by_state_change` pair is **not
re-prompted and is not the user's history** (the previous work item excludes exactly
those pairs from `/conflicts`' Resolved section). The user's answer would vanish from
their history — the pair would read as "nobody answered". That directly violates the AC:
"Keep both keeps the indicator ... and is never re-prompted; skip and move clear it",
and the general rule that a pair the user answered is history the user created.

**Why not "record the resolution, then un-save, then re-record"?** Because it writes the
pair twice and leaves a window in which the row says `resolved` with a resolution and
then `cleared_by_state_change` without one. The exclusion parameter is the smaller
change.

The `unsaved` audit entry is written by `unsave_event` as it is today, with the
`conflict.resolved` entry written by the resolve service. **One audit trail per action**,
as the AC asks — and the two are separate facts (the pair was answered; the save was
released), so two entries is right, not two trails for one fact.

### D2b — The client contract for "skip and move clear the indicator"

FR-58 says "keep both" keeps a **calm permanent reminder**; the other two clear it. The
indicator lives on the Pulse Card and the Timeline block, and both read the pair's
status. So:

- `keep_both` → the pair stays `resolved`, and the indicator reads it as a permanent
  reminder.
- `skip_public` and `delete_new` → the side is gone, so there is nothing to remind
  about; the pair closes and the indicator clears with it.
- `edit_new` / `update_existing` → the pair is resolved, the client opens the side in
  edit mode, and **detection re-runs after the edit** (today's behaviour). If the edit
  does not remove the overlap, a **new** pair is created and the prompt appears again —
  which is correct: the overlap still exists.

**The indicator's logic is unchanged by this work item.** It already reads the pair's
status and resolution; this item only adds one more resolution value, and the "keep both"
case is the one that keeps the reminder. The AC's requirement — "Keep both keeps the
indicator (FR-58: 'a calm permanent reminder') and is never re-prompted; skip and move
clear it" — is satisfied by the **pair's status**, not by a new indicator rule. No
indicator code changes; a test pins that `keep_both` leaves the pair `resolved` and
`skip_public` removes the side.

---

## D3 — Duplicate-kind pairs with a saved side

### The question

A duplicate pair is two events with the same name — one personal, one saved. The
existing duplicate prompt offers `keep_both`, `update_existing`, `delete_new`. Which of
those makes sense when the side is a **saved** event?

### Choice: **the same three actions — `keep_both`, `update_existing`, `delete_new` — and
`skip_public` is refused**

A duplicate pair's meaning is "these two events are the same thing". The user is being
asked: one of them, or both?

- **`keep_both`** — "I'll manage both." Meaningful for a duplicate, as it is today.
- **`update_existing`** — "Update the existing one." Meaningful: the client opens the
  existing side in the edit sheet so the user can correct it. But **which side is
  "existing"**? The pair row is symmetric and stores no such thing. Today the client
  supplies the asymmetry (it knows which event it just made), which is why the endpoint
  takes the side from the body.
- **`delete_new`** — "Delete the new one." For a **saved** side this would mean deleting
  a save, which is what `skip_public` is for.

**So what does the client do for a duplicate pair with a saved side?** This is the
genuine gap, and the answer is: **the same way it does for a personal side, and the
saved side's actions are the ones that touch it.**

The design's answer: **a duplicate pair with a saved side offers exactly the three
actions a time pair offers** — `keep_both`, `update_existing`, `skip_public` — with
`delete_new` **replaced by** `skip_public` when the side the action is about is a saved
event.

That is: **the action set depends on the side the action is about, not on the pair's
kind.** The kind decides *which* actions exist for a personal side (a time pair has
`edit_new`, a duplicate has `update_existing`); the side's kind decides *what happens*
when the destructive action is chosen.

This is a cleaner model than "the kind decides the set", and it is what the action table
in D2 already implies. But it has a consequence: **`RESOLUTIONS_BY_KIND` can no longer be
the only source of the allowed set** — it would become `RESOLUTIONS_BY_KIND_AND_SIDE`.

### The consequence for `RESOLUTIONS_BY_KIND`

The AC says: "`ConflictPair.Resolution` and `RESOLUTIONS_BY_KIND` gain what the new
actions need". And the previous work item made `RESOLUTIONS_BY_KIND` the **one source**
for the actions offered in `/conflicts`. Changing its shape is therefore a real decision.

**Choice: `RESOLUTIONS_BY_KIND` stays, and a second map is added beside it.**

```python
#: The resolutions each kind of conflict offers, for a pair whose sides are personal.
RESOLUTIONS_BY_KIND: dict[str, frozenset[str]] = {...}   # unchanged

#: The resolutions each kind offers when the side the action is about is a **saved**
#: event. The destructive action is `skip_public` rather than `delete_new`: a save is
#: released, not deleted.
RESOLUTIONS_BY_KIND_SAVED_SIDE: dict[str, frozenset[str]] = {
    ConflictPair.Kind.TIME: frozenset({KEEP_BOTH, EDIT_NEW, SKIP_PUBLIC}),
    ConflictPair.Kind.DUPLICATE: frozenset({KEEP_BOTH, UPDATE_EXISTING, SKIP_PUBLIC}),
}
```

Two maps, not one map keyed by `(kind, side_kind)`, because the key is used in two
different places with two different shapes of question:

- `/conflicts` (the list) must offer the actions **for the pair**, and it presents both
  sides symmetrically — it does not know which side the user will act on. It offers the
  **union**: the actions legal for either side of that pair's shape. For a
  personal-vs-saved pair that union is
  `{keep_both, edit_new, update_existing, delete_new, skip_public}` — five actions, which
  is more than the three buttons FR-58 specifies.

Hmm. That is a problem, and it is the real content of D3.

### D3, resolved properly

FR-58 says the prompt has **exactly three buttons and no dismiss**. A personal-vs-saved
pair must therefore offer exactly three actions, and the *buttons* are about **a
specific side**, not about the pair.

**The final choice: the action set is decided by the pair's kind and by which side the
action targets, and the client always targets exactly one side.** The three buttons for a
personal-vs-saved pair are:

| Button | Action | Target side | Meaning |
|---|---|---|---|
| "Move {personal event}" | `edit_new` | the personal side | open the personal event to move it |
| "Skip {public event}" | `skip_public` | the saved side | release the save |
| "Keep both — I'll manage" | `keep_both` | — | keep both, keep the reminder |

For a **duplicate** personal-vs-saved pair, the three buttons are the same three actions
in the same order, but the first is relabelled — "Update the existing one" maps to
`update_existing` and targets the personal side (the existing one is the personal
event; the saved public event is the *new* one the user just saved). This matches how
the duplicate prompt already relabels button 2.

**So the three-button set for a pair with a saved side is:
`{keep_both, edit_new-or-update_existing, skip_public}` — where the middle action
targets the personal side and `skip_public` targets the saved side.**

And the crucial structural consequence: **for a pair with a saved side, the action
determines the target side.** The client does not choose the side; the action does.
`skip_public` *is* "the saved side"; `edit_new` *is* "the personal side".

This is why `side: {kind, id}` (D2) is still required: the server must verify that the
`side` the client sent is the one the action targets. A client that sends
`{kind: saved_event, id: X}` with `resolution: edit_new` is refused — `edit_new` does
not apply to a saved side.

### The consequence for `RESOLUTIONS_BY_KIND` — final

The two maps are **per (kind, side-kind)** pairs:

```python
#: The resolutions offered for a pair whose sides are both personal events.
RESOLUTIONS_BY_KIND: dict[str, frozenset[str]] = {
    TIME:     frozenset({KEEP_BOTH, EDIT_NEW, DELETE_NEW}),
    DUPLICATE: frozenset({KEEP_BOTH, UPDATE_EXISTING, DELETE_NEW}),
}

#: The resolutions offered for a pair with **one saved side** — the personal side is
#: the one the "move" action targets, and the saved side is the one "skip" targets.
RESOLUTIONS_BY_KIND_WITH_SAVED_SIDE: dict[str, frozenset[str]] = {
    TIME:     frozenset({KEEP_BOTH, EDIT_NEW, SKIP_PUBLIC}),
    DUPLICATE: frozenset({KEEP_BOTH, UPDATE_EXISTING, SKIP_PUBLIC}),
}
```

`RESOLUTIONS_BY_KIND` **keeps its meaning and its shape** — the AC's requirement that it
"gains what the new actions need" is met by the new map, and the existing map is
untouched, so every existing personal-vs-personal resolution behaves exactly as before
(the AC's requirement).

**Which map the list uses.** `/conflicts` presents both sides symmetrically and does
not know which side the user will act on. It offers the **union of the two maps for
that pair's shape** — which for a personal-vs-personal pair is `RESOLUTIONS_BY_KIND[kind]`
(exactly the current behaviour, three actions) and for a personal-vs-saved pair is the
union of the personal set and the saved set.

The union of `{keep_both, edit_new, delete_new}` and `{keep_both, edit_new, skip_public}`
is `{keep_both, edit_new, delete_new, skip_public}` — **four**, not three.

**So the list cannot offer the union.** It must offer **one set of three**, chosen by the
pair's shape, and the client picks the target side per action.

**Final answer for the list:** for a pair with a saved side, the list offers the
**saved-side map** (`RESOLUTIONS_BY_KIND_WITH_SAVED_SIDE[kind]`) — three actions, and the
destructive one is `skip_public`. For a pair with no saved side, it offers
`RESOLUTIONS_BY_KIND[kind]` — today's behaviour, unchanged.

Why the saved-side map and not the personal one? Because `delete_new` on a pair with a
saved side is **never** what the user wants: the user never wants their *saved public
event* deleted — they want it *skipped* (released). And `delete_new` targeting the
personal side of a personal-vs-saved pair is a real possibility ("delete my personal
event, keep the save") — but the **save is the thing the user just added**, so the
prompt's destructive button is about the save. The prompt is about the *new* thing; the
new thing here is the save.

Hmm — but wait. The pair row is symmetric and the *list* doesn't know which side is
new. On `/conflicts`, reviewed later, the user sees two events and picks.

I am going back and forth. Let me settle it with the strongest available principle and
stop:

**The list offers the actions legal for *both* sides of that pair, and the client names
the side it acts on.** For a personal-vs-personal pair that is one map (three actions).
For a personal-vs-saved pair, the actions legal for the personal side and for the saved
side differ only in the destructive one — and **both are legal**, on their own side.

So the list offers **four** for a mixed pair: `{keep_both, edit_new, delete_new,
skip_public}`.

But FR-58 says three buttons. Does FR-58's "three buttons" bind the *list*? FR-58 is
about the **prompt** — the 409 conflict prompt. The `/conflicts` page is a *list of pairs
to answer*, and the previous work item's AC asked for "the allowed actions from the one
`RESOLUTIONS_BY_KIND`". A pair can legitimately have four applicable actions because it
has two sides and each side has its own destructive option — but the *prompt* for any
one pair-and-side offers three.

**This is the honest resolution, and it is a change to the previous item's output:**

> A **personal-vs-personal** pair offers three actions: `{keep_both, edit_new-or-
> update_existing, delete_new}` — today's behaviour, unchanged.
>
> A **personal-vs-saved** pair offers four actions: `{keep_both, edit_new-or-
> update_existing, delete_new, skip_public}` — because the personal side can be deleted
> and the saved side can be skipped, and the pair has both sides.

But then the prompt (the 409) must offer exactly three — and the 409 knows which side is
new. So the **409** picks the side-specific set (three), and the **list** offers the
union (four).

Hmm, that means the list and the prompt can disagree about the action set for the same
pair. Is that acceptable? The list is "here are all the things you could do with this
pair"; the prompt is "here is what you can do with the one thing you just did". They
answer different questions. I think that is right, and it is defensible.

**But it breaks the previous item's invariant** — `conflict_list.py` reads
`RESOLUTIONS_BY_KIND[pair.kind]` and the AC said "the same `RESOLUTIONS_BY_KIND` the
resolve endpoint enforces — one source, not a second list". If the list now offers a
superset, the "one source" is still true (both read from the same maps), but the list's
value is not a single map lookup.

### The cleanest final design

Let me make the maps **per side kind**, and derive both the list's union and the
prompt's per-side set from them. One source, two derivations, no second list:

```python
#: The resolutions each kind of conflict offers **against a personal-event side**.
RESOLUTIONS_BY_KIND: dict[str, frozenset[str]] = {
    TIME:      frozenset({KEEP_BOTH, EDIT_NEW, DELETE_NEW}),
    DUPLICATE: frozenset({KEEP_BOTH, UPDATE_EXISTING, DELETE_NEW}),
}

#: The resolutions each kind of conflict offers **against a saved-event side**.
RESOLUTIONS_BY_KIND_SAVED: dict[str, frozenset[str]] = {
    TIME:      frozenset({KEEP_BOTH, EDIT_NEW, SKIP_PUBLIC}),
    DUPLICATE: frozenset({KEEP_BOTH, UPDATE_EXISTING, SKIP_PUBLIC}),
}
```

- The **409 prompt** (which knows the new side's kind) offers the set for that side:
  three actions, exactly as FR-58 requires. Today that is always
  `RESOLUTIONS_BY_KIND[kind]`, because the new side is always a personal event — so
  **existing behaviour is unchanged**.
- The **list** (which does not know which side the user will act on) offers the
  **union** of the personal set and the saved set for that pair's shape. For a
  personal-vs-personal pair that union is exactly `RESOLUTIONS_BY_KIND[kind]` — three
  actions, unchanged. For a personal-vs-saved pair it is four.
- The **resolve endpoint** accepts a resolution if it is in the set for the **side the
  request names**. `delete_new` is in the personal set and not the saved set, so it
  refuses a saved side. `skip_public` is in the saved set and not the personal set, so
  it refuses a personal side. **One map, two derivations, no second list — and the
  "one source" invariant of the previous work item is preserved.**

This is coherent, and it keeps every existing behaviour exactly as it was. The only
change the previous item sees is that a personal-vs-saved pair's `actions` tuple has
four entries instead of three.

### D3's answer, stated

> **A duplicate-kind pair with a saved side is treated exactly like a time pair with a
> saved side.** The *kind* decides the middle action's name (`edit_new` for time,
> `update_existing` for duplicate); the *side's kind* decides the destructive action
> (`delete_new` against a personal side, `skip_public` against a saved side).
>
> The prompt offers three actions — the set for the side the user just acted on. The
> list offers the union across the pair's sides, which is three for a personal-vs-
> personal pair and four for a mixed one.
>
> `skip_public` is **not** in the `duplicate` set of `RESOLUTIONS_BY_KIND`, so the
> database's `conflict_pair_resolution_kind_ck` rejects it for a duplicate pair — the
> constraint keeps its kind-based meaning, and the *side* rules are enforced in the
> service.

Wait — that last paragraph contradicts what I just decided. If `RESOLUTIONS_BY_KIND_SAVED[DUPLICATE]` contains `SKIP_PUBLIC`, then a duplicate pair **can** have `skip_public`, and the database constraint must allow it.

So the database constraint's kind-based restriction must be **relaxed**: `skip_public` is
legal for both kinds. The constraint becomes:

```python
models.Q(kind="time")     & (resolution__isnull=True) | resolution__in=["keep_both", "edit_new", "delete_new", "skip_public"])
models.Q(kind="duplicate") & (resolution__isnull=True) | resolution__in=["keep_both", "update_existing", "delete_new", "skip_public"])
```

`skip_public` is legal for both kinds. The **side** rule — that `skip_public` only
applies to a saved side — is a service rule, and the service is where the side shape is
knowable.

**That is the final D3.** `skip_public` joins both kinds' constraint sets; the
side-specific action sets live in the two maps; the constraint stops being the place
where the side rule lives (it never was).

---

## D4 — The 409 payload

### The question

The AC: "the 409's `details` carry everything the client needs to post the resolution."
The current 409 carries `{event_id, conflicts: [{pair_id, kind, other, actions}]}` — one
`other` side and a flat `actions` list. For a save → 409 → resolve round trip where the
**saved** side is the new one, the client needs to name the saved side.

### Choice: **widen `ConflictOut` to carry both sides; keep `details` narrow**

`ConflictOut` becomes:

```python
class ConflictOut(Schema):
    pair_id: UUID
    kind: str
    new_side: ConflictSideOut       # the side the user just created or saved
    other_side: ConflictSideOut     # the side it clashes with
    actions: list[str]
```

Both sides are named — matching what `/conflicts` already returns (the previous work
item's `ConflictPairView` carries `left` and `right`). The client has everything: the
pair id, both sides with their kinds, and the actions legal for the side it just acted
on.

**Why not reuse the conflict list's shape (`left`/`right`)?** Because the 409's
asymmetry is meaningful and known: the user just did something, and the prompt is about
that thing. `left`/`right` would throw that away and force the client to work out
which side it just touched. `new_side`/`other_side` names it.

**Why not keep `other` and add `new_side`?** The existing field is `other`. Renaming it
to `other_side` makes the pair symmetric and readable; keeping `other` and adding
`new_side` is asymmetric in naming. The client is regenerated anyway (`make client`), so
the break is loud — which is the same principle as D2.

**The actions in the 409 are the set for the new side** — three, always. That is
FR-58's "exactly three buttons", and it is the set the user is being asked to choose
from right now.

**The `event_id` in `details`** stays — it is the record that was written (the personal
event, or the save). For a save it is the **save's** id, which is what
`save_event`'s 409 already returns (`result.saved.id`).

---

## Summary of the design

### The API

```http
POST /api/personal/events/conflicts/{pair_id}/resolve
{
  "resolution": "skip_public",
  "side": { "kind": "saved_event", "id": "<uuid>" }
}
```

```python
class ConflictSideRef(Schema):
    kind: ConflictSideKind     # "personal_event" | "saved_event"
    id: UUID

class ConflictResolutionIn(Schema):
    resolution: ConflictResolutionValue
    side: ConflictSideRef
```

### The response

```http
200 OK
{
  "pair_id": "...",
  "kind": "time",
  "resolution": "skip_public",
  "status": "resolved",
  "action_side": { "kind": "saved_event", "id": "..." },
  "other_side":  { "kind": "personal_event", "id": "..." }
}
```

`new_side_id`/`existing_side_id` become `action_side`/`other_side` — the same
renaming principle as the request, and the response now carries the kind too, which it
did not before (the old `new_side_id` was always a personal event, so the kind was
implied).

### The service

```python
def resolve_conflict(
    *,
    user_id: UUID,
    pair_id: UUID,
    resolution: str,
    side_kind: str,
    side_id: UUID,
    actor: Actor,
    now: datetime,
) -> Resolution:
```

The signature keeps `new_side_kind`/`new_side_id`'s *shape* but renames them to
`side_kind`/`side_id`. The body changes to:

1. Look up the pair scoped to `user_id` → 404 if absent.
2. Refuse if the pair is not `active` → `ConflictAlreadyResolvedError`.
3. **Verify the named side is one of the pair's two sides.** A side that is not in the
   pair is refused — this is the "cannot be abused" requirement. Currently
   `_other_side` returns `(None, None)` for an unknown side, which is silently accepted
   and produces a resolution with no other side.
4. Choose the allowed set by **(kind, side_kind)** and refuse a resolution outside it
   → `IllegalResolutionError`.
5. Refuse `delete_new` on an imported personal event → `ImportedEventNotDeletableError`.
   (Unchanged: an imported event is a personal event, and imported events stay
   non-deletable, as the AC requires.)
6. Record the resolution on the pair (`status = resolved`, `resolution`, `resolved_at`).
7. Act: `delete_new` → `delete_personal_event`; `skip_public` → `unsave_event` with
   `keep_pair=pair.id`.
8. Write the audit entry.

### The files

| File | Change |
|---|---|
| `backend/apps/personalization/models.py` | `Resolution.SKIP_PUBLIC`; the kind constraint gains `skip_public` in both sets |
| `backend/apps/personalization/migrations/00XX_conflictpair_resolution_skip_public.py` | drop + re-add the constraint |
| `backend/apps/personalization/services/conflict_resolutions.py` | the new side-based action sets, the side-in-pair check, the `skip_public` branch |
| `backend/apps/personalization/services/saved_events.py` | `unsave_event` gains `keep_pair` |
| `backend/apps/personalization/services/conflict_list.py` | the actions for a mixed pair become the union of the two maps |
| `backend/apps/personalization/schemas.py` | `ConflictSideRef`, the reworked `ConflictResolutionIn`/`Out`, the widened `ConflictOut` |
| `backend/apps/personalization/api.py` | the resolve endpoint takes `body.side`; the 409 uses the new `ConflictOut` |
| `backend/tests/personalization/test_conflict_resolutions.py` | the new tests |
| `frontend/lib/api/` | regenerated by `make client` |

### The tests

| Test | Proves |
|---|---|
| Every action against both pair shapes | `keep_both` / `edit_new` / `delete_new` against personal-vs-personal; `keep_both` / `edit_new` / `skip_public` against personal-vs-saved |
| An illegal action is refused | `skip_public` on a personal side; `delete_new` on a saved side; `update_existing` on a time pair |
| Ownership | another user's pair → 404; a side naming another user's record → 404 |
| The already-resolved case | a second resolve → `ConflictAlreadyResolvedError` |
| A side not in the pair | refused |
| The migration | forwards on a database holding rows in all three statuses |
| `skip_public` writes the audit | `conflict.resolved` + `saved_event.unsaved`, and the pair's resolution is `skip_public` (not `cleared_by_state_change`) |
| Imported events stay non-deletable | `delete_new` on an imported personal event → `ImportedEventNotDeletableError` |
| The round trip | save → 409 → resolve → the save is gone and the pair is `resolved` with `skip_public` |

---

## Open questions for Checkpoint 1

1. **D3's union in the list.** A personal-vs-saved pair's `actions` becomes **four**
   (`keep_both`, `edit_new`/`update_existing`, `delete_new`, `skip_public`) rather than
   three. The 409 prompt stays at three. Is a four-action list entry acceptable, or
   should the list offer only the saved-side set (three, with `skip_public` and no
   `delete_new`)?
2. **The `delete_new` on the personal side of a mixed pair.** Under the union it is
   offered; under the saved-side-only set it is not. The union says "you may delete your
   personal event, or skip your save" — both are real choices.
3. **`keep_both` on a mixed pair keeps the indicator** on both sides, including the
   saved side. Confirmed as the intent by FR-58's "calm permanent reminder"?

---

*Design proposed. Implementation follows approval.*
