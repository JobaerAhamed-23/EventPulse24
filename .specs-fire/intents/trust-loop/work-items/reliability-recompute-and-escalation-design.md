---
work_item: reliability-recompute-and-escalation
intent: trust-loop
created: 2026-11-11
mode: validate
checkpoint_1: approved
---

# Design: The score that remembers — history, weekly recompute, and escalation

## Summary

FR-16's score cannot live on one field of `Source`. Its spike rule compares *this week*
with *last week*, so the score needs a history; and "updated at least weekly" needs a
recorded computation to compare against. So the score becomes a **table of computed rows** —
`SourceReliabilityScore`, one row per (source, computation) — and `Source` gains a
**denormalised current score** that the job writes in the same transaction as the row it
computed.

The counting rule is the load-bearing decision, and it is decided here, once, in a table
that both the recording site and the recompute job read:

| Verdict | Sign | Why |
|---|---|---|
| **Reject** | negative | The listing was wrong. The source got it wrong. |
| **Edit** | negative | **The source was wrong.** A corrected listing is evidence against the source, not for it — the editor did the source's work for it. |
| **Approve** | positive | The listing was right. |
| **Dismiss** | **neutral** | An editor looked at a `source_reliability` item and found no fault. It is *not* an approval of the source (nothing about the source was checked) and it is not a rejection. It counts as **no observation at all**. |
| **User report** | negative, **only when upheld** | A report is a claim. It becomes an observation only when an editor's verdict upholds it. |

**"Upheld" is defined as: the editor's verdict on the event was `rejected` or `edited`.**
A report on an event the editor then approved was *not* upheld — the editor looked and said
the listing was fine.

**One verdict counts once, no matter how many reports it carried.** Five reports on one
event, one editorial verdict → **one** observation, not five. This is the rule the AC names
and it is enforced by the storage, not by arithmetic after the fact.

**Dismissals (FR-25) are a named, unimplemented input.** They are listed in the counting
table, they count as neutral, and nothing pretends they are implemented.

## Scope

**In Scope:**

- `SourceReliabilityScore`: the model, its migration, its constraints
- `Source.reliability_score` — the denormalised current score, plus `reliability_scored_at`
- `shared/constants.py`: the observation sign table, the weekly cadence, the due window
- `apps/ingestion/services/reliability.py`: the counting, the recompute, the escalation
- `apps/ingestion/services/editorial_review.py`: recording the observation *at resolution
  time*, with the report count the verdict carried
- `worker/tasks.py`: the recompute task, enqueued from `tick`
- The never-removal guarantee, asserted by a test

**Out of Scope:**

- **Ranking.** `ranking-consumes-reliability` (work item 9) reads the stored score. This
  item writes it.
- **FR-25's dismissal rate.** The input is named; the rate is not computed.
- **Any change to `Source.status`, `ingestion_cadence`, or the scheduling.** FR-16 says
  "escalation, never removal", and this item's job is to make that true, not to argue
  about it.
- **The `SourceObservation` table.** It already exists (migration `0010`) and already holds
  the facts. This item reads it and adds the *computed* rows beside it.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **D1. The score is a table of computed rows, and `Source` carries the current one** | `SourceReliabilityScore` (append-only, one row per (source, computation)) **plus** `Source.reliability_score` and `Source.reliability_scored_at`, written in the same transaction as the row. | The AC allows either "a denormalised field on `Source`" or "a latest-row read", and says the design decides. **Both**, because they answer different questions: the field answers *"what is this source's score right now?"* — the ranking consumer's question, asked per event, thousands of times — and the table answers *"what was it last week?"*, which is the spike rule's question and the only one a field cannot answer. A latest-row read for the current score would be a correlated subquery per lookup, on the hot path, for a value that changes once a week. The field is written **only** by the recompute job, in the same transaction as the row it computed, so the two cannot disagree: a crash between them rolls back both. |
