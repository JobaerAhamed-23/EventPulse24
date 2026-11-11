---
run: run-eventpulse24-026
work_item: review-queue-model
intent: trust-loop
mode: validate
checkpoint: plan (checkpoint 2)
approved_at: 2026-11-10
---

# Implementation Plan: Something to queue onto — the ReviewItem and the editorial group

## Approach

Build exactly what the approved design (D1–D12) fixes, in this order:

1. The constant.
2. The model and its constraints.
3. A migration, hand-checked against `makemigrations` output, with the trigger in `RunSQL` and reverse SQL.
4. The `raise_review_item` command.
5. The editorial grant.

Tests come before or alongside each piece. The constraint and trigger tests use **raw SQL on the catalog connection**, following `tests/ingestion/test_triggers.py`'s `restricted()` helper, so a pass proves the database layer itself and not a Python guard. Every rejection test asserts the specific constraint name or trigger message, so a test cannot pass because a *different* check fired.

The grant change is shown failing first. The existing `test_the_editorial_group_holds_exactly_the_granted_permissions` (`len == 12`, the `EXPECTED_CODENAMES` set) must fail after the `EDITORIAL_GRANTS` edit and before its expectation is updated.

**Concurrency** follows `tests/ingestion/test_ingest_concurrency.py`: `transaction=True` and two threads, each with its own connection. A `threading.Barrier` releases both raisers into `raise_review_item` together, and the test asserts one row with tallies summing to 2. To prove the test can fail, a recorded probe temporarily removes the `IntegrityError` recovery. The test must then raise, and the probe is reported in the test report.

**The closed-row race (D10)** is tested deterministically, not with threads. The first insert is forced to collide, and the open row is resolved between the collision and the locked re-read, using a monkeypatched hook on a private `_reread_open` seam. The assertion is that a fresh row was opened and the closed row is untouched.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/apps/ingestion/migrations/0008_reviewitem.py` | `CreateModel` (generated, then reviewed), plus `RunSQL` for `catalog.guard_review_item()` and the `review_item_guard` trigger, with reverse SQL |
| `backend/apps/ingestion/services/review_queue.py` | `raise_review_item`, `RaiseResult`, and the private `_reread_open` seam (D10) |
| `backend/tests/ingestion/test_review_item_model.py` | D1, D3, D6 and D8 constraints; D2 partial uniqueness; D7 trigger, `FIXED_FIELDS` parity, and delete under purge; the `report_count` property; retention category |
| `backend/tests/ingestion/test_review_queue.py` | Raise, bump, validation, the audit action and actor (D4), a raise after a close, and the closed-row race |
| `backend/tests/ingestion/test_review_queue_concurrency.py` | Two-thread concurrent raise, `transaction=True` |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/shared/constants.py` | `REVIEW_SLA_USER_REPORTED = timedelta(hours=24)`, beside the other review and confidence constants |
| `backend/apps/ingestion/models.py` | The `ReviewItem` class, which has: the `Reason`, `Status`, `Resolution` and `ReportCategory` choices; the `REPORT_FIELDS` map (category to column); `FIXED_FIELDS`; fields; the six constraints; the partial index; `retention_category = SOURCE_REGISTRY`; and the `report_count` property. The module docstring's ownership line already names `ReviewItem`. |
| `backend/tests/ingestion/factories.py` | `ReviewItemFactory`, open, with an `in_review` event target by default |
| `backend/config/management/commands/seed_local_stack.py` | `EDITORIAL_GRANTS["reviewitem"] = ("change", "view")`; docstring "twelve" becomes "fourteen" (both places) |
| `backend/tests/e2e/test_end_to_end.py` | `EXPECTED_CODENAMES` gains `change_reviewitem` and `view_reviewitem`; `len == 14`; adds `has_perm("ingestion.delete_reviewitem") is False` and `has_perm("ingestion.add_reviewitem") is False` |

## Tests

| Test File | Coverage |
|-----------|----------|
| `test_review_item_model.py` | **Target check:** an event item with a source too, an event item with neither target, and a source item with an event (each asserts `review_item_target_ck`). **Uniqueness:** a second open (event, reason) is refused, while a second item with a different reason on the same event, and a second item after a close, are both allowed. **Tallies** on a non-report item are refused. **Due date:** `due_at` null on a report is refused, and `due_at` set on `in_review` is refused. **Resolution (D6):** open with a resolution, resolved without a resolver, `approved` by a system actor, `withdrawn` by a user, `dismissed` on an event item, and `approved` on a source item. **Trigger (D7):** an update of a resolved row is refused, a change to `reason`/`event_id`/`source_id`/`raised_at` on an open row is refused, delete is refused, and delete is allowed under `retention_purge`. **Parity:** the trigger body's fixed columns equal `ReviewItem.FIXED_FIELDS`. |
| `test_review_queue.py` | **Raise:** creates an open row with `due_at = now + 24h` for a report, and none otherwise. **Bump:** increments the right tally, leaves `due_at` alone, and moves `last_raised_at`. **Audit:** `review_item_raised`, then `review_item_bumped`, with the passed actor. **D4:** a report-raised audit row has `actor_kind=system` and `actor_id IS NULL`. **Validation:** a missing category on a report, a category on a non-report, a reason/target mismatch, and no target at all each raise `ValidationError` and write nothing. **After a close**, a raise opens a new row. **Closed-row race:** handled by the seam. **Transaction:** calling inside an outer catalog atomic block that then rolls back leaves no row and no audit. |
| `test_review_queue_concurrency.py` | Two threads raise the same (event, `user_reported`) with different categories. The result is one open row, two tallies at 1, `report_count == 2`, and two audit rows. |
| `tests/e2e/test_end_to_end.py` (modified) | The grant set is exactly 14 codenames, and there is no add or delete on `reviewitem` |

## Technical Details

- **Migration numbering.** The latest is `0007_source_cadence_ceiling`, so this is `0008_reviewitem`. One migration, forward-only, per the constitution.
- **Resolver columns** are `resolved_by_kind` (CharField, blank), `resolved_by_id` (UUID, null) and `resolved_by_label` (CharField(64), blank). The D6 check is written out in full rather than reusing `actor_check()`, because `actor_check()` requires a non-empty kind.
- **The bump** is `ReviewItem.objects.using(CATALOG).filter(pk=…, status="open").update(**{col: F(col) + 1}, last_raised_at=now, updated_at=now)` after the `select_for_update()` read. If the filtered update returns 0, the row closed under us, and we retry the insert once (D10).
- **Errors:** `domain.errors.ValidationError`, with the `details={"errors": [...]}` shape `_add_domain_error` already reads, so the admin item can surface refusals for free.
- **No new ruff or import-linter exceptions.** `review_queue.py` imports only `apps.ingestion.models`, `apps.ingestion.services.audit`, `shared.*` and `domain.errors`.
- **Verification commands**, using the existing toolchain: `uv run pytest`, `uv run python manage.py check`, `uv run python manage.py makemigrations --check --dry-run`, `uv run lint-imports`, `uv run ruff check` and `uv run ruff format --check`. The local Postgres must be up; if Docker is stopped, run `systemctl --user start docker-desktop` and then `make up`.

## Based on Design Doc

Reference: `.specs-fire/intents/trust-loop/work-items/review-queue-model-design.md` (checkpoint 1 approved, 2026-11-10)

---
*Plan approved at checkpoint. Execution follows.*

---

## Work Item: event-rejection-state

**A reject that is a state, not a delete** — high complexity, validate mode.
Built from `event-rejection-state-design.md` (checkpoint 1 approved, 2026-11-10).

### Approach

A Reject is **two writes in one `CATALOG` transaction**, and the design's central finding is that neither is sufficient alone:

1. `Event.publication_status = 'rejected'` — removes the event from all ten public reads with **no read code changed**, because every one of them filters `publication_status == published` by equality.
2. A deliberate `event_version + 1` and an `EventStateChange(kind='delisted')` — the only way to reach savers, whose rows are across the schema wall. It rides the existing AD-17 outbox: `_record_change` already enqueues propagation on commit.

Write 1 alone leaves reminders firing for an event editorial called fake. Write 2 alone leaves it visible.

`publication_status` deliberately does **not** join `LIFECYCLE_FIELDS` (design D2): ingestion already moves events `in_review → published` silently on every re-resolution, and that transition must not start demanding version bumps or emitting changes to savers. The trigger only *requires* a bump when a lifecycle field moves and never forbids a deliberate one, so the command bumps the version itself.

**The command layer** is a new `editorial_state.py`, holding the guards, the actor rule and the audit write. The low-level write is published from `event_writes.py`, which already owns `_record_change` and `_request_revalidation` — so `EventStateChange` keeps exactly one writer.

### Files to Create

| Path | Purpose |
|---|---|
| `backend/apps/ingestion/services/editorial_state.py` | `reject_event` and `reinstate_event` — the only writers of `rejected`. Guards, user-actor rule (AD-14), audit entry (AD-5). |
| `backend/apps/ingestion/migrations/0009_event_rejected.py` | The `PublicationStatus` / `Kind` choices and the `guard_event_write` replacement, forward and reverse. |
| `backend/tests/ingestion/test_editorial_state.py` | The two commands: guards, idempotency, actor refusal, audit shape, the change row's kind and version. |
| `backend/tests/ingestion/test_rejected_triggers.py` | The four legal transitions, and each refused without the version bump. Raw SQL through `connections[CATALOG]`, asserting `RestrictViolation`. |
| `backend/tests/ingestion/test_rejected_absence.py` | One absence test per public read, each proven to fail when its filter is removed. |
| `backend/tests/e2e/test_rejection_proof.py` | Save → reject → no email, reminders cancelled, pair still open, absent everywhere → reinstate → reminders re-minted, pair intact. |

### Files to Modify

| Path | Change |
|---|---|
| `backend/apps/ingestion/models.py` | `PublicationStatus.REJECTED`; `EventStateChange.Kind.DELISTED` and `RELISTED`. |
| `backend/shared/constants.py` | `LIFECYCLE_SEND_BEHAVIOUR` += `delisted: CANCEL`, `relisted: REMINT`. `LIFECYCLE_PERSONAL_BEHAVIOUR` += both as `NONE`, each carrying its D5/D6 rationale in the comment beside it. |
| `backend/apps/ingestion/services/event_writes.py` | Publish `apply_publication_change(...)` over the existing `_record_change` + `_request_revalidation`. Freeze `publication_status` in the update path when the stored event is `rejected` (D8). |
| `backend/apps/delivery/services/state_notices.py` | `raise_state_notice` returns `False` for `delisted` and `relisted` at guard 0, where the typo-only `detail_changed` is already refused. |
| `backend/tests/worker/test_propagation_tasks.py` | Extend `test_only_sold_out_and_detail_changed_skip_the_personal_side` to the four NONE kinds; narrow `test_the_kinds_that_skip_the_personal_side_still_keep_their_sends` to its real invariant; add `test_a_kind_that_skips_the_personal_side_moves_no_time`. |
| `backend/tests/delivery/test_scheduled_sends.py` | The parametrised sweep at :861 picks up the two new kinds automatically; add the `delisted → CANCEL` case explicitly. |
| `backend/tests/domain/test_notices_and_sources.py` | Assert both new kinds raise no notice. |

### Tests

Following `testing-standards.md`: `test_<unit>_<condition>_<expected>`, `@pytest.mark.django_db(databases=[PERSONAL, CATALOG])` for anything touching catalog, frozen time, factories, no mocked ORM.

