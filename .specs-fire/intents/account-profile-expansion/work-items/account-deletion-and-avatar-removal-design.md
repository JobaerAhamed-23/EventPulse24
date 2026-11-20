---
work_item: account-deletion-and-avatar-removal
intent: account-profile-expansion
created: 2026-11-20
mode: validate
---

# Design: Deleting an Account — and the Picture That Must Not Outlive It

## Summary

Two named commands in `apps/identity/services/` — `request_account_deletion` and
`cancel_account_deletion` — plus a `destroy_account` command the worker runs when the
30-day grace expires. A `DeletionRequest` row holds the grace period. The picture's
object is removed **when the account is destroyed**, not when deletion is requested, so
a user who cancels gets their picture back.

**The scope is deliberately bounded.** This item builds the deletion *engine* and the
audit trail, and it makes the picture's removal a real, probed fact. The A-16 modal is
**explicitly scoped to a follow-up item** — this one says why that is honest rather than
quiet.

## Findings that shape this design

Probed, not assumed.

### 1. There is no retention sweep, and `shared/retention.py` names one that does not exist

`shared/retention.py:5` says *"The sweep job, account deletion and export (FR-52) all
read `retention_registry()`."* **There is no sweep job.** `worker/tasks.py` has
`sweep_due_sends` — which sweeps *due outbound sends*, not expired rows — and
`config/management/commands/` has no purge command. The docstring names a thing that
was never built.

**This matters because the 30-day grace period needs a clock.** Three options:

| Option | Cost |
|--------|------|
| A new worker task that scans for expired deletion requests | Correct, and touches the worker — a larger surface than this item wants |
| A management command an operator runs | Not automatic; the promise of "within 30 days" becomes "when someone remembers" |
| **A dedicated `destroy_account` command, plus a worker task that calls it** | **Chosen.** The command is the unit of behaviour and is testable alone; the task is a thin caller |

**The command is the deliverable; the task is a caller.** That way the grace period has
a real mechanism without this item becoming a worker redesign.

### 2. The audit tables are append-only, and `delete()` raises

`shared/models.py` — `AppendOnlyModel.delete()` raises `AppendOnlyViolation`, and a
Postgres trigger `forbid_history_mutation()` refuses `DELETE` on the audit tables unless
`SET LOCAL eventpulse.retention_purge = 'on'` is in effect. **No Python code sets that
setting** — the tests do it by hand (`tests/ingestion/test_triggers.py:121`).

**"The audit log survives" therefore means the opposite of what it sounds like.** The
audit rows are *not* deleted by account deletion. They are append-only by design, and
AD-13 keeps PII out of them precisely so they can outlive the account. So deletion does
not need to purge them, and must not try: doing so would need the purge session setting
and would destroy the record that the deletion happened.

**But the four audit tables reach their user through `actor_id`, not `user_id`**
(`shared/models.py:127`, `export_user_path = "actor_id"`). So the deletion *enumeration*
has to find them — while the deletion *action* leaves them alone.

### 3. The audit row for a deletion cannot be written by the deleted account

`write_audit` requires an open `transaction.atomic(using=PERSONAL)` and an `Actor`. The
deletion's own audit row must say *the account asked to be deleted* — but the row is
written **before** the account is destroyed, so `Actor.user(user_id)` still resolves
against a live row.

**The actor for a deletion is the account itself.** `Actor.user(user.pk)` carries the id
and no label, which is exactly right: AD-13 forbids an email in a label, and an id is
not PII in the sense the audit table cares about (the row is *about* that id).

### 4. `SavedCollectionItem` reaches its user through its collection

`apps/personalization/models.py:1289` — `export_user_path = "collection__user_id"`. It
has no `user_id` of its own, and it is in `ACCOUNT_CONTENT`. The deletion walk must use
the same per-model path resolution the export uses, or collection items survive their
own collection.

**The export's machinery is the right pattern and is directly reusable.** `export_serializer`
already answers "which models are the user's" and "how does this model reach its user",
reading `retention_registry()`. **But it is not the same question**, and reusing it
wholesale would be wrong:

- The export's `EXPORTED_CATEGORIES` is a *portability* set. Deletion needs a
  *retention* set — which categories die with the account, and which survive their own
  window.
- The export skips `sessions.session` (not portable). Deletion must **delete** it.

So the deletion gets a **sibling** module beside the export serializer, sharing the same
two answers it can honestly share — the registry walk and the per-model user path — and
answering the category→action question in its own place.

### 5. `sessions.session` has no user column

The user id lives inside the encoded `session_data` payload. `session.py:_user_sessions`
already reads every session and filters in Python. Deletion reuses that exact helper
rather than inventing a second way to find a user's sessions.