| **D2. The row is keyed by (source, computation), and the computation is identified by its period** | `UniqueConstraint(fields=["source", "period_start"])` where `period_start` is the ISO Monday of the week being computed. | "One row per (source, computation)" and "idempotent within a period: a re-run writes no duplicate row" are the same statement. Keying on the **period**, not on a timestamp, is what makes idempotence a database guarantee rather than a hopeful `get_or_create`: two runs of the same week collide on the constraint, and the second run updates the existing row. Keying on `computed_at` would make every run a new row and make "a re-run writes no duplicate row" false. |
| **D3. The period is the ISO week, and the recompute is a *rolling* last-week comparison** | `period_start` = the Monday 00:00 UTC of the week being computed. The recompute for week W compares W's rate with W−1's rate. | The spike rule is week-over-week. A **calendar** week is the honest reading of "this week with last week" and it makes the table readable: one row per source per week, and "the score history" is the rows in order. A *rolling* 7-day window would need a per-source timestamp of the last computation to define its window, which is a second state to keep in step with the row. Calendar weeks it is — and the first week of a source's history has no predecessor, so it simply cannot spike. |
| **D4. An edit is a negative observation** | `edited → negative`. | The work item says it is "arguably negative, since the source was wrong", and this design takes that side. **The reason is that the source's job was to state the facts, and the editor had to change them.** A typo in a title is a fact the source got wrong; a wrong date is a fact the source got wrong. There is no *severity* distinction in FR-16 — the floor at 0.32 and the min-N of 30 are the only brakes on a new source, and they are enough. The alternative (edits are neutral) would mean a source that gets every event's time wrong scores the same as one whose times are right, which is not a distinction FR-16 would want to draw. |
| **D5. A dismissal is neutral — not an observation at all** | `dismissed` is recorded as a `SourceObservation` (the fact that an editor looked and found nothing) but contributes **neither** a positive nor a negative to the counts. | A `source_reliability` item is raised by the *system*, so "dismiss" means "I looked at this source and found no fault in it" — not "I checked an event from this source and it was right." There was no event to check. Treating it as positive would let an editor clear a bad score by dismissing it, and would make the score a measure of *dismissals* rather than of *evidence*. Treating it as negative would punish an editor for doing the review the escalation asked for. Neutral is the only reading that is neither a reward nor a punishment. |
| **D6. FR-25's dismissal rate is a named input, not a faked one** | The counting table lists `dismissed` as FR-25's input, with a comment saying the *rate* is unimplemented. | `domain/reliability.py` already set the precedent: "an absent input is absent from the expression, never pinned to a stand-in that makes the formula look verifiable when it is not." The dismissal rows exist and are counted as neutral; no `dismissal_rate` term appears anywhere, because there is no such requirement to satisfy yet. |
| **D7. An upheld report is a report whose event was later rejected or edited** | "Upheld" = the editorial verdict on the reported event was `rejected` or `edited`. A report on an approved event is **not** upheld and counts for nothing. | FR-59's four categories are all claims of error (`wrong_date_time`, `wrong_venue`, `does_not_exist`, `duplicate`). A report that the editor's verdict contradicts was a bad report. FR-16 says the MVP inputs are "editorial rejects and **upheld user reports** (negative)" — so the report only counts when the editor agrees with it. Defining "upheld" *by the verdict* rather than by a separate review step means there is no second decision to make and no second place to make it: the editor's verdict is the answer to "was this report right?" |
| **D8. One verdict counts once, however many reports it carried** | The observation records **one** row per resolution. A `user_reported` item resolved as `rejected` records **one** negative observation, carrying the report count in a field — not five observations. | The AC says it outright: "specifies how one editorial verdict on an event with five reports is counted: once or five times. **Several reports must not multiply one verdict.**" The multiplication is prevented *structurally*: `SourceObservation` already has `UniqueConstraint(fields=["review_item"], name="source_observation_item_uq")` — one observation per review item — and an event's reports all live on **one** `user_reported` item (D2 of `review-queue-model`: one open item per (event, reason)), which the verdict closes with the others. So the storage already forbids the multiplication; this design records the report count as a field so the *fact* of the five is not lost, and the arithmetic reads one row. |
| **D9. The cross-database wall is held by recording the observation at resolution time** | The observation is written by `editorial_review.py` **in `catalog`**, from the `ReviewItem`'s own tallies. The recompute job reads only `catalog`. The two options in the work item are: (a) the report's facts reach `catalog` when the item is bumped, or (b) the observation is recorded at resolution time from the item's own tallies. **This design takes (b).** | The wall is AD-3: `ingestion` may not read `personal`, and `personal.EventReport` lives there. Option (a) would have the bump carry the report counts across the wall — a `personal` → `catalog` copy of user-reported facts, which is the leak AD-3's ER note exists to prevent, and it would have to happen in the *hot* path (every report) rather than at the rare moment of a verdict. Option (b) has the counts **already in `catalog`** — `ReviewItem`'s four tally columns are incremented by `raise_review_item` in `catalog` — and the verdict reads them from the item it is closing. The report's *identity* never crosses the wall (D4 of `review-queue-model`: a report reaches the row as a category tally only), and only counts cross. **The job is single-database**, which is what the work item asked to be shown. |
| **D10. The recompute job is enqueued from `tick`, but the *weekly* cadence is a due-date, not a minute-modulo rule** | `tick` enqueues `recompute_reliability` **every tick**; the job itself claims only the sources that are **due** (no score row for the current week). | `tick`'s cadences are minute-modulo rules (`minute % 5`, `minute % 15`) — **and a weekly cadence is not expressible as a minute-modulo rule.** There is no "minute % 10080". The tick already contains the precedent for this: `schedule_digests` runs on *every* tick because "due" is a per-source wall-clock comparison, and the dispatcher does the comparison; the tick only asks it to look. The same shape: the tick asks the job to look; the job decides who is due. **The claim is persisted on the source row** (`Source.reliability_claimed_at`), so two overlapping ticks cannot recompute the same source twice — which is what makes the job's idempotence requirement reachable at all. A lock alone would not do: the recompute runs in its own transaction, so a `FOR UPDATE SKIP LOCKED` released with the claim's transaction prevents nothing. The marker outlives the transaction that took it, and a claim older than `RELIABILITY_CLAIM_TTL` is a lost job and is reclaimed. |
| **D11. The recompute is idempotent within a period, by the constraint** | `period_start` is the unique key per (source, week). A second run in the same week **updates** the existing row rather than inserting a second one. | The AC: "It is idempotent within a period: a re-run writes no duplicate row." With the constraint in place, the "no duplicate row" half is enforced by Postgres, not by the code's good manners. The row is *updated* rather than skipped, so a re-run after new observations in the same week refreshes the number — a score that is a week stale is a score that is wrong. |
| **D12. Escalation bumps, never duplicates** | The job calls `raise_review_item(source=..., reason=source_reliability)`. `raise_review_item` already bumps the open item for (source, reason) — `review_item_open_source_reason_uq` — and writes a `review_item_bumped` audit row. | The AC: "A source that is already escalated is bumped, not duplicated." That is D2 of `review-queue-model`, already implemented and already tested. This item **calls** it rather than reimplementing the rule, and the test asserts the item count stays at one. |
| **D13. Never removal is a *structural* property, not a promise** | The recompute writes **no `Source` column** except `reliability_score` and `reliability_scored_at`. Nothing else about the source changes. | FR-16: "no path in this item pauses, hides or deprioritises ingestion of a source." A test asserts `status`, `ingestion_cadence`, `last_ingested_at`, `consecutive_failures` and `stale_since` are all unchanged after an escalation. Asserting the *absence* of a line in the source would be trusting the source; asserting the values are unchanged proves it. |
| **D14. The counting rule lives in `shared/constants.py`, and both the recorder and the computer read it** | `shared/constants.py` holds `OBSERVATION_SIGNS = {"approved": 1, "rejected": -1, "edited": -1, "dismissed": 0}`, and `apps/ingestion/services/reliability.py` holds the *functions* that apply it. | The work item says the counting rule must be "decided and written down". A constant in `shared` is the project's existing way to write down a cross-cutting vocabulary (`REVIEW_PRIORITY`, `REPORT_CATEGORIES`, `LIFECYCLE_SEND_BEHAVIOUR`) — and `shared` sits below `apps`, so it cannot import `apps.ingestion.models` and the table is keyed **by value**, exactly as those three are. Two places reading one table cannot disagree about a sign. |
| **D15. The spike comparison uses the two weeks' *rates*, from `domain/reliability.py` only** | The job computes `weekly_negative_rate` for week W and for W−1 and calls `is_spike(previous, current)`. The score is `reliability_score(positives, negatives)`. The escalation test is `should_escalate(score, observations)`. | The AC: "It uses only the `reliability-score-domain` functions." The domain module's docstring explains at length why the spike must measure *rates* and not scores (a ratio of cumulative posteriors cannot fire), so re-deciding that here would be a second, worse implementation. Every rule — the floor, the min-N, the 3× multiplier, the escalation threshold — comes from `domain/reliability.py`, and `shared.constants` supplies only the numbers the domain already consumes. |
| **D16. A source with no score row reads as the 0.50 prior** | `reliability_score(None)` — no row — returns `Decimal("0.50")`, which is `posterior_mean(0, 0)`. The ranking consumer's read service does this. | The AC: "A source with no row reads as the 0.50 prior." The prior *is* 0.50 — `domain/reliability.py`'s "No observations gives the prior mean, 0.50" — so the read path calls `domain.reliability.reliability_score(0, 0)` rather than hard-coding `0.50`, and the two cannot drift if the prior is ever re-tuned. |

