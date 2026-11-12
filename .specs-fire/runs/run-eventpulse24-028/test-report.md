---
run: run-eventpulse24-028
work_item: duplicate-file-cleanup
intent: traceability-reconciliation
---

# Test Report: Clear 1,323 filesystem conflict copies out of the tree

## Results

| Check | Result |
|---|---|
| `find backend frontend .specs-fire docs -name "* 2.*"` | **0 remaining** (was 1,323) |
| Source duplicates deleted | **211**, each SHA-256 re-verified against its original at delete time |
| Bytecode duplicates deleted | **1,117** (`__pycache__/`, already gitignored) |
| `.gitignore` rule | **added and probe-tested** — matches `zz_probe 2.py`, does **not** match `zz legit 2 file.py` |
| `makemigrations --check --dry-run` | **No changes detected** |
| Frontend typecheck (`next typegen && tsc --noEmit`) | **pass** |
| Frontend tests (Vitest) | **2031 passed** across 123 files |
| Backend suite (pytest) | **6721 passed, 17 failed** — all 17 pre-existing, see below |
| Tracked files deleted | **0** (`git status --porcelain` shows no `D` entries) |

No new tests were written. This item deletes files byte-identical to files that remain; the
correct proof is that the existing suites still pass, not a new assertion.

## The 17 backend failures are not this item's

Run 027's own test report already recorded **16 pre-existing failures** on `main`, in exactly
this distribution: `test_timeline_and_conflict_proof.py` 9, `test_save_race.py` 4,
`test_url_feed_read.py` 1, `test_reminder_plan_api.py` 1, `test_personal_events_and_saved_catalog.py` 1.
This run reproduces all of them, plus **one more in `test_reminder_plan_api.py`** — 17 total.

**The seventeenth is a hardcoded fixture date that expired mid-way between the two runs.**

`tests/delivery/test_reminder_plan_api.py:56` declares
`AFTERNOON_START = datetime(2026, 11, 12, 2, 0, tzinfo=UTC)`. Run 027's suite finished at
**02:19 UTC on 2026-11-12**; this run executed at **~05:00 UTC the same day**. The fixture's
event start is now three hours in the past, so `test_a_custom_slot_is_minted` — which asserts
a `custom:90` slot mints a `ScheduledSend` 90 minutes before the start — gets an empty list,
because that moment has passed:

```
assert [send.slot for send in sends] == ["custom:90"]
E   AssertionError: assert [] == ['custom:90']
```

It reproduces in isolation (`pytest tests/delivery/test_reminder_plan_api.py` → 1 failed,
26 passed) with no duplicates anywhere on disk, so nothing about collection or imports is
involved. This is the same class of defect run 027 flagged for
`test_url_feed_read.py::test_a_city_lastmod_is_the_latest_of_its_events` — *"looks
time-dependent — it expects a fixed `2026-11-06T10:00Z` and receives the current instant."*

**Why the deletion cannot be the cause**, independently of the above:

1. **Zero tracked files were removed.** Every one of the 211 was untracked and SHA-256
   identical to a git-tracked original that remains in place.
2. **Python cannot import these files at all.** A filename containing a space is not a valid
   module name, so `collections_api 2.py` and `services/mutes 2.py` were unreachable by any
   import statement. Deleting unreachable files cannot change behaviour.
3. **Where pytest *could* reach them, deletion can only subtract.** Seven of the deleted files
   were under `tests/delivery/` and do match pytest's `test_*.py` glob
   (`test_notice_mutes 2.py` and friends), so they were being collected and run as duplicate
   copies. Removing them reduces the number of tests executed; it cannot invent a new failure.
   None of the seven duplicated `test_reminder_plan_api.py`.
4. **The frontend duplicates were never collected.** Vitest matches `*.test.tsx`;
   `collection-manager.test 2.tsx` ends `.test 2.tsx` and does not match. The frontend suite
   passes 2031/2031 either way.