### 6. The bucket has no list, no exists, and no head

`ports/blob.py` — `BlobPort` has `put`, `open`, `delete`, `url_for`. Nothing else. The
only existence probe is `open(key)` raising `BlobNotFound`. **And `delete("")` raises
`ValueError`** from `_validate_key` — not a `BlobError` — so the empty-key case must be
guarded *before* the delete, which is exactly what `clear_user_avatar` already does
(`if previous:`).

### 7. A-16 specifies a modal, and the modal does not exist

`_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/DESIGN.md:305`
(`component.modal.account-delete`) and `EXPERIENCE.md:415`
(`Component.Modal.AccountDelete`) specify: 480px modal, three paragraphs (30 days;
anonymised aggregates survive; cancel any time), **type-to-confirm gated on exactly
`DELETE`, case-sensitive**, Cancel + "Start 30-day deletion" footer, focus trapped,
`Esc` closes, `Enter` on the input does **not** submit.

`/settings/privacy` renders only the ranking formula, and its own docstring records
that deletion is not there. There is no modal component anywhere in the frontend.

## Scope

**In scope:**

- `DeletionRequest` model + migration (the grace period, cancellable)
- `request_account_deletion`, `cancel_account_deletion`, `destroy_account` — named
  commands (AD-5)
- The retention walk: every model with a `retention_category` is classified into
  **purge / keep-for-own-window / not-the-user's**, and the classification is
  **enumerated and asserted** so a model added later cannot be silently missed