## Technical Approach

### The two tables, and what each is for

```
SourceObservation                          SourceReliabilityScore
─────────────────                          ─────────────────────────
FACTS: what happened                        COMPUTATIONS: what was concluded
one row per editorial verdict               one row per (source, week)
append-only                                 append-only
  approved / rejected / edited / dismissed    score, positives, negatives,
  + the report count the verdict carried        computed_at, period_start
  + which event it was about
                                                 ▲
                                                 │ recompute job reads the facts
                                                 │ and writes the conclusions
```

`SourceObservation` already exists (migration `0010_sourceobservation`, shipped by
`editorial-review-commands`). This item adds one field to it (`report_count`) and the
`SourceReliabilityScore` table beside it.

### The counting, in one place

```python
# shared/constants.py
OBSERVATION_SIGNS = {
    "approved":  1,   # FR-16 positive
    "rejected": -1,   # FR-16 negative
    "edited":   -1,   # FR-16 negative — the source was wrong (D4)
    "dismissed": 0,   # FR-25's named input; neutral, and the rate is unimplemented (D5, D6)
}
```

```python
# apps/ingestion/services/reliability.py
def counts_for(observations) -> tuple[int, int]:
    """(positives, negatives) over a source's observations."""
```

The recompute reads **all** of a source's observations, applies the table, and hands the two
counts to `domain.reliability.reliability_score`. The domain module owns the arithmetic;
this module owns the *meaning* of each observation. Neither can disagree with the other
about what a score is.