- **Transitions (6+):** the four legal moves with `v+1`; each refused without the bump; `rejected` is *not* terminal (unlike `superseded`).
- **Absence (10):** catalog list, catalog detail, city page, Event Fit, URL feed (×2), preview, digest candidates, sitemap/share slug, public Event URL. Each paired with a mutation probe proving it fails when its filter is dropped — the project's standing bar.
- **Re-entry (3):** a re-poll of a rejected source item does not republish it (D8); it still updates the `ExtractedRecord`; it raises no new `ReviewItem` (D9).
- **Propagation (5):** `delisted` cancels pending sends; raises no notice; writes nothing on the personal side; leaves the conflict pair open and `available: false`; `relisted` re-mints.
- **Map parity (3):** the two extended tests plus the new "skips personal ⟹ moves no time" invariant.
- **Commands (5):** idempotent re-reject; reject of an already-rejected event; `Actor.system` refused; audit entry written; revalidation enqueued.

### Technical Details

- **Migration numbering.** `0008_reviewitem` is committed, so this is `0009_event_rejected`. Forward-only, one per PR.
- **The trigger rule** fires only on the boundary into or out of `rejected`, so ingestion's silent `in_review ↔ published` transitions are untouched:
  ```sql
  IF (OLD.publication_status = 'rejected') IS DISTINCT FROM (NEW.publication_status = 'rejected')
     AND NEW.event_version <> OLD.event_version + 1 THEN
    RAISE EXCEPTION 'entering or leaving rejected needs event_version + 1'
      USING ERRCODE = 'restrict_violation';
  END IF;
  ```
  Written as `CREATE OR REPLACE FUNCTION`, following `0002_ingest_pipeline`'s precedent; the reverse restores the `0002` body verbatim.
