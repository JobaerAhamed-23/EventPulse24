---
run: run-eventpulse24-025
work_item: e2e-proof-and-contract-tests
intent: event-state-sync
generated: 2026-11-10
mode: confirm
---

# Implementation Walkthrough: Proving the whole path works

## Summary

Twelve work items built this intent. Each was tested in isolation — the ingestion outbox,
the propagation consumer, the send lifecycle, the notice, the API, the card, the strip.
**None of them tested the seams.** And the seams are where the failures live: a send
cancelled in one test and a notice raised in another are two events, not one user's
evening.

**This item adds no production code.** It adds the proof, the contract tests, and the
mutation probes — and, in doing so, it **found the implementation to be correct in three
places where the first draft of the test was wrong**. Those three are the most valuable
output, and they are written down below rather than papered over.

## Structure Overview

```text
backend/tests/
├── domain/
│   └── test_notices_and_sources.py      (new)  11 tests — the two `domain/` modules the
│                                                 100% gate was missing
└── e2e/
    ├── test_state_change_proof.py       (new)  30 tests — the seven journeys
    ├── test_state_change_contract.py    (new)  13 tests — the contract the seams are
    │                                                 bound by
    └── mutation_probe_state_change_e2e.py (new)  6 probes — each bug applied, the suite
                                                  run, the file restored
```

## The seven journeys

Every journey drives the **real** write path. The `catalog.guard_event_write` trigger
refuses a status change without a version bump, so `apply_lifecycle_change` — the
ingestion write path — is the *only* way a cancellation happens. The proof drives it, so
the `EventStateChange` it asserts on is the one the pipeline would have written, with the
version the pipeline would have given it.

| Journey | What it proves |
|---|---|
| **Hold and release** | A send claimed by the sweep while its event is mid-change is **held, not sent**, excluded from the next claim, and released by the propagation. AD-17's race — the one no unit test can catch alone |
| **Cancellation** | Pending sends cancelled · the conflict pair closes · the card shows cancelled · one notice in the strip and one email |
| **Postponement** | The snapshot moves · reminders re-mint against the new version · a new overlap surfaces as the **calm Detail notice**, not the FR-58 forced prompt |
| **Sold out** | Reminders **kept** · badge on the card · the snapshot does not move · one notice |
| **Reinstatement** | Reminders re-mint from the surviving plan under a **new** key · the save returns to live · the old spent key does not block the new send |
| **Backlog drain** | Unpropagated changes that predate the intent are drained without manual intervention |
| **Mute** | A muted event's change produces **no notice and no email**, while its reminders still fire · a **terminal** change is raised anyway |

Plus **the strip and the banner**, over the real HTTP stack with a session cookie — the
only place the server's bound on the strip, the server's mute fact, and the recorded
dismissal are observable.

## The four decisions this item turns on

**1. The version is the spine, and every journey asserts one.** AD-17 gates every consumer
on `EventStateChange.event_version`. A proof that asserted only *existence* would pass
against a propagation that applied the wrong version to the wrong rows. So each journey
names the version it expects and finds it on the row — not merely "a row exists".

**2. The clock is frozen at a fixed instant, and the event starts two days past the wall
clock.** Two reads are bounded by the wall clock — `get_public_event` and the Detail
endpoint — and a proof whose answer depended on the hour it ran would be flaky. The event
starts on the 13th while `NOW` is the 10th, so the Detail read finds it whenever the
suite runs.

**3. The proof asserts on `idempotency_key` membership, never on a mail count.** The first
draft asserted `counts.sent == 1` and found **two** mails: the reminder and the notice. A
total would also be a claim about the *notice* — a different journey's business. Each
journey's claim is about *which* mail went out, and that is what is asserted.

**4. The contract tests delegate to the tree's own rules rather than re-implementing
them.** The first draft of "ingestion never writes to personal" scanned for the word
`PERSONAL` and **failed on `apps/ingestion/admin.py`** — which *reads* the user model
from `personal` to show an actor's name in the admin's list column. **A read across the
wall is legal**; AD-3 is about a write and about a transaction spanning both schemas. So
the test now calls the tree's own `test_no_app_writes_a_table_it_does_not_own` over its
own source list. **One rule, one discovery, and the two lists can never disagree.**