### The weekly recurrence, and the week-over-week comparison

```
tick (every 60s)  ──enqueue──►  recompute_reliability
                                      │
                                      ├─ claim the sources due (no row for this week)
                                      ├─ for each source:
                                      │     observations = SourceObservation for the source
                                      │     positives, negatives = counts_for(observations)
                                      │     score = domain.reliability.reliability_score(...)
                                      │     this_week  = weekly_negative_rate(negatives_this_week, obs_this_week)
                                      │     last_week  = weekly_negative_rate(negatives_last_week, obs_last_week)
                                      │     spike = domain.reliability.is_spike(last_week, this_week)
                                      │     write SourceReliabilityScore(source, period_start, score, ...)
                                      │     write Source.reliability_score = score
                                      │     if domain.reliability.should_escalate(score, n) or spike:
                                      │         raise_review_item(source=..., reason=source_reliability)
                                      └─ release the claim
```

**The "this week" / "last week" split is by `occurred_at`,** and the period boundary is the
ISO Monday 00:00 UTC. The first week of a source's history has no predecessor: its
`last_week` rate is computed over zero observations, and `is_spike` compares a smoothed
prior against a smoothed week — which is a ratio of at most 1.56 for a small sample, so it
cannot fire spuriously. That is the domain module's own small-sample suppression doing its
job, and it is why the job can pass `(previous, current)` unconditionally.

### Idempotence, enforced by the database

```
SourceReliabilityScore
  UNIQUE (source_id, period_start)      ← the idempotence guarantee
  CHECK (positives >= 0 AND negatives >= 0)
  CHECK (period_start = date_trunc('week', period_start))   ← it is a week, not a moment
  CHECK (score >= 0 AND score <= 1)
```

A second run in the same week hits the constraint and **updates** the row. The Postgres
`ON CONFLICT (source_id, period_start) DO UPDATE` is the mechanism, so the "no duplicate
row" half is a guarantee rather than a convention.

### The report count, and why it is a field and not five rows

```
user_reported item:  reports_wrong_date_time = 1
                     reports_wrong_venue    = 2
                     reports_does_not_exist = 1
                     reports_duplicate      = 1
                     report_count           = 5
                              │
                              │ the editor rejects the event
                              ▼
one SourceObservation:  kind = "rejected", report_count = 5
                        │
                        ▼
the score counts:  negatives += 1     ← ONCE
```

`SourceObservation.source_observation_item_uq` (one observation per review item) is what
makes five rows impossible. The count is kept on the observation so the *fact* survives
without the *weight* multiplying.

## Integration Points