- **Naming.** `rejected` is the verdict (FR-57's button); `delisted`/`relisted` is the consequence that travels. Avoids collision with `Gate.REJECT` ("never becomes an Event") and `ReviewItem.resolution = withdrawn`.
- **Actor.** Both commands require `Actor.user(...)`; `Actor.system(...)` raises `ValidationError`. AD-14: a job must not be able to reverse an editor.
- **Errors:** `domain.errors.ValidationError` with the `details={"errors": [...]}` shape, so the admin surfaces refusals for free.
- **No new ruff or import-linter exceptions.** `editorial_state.py` imports only `apps.ingestion.models`, `apps.ingestion.services.{audit,event_writes}`, `shared.*` and `domain.errors`.
- **No API change**, so no `make client` regeneration and no OpenAPI diff. The frontend is untouched: `available: false`, `catalog_event_missing`, `public_slug: None` and `status: None` already render.
- **Verification:** `uv run pytest`, `manage.py check`, `makemigrations --check --dry-run`, `lint-imports`, `ruff check`, `ruff format --check`, coverage at both gates (80% / 100% `domain/`). Postgres must be up (`make up`).

### Deviations from the Design

None. The plan implements the approved design as written.

### Based on Design Doc

Reference: `.specs-fire/intents/trust-loop/work-items/event-rejection-state-design.md` (checkpoint 1 approved, 2026-11-10)

---

## Work Item: reliability-score-domain

**The arithmetic of trust — FR-16's score as pure functions** — medium, confirm mode.

### Approach

Pure `domain/` code: Decimal-only functions, no Django, no database, beside `confidence.py`
and `ranking.py`. The recompute job (`reliability-recompute-and-escalation`) and the ranking
consumer (`ranking-consumes-reliability`) both call it later; this item builds the arithmetic
and nothing that stores or schedules anything.

Two readings the AC required to be confirmed were settled with the user on 2026-11-10, both
after checking the arithmetic rather than the prose.

### Decisions confirmed at this checkpoint

**D1. Under 30 observations the posterior moves, clamped at 0.32.**

FR-16 says both "a source needs at least 30 observations before its score moves" *and* "a new
source (under 30 observations) cannot have its score drop below 0.32". Taken literally the
first makes the second unreachable.

The arithmetic resolves it. With α=β=5 the all-negative posterior runs 0.50, 0.45, 0.42, 0.38,
0.36, **0.33** (n=5), **0.31** (n=6) — so **0.32 is the posterior after five or six straight
failures**. It is not the floor at n=29, which is 0.13. Read that way the floor is a
deliberate statement: *until there are 30 observations, never judge a source worse than about
five strikes.*

So `reliability_score` = `max(posterior_mean, 0.32)` while `n < 30`, and the plain posterior
at `n >= 30`. Escalation requires `n >= 30`, so the clamp never suppresses one.

**PRD amendment owed:** FR-16's "before its score moves" → "before its score moves freely".

**D2. The 3× spike is measured on the rate of bad events, not on the score.**

A ratio of scores cannot fire, and this was verified numerically rather than asserted:

- Under 30 observations D1's clamp pins the score between 0.50 and 0.32 — a ratio of at most
  **1.56**.
- At or above 30, any score low enough to be a third of its predecessor is already below 0.30,
  so `should_escalate` has already fired.
- A cumulative posterior is sticky: an established source at 0.80 needs ~**100 all-negative
  events in one week** to reach even a 2.96× drop.

So `is_spike` compares **week-over-week negative rates**. Each week's rate is smoothed with
the *same* α=β=5 prior, which costs no new constant and buys three things at once: no division
by zero on a clean previous week, automatic small-sample suppression, and a signature identical
to the one the AC specifies.

```
W1: 40 events,  2 bad -> (5+2)/(10+40) = 0.14 | W2: 24 bad -> 0.58 | 4.1x  SPIKE
W1:  2 events,  0 bad -> (5+0)/(10+2)  = 0.42 | W2:  1 bad -> 0.50 | 1.2x  noise, ignored
W1: 40 events,  0 bad -> 0.10                 | W2: 20 bad -> 0.50 | 5.0x  SPIKE
```

**PRD amendment owed:** FR-16's "3× week-over-week drop in reliability score" → "3×
week-over-week rise in the smoothed rate of negative observations".

### Files to Create

| Path | Purpose |
|---|---|
| `backend/domain/reliability.py` | `posterior_mean`, `reliability_score`, `weekly_negative_rate`, `is_spike`, `should_escalate`, `checked_count` |
| `backend/tests/domain/test_reliability.py` | The full AC matrix plus the exhaustive property tests |

### Files to Modify

| Path | Change |
|---|---|
| `backend/shared/constants.py` | Six constants, with the D1/D2 reasoning recorded beside them |
| `backend/tests/shared/test_constants.py` | Pin all six values |
| `backend/domain/ranking.py` | Update the "`source_reliability` — Absent" row: the arithmetic now exists, the `Source` field does not yet. **Docstring only; no formula change** — that is `ranking-consumes-reliability`. |

### The interface

```python
RELIABILITY_PRIOR_ALPHA        = 5
RELIABILITY_PRIOR_BETA         = 5
RELIABILITY_MIN_OBSERVATIONS   = 30
RELIABILITY_NEW_SOURCE_FLOOR   = Decimal("0.32")
RELIABILITY_ESCALATION_SCORE   = Decimal("0.30")   # below this, with n >= 30
RELIABILITY_SPIKE_MULTIPLIER   = Decimal("3")

posterior_mean(positives: int, negatives: int) -> Decimal   # (5+p)/(10+n), 2dp, [0,1]
reliability_score(positives: int, negatives: int) -> Decimal # + the D1 clamp
weekly_negative_rate(negatives: int, observations: int) -> Decimal  # same prior
is_spike(previous: Decimal, current: Decimal) -> bool        # current >= 3 x previous
should_escalate(score: Decimal, observations: int) -> bool   # < 0.30 and n >= 30
```

`checked_count` refuses non-`int` and negative counts, mirroring `checked_confidence`'s
refusal of floats — and `bool` is refused too, since `True` is an `int` in Python and
`posterior_mean(True, False)` should not quietly mean `(1, 0)`.

### Tests

Every case the AC names, plus the boundaries:

- a new source is exactly 0.50 (`n=0`)
- one negative gives 0.45, not a crater
- the floor holds under 30 (`n=10, 29` all-negative → 0.32)
- the boundary **at exactly 30** — clamp off, 0.13
- escalation at 0.29/0.30 crossed with n=29/30 (all four combinations)
- spike at exactly 3× and just below
- spike ignores a two-event week
- `Decimal` refused where an `int` is wanted; `float` refused where a `Decimal` is wanted; `bool` refused as a count
- **property (exhaustive, not `hypothesis` — it is not a dependency):** for every
  `n` in 0..200 and every split, the score is in [0, 1] and is monotone non-increasing in
  negatives
- `tests/shared/test_constants.py` pins all six constants

### Technical Details

- **Decimal only, two decimals, `ROUND_HALF_UP`** — matching `checked_confidence` and the
  spine's `numeric(3,2)`. The quantize happens once, at the end of each public function.
- **`domain-pure` holds:** stdlib + `shared.constants` only. No Django import, enforced by
  import-linter and `tests/architecture/test_stdlib_only.py`.
- **The FR-25 seam is documented, not faked.** The signature takes positive and negative
  counts, so dismissals become another source of negatives with no signature change. Recorded
  in the module docstring, following `ranking.py`'s precedent of naming a debt rather than
  multiplying a term by a constant.
- **Coverage:** `domain/` is gated at **100%**, so every branch including each refusal needs
  a test.
- No migration, no API change, no `make client`, no frontend change.

### Deviations from the work item

Two, both confirmed with the user above and both requiring a PRD amendment: the min-N reading
(D1) and the spike definition (D2). The AC asked for exactly these to be proposed and
confirmed rather than assumed.

---

## Work Item: review-intake-and-backfill

**Nothing stuck in review without a ticket** — medium, confirm mode.

### Approach

One invariant: **an Event in `publication_status = in_review` always has an open
`in_review` ReviewItem, and an Event that is not in review has none.**

The elegant part is that this is enforced on the **resulting publication status**, not on the
gate that produced it. So a single helper keeps both halves true, and FR-14's LLM path
inherits the queue the moment it ships without touching this code — which is exactly what the
AC asks for.

```python
# apps/ingestion/services/review_intake.py
def sync_review_item(*, event, actor, now) -> None:
    if event.publication_status == Event.PublicationStatus.IN_REVIEW:
        raise_review_item(event=event, reason=Reason.IN_REVIEW, actor=actor, now=now)
    else:
        withdraw_review_item(event=event, reason=Reason.IN_REVIEW, actor=actor, now=now)
```

**Where it is called from, and why there.** `ingest_item._resolve_and_write` already calls
`_write_fit` immediately after each write, with the comment *"after the event's own write"*.
The raise goes in the same four places, for the same reason and inside the same
`atomic(using=CATALOG)`:

| Path | Call |
|---|---|
| `dedup.New` → `create_event` | `sync(event)` |
| `supersede_event` | `sync(new)` **and** `withdraw(old)` — see D3 |
| `apply_lifecycle_change` | `sync(event)` |
| `apply_silent_update` | `sync(event)` — this is the gate-change path (run-015 P1) |
| `bound_other_source` | nothing: this source does not write the event's gates |

### Decisions

**D1. Published-but-flagged events stay out of the queue.** *(Confirmed with the user,
2026-11-10.)* A `tz_review_pending` event is published, digest-eligible and working; it is
neither stuck nor reported. `ReviewItem` has no priority column, so a low-priority item would
need a migration, and the volume of 0.70–0.89 timezone scores is unknown and potentially
large — it would dilute the queue size and oldest-item metrics the admin exists to show. If a
flagged event's time really is wrong, FR-59 gives the user a path and that raises a
`user_reported` item with a 24-hour SLA. **Settles an open question from the intent brief.**

**D2. The backfill is a management command, not a data migration.** `review-queue-model` D9
set this precedent inside this very intent, choosing the idempotent command over the data
migration its AC had asked for. A command is re-runnable, reports counts, is testable without
a migration harness, and keeps a service call (with its audit write) out of the migration
graph. `backfill_review_items`, idempotent via `raise_review_item`'s own one-open-item-per-
(target, reason) rule — a second run bumps nothing because the first run's items are open.

**D3. Leaving `in_review` by a non-editorial route withdraws the item.** The three routes:

| Route | What happens |
|---|---|
| Ingestion re-gates it to `published` (better tz confidence on a later poll) | Item closes, resolution `withdrawn`, system actor |
| `supersede_event` — the Event is replaced and terminal (AD-4) | The **old** event's item closes as `withdrawn`; the replacement gets its own `sync` |
| An editor approves, edits or rejects it | **Not this item.** Those are editorial resolutions and belong to `editorial-review-commands`, which closes every open item on the event with the verdict |

`withdrawn` already exists: `review-queue-model` D5 added it *"for a system close, when the
target leaves review by another route (for example, superseded) — `review-intake-and-backfill`
needs it and should not have to migrate this table again."* This item spends that provision;
no migration is needed.

**Known gap, documented not fixed:** `reject_event` (work item 2) does not close review
items — it is out of its scope by design. Until `editorial-review-commands` lands, a rejected
`in_review` event keeps an open item. A rejected event is *not* `in_review`, so `sync` would
withdraw it; the plan deliberately does **not** route rejection through `sync`, because a
reject is an editorial verdict and must be recorded as one, not as a system withdrawal. A
test pins the current behaviour so the gap is visible rather than silent.

### Files to Create

| Path | Purpose |
|---|---|
| `apps/ingestion/services/review_intake.py` | `sync_review_item`, `withdraw_review_item` |
| `config/management/commands/backfill_review_items.py` | The idempotent backfill |
| `tests/ingestion/test_review_intake.py` | Intake, withdrawal, the transaction invariant |
| `tests/ingestion/test_backfill_review_items.py` | Backfill and its idempotence |

### Files to Modify

| Path | Change |
|---|---|
| `apps/ingestion/services/ingest_item.py` | Four `sync_review_item` calls, beside the existing `_write_fit` calls |
| `tests/ingestion/mutation_probe_rejection.py` → renamed `mutation_probe_trust_loop.py` | Add the probes below, including the in-transaction one |

### Tests

- **The invariant after every ingest path:** new, lifecycle update, silent update (the
  re-gate), supersede, bound-other-source
- **The in-transaction probe (AC):** a probe that moves the raise outside the
  `atomic(using=CATALOG)` block and asserts the suite fails — proving the test actually
  pins "same transaction" and not merely "eventually"
- **Low extraction confidence:** a synthetic `IncomingEvent` at `extraction_confidence =
  0.60` reaches `Gate.IN_REVIEW` and raises an item, proving the FR-14 seam without an LLM
- **Re-gating out:** a second poll with better tz confidence publishes the event and
  withdraws the item, with a system resolver
- **Supersede:** the old event's item closes `withdrawn`; the replacement gets its own
- **Backfill:** raises for every pre-existing stranded `in_review` event; a second run raises
  nothing; it does not touch published or already-ticketed events
- **D1:** a `tz_review_pending` event raises **no** item

### Technical Details

- No migration — `withdrawn` and every column needed already exist (`review-queue-model` D5).
- No API change, no `make client`, no frontend change.
- `withdraw_review_item` uses `Actor.system("review_intake")`: `ReviewItem`'s D6 check (d)
  requires a system resolver for `withdrawn` and a user resolver for every other resolution,
  so the database refuses a job recording a verdict.
- The backfill command follows `seed_local_stack`'s shape: idempotent, prints counts, safe to
  re-run.
- Gates: ruff, format, `lint-imports`, `manage.py check`, `makemigrations --check`, coverage.

---

## Work Item: event-report-api

**A user can say "this is wrong"** — medium, confirm mode.

### Approach

FR-59's user half. `EventReport` lives in `personal` because it is attributable to a person;
the `ReviewItem` it raises lives in `catalog` and **never learns who reported** (AD-3). The
two writes are in two databases, which AD-3 forbids sharing a transaction, so the hop between
them is the design problem and the subject of D2.

### Decisions

**D1. `EventReport` is unique on `(user, event_id, category)`; a repeat is an idempotent
no-op.**

The AC requires that one user cannot inflate the `ReviewItem` count, and the choice is forced
by machinery that already exists: `raise_review_item` bumps a per-category tally with
`F() + 1` and **has no decrement path**. So "one row per (user, event), latest category wins"
is unimplementable without inventing one — moving a user's report from `wrong_venue` to
`duplicate` would have to decrement the first tally.

With uniqueness on all three, each tally counts **distinct reporters of that category**, which
is what an editor reading "4 people say the date is wrong" needs it to mean. One user can
contribute at most 1 to each of the four categories, and the daily limit is 5 anyway. A
repeat of the same category returns the existing row and raises nothing; a *different*
category from the same user is a genuine second signal and bumps that category.

**D2. The cross-wall hop is an outbox with a reconciler.** *(Confirmed with the user,
2026-11-10.)*

`EventReport.raised_at` is null until the `ReviewItem` exists. The write order is:

```
1. personal:  write EventReport (raised_at = NULL)       <- the user's fact, committed first
2. catalog:   raise_user_report(event_id, category)      <- best-effort, outside the txn
3. personal:  stamp raised_at                            <- only on success
   on failure: leave NULL, log, and still answer 200
```

**Report first, ticket second, and that order is load-bearing.** The reverse would leave an
editor holding a ticket with an inflated tally and no stored report, and FR-16's "upheld
report" accounting reads the report. A lost *ticket* is recoverable from the report; a lost
*report* is not recoverable from the ticket.

`reconcile_event_reports` sweeps `raised_at IS NULL` rows on the **existing 5-minute cadence
inside `tick()`** — no new beat entry (the handoff's standing rule, and `reconcile_outbox`
and `reconcile_revalidation` are already there). It is idempotent twice over: the sweep
filters on null, and `raise_review_item` refuses to stack a second open item.

**D3. A published `raise_user_report` is added to `ingestion`, because the existing signature
cannot be called across the wall.** `raise_review_item` takes an `Event` **model instance**,
and the `models-ingestion` contract allows only `apps.ingestion` to import
`apps.ingestion.models`. A thin `raise_user_report(*, event_id, category, now)` in
`review_queue.py` resolves the Event internally and calls `raise_review_item` with
`Actor.system("event_report")` — which D4 of `review-queue-model` already **requires**, so
that the reporter's id never reaches a `catalog` audit row every editor can read.

**D4. Retention is `ACCOUNT_CONTENT`.** The report is the user's, purged with their account.
**The FR-16 signal survives that deletion**, because the thing FR-16 counts is the anonymous
tally on the `catalog` ReviewItem — so a user can be forgotten without erasing the editorial
evidence. That is AD-3's separation paying off rather than a gap.

### Files to Create

| Path | Purpose |
|---|---|
| `apps/personalization/migrations/0013_eventreport.py` | The model, its unique constraint and its category check |
| `apps/personalization/services/event_reports.py` | `report_event`, `reconcile_unraised_reports` |
| `tests/personalization/test_event_reports.py` | Service, throttle, idempotence, the outbox |
| `tests/api/test_event_report_api.py` | Contract tests |

### Files to Modify

| Path | Change |
|---|---|
| `apps/personalization/models.py` | `EventReport` |
| `apps/personalization/schemas.py` | `EventReportIn`, `EventReportOut` |
| `apps/personalization/api.py` | `POST /api/personal/event-reports` |
| `apps/ingestion/services/review_queue.py` | `raise_user_report` (D3) |
| `shared/constants.py` | `EVENT_REPORT_DAILY_LIMIT = 5`, its window, `EVENT_REPORT_RECONCILE_EVERY_MINUTES` |
| `worker/tasks.py` | `reconcile_event_reports` on the existing 5-minute branch |
| `frontend/lib/api/openapi.json` + `schema.ts` | Regenerated by `make client` (AD-19) |

### The endpoint

```
POST /api/personal/event-reports      {event_id, category} -> 201 {reported: true, category}
  401  signed out
  404  unknown event, or one not publicly visible (the Detail read's own refusal)
  422  not one of the four categories
  429  the sixth report in a day, with retry_after_seconds
```

The response carries what the toast needs and nothing more — no report id, no tally, no queue
state. A client that could read the tally could count other people's reports.

### Tests

- Each of the four categories accepted; a fifth value rejected 422
- The repeat rules: same category twice is a no-op with one row and one bump; a second
  *category* from the same user adds a row and bumps that category only
- **The tally counts people, not clicks** — two users reporting the same category gives 2;
  one user reporting it twice gives 1
- Throttle: the 5th allowed, the 6th 429 with `retry_after_seconds`, through the in-memory
  adapter's injectable clock (no sleeping)
- Signed out → 401; unknown event → 404; `in_review` and `rejected` events → 404, so the
  endpoint cannot probe hidden events
- **AD-3: the raised `ReviewItem` and its audit row contain no user id** — asserted over
  every column, not just the obvious one
- **Visibility is unchanged:** a reported event is still in `list_public_events` and
  `list_public_candidates`
- The outbox: a failing `raise_user_report` still answers 201 and leaves `raised_at` null;
  the reconciler then raises it; running the reconciler twice raises nothing more
- Contract test + `make client` with no diff

### Technical Details

- No FK across the wall: `event_id` is a plain `UUIDField`, indexed (AD-3, `eventuale.E002`).
- The category vocabulary is **re-exported from `ReviewItem.ReportCategory`** per
  `review-queue-model` D3, so the four values exist once.
- `make client` is required by this item (AD-19) — the first API change in this run.
- Gates: the full set, plus `manage.py check` for the AD-15 retention declaration.

---

## Work Item: editorial-review-commands

**Approve, edit, reject — the editor's three verbs** — medium, confirm mode.

### Approach

AD-14: `editorial` owns no tables and gets no privileged write path. These four commands in
`apps/ingestion/services/editorial_review.py` are the only way a `ReviewItem` is resolved and
the only way an editor changes an event. `editorial-admin-queue` will be a thin caller.

**This item closes the two gaps earlier items deliberately left open**, and the tests that
pin them are written to be changed by it:

- `reject_event` records no verdict — `test_rejecting_an_in_review_event_leaves_its_item_open`
- one verdict must close **every** open item on the event (`review-queue-model` D2)

### Decisions

**D1. The editorial lock is the content-hash skip that already exists.** *(Confirmed with the
user, 2026-11-10.)* `ingest_item` hashes the **source's** payload and venue and returns
`["unchanged"]` *before* touching the Event when that hash matches. So an editor's correction
already survives a source repeating the same bad data, indefinitely, with no column and no
new code. Genuinely new source data wins, because the source has said something it did not
say before — and a source that keeps being wrong is what FR-16's score is for, rather than a
permanent per-event veto. **A test pins both halves**, which is the AC's requirement.

**D2. One verdict closes every open item on the event.** `review-queue-model` D2 allows an
event to carry two open items (quarantined *and* reported), and pinned this as an integration
requirement for this work item. The editor decides once; `_close_open_items(event, resolution,
actor)` closes them all with the same resolution.

**D3. Staleness is checked on both the item and the event.** Each command takes
`expected_event_version`. It refuses when the item is already resolved (`guard_review_item`
would refuse the write anyway; refusing in the command names the reason) and when the event's
version has moved since the editor loaded the page. An editor must never silently overwrite an
ingestion update they did not see.

**D4. `SourceObservation` is built now, because `domain/reliability.py` already fixes its
shape.** The AC allows deferring it, but work item 3 has already pinned the interface:
`posterior_mean(positives, negatives)` and `weekly_negative_rate(negatives, observations)`.
A table feeding those is determined — one row per resolution, carrying the owning `Source`,
the kind, the event, the item and the instant. Deriving the same counts from
`IngestionAuditEntry` would mean scanning JSON details and would expire on the audit log's
24-month retention.

**The sign of `edited` is deferred, not guessed.** The brief names rejects and upheld reports
as negative and approvals as positive, and says nothing about edits. So `edited` is stored as
its **own kind** and `reliability-recompute-and-escalation` decides what it is worth. Storing
it as a fact rather than a score is exactly what the AC asks for, and the deferral is written
into that item's acceptance criteria.

### Files to Create

| Path | Purpose |
|---|---|
| `apps/ingestion/services/editorial_review.py` | The four commands |
| `apps/ingestion/migrations/0010_sourceobservation.py` | The FR-16 observation row |
| `tests/ingestion/test_editorial_review.py` | The four commands, their refusals, the observations |
| `tests/ingestion/test_editorial_lock.py` | D1: a poll after an edit, both halves |

### Files to Modify

| Path | Change |
|---|---|
| `apps/ingestion/models.py` | `SourceObservation` |
| `apps/ingestion/services/review_intake.py` | The rejection gap's test is rewritten here |
| `tests/ingestion/test_review_intake.py` | `test_rejecting_an_in_review_event_leaves_its_item_open` → asserts the item now closes `rejected` with the editor's id |
| `tests/architecture/test_write_ownership.py` | `ingestion_sourceobservation` |
| `shared/constants.py` | The editable field list, if it earns a name |

### The commands

```python
approve_review_item(*, item_id, actor, expected_event_version, now)  -> publishes, closes `approved`
edit_and_publish(*, item_id, actor, expected_event_version, fields, now) -> edits, publishes, closes `edited`
reject_review_item(*, item_id, actor, expected_event_version, now)  -> calls editorial_state.reject_event, closes `rejected`
dismiss_source_item(*, item_id, actor, now)                          -> closes `dismissed`, touches no Source
```

**The editable set is bounded:** `title`, `start_time_utc`, `end_time_utc`, `start_time_tz`,
`venue`. Not the slug (a public URL), not the source or `source_event_id` (identity, AD-4),
not the confidences (the gate's, not the editor's), not `publication_status` directly (that
is what approve and reject are for).

**A time or venue edit goes through `apply_lifecycle_change`**, the same function ingestion
uses — so it bumps the version, appends an `EventStateChange` and reaches saved users through
AD-17 with no parallel path. A title-only edit goes through `apply_silent_update`, because a
typo fix is not a notification (the `domain/notices.py` rule already in place).

### Tests

- Each command's happy path, including the publication status after approve and edit
- **Two open items on one event close together on one verdict** (D2)
- Refusals: an already-resolved item, a stale `expected_event_version`, a system actor, an
  anonymous actor
- A time edit bumps the version, appends a `time_moved` change, and cancels/re-mints the
  saved users' sends through the existing propagation
- A title-only edit writes **no** state change and notifies nobody
- `dismiss_source_item` leaves the Source `active` — FR-16's "escalation, never removal"
- One `SourceObservation` per resolution, attributed to the event's owning source
- **D1, both halves:** a re-poll with identical source data leaves the edit standing; a
  re-poll with changed data overrides it
- The rewritten rejection test: the item now closes `rejected`, with the editor's id

### Technical Details

- Migration `0010_sourceobservation` (0009 is this run's rejection migration).
- No API change — the admin is the next work item. No `make client`.
- `write_audit` refuses outside a catalog transaction; every command opens one.
- Gates: the full set.

---

## Work Item: editorial-admin-queue

**Where an editor actually works — the review queue in Django admin** — medium, confirm mode.

### Approach

AD-14: *"Django admin is the MVP surface for FR-57."* The `editorial` app already exists,
already says it *"owns nothing; acts only through ingestion commands"*, and already has an
empty `admin.py`. This item fills it — but **not** by putting a `ModelAdmin` there, and the
reason is the architecture rather than a preference.

**D1. The `ModelAdmin` lives in `apps/ingestion/admin.py`, and `apps/editorial/admin.py`
holds the editorial read service.**

Django's `admin.site.register` needs the model class, and the `models-ingestion`
import-linter contract says only `apps.ingestion` may import `apps.ingestion.models`. A
`ModelAdmin` for `ReviewItem` in `apps/editorial/admin.py` would therefore break AD-2 — so
the coding standard already answers this:

> *"An app's admin lives in that app (`admin.site.register` needs the model, which
> `models-<app>` keeps private). `editorial` holds the review queue, not ModelAdmins for
> other apps' models."*

So the split is by **who owns the row**, not by who works it: `ingestion` owns `REVIEW_ITEM`
(AD-16) and therefore owns the admin that renders it; `editorial` owns the *editorial
reading* of it. The admin surface a editor sees is one queue, whichever module renders it.

**The consequence, stated rather than hidden:** Django groups the admin index by
`model._meta.app_label`, so the queue appears under **Ingestion**, not under a separate
"Editorial" heading. A separate `AdminSite` with its own URL prefix would give the
editorial group its own index, but it would also give it a second login, a second
permission namespace and a second `LogEntry` — a *privileged surface*, which is the one
thing AD-14 exists to prevent. One admin site, one permission model, one audit log.

**D2. The admin reads through a new `ingestion` read service, and never touches a model.**

`apps/ingestion/admin.py` may import `apps.ingestion.models`, so it *could* query
`ReviewItem` directly. It does not, for one reason: **the AC asks for the queue metrics to
be computed by an `ingestion` read service, "not in the template"**, and FR-29's dashboard
will later read the same three numbers. A template cannot compute them — it has no clock and
no query. So the three metrics live in a service that both the admin and the future
dashboard call, and the admin renders what it is given.

That service returns **plain data** — frozen dataclasses, not model instances — following
`catalog_read.py`'s precedent, so the shape it hands over is a contract rather than a row.

**D3. The summary is a changelist header, not a separate page.** Django's
`ChangeList` has no header hook, so the summary is injected through the admin's
`changelist_view` context (`extra_context`). Three numbers, computed by the service:
`queue_size` (open items), `oldest_open_age` (how long the oldest open item has waited),
`sla_breaches` (open `user_reported` items past their 24h `due_at`).

### Decisions

**D4. Ordering is open-first, then priority, then `due_at`.** The AC names the order
*"open items first, then ordered by priority and `due_at`"*. `ReviewItem` has **no priority
column** (`review-queue-model` D-notes; the `review-intake-and-backfill` D1 explicitly
declined to add one, so a low-priority item would not dilute the queue metrics). So
"priority" is derived from the **reason**, not from a column:

| Reason | Priority | Why |
|---|---|---|
| `user_reported` | 0 (highest) | A person says something is wrong, and FR-59's 24h SLA is running |
| `source_reliability` | 1 | FR-16's escalation: a source keeps being wrong |
| `in_review` | 2 (lowest) | The gate caught it; nobody has complained yet |

The derivation lives in the read service as a `Case/When` expression, so the ordering is
one query rather than N queries, and it is a **declared constant** in `shared/constants.py`
rather than a magic number in a template.

`due_at` is null for everything except `user_reported` (the D8 check), so nulls sort last
within a priority band — `F("due_at").asc(nulls_last=True)`.

**D5. The SLA mark is a boolean column, computed in Python.** A `user_reported` item past
its `due_at` is *"visibly marked"*. The mark is `True` when `reason == user_reported` and
`due_at < now`. It is computed **per row in Python**, not as an annotation, because
`due_at` is relative to *now* and the list is paginated — a `Case/When` would work, but the
same `now` has to reach the mark and the ordering, and passing one instant is simpler and
unambiguous.

**D6. "No reporter identities" is structural, not a filter.** The `ReviewItem` row has no
user column at all (D4 of `review-queue-model`), and the report lives in
`personal.EventReport`. The admin therefore **cannot** show a reporter even by accident:
there is nothing to show. The tallies are counts. The test asserts this over the rendered
HTML, not over the schema alone.

**D7. The detail page shows facts, and for a source item, the score history.**

- **Event item:** the event's title, start, end, timezone, venue, publication status, and
  its `event_version` (which is also the staleness token the commands take).
- **Source item:** the source's name, type, badge and **its score history** — the
  `SourceObservation` rows, newest first, each with its kind and when it happened.

The score history comes from the read service as a list of plain rows. The *score* itself
does not exist yet: `reliability-recompute-and-escalation` (work item 8, still pending)
computes and stores it. So the source page shows the **observations the score is computed
from**, labelled as such — which is honest and is exactly what an editor deciding
"is this source repeatedly wrong?" needs. Inventing a score display before the work item
that computes it would be a second source of truth.

*Confirmed with the user, 2026-11-11: observations only, labelled as such. The page does
not compute a live score from `domain/reliability.py` — that would be a second
implementation of work item 8's job.*

**D8. The four actions are admin *actions* on the changelist plus a change page.**

- **Approve**, **Reject** and **Dismiss** are changelist actions (`@admin.action`), because
  they take no further input.
- **Edit** is a **change page**: it needs a form limited to `EDITABLE_FIELDS`
  (`title`, `start_time_utc`, `end_time_utc`, `start_time_tz`, `venue_id`), so it cannot
  be a button on the list.

Each action calls its `editorial_review` command with `Actor.user(request.user.pk)`. A
command's refusal — a stale version, an already-closed item — **shows on the page as a
message, not as a 500**. Django's `message_user` is the channel for that; the action
catches `DomainError` and reports its message.

**D9. The staleness token travels in the form, not in the URL.** The commands take
`expected_event_version`. The change page renders it as a hidden field, and the action
reads it from the queryset row's current version. **A stale token is refused** (D3 of
`editorial-review-commands`): the editor is told the event changed and must reload.