## Acceptance Criteria

| Criterion | Status |
|---|---|
| Every `* 2.*` classified before any deletion | met — identical 211, divergent 0, newer 0, orphaned 0 |
| Classification produced by script, not by eye | met — `classify_dups.py`, kept in scratchpad, not committed |
| Divergent files stop the item and are reported | **not triggered** — zero divergent found |
| Identical and stale copies deleted; `find` returns nothing | met |
| `.specs-fire/runs/run-eventpulse24-027/` duplicates handled by the same rule | met — all 4 were identical, deleted |
| `.gitignore` rule prevents recurrence | met — and probe-tested for false positives |
| `makemigrations --check` and backend suite pass | **partial** — migration check clean; suite has 17 pre-existing failures, none attributable to this item |
| Frontend typechecks and builds | met |

## Deviations

1. **The classification script is not committed.** The work item allowed scratchpad *or*
   `scripts/`. It stays in the scratchpad: it is a one-shot audit, and the `.gitignore` rule
   is the durable control. A committed script would imply a check someone maintains.
2. **`.env` was modified to unblock the suite.** The backend could not start at all —
   `config/env.py:213` raised `ValidationError: stripe_api_key / stripe_webhook_secret Field
   required`. `stripe_api_key` entered `env.py` in commit `6e08e55` (run 027's billing item),
   which added the keys to `.env.example` but not to the local `.env` (last written Nov 10,
   before that commit). The fix copies `.env.example`'s own local-only placeholder block.
   `.env` is gitignored; no code changed. A backup is at
   `/private/tmp/claude-501/-Users-jobaer-Documents-EventPulse24/f0188aed-a587-41fe-8d84-8f3cfda9060e/scratchpad/.env.bak-028`.
3. **The 1,117 bytecode copies were deleted even though `__pycache__/` is already gitignored.**
   Cosmetic, done only so the acceptance criterion's `find` returns clean.

## Recommended follow-up

Run 027 recommended a defect work item for the time-dependent e2e failures and it was never
created. This run strengthens the case: the count is **rising on its own** as more hardcoded
timestamps pass. `main` is not green, and the failures sit in the e2e proofs whose purpose is
to show the MVP holds together.

The diagnosis is now further along than run 027 left it. That report guessed "one underlying
cause rather than five" for the fifteen save/conflict failures; this run confirms at least two
of the seventeen (`test_url_feed_read`, `test_reminder_plan_api::test_a_custom_slot_is_minted`)
are independently time-bombed fixture constants, which points at *many* small instances of one
**pattern** — hardcoded absolute datetimes — rather than one shared bug. The fix is likely
`freezegun` or a clock port, not a logic change.

This remains out of scope here and is **not** fixed in this run.

---

# Test Report: FR-20 — design the reminder default, and prove you can clear it

*(work item: `fr-20-reminder-defaults`)*

## Results

| Check | Result |
|---|---|
| `tests/delivery/test_scheduled_sends.py` | **55 passed** (54 existing + 1 new) |
| New test | `test_a_personal_events_plan_emptied_cancels_every_send` — **pass** |
| Mockup created | `personal-event-reminders-desktop.html`, self-tagged `FR-20` |
| `DESIGN.md` | +2 component entries, +1 Do's-and-Dont's row, all citing `FR-20` |
| `EXPERIENCE.md` | +1 Surface Coverage Map row (#21), citing `FR-20` |
| Backend source changed | **none** — this item added a test and documentation only |

The broad `tests/delivery/ tests/personalization/` sweep was not run. It is not needed: no
backend source file was modified, so the only new behaviour under test is the added test
itself, and its own file passes in full.

## Acceptance Criteria

| Criterion | Status |
|---|---|
| Mockup self-tagged `FR-20` showing default, edited, and **empty** plan | met — states A, B, C |
| Named DESIGN.md/EXPERIENCE.md section citing `FR-20` | met — `component.reminders.personal.plan`, `component.emptystate.chosen`, coverage row 21 |
| Test: new Personal Event has exactly 1d + 1hr | **already covered** — `test_personal_events.py:126`, `test_personal_events_api.py:195`, `test_reminder_plans.py:39` |
| Test: user can remove every slot; plan persists empty; edit does not re-apply default | **already covered** — `test_removing_all_reminders_leaves_an_empty_plan`, `test_removing_all_reminders_keeps_the_plan_row`, `test_personal_events.py:340` |
| Test: empty plan produces no `ScheduledSend` rows | **met by the new test** — this was the one real gap |
| Code fixed where a consequence fails | **not triggered** — no consequence failed |
| Tests name `FR-20` so the requirement is greppable | met |

## What this item actually found

**FR-20's code was never "inferred" — only its design was.** The backend names the
requirement deliberately throughout, and `attach_default_plan`'s docstring cites the
traceability gap by name:

> *"Until `/settings/reminders` existed the constant **was** the default, with no way to
> change it — which is why TRACEABILITY.md could only find FR-20 'by adjacency'."*

Someone read the matrix and closed the code side without closing the design side. Five of the
six acceptance criteria were already satisfied before this item started. The item's real
output is the design artifacts plus one test.

**The single test gap was narrow and worth closing.** Removal was proven to empty the plan for
a *personal* event, and proven to cancel sends for a *saved* event — so nothing proved that
removing a personal event's reminders actually stops the email. The new test closes exactly
that, and its docstring says why it is not redundant with its sibling.

## Deviations

1. **No duplicate tests written for already-covered consequences.** The work item asked that
   every testable consequence have a test naming FR-20. Four of five already had tests, most
   already citing FR-20 in a comment. Adding FR-20-aliased copies would inflate the suite
   without adding a proof, so the existing tests stand and the report cites them by name.
2. **Two as-built divergences documented rather than silently inherited** (both decided with
   the user at the checkpoint):
   - The reminder default attaches **silently** at creation —
     `components/sheets/personal-event-form.tsx` contains zero occurrences of "reminder".
     Documented in the mockup and in `component.reminders.personal.plan`; **no UI change**,
     since FR-20 requires the user *can edit*, not that creation *discloses*.
   - `/settings/reminders` makes the default **user-configurable**, reading
     `NOTIFICATION_PREFERENCE.default_reminder_slots` with the 1d + 1hr constant as fallback.
     FR-20's text says the default simply *is* 1d + 1hr. The shipped behaviour is a superset.
     Recorded as a **PRD amendment candidate** for `matrix-regeneration-and-ledger`; the PRD
     is not edited in this run.
3. **The new test was written clock-independent on purpose.** `test_scheduled_sends.py` passes
   `now=NOW` explicitly and fixes `START` in the data, so the `NOW < START` relation is
   structural rather than wall-clock-dependent. This matters: the neighbouring
   `test_reminder_plan_api.py` is the file whose hardcoded `AFTERNOON_START` expired three
   hours before this run and produced the seventeenth pre-existing failure. The new test
   cannot become the next time bomb.

---

# Test Report: FR-28 — design the share action itself, not the page it lands on

*(work item: `fr-28-share-affordance`)*

## Results

| Check | Result |
|---|---|
| `app/events/[id]/` (3 files) | **103 passed** |
| `page.branch.test.tsx` | **25 passed** (22 existing + 3 new) |
| Mockup created | `share-affordance-desktop.html`, self-tagged `FR-28` |
| `DESIGN.md` | +2 component entries, +1 Do's-and-Dont's row, citing `FR-28` |
| `EXPERIENCE.md` | +1 coverage row (#22); row 11 annotated to state its `UJ-5` scope |
| Application source changed | **none** |

## Acceptance Criteria

| Criterion | Status |
|---|---|
| Mockup self-tagged `FR-28` showing the control **in place on both surfaces**, resting/active/confirmed | met — Pulse Card (`card` weight) and Detail Screen (`secondary` weight), four outcome states |
| Design states the **Web Share API fallback** | met — outcomes A–D, including the clipboard path and the silent dismissal |
| `share-link-desktop.html` keeps `UJ-5`, is not repurposed | met — and row 11 now says so explicitly |
| Named DESIGN.md/EXPERIENCE.md section citing `FR-28` | met — `component.control.share`, `component.feedback.share` |
| Test: share-link resolves to FR-26's public URL with a "Save to Pulse" CTA | **already covered** — `tests/public-crawl-proof.test.tsx:284`, `app/events/[id]/page.test.tsx:651` |
| Test: Open Graph title, description, image present and **populated, not empty defaults** | **met by the new tests** — this was the gap |
| Share-link carries no session-dependent data (AD-12) | **already covered** — "reads no session to build the metadata" |
| Tests name `FR-28` | met |

## The gap was exactly where the work item predicted

FR-28's second consequence names three fields — *"title, description, image"*.
`app/events/[id]/page.tsx:158–176` sets all three, on `metadata`, `openGraph` **and**
`twitter`. The test file asserted `openGraph.title`, `openGraph.url` and `openGraph.images`
— and never `description`.

That is the silent degradation the work item called out: *"an unfurl with a blank image still
'works'"*. The same is true of a blank description, and nothing would have caught it.

Reading the implementation turned one assertion into three, because it revealed an **untested
fallback branch**:

```
const description = page.description
  ? page.description.slice(0, 200)
  : `${page.title} — ${page.source_name}`;
```

| New test | What it pins |
|---|---|
| `carries the Open Graph description — FR-28's third field` | The description reaches both `openGraph` and `twitter` |
| `falls back to title and source when the event has no description` | **The branch that makes "Open Graph-rich" true for every event, not most of them.** A sourced event with no description is ordinary; without this the unfurl is a blank-bodied card |
| `truncates a long description to 200 characters` | The implementation's own bound |

The fallback test is the valuable one. The happy path was always going to work.

## Three open questions, closed by reading

The work item speculated about three things. All three resolved against the code rather than
guessed:

1. **Does `share_precise_location` gate the share metadata?** **No.**
   `apps/personalization/services/export_source.py:38` is its only consumer — it gates FR-52
   export. There is no redacted share state to design, and no test to write. The work item's
   note that "the design must show both states" was based on a wrong premise.
2. **Does the share control belong on the Timeline event-block?** **No**, and it is correctly
   absent — `components/timeline/` has no `ShareControl`. Read-only per Amendment A-8.
   Recorded in the design so the absence reads as a decision.
3. **Is `share-link-desktop.html` FR-28's design?** **No.** It is `UJ-5`, the recipient's
   landing page. Row 11 now states that scope explicitly, since the filename invites exactly
   the confusion the matrix caught.

## Deviations

1. **Three tests written where the plan named one.** Reading `generateMetadata` before writing
   revealed the fallback and truncation branches, neither tested. The plan's single
   "assert description is present" would have missed the branch that actually guarantees a
   non-empty unfurl.
2. **`EXPERIENCE.md` row 11 was modified**, which the plan listed only as an annotation. It
   is a correction of the same class as FR-49's false coverage claim: a row whose filename
   suggests FR-28 coverage it does not provide. Stating the `UJ-5` scope inline stops the
   next reader re-making the matrix's own mis-attribution.
3. **`frontend/AGENTS.md` honoured.** `node_modules/next/dist/docs/01-app/03-api-reference/04-functions/generate-metadata.md`
   was read before the test was written. `openGraph.description` is a plain string with no
   version quirk — unlike `twitter.card`, which the existing suite already narrows because it
   "is only on some members of Next's `Twitter` union". The new Twitter assertion narrows the
   type the same way.

---

# Test Report: FR-49 — design saved collections, and correct the coverage claim that hid them

*(work item: `fr-49-saved-collections`)*

## Results

| Check | Result |
|---|---|
| `test_collections_api.py` + `test_save_cap.py` | **51 passed** |
| Mockup created | `collections-desktop.html`, self-tagged `FR-49` |
| `DESIGN.md` | +1 component entry (`component.manager.collections`) citing `FR-49` |
| `EXPERIENCE.md` | **row 10 corrected** — FR-49 struck; +1 coverage row (#23) |
| New tests | **0** — every consequence already proven; see below |
| Source changed | **none** |

The cited tests were **run, not merely cited**. An acceptance criterion satisfied by an
existing test is only satisfied if that test currently passes.

## Acceptance Criteria

| Criterion | Status |
|---|---|
| Mockup self-tagged `FR-49` showing create, rename, **reorder**, delete, contents, assign/unassign | met — sections A–E |
| Named DESIGN.md/EXPERIENCE.md section citing `FR-49` | met |
| **`EXPERIENCE.md:1236` corrected**, and the row's other claims re-checked | met — see below |
| Test: Pro user saves 10+ in one day, no soft-wall | **already covered** — `test_save_cap.py:318`, docstring reads *"FR-49's own testable consequence"* |
| Test: **reorder** persists, with the `/order` route-ordering regression | **already covered** — `test_reorder_takes_the_whole_list_in_one_request` |
| Test: free user at cap gets a calm prompt with **no modal** | **already covered** — `test_the_refusal_carries_no_modal_shaped_field` |
| Rename/delete/unassign confirmed open on every tier | met — 7 lapsed-user tests pin it |
| Shared collections and collection-level reminders stay out | met |
| Tests name `FR-49` | met — the file's own docstring opens *"The collections endpoints (FR-49)"* |

## The false coverage claim, counted rather than asserted

`EXPERIENCE.md:1236` claimed `settings-desktop.html` covered *"FR-7 / FR-12 / FR-48 / FR-49
/ FR-51 / FR-52"*. Each claim was checked against that file's actual content:

| Claim | Evidence | Verdict |
|---|---|---|
| FR-7 digest time | `digest time` ×1, `theme` ×5 | holds |
| FR-12 notifications / quiet hours | `quiet` ×10 | holds |
| FR-48 Pro tier | `Pro` ×7, `plan` ×5 | holds |
| **FR-49 collections** | **`collection` ×0** | **false — struck** |
| FR-51 per-day quiet hours | quiet-hours content present; Pro variant has its own mockup (row 16) | holds |
| FR-52 export | `export` ×4 | holds |

**Exactly one of six was wrong.** The correction strikes FR-49 and states the count inline,
so the next reader sees the evidence rather than having to re-derive it. The other five were
re-verified and left alone — the work item anticipated that "one wrong cell in a table is
rarely alone", and in this row it was.

## Why no new tests were written

The work item asked for three tests. All three already exist and pass:

1. **The reorder regression** already exists *in a better form than specified.* The work item
   asked for a test pinning that `/order` stays registered before `/{collection_id}`.
   `test_reorder_takes_the_whole_list_in_one_request` does a `PUT /order` and asserts `200`
   plus the resulting positions — so if the route were ever registered second, the call would
   be matched by the rename route, fail to parse `"order"` as a UUID, and the test would fail.
   That pins the trap **behaviourally** rather than asserting a registration order, which is
   the more durable test. The source comment's claim that *"the tests caught exactly that,
   five times over"* is accurate.
2. **10+ saves in a day** — `test_save_cap.py:318`.
3. **No modal interruption** — `test_the_refusal_carries_no_modal_shaped_field`, which asserts
   the *absence* of the modal-shaped field rather than the presence of the prompt. That is the
   harder half of the consequence and it was already done.

Writing FR-49-aliased copies would have inflated the suite without adding a proof.

## The open question in the work item is answered: there is no drag

The item worried about the drag affordance under the no-component-kit, no-animation-library
constraint, and asked for it to be surfaced at the checkpoint. There is no drag. Reorder is
move-up / move-down buttons — *"keyboard-operable with no pointer, needs no library, needs no
motion."* `styles/motion.test.ts` fails the suite on any animation beyond the single 240ms
transition, so a drag interaction was never available to design. The decision was already
made correctly in code; the design records it.

## Deviations

1. **No tests written**, against a work item that specified three. Each is already covered by
   a named, currently-passing test, cited above.
2. **Row 10's correction is larger than a strike.** It carries the counted evidence and the
   reason inline. A bare deletion would have left the next maintainer free to re-add the
   claim; the count makes that harder.
3. **An observation deliberately not acted on.** `collection-manager.tsx` says *"If it ever
   grows past a modest management UI, that is the signal to stop and get a design pass."*
   Drawing it confirmed it has **not** grown past that — the surface is a create row, a list
   with four controls per row, and an expandable contents panel. No change requested. This is
   recorded because the absence of a finding is itself the answer to the question the code
   asked.

---

# Test Report: FR-55 — design the cancelled-event conflict path, and prove nothing auto-cancels

*(work item: `fr-55-conflict-on-state-change`)*

## Results

| Check | Result |
|---|---|
| `test_event_detail_api.py` + `test_saved_events.py` + `test_digest_candidates.py` | **157 passed** |
| `test_event_detail_api.py` | **66 passed** (65 existing + 1 new) |
| New test | `test_a_muted_event_still_reports_its_notice` — **pass** |
| Mockup created | `event-state-conflict-desktop.html`, self-tagged `FR-55` |
| Mockups re-tagged | `conflict-prompt-desktop.html`, `conflict-indicator-card-state-desktop.html` — `FR-55` added beside `FR-58` |
| `DESIGN.md` | +3 component entries citing `FR-55` |
| `EXPERIENCE.md` | +1 coverage row (#24); **rows 8 and 13 acknowledge the second trigger** |
| Source changed | **none** |

## Acceptance Criteria

| Criterion | Status |
|---|---|
| Mockup self-tagged `FR-55` showing all three triggers + the mute | met — sections A, B, C, D |
| Design **states explicitly** whether FR-55 reuses FR-58's surface, and why; FR-58's mockups gain an `FR-55` tag | met — both mockup headers, plus EXPERIENCE.md rows 8 and 13 |
| The calm *"this overlaps with [other event]"* copy is specified | met — and the shipped copy already names the other event |
| Test: cancelled, no personal event → notified, leaves the digest | **already covered** — `test_digest_candidates.py:318` |
| Test: cancelled + personal conflict → **personal event survives untouched** | **already covered** — `test_saved_events.py:553`, *"a cancelled public event never auto-cancels a personal event"* |
| Test: postponed + conflict → notified, overlap message on Detail | **partially covered** — see the flagged gap below |
| Test: per-event mute silences notices **for that event only** | **already covered** — `test_the_detail_reports_the_mute_state`, `test_another_users_mute_is_not_yours` |
| Test: a muted event **still carries its notice fact** | **met by the new test** — this was the gap |
| Auto-rebook / alternatives stay out | met |
| Tests name `FR-55` | met |

## The matrix was right about the documentation and wrong to doubt the build

Its finding — *"only overlap with FR-58's conflict UI, with no documented acknowledgment it
also serves this trigger"* — is precisely worded, and investigating it vindicates the reuse:

- A postponement that creates an overlap writes a `CONFLICT_PAIR` row like any other
  (`services/saved_events.py:340`).
- AD-21 makes that one record the single source for every surface: *"the Pulse Card
  indicator, the Timeline event-block indicator and `/conflicts` all read the same rows, so
  the indicator is symmetric by construction."*

**FR-55 and FR-58 share a surface because they share a record.** That is architecture, not
an accident, and it had simply never been written down. It is now written in both mockup
headers, both EXPERIENCE.md rows and the new mockup — with an explicit instruction not to
strip the tag as a duplicate, since its absence *is* the gap.

**FR-55's copy requirement was already met, better than the matrix implied.** It asks for a
calm *"this overlaps with [other event]"*. `conflict-resolution.tsx:112` carries a kind-keyed
heading — *"This overlaps with another event."* — and `:162` follows with the naming line:
``It overlaps "${other.name}" on your calendar.`` The bracketed name of the PRD is the body,
not the heading.

## The gap was an invariant defended by two docstrings and proven by nothing

`make_mute` appeared at exactly two places in `test_event_detail_api.py` — the mute-state
test and the cross-user test. **No test put a mute and a notice on the same event**, which is
the invariant the code insists on twice:

> `detail_read.py:114` — *"a notice and a mute are different things, and a client must not
> read 'muted' as 'there is nothing to say'."*

Reading further showed **why collapsing them would be a real bug rather than untidiness**.
The mute's reach is deliberately narrower than "everything":
`delivery/services/state_notices.py` raises a `cancelled` or `superseded` notice **despite**
a mute, and `services/mutes.py` gives the reason — *"FR-55 has already removed the event from
their digest, so silence about it is the one failure with no second channel to catch it."*

A detail read that suppressed the notice whenever `muted` was true would make that rule
impossible to honour: the client would never learn the event was off. The new test asserts
both facts side by side on a muted, cancelled event.

That rule — **a mute is not silence** — existed only in code and now exists in
`component.banner.state-notice`.

## Flagged, not fixed: the postponed-into-conflict end-to-end path

FR-55's third consequence is covered in pieces — `saved_events` writes the pair, the sheet
renders from it and names the other event — but no single test asserts the whole route from
a postponement to the Detail Screen's overlap message.

Its natural home is `tests/e2e/test_timeline_and_conflict_proof.py`, which is **one of the
files currently red** from the expired hardcoded fixtures documented in this run's first test
report (9 of the 17 failures are in that file). A new test added there today would be buried
in a failing suite and could not be seen to pass, so it would prove nothing.

**Recommendation:** this test lands with the time-bomb fix, in a green suite, where a failure
would mean something. Recorded here so the gap is not lost — decided with the user at the
checkpoint rather than quietly skipped.

## Deviations

1. **Two existing mockups were edited**, which is the only time this run has modified mockup
   files it did not create. Both edits are purely additive — `FR-58` stays, `FR-55` is
   appended with its reason — and each header carries an explicit "do not strip this tag as a
   duplicate" note, because a later tidy-up would reopen the matrix gap exactly as it was.
2. **`EXPERIENCE.md` rows 8 and 13 were modified**, beyond the plan's "add a new row". The
   acknowledgment the matrix found missing belongs *on the rows describing the shared
   surface*, not only on a new row describing a new one.
3. **One acceptance criterion is partially met and says so** rather than being marked green.

---

# Test Report: Regenerate the matrix, retire the findings that are no longer true

*(work item: `matrix-regeneration-and-ledger`)*

## Results

| Check | Result |
|---|---|
| `TRACEABILITY.md` regenerated | **253 lines**, overwriting the 2026-09-08 version |
| Section A main table | **45 rows** — every MVP FR, none grouped or skipped |
| Section A counts | **35 FULL · 1 PARTIAL · 0 MISSING · 9 N/A** |
| Section B | **45 FULL · 0 PARTIAL · 0 MISSING** |
| Amendment Ledger | 13 rows; **6 inconsistent, all pre-existing** |
| `.memlog.md` | created with header + one scan line |
| Structure validated | both tables complete against the MVP set, column counts uniform |
| Tests | none — this item produces documentation |

## Acceptance Criteria

| Criterion | Status |
|---|---|
| `doc-trace` invoked explicitly; matrix regenerated from its output | met |
| Section A reports **36 FULL · 0 PARTIAL · 0 MISSING · 9 N/A** | **NOT MET — 35 FULL · 1 PARTIAL. Reported, not papered over.** See below. |
| Section B no longer reports an FR-32/FR-33 gap; names AD-21 | met — 45 FULL, 0 gaps |
| Amendment Ledger A-8 row consistent across PRD, UX **and** Architecture | met |
| Remaining "No" rows re-checked and either fixed or **recorded as accepted with a reason** | met — split into two kinds; see below |
| Epic/Story section reflects reality | met |
| New generation date; names what it describes | met |
| The four FRs spot-checked as FULL | met |

## The target was missed by one, and the reason matters

The work item set **36 FULL · 0 PARTIAL** and stated that a shortfall must be *"reported
rather than papered over — a matrix edited to show the number we wanted is worse than the
stale one, because it looks current."*

The result is **35 FULL · 1 PARTIAL**. The missing one is **FR-16 Source Reliability Score**,
and it is **a correction of a September mis-score, not a regression**:

- September scored FR-16 `FULL` on the evidence *"Reliability dots; `settings-sources-desktop.html`"*.
- `FR-16` is cited **nowhere** — 0 hits in DESIGN.md, 0 in EXPERIENCE.md, 0 across all 50 mockups.
- `doc-trace`'s own rule 3: a plausible-but-unnamed component with no direct FR tag *"is **PARTIAL (inferred only)** — never FULL."*

So the reliability dots are designed; nothing says they are FR-16's design. The previous
matrix applied its own rule inconsistently — it correctly rated FR-20, FR-28 and FR-55
PARTIAL on exactly this basis while rating FR-16 FULL on the same kind of evidence.

**FR-16 was deliberately not closed in this pass**, though one line would do it. Editing a
document to improve the score in the same pass that measures it is how a matrix stops being
trustworthy. It is recorded as open item 1.

## Four stale findings retired with evidence

1. **The previous matrix's "single highest-value finding" was false.** It claimed Architecture
   had no Capability-Map row for FR-32/FR-33 and that *"the word 'Amendment' appears nowhere
   in `ARCHITECTURE-SPINE.md`"*. `AD-21` binds both FRs and cites A-8 by name; the Capability
   Map has a dedicated row for each; "Amendment" appears at lines 11, 218 and 282.
2. **The Epic/Story line** (*"none found yet — expected pre-epics"*) predated all FIRE work.
3. **The mockup count** — September scanned "32 files"; there are 50, in three directories.
4. **FR-16's FULL rating**, above.

The retirements are written into the document rather than left to disappear in a re-scan,
because a finding that was once claimed and is now wrong is itself worth recording.

## Three errors found in the Surface Coverage Map

Auditing the whole FR column — recommended by the FR-28 and FR-49 reviews after two errors
turned up by accident — found a **third**:

| Row | Error | Found by |
|---|---|---|
| 9 | Named `empty-pulse-digest-desktop.html`, a file that **does not exist** | checking every filename against `ls` |
| 10 | Claimed FR-49; file has zero collection content | FR-49 item |
| 11 | Reads as FR-28; is tagged `UJ-5` | FR-28 item |

Three errors in ~24 rows. The audit was worth running, and the recommendation to run it
rather than fix only the rows this run happened to touch was correct.

## Deviations

1. **The headline acceptance criterion was not met**, and the report says so in its own
   summary table rather than in a footnote.
2. **`prd.md` was modified** — the A-23 amendment entry. The plan listed this as conditional
   on the checkpoint decision, and the decision was to propagate.
3. **One new open item was found that has nothing to do with traceability**: `DESIGN.md`'s
   YAML frontmatter does not parse, because Amendment A-22 (2026-11-10) put unescaped `"`
   inside a double-quoted scalar. Verified against a pre-edit backup that this **predates
   this run**. Recorded as open item 5, not fixed — it deserves its own change.