| Surface | What changes |
|---|---|
| `SourceObservation` | One new column, `report_count`, defaulting to 0. It is set from the closed item's tallies. |
| `Source` | Two new columns: `reliability_score` (nullable `Decimal`, the current score) and `reliability_scored_at` (nullable). **Written only by the recompute job.** |
| `editorial_review.py` | `_observe` gains `report_count`, read from the item being closed. |
| `worker/tasks.py` | One new task, `recompute_reliability`, enqueued from `tick` on every tick. |
| `shared/constants.py` | `OBSERVATION_SIGNS`, the weekly cadence, the due window. |
| `ranking-consumes-reliability` (work item 9) | Reads `Source.reliability_score`, or the latest row. **Not this item.** |
| The admin's source page | Now shows a real score alongside the observations. **The display is work item 9's or the frontend's; this item only makes the score readable.** |

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| The tick's enqueue table test breaks | Medium — `tests/worker/test_scheduling_tasks.py` pins the tick's enqueue list minute-by-minute | The new task is **enqueued on every tick**, so it joins the "every tick" group, and the pinned table is extended in the same commit. The test file is read before it is edited. |
| Two overlapping ticks recompute the same source | Medium — duplicate rows (blocked by the constraint) and a doubled escalation | The due-claim is `FOR UPDATE SKIP LOCKED` on the source rows, and the escalation is a bump (D12). Even if two ran, the constraint makes the second an update. |
| The week boundary is ambiguous | Low — a source's observations split across two weeks | The period is the **ISO Monday 00:00 UTC**, stated in the constant and in the constraint (`period_start = date_trunc('week', period_start)`), so the database rejects a row that is not a week start. |
| A score is compared against a stale predecessor | Low — a missed week makes the "last week" comparison two weeks wide | The predecessor is the **previous ISO week's observations**, computed by the same smoothing as this week's. A missed week therefore means the predecessor week has no observations at all, and the prior smooths that week to 0.50 — which makes the comparison *more* conservative, not less: a two-week-old rate is not a spike. |
| An edit is counted as negative and a source is punished for a typo | Medium — a legitimate consequence of D4 | The floor (0.32) and the min-N (30) are FR-16's own brakes, and the escalation threshold needs n ≥ 30. A source with typos gets flagged for review, not removed (D13), and the editor who made the edit can dismiss the escalation, which is neutral (D5). |
| The `Source` field and the latest row disagree | Low — the ranking consumer would read a different number than the history shows | They are written in the **same transaction** by the same job. A crash rolls back both. A test asserts the field equals the latest row's score after a recompute. |

## Implementation Checklist

1. `shared/constants.py`: `OBSERVATION_SIGNS`, `RELIABILITY_RECOMPUTE_PERIOD` (weekly),
   `RELIABILITY_SCORE_MAX_AGE`
2. `Source.reliability_score` and `Source.reliability_scored_at`
3. `SourceObservation.report_count`
4. `SourceReliabilityScore` model + migration `0011_sourcereliabilityscore`:
   `CreateModel` with the unique constraint, the checks, and the index
5. `apps/ingestion/services/reliability.py`: `counts_for`, `due_sources`,
   `claim_due_sources`, `release_claim`, `recompute_source`, `recompute_due`
6. `editorial_review.py`: `_observe` carries the closed item's `report_count`
7. `worker/tasks.py`: `recompute_reliability`, enqueued from `tick`
8. `apps/ingestion/services/reliability_read.py` (or a function in the same module): the
   current score, `0.50` when there is no row
9. Tests: the counting table, the five-reports-one-verdict case, idempotence, the weekly
   guarantee, both escalation paths, no duplicate escalation, never-removal
10. Full gate set: ruff, ruff format, `lint-imports`, `manage.py check`,
    `makemigrations --check`, coverage

## PRD Amendment Owed

FR-16's "A source needs at least 30 dismissal observations before its score moves" and
"the score is updated at least weekly" need their terms pinned:

> A source's score is recomputed **at least weekly** from its recorded observations and
> stored as an append-only history of weekly computations. An observation is an editorial
> **reject** (negative), an editorial **edit** (negative — the source's facts were wrong),
> an editorial **approve** (positive), or a **user report upheld by an editorial verdict**
> (negative). One editorial verdict counts as **one** observation however many reports it
> carried. A source with no history reads as the **0.50 prior**. A score below 0.30 with at
> least 30 observations, or a 3× week-over-week rise in the rate of negative observations,
> raises a review item. **No score ever pauses, hides or deprioritises a source.**