**D10. The edit form's `clean()` runs the command's own checks.** The AC says so
explicitly: *"its `clean()` runs the command's own checks, as the ingestion admin does."*
`editorial_review` exposes no separate `check_*` function today, so this item adds one —
`check_review_edit(*, item_id, fields, expected_event_version)` — which performs the same
validation `edit_and_publish` does (unknown field, no fields, stale version, already
resolved) **without writing**. `edit_and_publish` then calls the same check before its own
work, so the form and the command cannot drift.

### Files to Create

| Path | Purpose |
|---|---|
| `apps/ingestion/services/review_queue_read.py` | The read service: `queue_summary`, `list_review_items`, `get_review_item_detail`, `list_source_observations`. Plain-data DTOs, no model instances leave it. |
| `tests/ingestion/test_review_queue_read.py` | The read service: ordering, the SLA mark, the summary's three numbers, the detail's facts, the source score history. |
| `tests/editorial/__init__.py` | The new test package. |
| `tests/editorial/test_admin_queue.py` | The admin, driven through the Django test client: ordering, the SLA mark, each action, a refusal on the form, the summary, delete 403, the access matrix. |

### Files to Modify

| Path | Change |
|---|---|
| `apps/ingestion/admin.py` | The `ReviewItemAdmin`, the edit form, the four actions, the summary header, the access rules. |
| `apps/ingestion/services/editorial_review.py` | `check_review_edit` — the write-free half of `edit_and_publish`, called by both the form's `clean()` and the command. |
| `shared/constants.py` | `REVIEW_PRIORITY` — the reason→priority mapping, with the reasoning beside it. |
| `tests/architecture/test_no_direct_writes.py` | The surface-file count: `apps/editorial/admin.py` gains content, but the *count* does not change (the file already existed). **No change expected** — verified, not assumed. |
| `config/management/commands/seed_local_stack.py` | The editorial group gains `view_source`/`change_source`? **No** — the grant set is unchanged. The group already holds `change_reviewitem` and `view_reviewitem`, which is exactly what this admin needs. |