## Three places the implementation was right and the test was wrong

These are the review's most valuable output. In all three, the fix was to the test — with
the reasoning recorded in the test so a later reader does not "fix" it back.

**1. The `CANCEL` branch leaves a held row's `held_at` marker on it, and that is inert.**
`claim_due_sends` filters on `status = PENDING` **and** `held_at IS NULL`;
`count_stuck_holds` filters on `status = PENDING`. **So the marker is inert on a terminal
row.** Clearing it would change no observable behaviour and would cost a write. The test
now asserts the marker **stays**, that the claim returns `[]`, and why.

**2. A reinstatement raises one notice, not two — and that is the daily cap.** FR-54 caps
notices at one per event per local day, resolved by `domain.lifecycle.PRECEDENCE`, which
puts `cancelled` above `reinstated`. The reinstatement was moved to `NOW + 1 day`, **and
the cap is now proved deliberately** by its own test. **A test that proves the rule beats
a test that works around it.**

**3. The `CANCEL` branch does not re-stamp the row's version — and that is right.** A
cancelled send is terminal, so its working version is nobody's business. The test asserts
the row keeps the version it was minted at.

## The mutation probes

Six bugs, one at a time, each applied to the source, the suite run, and the source
restored. **6 of 6 caught.** Every probe plants a bug that still *parses* and still runs —
a probe that broke the file badly enough to fail collection would "pass" the harness
while proving nothing.

| # | The bug | Caught by |
|---|---|---|
| 1 | The propagation applies the change but **never marks it propagated** | 6 tests |
| 2 | The `CANCEL` branch **runs and cancels nothing** | 2 tests |
| 3 | The `KEEP` branch **cancels the reminder anyway** | 3 tests |
| 4 | The mute is **never consulted** | 3 tests |
| 5 | The hold **does not exclude the row from the next claim** | 1 test |
| 6 | The **terminal exception is gone**, so a mute silences a cancellation | 2 tests |

**Probe 3 is the one this item exists to make impossible.** "The event is sold out, so
stop nagging about it" reads as sensible and is exactly wrong: `sold_out` maps to `KEEP`
because **the event still happens**, and a user who saved a sold-out concert still wants
to be reminded to go to it. The planted bug deletes the reminder for an event that is
going ahead.

**Probe 5 is AD-17's race, and it is the one no unit test can catch alone.** A unit test
of `hold_stale_sends` proves the row is held; a unit test of `claim_due_sends` proves the
claim filters on what it filters on. Only a test that **holds a row and then claims
again** proves that the hold is what stops it.

## What this item also fixed

**The `domain/` coverage gate was red at `HEAD` and is green now.** `make coverage-backend`
requires **100% for `domain/`**; it was at **99%**, on nine lines across two files —
`domain/notices.py` (**this intent's own module**) and `domain/sources.py`. Every one is
a branch a user can reach, and each changes what the user is told. **The gate is on the
whole directory, so an older gap keeps this intent's build red** — and a red gate is a
gate nobody reads.

**Two committed files failed `prettier --check`.** CI runs `make lint-web`, so the gate
was red on files this run did not touch. Fixed — whitespace only.

## The numbers

| | Result |
|---|---|
| **Tests added** | **54** (30 proof + 13 contract + 11 domain) |
| **Mutations proven able to fail** | **6 of 6** |
| Full backend suite | **5691 passed, 16 failed** — all 16 pre-existing |
| The baseline at `HEAD` | **17 failed** — so the delta is **−1**, not 0 |
| `domain/` coverage | **100%** (was 99%) |
| Overall coverage | **98.81%** (gate 80%) |
| Full frontend suite | **106 files / 1765 tests, 0 failed** |
| `lint-imports` | **19 contracts kept, 0 broken** |
| `axe-core` on both touched surfaces | **zero serious violations** |