- The avatar object's removal, **probed in the bucket**
- Sessions ended
- Audit rows, carrying no PII (AD-13)
- An API endpoint to request and to cancel deletion (the *engine*'s door)
- A worker task that calls `destroy_account` when the grace expires

**Out of scope, explicitly:**

- **The A-16 modal.** Scoped to a follow-up item, and said so in the work item and in
  the plan. The rationale is below.
- The anonymised aggregates A-16 promises — they are produced by the analytics pipeline,
  not by this command, and no aggregate row carries a user id to begin with.
- Billing cancellation. `Subscription` is `BILLING_RECORDS` — it survives, per its own
  window. The billing provider's own cancellation is a Stripe-side fact and is a
  separate item.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Where the grace period lives | A `DeletionRequest` row on `identity` | The row is the fact. It has a `scheduled_for` the worker reads. Cancelling is deleting the row, and the account comes back whole — **including its picture**, because the object was never removed. |
| When the picture's object is removed | **When the account is destroyed, not when deletion is requested** | The work item resolves the tension explicitly. Removing the object at request time makes the grace period a lie: the user cancels and their picture is gone. Removing it at destruction means the bucket holds a picture for thirty days after the person asked the product to stop holding it — **and that is the lesser cost, because the grace period is a promise the product made.** |
| How a model is classified | By **retention category**, with a per-model override for the exceptions | Same discipline as the export: a category, never a model name. A model cannot be forgotten into or out of deletion by being renamed. |
| Audit rows | **Survive.** Not purged. | They are append-only, AD-13 keeps PII out of them precisely so they can outlive the account, and they are the record that the deletion happened. Purging them would need the `retention_purge` session setting and would destroy the trail. |
| Billing records | **Survive** per `BILLING_RECORDS` | The acceptance criterion says so. Seven years, for tax and legal. |
| The actor on the deletion's audit row | `Actor.user(user.pk)` | The account asked. An id is not PII in the sense AD-13 means; an email would be. |
| Where the walk lives | A **sibling** of `export_serializer`, in `apps/identity/services/` | It shares the registry walk and the per-model user path, and answers the category→action question itself. It is not the export: the export answers *"what may this person carry away"*, deletion answers *"what dies with them"*. |
| The purge session setting | The destroy command sets `SET LOCAL eventpulse.retention_purge = 'on'` | The DB triggers refuse `DELETE` on append-only tables otherwise. **The setting exists in the triggers and no Python sets it** — this is the first production code to do so, and it is exactly what the triggers were written for. |
| The A-16 modal | **Out of scope, named as a follow-up** | See below. |

## Why the A-16 modal is scoped out rather than built

The work item's criterion is: *"The deletion is driven from a surface the user can reach
(A-16's modal), **or that surface is explicitly scoped to a follow-up item**."* The
second clause exists precisely for this case.

**Building the modal is a different kind of work from building the engine.** The engine
is a set of commands with a retention classification, a grace period, an object removal
and an audit trail — all of it backend, all of it testable against a real Postgres. The
modal is a 480px dialog with a focus trap, a case-sensitive type-to-confirm gate, and
three paragraphs whose exact wording A-16 fixes — all of it frontend, all of it e2e.

**More importantly, the modal would be built against an engine whose shape is not yet
settled.** A-16's third paragraph promises *"You can cancel anytime during the 30-day
grace from this page or from the email we send."* Two of those three promises are
**engine work this item does not build**: a cancellable row on a page, and a *deletion
email*. Building a modal that promises an email we do not send would be worse than not
building it — it would be a lie with a type-to-confirm gate in front of it.

**So this item builds the engine, exposes it over the API, and scopes the modal to a
follow-up item that can honour all three paragraphs.** The work item is updated to say
so, and the API's existence means the follow-up has something to call.

## Data Models Affected

### Creates

- **`DeletionRequest`** (on `identity`, `personal` schema)
  - `user_id` (UUID, by value — no FK, AD-3/OQ-8)
  - `requested_at` (timestamptz)
  - `scheduled_for` (timestamptz — `requested_at + 30 days`)
  - `retention_category = RetentionCategory.ACCOUNT_IDENTITY` (AD-15)
  - One forward-only migration.
  - **Why a separate model and not a column on `User`:** a column on `User` would have to
    be nullable and would travel with every read of the account — including the export
    and every `me` call — for a fact that is true for a thirty-day window and then false.
    A row that exists only while the deletion is pending says exactly what it is.

### Modifies

- **`User`**: no schema change. The `avatar_key` docstring's caveat ("nothing deletes an
  account yet") becomes false, and the caveat is removed in the same pass.

## The retention walk — the classification

Every model with a `retention_category` is in exactly one bucket.

| Bucket | Categories | What happens |
|--------|-----------|--------------|
| **Purge** | `ACCOUNT_CONTENT`, `PREFERENCE_SIGNALS`, `EMAIL_DELIVERY_EVENTS` | The rows are deleted with the account. |
| **Survive** | `AUDIT_LOG`, `BILLING_RECORDS` | The rows stay. They carry no PII (AD-13) and have their own legal windows. |
| **Purge with the account** | `ACCOUNT_IDENTITY` | The rows are deleted — **except the audit rows** and **except the billing rows**, which are named above. |
| **Not the user's** | `SOURCE_REGISTRY`, `TOS_REVIEW_RECORDS`, `ANALYTICS_AGGREGATES`, `NOT_USER_DATA` | Untouched. These are the catalog's and the operator's records, and the anonymised aggregates A-16 promises. |
| **Not in `personal`** | any model whose router alias is `catalog` | Untouched, and never queried. The alias filter is AD-3, and the export already learned this lesson — its first version reached `ingestion.IngestionAuditEntry` and the suite caught it. |

**The assertion that makes the classification honest.** A test walks
`retention_registry()` and asserts that **every** model with a category is either
classified, in the `catalog` schema, or a framework model. A model added next year
without a classification **fails the test** — it is the same guarantee the export's
`test_every_exported_model_can_name_its_user` gives.

**Per-model exceptions.** Three models do not fit the category rule:

| Model | Why | What happens |
|-------|-----|--------------|
| `identity.identityauditentry` | `AUDIT_LOG`, but its user is `actor_id` | **Survives** |
| `identity.subscription` | `BILLING_RECORDS` | **Survives** |
| `personalization.savedcollectionitem` | reaches its user through `collection__user_id` | Purged, via that path |

And `sessions.session` — a framework model, `ACCOUNT_IDENTITY`, no user column, and a
live credential — is **deleted** by decoding each session's payload, exactly as
`session.py` already does.

## Technical Approach

```
  request_account_deletion(user_id)
      │
      ├─ 1. refuse if a request already exists ... (idempotent: return the existing one)
      ├─ 2. create DeletionRequest(scheduled_for = now + 30d)
      ├─ 3. write_audit(action="account_deletion_requested", details={})
      └─ commit

  cancel_account_deletion(user_id)
      │
      ├─ 1. delete the DeletionRequest row
      ├─ 2. write_audit(action="account_deletion_cancelled", details={})
      └─ commit
      ── the account, its rows and its picture are all still exactly as they were

  destroy_account(user_id)          ← the worker calls this when the grace expires
      │
      ├─ 1. SET LOCAL eventpulse.retention_purge = 'on'   (inside the transaction)
      ├─ 2. read the avatar key ──────────────────────────── remember it
      ├─ 3. purge every PURGE-classified row for the user
      ├─ 4. delete the sessions (decoded payload)
      ├─ 5. delete the User row
      ├─ 6. write_audit(action="account_deleted", actor=user, details={})
      │     ── survives the account's own deletion; append-only
      ├─ 7. commit
      └─ 8. on_commit: blob.delete(avatar_key)  ← THE PICTURE GOES HERE
            └─ only if the key is non-empty; `delete("")` raises ValueError
```

**Step 8 is the whole point of the item.** The object is removed when the account is
destroyed, after the commit, and only if there was an object. `avatar.py`'s ordering
argument applies here too: the object store has no transaction, so the object is
removed *after* the row that named it is gone.

**And a failure to delete the object is a leak, not an error.** The account is already
destroyed; raising would turn a successful deletion into a failed one in the caller's
eyes, and there is nothing left to undo. `_delete_quietly` in `avatar.py` already states
this rule, and the destroy command uses the same shape.

## Affected Files

| File | Action | Purpose |
|------|--------|---------|
| `backend/apps/identity/models.py` | Modify | `DeletionRequest`; remove the `avatar_key` deletion caveat |
| `backend/apps/identity/migrations/00XX_deletionrequest.py` | Create | Forward-only |
| `backend/apps/identity/services/deletion.py` | Create | The three commands + the retention walk |
| `backend/apps/identity/services/__init__.py` | Modify | Publish the commands |
| `backend/apps/identity/api.py` | Modify | Two endpoints: request and cancel |
| `backend/apps/identity/schemas.py` | Modify | The request/cancel shapes |
| `backend/worker/tasks.py` | Modify | The grace-period task |
| `backend/tests/identity/test_account_deletion.py` | Create | The engine, with mutation probes |
| `backend/tests/identity/test_account_deletion_api.py` | Create | The endpoints |
| `backend/tests/identity/test_deletion_retention_walk.py` | Create | The classification assertion |
| `backend/tests/worker/test_account_deletion_task.py` | Create | The grace-period task |

## Security Considerations

- **The audit row carries no PII** (AD-13) — `details={}`, and the actor is an id.
- **The picture's key never reaches the audit log** — same rule `set_user_avatar` already
  follows.
- **The deletion is authenticated twice**: the endpoint requires a session, and the
  command takes the user id as an argument rather than reading "the current user" from
  ambient state.
- **The CSRF check comes first** on both endpoints, as on every write on that router.
- **The avatar object is private** and its URL is a redirect minted per request; deleting
  the account removes the object the redirect would point at.
- **`SET LOCAL eventpulse.retention_purge = 'on'` is scoped to the transaction** — it
  cannot leak into a later statement.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| A model added later is not classified | **High** — silent data survival | The classification assertion fails the build. This is the same guarantee the export gives. |
| The purge session setting leaks past the transaction | Medium | `SET LOCAL` is transaction-scoped by PostgreSQL, and it is set inside the atomic block. |
| A model's `delete()` is blocked by an append-only guard | Medium | The audit tables are classified as **survive**, so they are never deleted. The purge setting covers the rest. |
| Deleting the `User` row before its children | High — an FK error | Children are purged first, in the same transaction, and the `User` row is last. |
| The bucket delete fails | Low | `_delete_quietly` — a leak, not an error. The account is already gone; there is nothing to undo. |
| The 30-day promise is not kept automatically | Medium | A worker task calls `destroy_account` for every due request. The command is the unit of behaviour; the task is a caller. |
| The A-16 modal is missing | Medium | Scoped to a follow-up item, named in the work item and the plan, and the API it needs exists. |

## Implementation Checklist

- [ ] `DeletionRequest` with `retention_category`; one forward-only migration
- [ ] `request_account_deletion`, `cancel_account_deletion`, `destroy_account` (AD-5)
- [ ] The retention walk: category → action, with the three per-model exceptions
- [ ] **The classification assertion** — every categorised model is classified, in `catalog`, or a framework model
- [ ] The avatar object removed in `on_commit`, **only if the key is non-empty**
- [ ] The account with **no** avatar deletes cleanly
- [ ] Sessions deleted by decoding the payload (reuse `session.py`)
- [ ] Audit rows: requested, cancelled, deleted — all with `details={}`
- [ ] The audit rows **survive** the account
- [ ] Billing records **survive**
- [ ] `SET LOCAL eventpulse.retention_purge = 'on'` inside the transaction
- [ ] Two endpoints: request and cancel; CSRF first; 401 anonymous; 403 without a token
- [ ] The worker task that destroys accounts whose grace has expired
- [ ] The API contract regenerated (`make client`) and `test_contract.py` green (AD-19)
- [ ] Every test probed by mutation
- [ ] `tests/architecture/test_no_direct_writes.py` green; `lint-imports` green
- [ ] The work item updated to scope the A-16 modal to a follow-up item

---
*Generated by specs.md - fabriqa.ai FIRE Flow*