### The access matrix

The AC: *"a member of the editorial group can see and act. A signed-in user who isn't staff,
or is staff without the group, is refused. Superuser is not required."*

Django's admin already refuses non-staff users at the login gate (`AdminSite.has_permission`
requires `is_staff`), and refuses a staff user with no model permission on the model view.
So the matrix is:

| Who | Changelist | Change page | Action |
|---|---|---|---|
| Editorial group member (staff) | 200 | 200 | works |
| Staff, no editorial group, no `view_reviewitem` | 403 on the model view | 403 | — |
| Staff, no editorial group, but `view_reviewitem` granted directly | 200 | 200 | works |
| Signed in, not staff | redirected to the admin login | — | — |
| Not signed in | redirected to the admin login | — | — |

**"Superuser is not required"** is the interesting row, and it cuts both ways: a superuser
is *allowed* (Django's own rule — `has_permission` returns True for `is_active` +
`is_staff`, and `is_superuser` short-circuits the model permission check), but a superuser
is **not needed**. The editorial group is sufficient on its own. The test pins the group
member's access **without** any superuser flag, so the suite would fail if the group grant
regressed.

**"Staff without the group is refused"** — the subtle case. A staff user with *no*
`view_reviewitem` permission gets a 403 from Django's own model-permission check, which is
correct and needs no code. But a staff user who *has* the permission directly (not via the
group) is allowed — Django's permission model is per-user-permission, and a group is only
a bundle of permissions. **The AC says "staff without the group is refused", and the
strictest reading would require group membership as such.** That reading is wrong: it would
mean a superuser who is not in the group cannot work the queue, which contradicts "superuser
is not required" in the same sentence. The correct reading is that **staff without the
review permission is refused**, and the group is how the permission is normally granted.

Each case is tested, including the negative ones.

### Tests

- **Ordering:** open items before resolved ones; within open, `user_reported` before
  `source_reliability` before `in_review`; within a band, earliest `due_at` first, and
  null `due_at` last.
- **The SLA mark:** an open `user_reported` item past `due_at` is marked; one inside it is
  not; a non-report item is never marked.
- **The summary:** `queue_size` counts open items only; `oldest_open_age` is the age of the
  oldest open item; `sla_breaches` counts open reports past their deadline. An empty queue
  reads zero, not an error.
- **The detail page:** the event's facts for an event item; the source's facts **and its
  observation history** for a source item.
- **No reporter identities:** the rendered page contains no reporter's id or email, and the
  tallies render as counts.
- **Approve / Edit / Reject / Dismiss:** each runs its command, and the audit row records
  the acting editor.
- **A refusal shows on the page, not as a 500:** an already-resolved item and a stale
  `expected_event_version` each produce a 200 with the message, and nothing is written.
- **Delete is disabled:** the delete view returns 403 and the row survives.
- **The access matrix:** every row of the table above, including the negative ones.

### Technical Details

- **No migration.** `ReviewItem` already exists with every column the admin shows.
- **The queue stays under "Ingestion" in the admin index** (confirmed with the user,
  2026-11-11). One admin site, one permission model, one audit log — a second `AdminSite`
  for the editorial group would be a second privileged surface, which AD-14 exists to
  prevent.
- **No API change**, so no `make client` and no OpenAPI diff.
- **No import-linter change.** `apps/ingestion/admin.py` may import `apps.ingestion.models`;
  `apps/editorial/admin.py` imports `apps.ingestion.services.review_queue_read` and
  `apps.ingestion.services.editorial_review` — services, not models, which the
  `models-ingestion` contract permits.
- **The admin's `LogEntry` is off** for this admin too: the `IngestionAuditEntry` written by
  each command is the only history. A `LogEntry` would commit in `personal` even if the
  catalog write rolled back.
- **`_add_domain_error` and `_actor_names` are reused** from `apps/ingestion/admin.py`,
  as the work item's technical notes ask.
- **The actor is `Actor.user(request.user.pk)`** — by value, no label. A username never
  reaches `catalog` (design D17, OQ-8).
- **The summary's `now`** is one instant, passed to the read service, so the three numbers
  and the SLA marks agree.
- **Verification:** `uv run pytest`, `uv run python manage.py check`,
  `uv run python manage.py makemigrations --check --dry-run`, `uv run lint-imports`,
  `uv run ruff check`, `uv run ruff format --check`. Postgres must be up (`make up`).

### As built — two decisions that changed during implementation

The plan above is what was designed. Two things turned out differently once the code ran,
and both are recorded here rather than being silently absorbed into the diff.

**A1. The edit form's instance is the `ReviewItem`, not the `Event`.**

The plan said *"a change page with a form limited to `EDITABLE_FIELDS`"*. The first
implementation made the form a `ModelForm` over `Event` with `Meta.model = Event`. That
breaks two things at once, both of them Django's own machinery rather than our code:

- **`helpers.AdminReadonlyField.contents()` reads `obj = self.form.instance`.** The
  readonly panels — the event's facts, the source's facts, the report tallies — would
  have received the *event*, and every panel that reads a `ReviewItem` attribute (the
  reason, the tallies, the resolution) rendered as a dash. The queue's whole point is
  those panels.
- **`save_form` returns `form.save(commit=False)`**, which would have been the `Event`.
  `_changeform_view` redirects to `admin:ingestion_reviewitem_change` using the object it
  gets back, so the editor would have been sent to the *event's* URL after resolving a
  *review item*.

The fix is the same trick Django itself uses for a `ModelForm` with no fields: a
`ModelForm` whose `Meta.model` is `ReviewItem`, whose `Meta.fields` is `()`, and whose
**event fields are declared by hand**. The instance is therefore the `ReviewItem` — so the
readonly panels and the redirect both work — while the *fields* describe the `Event` and
are seeded from the event's current facts through `initial`.

`get_form` is overridden to bypass `modelform_factory` entirely (returning `self.form`
verbatim), `save_form` is overridden to return `form.item` (the `ReviewItem`), and
`save_model` calls `edit_and_publish` and then `adopt`s the item back onto the admin's
object. The form's `clean()` calls the command's `check_review_edit`, as D10 requires.

**A2. An event item's source is one hop away, and both sides now resolve it.**

D1 of `review-queue-model` says a `ReviewItem` target is an Event **or** a Source, never
both. So an event item has `source_id = NULL` — the item names the event, and the event
names the source the listing came from. Reading `item.source` therefore shows nothing for
the item kind that actually matters, and the source panels on an event item rendered as
dashes.

Both the read service and the admin now resolve it the same way, in a `_source_of` helper:
the item's own `source` if it has one, otherwise its event's source. Both also
`select_related("event__source")`. The two helpers are deliberately identical — a queue
whose summary came from one resolution rule and whose rows came from another would
describe two different queues.

**A3. The summary's age is formatted by the service, not the template.**

A Django template has no arithmetic: `{{ age.seconds // 3600 }}` is a syntax error, not
a silent zero. `QueueSummary.oldest_open_age_parts()` returns `(days, hours, minutes)`
(or `None` for an empty queue) so the template only lays the numbers out, and FR-29's
dashboard reads the same three numbers from the same place. This is the same "one
implementation, two readers" argument D2 makes, applied to the rendering.

**A4. Reading the queue and working the queue are two different permissions.**

The code review found that `may_review` was the single gate for both, and that it
accepted *either* `change_reviewitem` or `view_reviewitem`. A read-only auditor could
therefore publish quarantined events and rewrite event facts. The rule is now split:

| Predicate | Requires | Used for |
|---|---|---|
| `may_view` | `view_reviewitem` (or `change_reviewitem`) | reading the queue |
| `may_review` | `change_reviewitem` **only** | the verdicts and the edit |

**And the check is enforced in `_verdict`, not only in the action decorator.** Django's
`@admin.action(permissions=["change"])` is advisory: it filters the action out of the
dropdown, but the changelist's gate is `has_view_or_change_permission` — which a
read-only viewer satisfies — and `response_action` resolves the action *by name* from
the POST without a second check. So the enforcing check sits in the helper all three
actions share, and a fourth action cannot forget it.

**A5. The staleness token is rendered, and the check fails closed.**

`expected_event_version` was declared on the form but named in no fieldset, and Django
only renders fields that appear in a fieldset — so the page contained no token input at
all, and the optimistic lock did not run in production while every test (which posted
the field by hand) passed. The field is now in the "Correct the event" fieldset as a
hidden input, and it is `required=True`: **a post with no token is a refusal, not a
write that skips the lock.**


---

## Work Item: reliability-recompute-and-escalation

**The score that remembers — history, weekly recompute, and escalation** — high, validate mode.
Built from `reliability-recompute-and-escalation-design.md` (checkpoint 1, 2026-11-11).

### Approach

Three things must be built, in this order, and each is a place where two implementations
would be two truths:

1. **The counting rule** — what an observation is worth — written down once in
   `shared/constants.py` and applied by one function.
2. **The storage** — `SourceReliabilityScore` (the history) plus `Source.reliability_score`
   (the current value), written in one transaction by one job.
3. **The job** — a weekly recompute that reads only `catalog`, escalates through the
   existing `raise_review_item`, and **never touches anything but the score**.

The ordering matters because the counting rule decides what the storage holds, and the
storage decides what the job computes. Building the job first would mean writing the
arithmetic twice — once in the recorder and once in the computer — and the AC's
"only the `reliability-score-domain` functions" would be satisfied only in the computer.

**The cross-database question is settled before any code is written.** The work item
offers two options and requires the design to pick one and show that the wall holds. The
design picks **recording the observation at resolution time** from the `ReviewItem`'s own
tallies, because the counts are *already* in `catalog` — `raise_review_item` increments
them there — and only counts cross the wall, never identity (D4 of `review-queue-model`).
The job therefore never reads `personal`, and the wall is held by construction rather than
by discipline.

**The counting rule is a table, and the table is the design.** The work item hands three
open questions to the design: the sign of an edit, the definition of "upheld", and the
counting of five reports under one verdict. The design answers all three:

| Verdict | Sign | The question it answers |
|---|---|---|
| `approved` | **positive** | FR-16 says so. |
| `rejected` | **negative** | FR-16 says so. |
| `edited` | **negative** | The source's facts were wrong. A source that gets every event's time wrong must not score like one whose times are right. |
| `dismissed` | **neutral** | FR-25's named, unimplemented input. A dismissal is "I looked at this source and found no fault" — not evidence about the source's events, and not a reward for doing the review. |
| user report | **negative when upheld** | Upheld means the editorial verdict on the reported event was `rejected` or `edited`. A report the editor contradicted counts for nothing. |

And **one verdict counts once**: five reports, one verdict, **one** observation. The
multiplication is prevented *structurally* — `SourceObservation.source_observation_item_uq`
already permits one observation per review item, and all of an event's reports live on one
`user_reported` item — so the count is a *field* on the observation (the fact is not lost)
rather than five rows (the weight is not multiplied).

### Decisions

**D1. The score is a table of computed rows, and `Source` carries the current one.**

The AC allows "a denormalised field on `Source` or a latest-row read, as the design
decides". The design decides on **both**, because they answer different questions:

- `Source.reliability_score` answers *"what is this source's score right now?"* — the
  ranking consumer's question, asked per event, on the hot path.
- `SourceReliabilityScore` answers *"what was it last week?"* — the spike rule's question,
  and the one a field cannot answer.

The field is written **only** by the recompute job, in the **same transaction** as the row
it computed, so the two cannot disagree: a crash between them rolls back both. A test
asserts the field equals the latest row's score.

**D2. The row is keyed by (source, ISO week), and the constraint is the idempotence.**

"One row per (source, computation)" and "a re-run writes no duplicate row" are the same
statement, and the key makes it a *database* guarantee: `UNIQUE (source_id, period_start)`
where `period_start` is the Monday 00:00 UTC of the week computed. A second run in the
same week hits the constraint and **updates** the row (a score that is a week stale is a
score that is wrong). The week start is checked too — `period_start = date_trunc('week',
period_start)` — so a row that is not a week boundary is refused by Postgres.

**D3. The period is the calendar ISO week, not a rolling window.**

FR-16's spike rule is "this week with last week", and a calendar week is the honest
reading of that phrase. A rolling 7-day window would need a per-source timestamp of the
last computation to define its window — a second piece of state to keep in step with the
row. The first week of a source's history has no predecessor, and its `last_week` rate is
computed over zero observations, so the domain module's small-sample suppression keeps it
from firing spuriously.

**D4. An edit is a negative observation.** The work item says "arguably negative, since
the source was wrong"; this design takes that side, because the source's job was to state
the facts and the editor had to change them. FR-16's own brakes — the 0.32 floor and the
min-N of 30 — are the protection, and the escalation is a review, never a removal.

**D5. A dismissal is neutral.** A `source_reliability` item is raised by the system, so
"dismiss" means "I looked at this source and found no fault in it", not "I checked an
event from this source and it was right" — there was no event to check. Positive would
let an editor clear a bad score by dismissing it; negative would punish an editor for
doing the review the escalation asked for.

**D6. FR-25's dismissal rate is named, not faked.** The `dismissed` kind is in the table
with a comment saying the rate is unimplemented, and no `dismissal_rate` term appears
anywhere — `domain/reliability.py` set the precedent that "an absent input is absent from
the expression, never pinned to a stand-in".

**D7. "Upheld" means the editorial verdict upheld it.** A report on an event the editor
then rejected or edited is upheld (negative). A report on an event the editor then
approved was a bad report and counts for nothing. This defines "upheld" *by the verdict*
rather than by a separate step, so there is no second decision and no second place to make
it.

**D8. One verdict, one observation, whatever the report count.**

**D9. The observation is recorded at resolution time, from the item's own tallies.**

**D10. The weekly cadence is a due-date, not a minute-modulo rule.** `tick` enqueues the
recompute job **every tick**; the job decides who is due. This is not a new shape — the
tick already contains the precedent: `schedule_digests` runs on every tick because "due"
is a per-source comparison and the dispatcher makes it, while the tick only asks it to
look. **A weekly cadence is not expressible as a minute-modulo rule** (there is no
`minute % 10080`), so the alternative was a second beat entry, which AD-7 forbids. The
due-claim is `FOR UPDATE SKIP LOCKED` on the source rows, so two overlapping ticks cannot
recompute the same source twice.

**D11. Escalation bumps, never duplicates.** The job calls the existing
`raise_review_item(source=..., reason=source_reliability)`, which bumps the open item for
(source, reason) under `review_item_open_source_reason_uq` and writes a
`review_item_bumped` audit row. The rule is *called*, not reimplemented.

**D12. Never removal is asserted, not promised.** The recompute writes no `Source` column
except `reliability_score` and `reliability_scored_at`. A test asserts `status`,
`ingestion_cadence`, `last_ingested_at`, `consecutive_failures` and `stale_since` are all
unchanged after an escalation — asserting the *values*, not the absence of a line, because
trusting the absence of a line is trusting the source.

**D13. The counting table lives in `shared/constants.py`, keyed by value.**

```python
OBSERVATION_SIGNS = {
    "approved":  1,
    "rejected": -1,
    "edited":   -1,
    "dismissed": 0,
}
```

`shared` sits below `apps` and cannot import `apps.ingestion.models`, so the table is
keyed by value — exactly as `REVIEW_PRIORITY`, `REPORT_CATEGORIES` and
`LIFECYCLE_SEND_BEHAVIOUR` are. The recorder and the computer both read it, so two
implementations of the same sign cannot exist.

**D14. Every rule comes from `domain/reliability.py`.** The score is `reliability_score`,
the spike test is `is_spike` over two `weekly_negative_rate`s, the escalation test is
`should_escalate`. The domain module's docstring explains at length why the spike must
measure *rates* and not scores, so re-deciding that here would be a second, worse
implementation of a rule that is already written down.

**D15. A source with no score row reads as the 0.50 prior.** The read path calls
`domain.reliability.reliability_score(0, 0)` rather than hard-coding `0.50`, so the two
cannot drift if the prior is re-tuned.

### Files to Create

| File | Purpose |
|------|---------|
| `backend/apps/ingestion/models.py` (modify) | `SourceReliabilityScore`; `Source.reliability_score` and `Source.reliability_scored_at`; `SourceObservation.report_count` |
| `backend/apps/ingestion/migrations/0011_sourcereliabilityscore.py` | `CreateModel` with the unique constraint, the checks and the index |
| `backend/apps/ingestion/services/reliability.py` | `counts_for`, the due-claim, `recompute_source`, `recompute_due`, and the current-score read |
| `backend/tests/ingestion/test_reliability_score.py` | The counting table, the five-reports case, idempotence, the weekly guarantee |
| `backend/tests/ingestion/test_reliability_escalation.py` | Both escalation paths, no duplicate escalation, never-removal |
| `backend/tests/ingestion/test_reliability_worker.py` | The tick enqueues the job; the job claims and releases |

### Files to Modify

| File | Changes |
|------|---------|
| `backend/shared/constants.py` | `OBSERVATION_SIGNS`, the weekly period constant, the due window |
| `backend/apps/ingestion/services/editorial_review.py` | `_observe` carries the closed item's `report_count` |
| `backend/worker/tasks.py` | `recompute_reliability`, enqueued from `tick` |
| `backend/tests/worker/test_scheduling_tasks.py` | The pinned tick enqueue table gains the new task |

### Tests

| Test File | Coverage |
|-----------|----------|
| `test_reliability_score.py` | **Each verdict's sign**: approve positive, reject negative, edit negative, dismiss neutral. **The five-reports-one-verdict case**: five reports on an event, one `rejected` verdict → exactly one observation, `negatives == 1`, and the report count recorded on it. **A report on an approved event** counts for nothing. **Idempotence**: two recomputes in the same week → one row. **The weekly guarantee**: a source with no row for the current week is due; a source with one is not. **The prior**: a source with no row reads 0.50. |
| `test_reliability_escalation.py` | **The low-score path**: 30 observations, a score below 0.30 → a `source_reliability` item is raised. **The spike path**: this week's rate 3× last week's → raised, even while the score is fine. **No duplicate escalation**: a second escalation in the same week leaves one item and bumps it. **Never-removal**: the source's `status`, `ingestion_cadence`, `last_ingested_at`, `consecutive_failures` and `stale_since` are unchanged after an escalation. |
| `test_reliability_worker.py` | The tick enqueues `recompute_reliability` on every tick. The job claims the due sources and releases them. A source that is not due is not claimed. |

### Technical Details

- **Migration numbering.** The latest is `0010_sourceobservation`, so this is
  `0011_sourcereliabilityscore`.
- **The unique constraint does the idempotence.** `UNIQUE (source_id, period_start)`; the
  write is an `ON CONFLICT (source_id, period_start) DO UPDATE`, so a re-run updates
  rather than inserts. Postgres enforces "no duplicate row"; the code does not have to be
  careful.
- **The score column is a `DecimalField(max_digits=4, decimal_places=2)`** — the domain
  returns a two-decimal `Decimal`, and `checked_rate` refuses anything else.
- **`period_start` is a `DateField`**, not a `DateTimeField`: a week is a calendar date,
  and `date_trunc('week', ...)` is a date. The check constraint keeps it on a Monday.
- **The due-claim** is `Source.objects.using(CATALOG).filter(status=active).exclude(
  reliability_scores__period_start=current_week)` with `select_for_update(skip_locked=True)`
  — a source with a row for this week is not due. `skip_locked` is what keeps two
  overlapping ticks from recomputing the same source.
- **No API change** and no frontend change: the score is readable, but nothing renders it
  yet (the admin's source page shows the observations; work item 9 makes the score
  meaningful to the ranking consumer).
- **Gates**: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`,
  `uv run lint-imports`, `uv run python manage.py check`,
  `uv run python manage.py makemigrations --check --dry-run`.

### Based on Design Doc

Reference: `.specs-fire/intents/trust-loop/work-items/reliability-recompute-and-escalation-design.md`
(checkpoint 1, 2026-11-11).

### As built — three things the plan got wrong

A plan that silently differs from the code is worse than no plan. Each of these was
found by a test, not by reading the code, and each is recorded here rather than only in
the commit.

1. **The shared append-only trigger could not carry this table.**
   The plan said *"append-only with one exception"* and assumed
   `catalog.forbid_history_mutation` would enforce it. That trigger allows exactly **one**
   column to go from NULL to a value — an outbox's `propagated_at`. This row's same-period
   refresh rewrites four non-nullable columns at once (`score`, `positives`, `negatives`,
   `computed_at`), which the shared trigger refuses. And that refresh is exactly what the
   AC's idempotence requires: *"a re-run writes no duplicate row"* — and a score a week
   stale is a score that is wrong.

   **As built:** the table has **its own trigger**, `catalog.guard_reliability_score()`,
   written out in full and narrow — the source and the period are fixed, the id and the
   creation time are immutable, the four computed columns may move, and a delete is
   refused except inside a retention purge. The shared trigger was **not** weakened.

   This is a **divergence from the design doc**, which assumed the shared trigger would
   do. The design doc's *intent* — append-only, with a narrow same-period refresh — is
   preserved exactly; only its *mechanism* changed.

2. **The escalation creates the review item, so the item cannot be read before the first
   recompute.** The plan's escalation tests were written as though the item existed
   first. It does not: the item is the escalation's **output**. `test_the_bump_is_audited`
   now fetches the item after the first `recompute_source`.

3. **An append-only guard refuses to *rewrite* a row, so an unknown-kind observation has
   to be created, not updated.** `test_an_unknown_kind_is_refused_rather_than_skipped`
   originally tried `SourceObservation.objects.filter(...).update(kind="invented")` and
   hit `AppendOnlyViolation` — the guard working correctly. The row is now created
   directly with the unknown kind.

### As built — three architecture maps that had to learn about the new table

Adding a table is never just adding a table. Three maps exist precisely to catch an
unowned table, and each had to gain `ingestion_sourcereliabilityscore`:

| Map | What it says |
|---|---|
| `tests/architecture/test_write_ownership.py` (`TABLE_OWNERS`) | AD-16: `ingestion` owns it, written only by the ingestion recompute service |
| `tests/wall/test_schema_placement.py` | It is a **catalog** table — a standing fact about a source, carrying no user identity |
| `tests/ingestion/test_models.py` | The designed-model count goes twelve → **thirteen**; the retention category is `SOURCE_REGISTRY` |

A score is a standing fact about a source, not user data, so it is purged with the
source registry rather than with an account. That is why the table's own trigger permits
deletion inside a retention purge — and why that one case is the *only* way a history row
goes away.

### As built — the gates, and the baseline

| Gate | Result |
|---|---|
| `pytest` (full suite) | **6124 passed, 16 failed** — the 16 verified as pre-existing by stashing the branch and re-running at HEAD |
| `pytest` (the four new files + the modified worker file) | **88 passed** |
| `ruff check` / `ruff format --check` | all checks passed · 577 files formatted |
| `lint-imports` | 19 contracts kept, 0 broken |
| `manage.py check` / `makemigrations --check --dry-run` | no issues / no changes detected |
| Coverage `domain/` (AD-8) | **100%** |

### As built — what the code review changed

The code review found **two CRITICAL defects** that 68 passing tests had not seen, both
about the claim, and both fixed. The full findings table is in `review-report.md`; the
ones that changed the shape of the code:

1. **The claim is now persisted, not merely locked.** `Source.reliability_claimed_at` is
   written in the claim's transaction, so it outlives that transaction — and the recompute,
   which runs in its own, is what the claim has to cover. A `FOR UPDATE SKIP LOCKED`
   released with the claim's transaction prevents nothing. Migration `0012`.
2. **The write is now one statement.** `get_or_create` under `select_for_update`, not a
   `SELECT`-then-`INSERT`. The old form was a race whose loser got an uncaught
   `IntegrityError` that failed the whole job.
3. **The batch catches per source**, and a failed source's claim is released so it is
   retried on the next tick.
4. **The observations are read inside the recompute's transaction**, so the counts and the
   row they produce are read and written against the same snapshot.
5. **One N, not two.** The escalation's min-N and the score's floor both use
   `counts.total` — the observations that carry a sign.
6. **The dead constants are gone and the live ones are used.**
   `RELIABILITY_SCORE_MAX_AGE` is deleted (the rule it promised is not the rule the AC
   asks for); `RELIABILITY_CLAIM_TTL` and `RELIABILITY_BATCH_SIZE` are added and used.
7. **The admin shows the stored score**, because this work item stores it — the copy that
   said "it is not stored yet" was this work item's own stale text.

---

# Work Item 9 — `ranking-consumes-reliability`

*The ranking debt, paid: FR-16's score enters the Relevance Pulse.*

**Design:** `.specs-fire/intents/trust-loop/work-items/ranking-consumes-reliability-design.md`
**Status:** implemented · tested · reviewed

## What this item is

`domain/ranking.py` published a **reduced** Relevance Pulse and named the debt in its
own docstring: `source_reliability` — FR-16's term — was absent because `Source` had no
score. The predecessor work item built the score and stored it. **This item wires it in.**

It is a **reweighting**, not an addition: the reduced formula's four weights summed to
1.0, so adding a fifth means taking the weight from somewhere. Every user's digest is
re-weighted, which is why the ADR (D2.3) and the AD-10 analysis (D9) are the substance
of this item rather than its paperwork.

## The decisions

1. **The weights are `0.35 / 0.20 / 0.10 / 0.10 / 0.25`** — interest, recency, city,
   confidence, reliability. **`source_reliability` is at FR-22's published weight of
   0.25, exact**, and `recency` is back at FR-22's published 0.20. The slack from
   `novelty_vs_exploration` (FR-25, absent) went to `interest_overlap`, which stands in
   for `preference_graph_match`.

2. **The inert-at-launch problem is answered: the term enters for every source, with
   the prior as a neutral value.** The alternative — gating on the minimum observation
   count — was rejected because it makes the formula's *shape* depend on a fact the
   formula does not carry (breaking FR-22's "the inputs are enough" promise), puts two
   formulas in production at once, and puts a cliff in the ranking.

3. **The term is not inert**, and the module docstring says why in the module's own
   terms: it is a per-candidate *variable* read from a stored computed number, and the
   prior is a value (`reliability_score(0, 0)`) rather than a constant in the
   expression. A source at 0.20 and one at 0.80 differ by exactly `0.25 × 0.60`.

4. **The read costs no query.** The candidate read already does
   `select_related("venue", "source")`, and the score is a column on that joined row.
   The term rides along; there is no second lookup and no N+1.

5. **A personal event's reliability is the prior.** A personal event has no `Source`,
   so there is nothing that could be unreliable — the same structure the personal path
   already uses for `city_match = 0.00` and `confidence = 1.00`.

6. **Slot 3 does not invert the reliability.** FR-5 *multiplies by* it — it is a quality
   gate, not a popularity term. Inverting it would make Slot 3 structurally prefer the
   least reliable sources.

7. **An ADR was owed, and it is created.** FR-22: "Amendments are tracked in
   `docs/adr/`" — the directory did not exist. `docs/adr/ADR-0025.md` is created, and
   the pin test reads it, so "bump the weight and update the string" is not a way past
   the pin.

8. **The e2e mutation probe's literal had to move.** It hard-coded `0.45`, which no
   longer appears in `shared/constants.py` — the probe's edit would have found nothing
   to replace and the suite would have stayed green, proving nothing. That is the
   **false green** the probe's own comment warns about.

## The proofs

| Proof | Where | Verified by mutation |
| --- | --- | --- |
| Two sources (0.20 / 0.80) rank in that order, in **each** slot | `tests/domain/test_ranking.py` | ✅ removing the term fails all three |
| The difference is the term's and nothing else | `tests/domain/test_ranking.py` | ✅ |
| The value travels through the composition | `tests/personalization/test_digest_composition.py` | ✅ removing the term fails it |
| An unscored source contributes the **prior**, not a zero | `tests/personalization/test_digest_composition.py` | ✅ replacing the prior with `0.00` fails it — **after the review**; before, it passed |
| No N+1: the catalog query count does not grow with the pool | `tests/personalization/test_digest_composition.py` | ✅ a per-candidate lookup gave 12 queries for 10 candidates against 2 for 1 |
| Stored explanations are never rewritten (AD-10) | `tests/architecture/test_ad10_explanation_persistence.py` | ✅ inserting an `update()` fails it |
| Hysteresis never crosses a composition | `tests/architecture/test_ad10_explanation_persistence.py` | ✅ |
| The ranking consumes FR-16's score and never writes it | `tests/architecture/test_ad10_explanation_persistence.py` | ✅ a planted assignment fails it |
| The weight pin fails on an unreferenced change | `tests/shared/test_constants.py` | ✅ the e2e probe catches it |

## The gates

| Gate | Result |
| --- | --- |
| `pytest` (the whole suite) | **6158 passed, 16 failed** — the same 16, verified pre-existing at HEAD by stashing |
| `pytest tests/architecture/ tests/domain/ tests/personalization/ tests/shared/` | **2882 passed** |
| `pytest tests/domain/ --cov=domain` | 643 passed · `domain/ranking.py` at **100%** |
| `pytest tests/e2e/mutation_probe_contract_e2e.py` | **all 10 contract probes caught** |
| `ruff check` / `ruff format --check` | all checks passed · 578 files formatted |
| `lint-imports` | 19 contracts kept, 0 broken |
| `manage.py check` / `makemigrations --check --dry-run` | no issues / **no changes detected** |

## The files

| File | Change |
| --- | --- |
| `backend/shared/constants.py` | Five weights; `RANKING_WEIGHT_SUM` over five; `RANKING_WEIGHTS_AMENDMENT`; the comment block rewritten (it described a reduction that is no longer the truth) |
| `backend/domain/ranking.py` | Module docstring; `RankingInputs.source_reliability` (required); `relevance_score`; slot 2's docstring; slot 3's inverted inputs |
| `backend/apps/ingestion/services/catalog_read.py` | `PublicEventCandidate.source_reliability`; `_source_reliability` resolves the prior from `domain.reliability`. **Review:** the DTO's default is now `reliability_score(0, 0)`, not a literal |
| `backend/apps/personalization/services/digest_composition.py` | `_inputs_for_public` passes the candidate's reliability; `_inputs_for_personal` passes the prior |
| `docs/adr/ADR-0025.md` | **Created** — the amendment record. **Review:** the header now points at the PRD's `Amendment A-10` block |
| `_bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md` | **Review:** FR-22 now carries the `Amendment A-10 (2026-11-11)` block the ADR cites |
| `backend/tests/shared/test_constants.py` | The weight pin rewritten; the ADR-file check added |
| `backend/tests/domain/test_ranking.py` | The proof tests |
| `backend/tests/personalization/test_digest_composition.py` | The wiring proof; the query-count bound. **Review:** the prior test rewritten — it was a false green |
| `backend/tests/architecture/test_ad10_explanation_persistence.py` | The two AD-10 guards. **Review:** a third added — the ranking never writes the reliability column |
| `backend/tests/e2e/mutation_probe_contract_e2e.py` | The probe's stale literal moved to `0.35` |

**No migration.** `Source.reliability_score` already exists; `DigestComposition` is
unchanged; no column is added anywhere.

---

# Work Item 10 — `frontend-report-control`

*The small flag: "Report this event" on the Detail screen.*

**Design:** `.specs-fire/intents/trust-loop/work-items/frontend-report-control-design.md`
**Status:** implemented, tested, reviewed

## What this item is

FR-59's user-facing half. The API is built (`event-report-api`, completed): `POST
/api/personal/event-reports` takes `{event_id, category}`, answers 201 with
`{category, reported}`, and refuses the sixth report in a day with a 429. This item builds
the **control** — the flag in the secondary action row, the modal with FR-59's four
categories, and the toast.

**The event's state never changes.** The API says so, and `event-report-api` proved it
with a test. A report is a private signal to an editor, not a state of the event. So
there is no "reported" badge, no greyed card, and no re-read of the event after the
report.

## The decisions

1. **Signed out, the flag is hidden** — and it is hidden *for free*. The whole action row
   is already inside `{personal ? … : null}` (`app/events/[id]/page.tsx:477`), so placing
   the flag in `DetailActions` inherits Save's behaviour rather than re-implementing it.
   It cannot drift from Save's, because it is the same `if`. Routing to sign-in was
   rejected: a control that always ends at a sign-in wall is a control that does nothing,
   plus three taps.

2. **The rate limit is an inline message inside the modal**, in the API's own words, and
   the modal stays open. A toast is transient and a limit lasts until tomorrow; a message
   that vanishes on a timer is a message the user will miss.

3. **A network failure leaves the modal open with the selection preserved**, showing
   `OFFLINE_MESSAGE`, and Submit is live again. The selection is the user's work, and
   losing it makes the user do the thing twice — the opposite of FR-59's "one tap
   submits".

4. **The toast is a bare `<p aria-live="polite">`, always in the DOM, and never a second
   `role="status"`.** The row already owns the page's one status region (the
   conflict-failure line), and `page.test.tsx:1121` asserts `queryAllByRole("status")` is
   empty in the resting state.

5. **The flag is a ⚑ glyph *and* the words "Report this event".** FR-59 asks for a glyph;
   the house rule (`share-control.tsx`'s docstring, WCAG 1.1.1) forbids an icon-only
   button. The accessible name contains the visible text (WCAG 2.5.3).

6. **The options are `role="radiogroup"` + `role="radio"` + `aria-checked`** — a category
   is a *state* (exactly one is true), unlike a conflict's three resolutions, which are
   *actions* and use `role="group"`. **There is no precedent for this in the codebase;
   this item establishes it.** The option's accessible name is the label alone; the
   mockup's description is `aria-hidden`, so `getByRole("radio", { name: "Wrong date or
   time" })` resolves.

7. **The four labels are FR-59's verbatim**, and the four values are the **generated**
   union — `components["schemas"]["EventReportIn"]["category"]` — so a category outside
   the contract is a type error, not a runtime surprise.

8. **No free-text field exists at all**, and the Submit is disabled until a category is
   chosen. Selecting does *not* submit: a report that fires on a mis-tapped radio is a
   report the user did not mean to make.

9. **Focus returns to the flag** when the modal closes — by Esc, by Cancel, or by a
   successful submit. The effect is keyed on the *transition* (`wasOpen && !open`), so it
   cannot steal focus on the first render.

10. **The `Sheet` is dismissible**, unlike the conflict prompt. A report is optional; a
    conflict is a forced choice (FR-58). The native `<dialog>` gives the focus trap with
    no JavaScript and no library.

11. **Three mockup features do not ship**, and each is recorded rather than silently
    dropped: the **daily counter** (no endpoint carries the tally, and FR-59 rejects the
    visible counterpart), the **pre-emptively disabled Submit** (the client cannot know
    the user is on their sixth report — the server's limit is discovered by attempting and
    rendered calmly), and the **repeat-reporter warning** (needs the user's editorial
    rejection history; no endpoint carries it — **a remaining FR-59 consequence**).

## The one existing test this item breaks

`frontend/app/events/[id]/page.test.tsx:1137` asserts the Detail Screen renders **no**
"report this event" text. It was written when the feature did not ship, and it is now
wrong by design. **The one assertion is removed and replaced with its positive form** (in
the signed-in state, the page *does* render it); the test's other three assertions —
reviews, similar events, "attended" — are **untouched**, and a new test pins the
signed-out absence.

**This is not a test bent to fit the code.** The test's purpose is "the Detail Screen
ships only the sections that have shipped", and the report control is now one of them. A
test asserting a shipped section was absent would be the defect.

## The Playwright gap

The criterion says "the existing Playwright and axe gates cover it". **Playwright is not
in this repository** — no `playwright.config.ts`, no `@playwright/test` dependency, no
e2e runner; the frontend has 14 Vitest suites and nothing else. So the **axe half** is
honoured in the house's own way: a Vitest + axe-core case in
`frontend/tests/event-detail-a11y.test.tsx` — the file that already is the Detail
Screen's axe gate — auditing the open modal over `document.body`, with `color-contrast`
disabled explicitly as in every other case. **The Playwright half is reported as a gap,
not claimed as satisfied.**

## The files

| File | Change |
| --- | --- |
| `frontend/components/detail/event-report-control.tsx` | **Created** — the flag, the modal, the toast. One island, like `ShareControl` and `DetailMuteControl` |
| `frontend/components/detail/event-report-control.test.tsx` | **Created** — 36 component tests |
| `frontend/components/detail/detail-actions.tsx` | Import and render `<EventReportControl />` after `<ShareControl />`. Nothing else changes |
| `frontend/app/events/[id]/page.test.tsx` | The "no report link" assertion removed and replaced with the positive form; a signed-out test added |
| `frontend/tests/ad19-endpoint-coverage.test.ts` | `POST /api/personal/event-reports` added to `NEW_ENDPOINTS`, operation id `apps_personalization_api_report_event_endpoint`, caller `components/detail/event-report-control.tsx` |
| `frontend/tests/event-detail-a11y.test.tsx` | The axe case for the open modal |

**Not touched:** the schema (`event-report-api` regenerated it), `openapi.json`, the
backend, and `app/events/[id]/page.tsx` (the flag inherits the `personal` gate).

## The gates

| Gate | Result |
| --- | --- |
| `pnpm test` (the whole frontend suite) | ✅ **107 files, 1810 tests, all passed** |
| `pnpm typecheck` | ✅ `tsc --noEmit` clean |
| `pnpm lint` | ✅ `eslint .` clean |
| `pnpm format:check` | ✅ "All matched files use Prettier code style!" |
| Every assertion proved by mutation | ✅ **33 probes, 33 caught** (24 control · 2 page · 7 AD-19) — none BROKEN |
| The backend suite (unchanged by this item) | ✅ **6158 passed, 16 failed** — the run's 16 standing failures, untouched |

**No backend change. No migration. No new endpoint.**


---

# Work Item 11 — `e2e-proof-and-contract-tests`

**The proof — a report, a verdict, a score, a ranking** · mode `confirm` · intent `trust-loop`

## What this item is

The ten items before it each proved their own piece against its own seam. This one proves
the **claim the intent was captured on**: that FR-59, FR-57 and FR-16 are *one loop*, and
that the loop closes. It is the same shape every earlier intent closed with — a proof file
and a contract file in `tests/e2e/`, plus a mutation probe that shows the proof can fail.

**Nothing in `apps/`, `domain/`, `worker/` or `frontend/` changes.** If the proof finds a
defect, that is a finding for the run log and a decision for the user, not a silent fix
smuggled into the item that was supposed to be measuring.

## The approach

### 1. The chain (`TestTheLoopCloses`)

One journey, one source, one event, one user, one editor — driven through the **real**
write paths, never the ORM:

| Step | Driven through |
| --- | --- |
| A signed-in user reports a published event | `POST /api/personal/event-reports` via the Django test client, signed in |
| A `user_reported` `ReviewItem` appears, with no user identity | `ReviewItem` row read in `catalog`; asserted that no column and no rendered admin page carries the reporter |
| The event is still in the digest | `compose_digest` → `read_digest`, the card is there |
| An editor rejects it through the admin | `client.post(changelist, {"action": "reject_items", ...})` as a **group member, `is_superuser=False`** |
| The event leaves the digest, the public URL and the sitemap | `list_public_events`, `get_public_event_by_slug`, `list_url_feed` |
| Saved users are handled as `event-rejection-state` decided | reminders cancelled, no email out of `sweep_due_sends`, the `SavedEvent` row untouched |
| The source's observation count rises | `SourceObservation` rows for the source, `kind="rejected"` |

The outbox is drained the way the worker's reconciler does (`reconcile_outbox` +
`propagation.propagate`), as `test_rejection_proof.py` already does.

### 2. The score moves the ranking (`TestTheScoreMovesTheRanking`)

**30 rejects, because 30 is the number the arithmetic demands.** With α = β = 5, a source
with `p` approvals and `n` rejects scores `(5 + p) / (10 + p + n)`. Thirty rejects and no
approvals gives `5 / 40 = 0.125` — below `RELIABILITY_ESCALATION_SCORE` (0.30) and at
exactly `RELIABILITY_MIN_OBSERVATIONS` (30), so both halves of `should_escalate` are
satisfied and neither is satisfied by accident. Each reject is a separate event and a
separate `ReviewItem`, because `source_observation_item_uq` permits one observation per
item.

Then `recompute_due(now=...)` — the job the worker tick calls, not `recompute_source`
directly — and:

- a `source_reliability` `ReviewItem` is open for that source;
- the source is **not** paused: `status == "active"`, cadence and every other column
  unchanged (asserted as a whole-row comparison, not field by field);
- a fresh event from the collapsed source ranks **below** an otherwise-identical event
  from a healthy source, through `compose_digest` — same title shape, same start, same
  city, same chips, same venue city, differing only in their `Source`.

The ranking delta is asserted as a number too (`0.25 × (0.50 − 0.125) ≈ 0.09`), so the
test fails if the term is silently dropped from the expression rather than merely
reordered.

### 3. The stranded-event path (`TestTheStrandedEventGetsOut`)

The path the intent exists for, through the **real confidence gate** rather than a
monkeypatched gate table: a venue registered in `US/Pacific`, a VEVENT carrying
`TZID=America/New_York` for that venue — the A3 conflict, `tz_inference_confidence = 0.60`
— ingested through `ingest_source`. That lands `publication_status = in_review`,
`sync_review_item` raises the `in_review` item inside the write's transaction, the editor
approves through the admin, and the event appears in the digest.

### 4. The negative paths (`TestTheRefusals`)

- **A non-editor is refused by the admin.** A staff user with no review permission gets
  302/403 from the changelist and the change page, and posting the reject action writes
  **no** `ReviewItem` resolution and **no** audit row.
- **A sixth report in a day is refused.** Five `POST`s to five distinct events answer 201;
  the sixth answers **429** with `retry_after_seconds`, and no sixth `EventReport` exists.
- **A stale-version resolve is refused.** The admin edit form posted with
  `expected_event_version` one behind answers 200 with the refusal on the form, the event
  is unchanged and the item is still open.

### 5. The contract file

`tests/e2e/test_trust_loop_contract.py`, in the shape of `test_state_change_contract.py`:

- `POST /api/personal/event-reports` is in the committed `openapi.json`, with exactly that
  verb.
- `EventReportIn` / `EventReportOut` are in `components.schemas`; the four categories are
  **enumerated** in the document; `EventReportIn` carries **no free-text property** and
  `EventReportOut` carries **no report id and no tally**.
- `schema.ts` carries the operation id the frontend calls.
- **Regenerating changes nothing** — `openapi-typescript` is re-run and the file restored,
  the same measurement the earlier contract file makes.
- The architecture invariants, for *this* intent's seams: `editorial` owns no model and
  imports no `apps.ingestion.models`; `apps/ingestion/admin.py` never calls `obj.save()`;
  the report path writes no `catalog` row from `personalization`; `lint-imports` passes
  and the contract count is still pinned; nothing on the trust-loop path imports a network
  client.

### 6. The known gaps, as a test and not as prose

The AC asks that the intent's known gaps be *listed*. A list in a docstring rots silently,
so each gap is a **named assertion that the gap is still a gap** — and will fail, loudly
and on purpose, on the day it is closed:

| Gap | The assertion |
| --- | --- |
| FR-25 dismissals are a seam, not an input | `OBSERVATION_SIGNS["dismissed"] == 0` and no dismissal term in `domain/reliability.py` |
| FR-14's LLM path | structured ingestion still writes `EXTRACTION_CONFIDENCE_STRUCTURED == 1.00`, so the extraction gate is unreachable |
| Free-text reports | no free-text property in `EventReportIn`, and four categories exactly |
| The FR-29 dashboard | the queue metrics exist only in the admin: no route serves `QueueSummary` |
| Merging duplicates | `duplicate` is a report category, and the admin offers no merge action |
| The PRD amendments owed | ADR-0025 and `RANKING_WEIGHTS_AMENDMENT` are the recorded place; the files exist and name the amendment |

### 7. The mutation probes

`tests/e2e/mutation_probe_trust_loop_e2e.py`, in the harness style of
`mutation_probe_contract_e2e.py`: one real, parsing, plausible bug per claim, each naming
the suite that must catch it. Planned probes, one per AC clause:

1. The report hides the event (`report_event` sets `publication_status`).
2. The `ReviewItem` raise is skipped for a reported event.
3. `reject_event` leaves the event in the sitemap (`url_feed` drops the status filter).
4. The reject records no `SourceObservation`.
5. `should_escalate` uses `or` instead of `and` on the min-N — escalation fires early.
6. The ranking drops the `source_reliability` term.
7. `sync_review_item` skips `in_review` events (the stranded path never gets a ticket).
8. `may_review` accepts `view_reviewitem` (the non-editor gets in).
9. The report throttle is checked after the idempotence shortcut (the sixth slips past).
10. The edit form ignores `expected_event_version` (the stale resolve lands).

A probe that is **not caught** is a finding reported to the user, not a test quietly
deleted.

## Files to Create

| File | Purpose |
| --- | --- |
| `backend/tests/e2e/test_trust_loop_proof.py` | The four journeys above |
| `backend/tests/e2e/test_trust_loop_contract.py` | The endpoint contract, the architecture invariants, the known gaps |
| `backend/tests/e2e/mutation_probe_trust_loop_e2e.py` | The ten probes |

## Files to Modify

**None expected.** If a probe or a journey finds a real defect, it is reported before
anything is changed.

## Tests

- `uv run --directory backend pytest tests/e2e/test_trust_loop_proof.py tests/e2e/test_trust_loop_contract.py`
- `uv run --directory backend python tests/e2e/mutation_probe_trust_loop_e2e.py`
- The whole backend suite, against the recorded baseline (the run's standing failures are
  counted before this item starts, so a new failure is distinguishable from an old one).
- `make lint-backend`

## Gates

| Gate | Requirement |
| --- | --- |
| The new suites | all green |
| The whole backend suite | no failure that is not in the recorded baseline |
| Mutation probes | every probe caught, or reported as a finding |
| `ruff` + `lint-imports` | clean |
