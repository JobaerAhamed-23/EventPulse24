---
run: run-eventpulse24-028
work_item: duplicate-file-cleanup
intent: traceability-reconciliation
mode: confirm
checkpoint: plan-approval
approved_at: 2026-11-12T04:52:00Z
---

# Implementation Plan: Clear 1,323 filesystem conflict copies out of the tree

## Approach

The classification the work item demanded is **already done**, read-only, before this
checkpoint — because the deletion cannot be judged safe without it. The result removes
essentially all of the risk the work item was written to guard against.

**The 1,323 files split cleanly in two:**

| Group | Count | What it is |
|---|---|---|
| Inside `__pycache__/` | **1,117** | Compiled bytecode. `.gitignore:7` already ignores `__pycache__/`, so these were never tracked and are regenerated on next import. |
| Real source files | **206** | `.py`, `.tsx`, `.ts`, `.mjs` — plus 5 more under `.specs-fire/` and `docs/`, **211** in total. |

**All 211 source duplicates are byte-identical (SHA-256) to their originals, and all 211
originals are git-tracked.** The classification found:

- `identical`: **211**
- `divergent`: **0** — no copy holds content found nowhere else
- `duplicate newer than original`: **0** — the sync never wrote the real edit into a copy
- `no original found`: **0** — no orphans

So the stop-condition in the work item's acceptance criteria — *"any file classified
divergent stops the item and is reported, not deleted"* — **does not fire**. Nothing is at
risk. This is now a mechanical deletion with a verification pass after it.

That makes the plan: delete both groups, add the ignore rule, then prove by running the
suites that nothing was resolving an import through a duplicate.

## Files to Create

| File | Purpose |
|------|---------|
| (none) | |

## Files to Modify

| File | Changes |
|------|---------|
| `.gitignore` | Add a rule matching `* 2.*` conflict copies so they can never enter history |

## Files to Delete

| Group | Count | Basis |
|---|---|---|
| `__pycache__/**/* 2.*` under `backend/`, `frontend/` | 1,117 | Regenerable bytecode, already gitignored |
| Source `* 2.*` under `backend/`, `frontend/`, `.specs-fire/`, `docs/` | 211 | SHA-256 identical to a git-tracked original |

Notable members, all verified identical: `apps/personalization/migrations/0013_eventreport 2.py`
(the migration-loader hazard that motivated this item), `apps/personalization/collections_api 2.py`,
`adapters/revalidation/fake 2.py`, `components/collections/collection-manager 2.tsx`, and the
four FIRE run records under `.specs-fire/runs/run-eventpulse24-027/`.

Explicitly **out of scope**: `.puku-cli/worktrees/` holds zero matches, so the question of
whether that worktree is live never arises. `node_modules/` and `.next/` are excluded.

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend` suite (existing) | Proves no import resolved through a duplicate module |
| `python manage.py makemigrations --check --dry-run` | Proves the migration loader is clean without `0013_eventreport 2.py` |
| `frontend` typecheck + build (existing) | Proves no TS/TSX import resolved through a duplicate |

No new tests are written for this item. It deletes files that are byte-identical to files
that remain; the correct proof is that the existing suites still pass, not a new assertion.

## Technical Details

The classification script lives at
`/private/tmp/claude-501/-Users-jobaer-Documents-EventPulse24/f0188aed-a587-41fe-8d84-8f3cfda9060e/scratchpad/classify_dups.py`
with its output at
`/private/tmp/claude-501/-Users-jobaer-Documents-EventPulse24/f0188aed-a587-41fe-8d84-8f3cfda9060e/scratchpad/dup_classification.json`.
Per the work item, it stays in the scratchpad and is **not** committed as repo tooling — it
is a one-shot audit, not a maintained check. If duplicates recur, the `.gitignore` rule is
the control, not a script.

The `.gitignore` pattern needs care: it must catch `collections_api 2.py` and
`fake 2.cpython-313.pyc` (a space-2-dot anywhere in the basename) without catching a
legitimate filename that merely contains a space and a 2. A pattern anchored on `" 2."` is
right; the repo currently has no legitimate file matching it, which the deletion itself
confirms.

Order matters: delete, then run the suites. Running them first proves nothing, since the
duplicates are inert until something imports one.

The `.pyc` deletion is cosmetic — those files are already invisible to git. They are removed
in the same pass only so that `find . -name "* 2.*"` returns clean, which is the acceptance
criterion as written.

---
*Plan approved at checkpoint. Execution follows.*

---

## Work Item: fr-20-reminder-defaults

*mode: confirm · checkpoint: plan-approval · approved_at: pending*

### Approach

**The verification half is almost entirely done already, and the discovery is that FR-20 was
never really "inferred" in code — only in design.** The backend names the requirement
repeatedly and deliberately. `apps/delivery/services/reminder_plans.py` opens by listing its
three commands against their FRs, including *"`remove_all_reminders` — FR-9/FR-20: an empty
plan is a valid state, not an error"*, and `attach_default_plan`'s docstring cites the
traceability gap **by name**:

> *"Until `/settings/reminders` existed the constant **was** the default, with no way to
> change it — which is why TRACEABILITY.md could only find FR-20 'by adjacency'."*

So someone read the matrix and closed the code side without closing the design side. This
item closes the design side and fills the one real test gap.

**Existing coverage, verified by reading the tests, not by grepping for the tag:**

| PRD consequence | Covered by |
|---|---|
| New Personal Event has 1d + 1hr | `test_personal_events.py:126`, `test_personal_events_api.py:195`, `test_reminder_plans.py:39` |
| User can remove all reminders | `test_removing_all_reminders_leaves_an_empty_plan`, `test_removing_all_reminders_keeps_the_plan_row` |
| Removal cancels pending sends | `test_scheduled_sends.py::test_a_plan_edited_to_zero_slots_cancels_every_send` — **but for `saved_event`, not `personal_event`** |
| Default not re-applied on edit | `test_personal_events.py:340` |
| Imported calendar events get the same default | `test_calendar_sync.py` |

**The one genuine test gap** is the last-mile of FR-20's second consequence on FR-20's own
target kind: removal is proven to cancel sends for a *saved* event, and proven to empty the
plan for a *personal* event, but nothing proves removal on a **personal event** leaves no
`ScheduledSend`. That is a one-test gap, not a feature gap.

**Two findings the design must record rather than silently inherit:**

1. **The Personal Event creation form never mentions reminders.**
   `components/sheets/personal-event-form.tsx` contains zero occurrences of "reminder". The
   1d + 1hr plan is attached server-side with nothing in the creation UI saying so. The PRD
   says the user *"can edit"*, not that creation must disclose — so this is defensible, but
   it is exactly the kind of decision that, left undocumented, becomes a bug report. The
   design states where the default first becomes visible.
2. **`/settings/reminders` makes the default user-configurable, which is beyond FR-20's text.**
   FR-20 says the default *is* 1d + 1hr. The shipped behaviour reads the user's
   `NOTIFICATION_PREFERENCE.default_reminder_slots` and falls back to the constant. That is a
   superset of the requirement and a better product, but the PRD does not describe it. Flagged
   for the matrix item; it may warrant a PRD amendment rather than a silent divergence.

### Files to Create

| File | Purpose |
|------|---------|
| `mockups/personal-event-reminders-desktop.html` | Self-tagged `FR-20`. Three states: the default as created, an edited plan, the deliberately empty plan. |

### Files to Modify

| File | Changes |
|------|---------|
| `DESIGN.md` | Named component section citing `FR-20`: how the personal-event case relates to FR-9's `Input.ReminderSlot`, and the empty state's treatment |
| `EXPERIENCE.md` | Flow entry for the personal-event reminder path, citing `FR-20`, naming both routes (`/events/[id]/reminders`, `/settings/reminders`) |
| `backend/tests/delivery/test_scheduled_sends.py` | Add the `personal_event` variant of the zero-slots cancellation test |

### Tests

| Test File | Coverage |
|-----------|----------|
| `tests/delivery/test_scheduled_sends.py` | New: removing all reminders on a **personal event** cancels every pending send |

No other tests are written. The remaining consequences are already covered by named tests;
duplicating them under an `FR-20` alias would inflate the suite without adding a proof.
Where an existing test proves an FR-20 consequence without naming it, a comment citing FR-20
is added so the requirement is greppable — the acceptance criterion's intent — rather than a
second copy of the test.

### Technical Details

House style for the mockup, from `reminder-picker-desktop.html` (294 lines, the nearest
neighbour): `<!doctype html>`, `<html lang="en" data-theme="dark">`, the `:root` token block
verbatim, the A-8 shell with 6-route sidenav, brand-only topbar, Google Fonts preconnect for
Inter / JetBrains Mono / Source Serif 4, and a header comment carrying the FR tag plus any
amendment lineage. The crumb replaces a back affordance.

The empty state is the one worth drawing carefully. It must read as *a choice the user made*,
not as a broken or unset control — mirroring `remove_all_reminders`'s own comment, *"'no
reminders' is a state the user chose, not the absence of a plan"*. That is a copy and
affordance decision, and it is the thing FR-20's second consequence actually protects.

`reminder-states.tsx` covers only `missing` and `unavailable`; neither is the empty plan, so
the empty state is a content state, not an error state. The mockup should not borrow their
treatment.

### Risk to flag early

`tests/delivery/test_reminder_plan_api.py` currently has **two failing tests** from expired
hardcoded fixture dates (see this run's test report). They are pre-existing and unrelated, but
they sit in the file closest to this item's subject. The new test must be written with a
relative or explicitly-passed `now` — every service here takes `now` as a parameter precisely
so this is possible — or it will become the next time bomb.

---

## Work Item: fr-28-share-affordance

*mode: confirm · checkpoint: plan-approval · approved_at: pending*

### Approach

Same shape as FR-20: the code is thorough and self-aware, the design is absent.
`components/share/share-control.tsx` opens by naming itself *"FR-28's sender side"* and
cites `EXPERIENCE.md §964` — the very one-line footnote the matrix called insufficient. It
already handles everything the work item worried about:

- **Mounted on both surfaces FR-28 names** — `components/digest/pulse-card.tsx:336`
  (`weight="card"`) and `components/detail/detail-actions.tsx:462` (`weight="secondary"`).
- **Web Share API with a clipboard fallback**, and the control distinguishes three outcomes
  because *"'I copied it' and 'I shared it' are different claims"*.
- **A cancelled share sheet says nothing**, because dismissing is a choice, not an error.
- **Shares `/events/{slug}`, never `/events/{uuid}`** — the docstring records that the uuid
  bug *existed here before this component did*, when the Detail Screen shared
  `window.location.href`.

**Three open questions from the work item, all resolved by reading rather than guessing:**

| Question | Answer |
|---|---|
| Does `share_precise_location` gate the share metadata? | **No.** `apps/personalization/services/export_source.py:38` is its only consumer — it gates FR-52 export, not sharing. The work item's speculation was wrong; no second state to design. |
| Does the share control belong on the Timeline event-block? | **No**, and it is correctly absent. The Timeline is read-only per Amendment A-8; `components/timeline/` has no `ShareControl`. The design will say so rather than leave it open. |
| Is `share-link-desktop.html` repurposed? | **No.** It keeps its `UJ-5` tag. It is the *recipient's* landing page; this item designs the *sender's* affordance, which is the other end. |

**The one real gap is a test, and it is the exact one the work item predicted.** FR-28's
second consequence names three Open Graph fields — *"title, description, image"*.
`app/events/[id]/page.tsx:158–176` sets all three (on `metadata`, `openGraph` **and**
`twitter`, with the description truncated to 200 chars). The test file asserts
`openGraph.title`, `openGraph.url` and `openGraph.images` — **and never `description`**.

That is precisely the failure the work item named: *"an unfurl with a blank image still
'works'"*. The same is true of a blank description, and nothing would catch it.

### Files to Create

| File | Purpose |
|------|---------|
| `mockups/share-affordance-desktop.html` | Self-tagged `FR-28`. The sender's control on **both** surfaces, in its resting, shared, copied and failed states, plus the no-Web-Share fallback. |

### Files to Modify

| File | Changes |
|------|---------|
| `DESIGN.md` | `component.control.share` entry citing `FR-28`: two weights, four outcome states, the live-region rule |
| `EXPERIENCE.md` | Coverage row for the sender's affordance; annotate row 11 so `share-link-desktop.html`'s `UJ-5` scope is explicit rather than merely untagged for FR-28 |
| `frontend/app/events/[id]/page.branch.test.tsx` | Assert `openGraph.description` and `twitter.description` are present and non-empty |

### Tests

| Test File | Coverage |
|-----------|----------|
| `app/events/[id]/page.branch.test.tsx` | New: the Open Graph **description** is populated, not an empty default — FR-28's untested third field |

The other FR-28 consequence — *"a share-link opens the public Event URL with a 'Save to
Pulse' CTA"* — is **already covered** by `tests/public-crawl-proof.test.tsx:284` ("shows the
Save to Pulse call to action") and `app/events/[id]/page.test.tsx:651`. Not duplicated.

AD-12 (*the public surface never depends on a session*) is already pinned by the existing
test *"reads no session to build the metadata"*, which exists specifically to stop
`generateMetadata` opting the route out of static generation. Not duplicated either.

### Technical Details

**`frontend/AGENTS.md` applies to the test change**: *"This is NOT the Next.js you know …
Read the relevant guide in `node_modules/next/dist/docs/` before writing any code."* The
change touches `generateMetadata`'s typed `Metadata` return, so the metadata guide gets read
before the assertion is written. The existing Twitter-card test already shows one version
quirk worth respecting — it notes `card` *"is only on some members of Next's `Twitter`
union"* and narrows the type rather than reaching through it.

Mockup house style as before, from `reminder-picker-desktop.html`. This mockup differs from
FR-20's in that it must show the control **in context on two different surfaces at two
different weights**, not one surface in three states — so the composition is a Pulse Card
with its card-weight control beside a Detail Screen action row with its secondary-weight one.

The four outcome states are the substance, because they are where the control makes claims:
`Shared.` / `Link copied.` / `Couldn't copy the link. Try again.` / and silence after a
cancelled sheet. The design must record that **silence is a state**, since a designer reading
only the mockup would otherwise add a "Share cancelled" toast and contradict the code.

### Risk to flag early

The mockup will show a confirmation line under the button. That line is a **bare
`aria-live="polite"` region and deliberately not a `role="status"`** — the docstring explains
that the digest page and the Detail Screen's action row already own the one `role="status"`
each, and a second would make *"which one is the page talking?"* unanswerable. A future
implementer reading a mockup that merely *looks* like a toast could reasonably reach for
`role="status"` and regress that. The DESIGN.md entry states the rule explicitly.

---

## Work Item: fr-49-saved-collections

*mode: confirm · checkpoint: plan-approval · approved_at: pending*

### Approach

FR-49 is the only one of the four the matrix rated **MISSING** rather than PARTIAL, and it
is the one where the code most explicitly asks for this work.
`components/collections/collection-manager.tsx` opens:

> *"**This surface has no approved design, and that is a fact about the build rather than an
> oversight.** EXPERIENCE.md's coverage table claims `settings-desktop.html` covers FR-49;
> TRACEABILITY.md checked and found 'the mockup contains zero collection content'. So it is
> assembled from the design system's existing vocabulary … and invents no new visual
> language. **If it ever grows past a modest management UI, that is the signal to stop and
> get a design pass.**"*

This item is that design pass, recording what was assembled.

**The false coverage claim is confirmed and precisely bounded.** `EXPERIENCE.md:1236` claims
`settings-desktop.html` covers *"FR-7 / FR-12 / FR-48 / FR-49 / FR-51 / FR-52"*. Counting
occurrences in that file:

| Claim | Evidence in the file | Verdict |
|---|---|---|
| FR-7 digest time | `digest time` ×1, `theme` ×5 | holds |
| FR-12 notifications / quiet hours | `quiet` ×10 | holds |
| FR-48 Pro tier | `Pro` ×7, `plan` ×5 | holds |
| **FR-49 collections** | **`collection` ×0** | **false** |
| FR-51 per-day quiet hours | quiet-hours content present; the Pro variant has its own mockup (row 16) | holds |
| FR-52 export | `export` ×4 | holds |

Exactly one of six claims is wrong. The correction is surgical — strike FR-49 from row 10 —
not a rewrite of the row.

**Verification is already complete, and more thorough than the work item assumed.** All
three of FR-49's PRD consequences have named tests:

| PRD consequence | Covered by |
|---|---|
| Pro user saves 10+ in one day, no soft-wall | `test_save_cap.py:318` — docstring literally reads *"FR-49's own testable consequence"* |
| Create, rename, delete **and reorder** | `test_collections_api.py` — 3 reorder tests among ~30 |
| Free user at the cap sees a **calm in-app prompt, no modal** | `test_the_refusal_carries_no_modal_shaped_field` (`:288`) |

**The reorder regression test the work item asked for already exists, in the right form.**
`test_reorder_takes_the_whole_list_in_one_request` does a `PUT /order` and asserts `200`
plus the new positions. If `/order` were ever registered after `/{collection_id}`, that call
would be matched by the rename route and fail on UUID parsing — so the trap is pinned by
*behaviour* rather than by asserting a registration order, which is the better test. The
source comment's claim that *"the tests caught exactly that, five times over"* is accurate.

So no new backend test is written. Writing one would duplicate a passing proof.

**The open question in the work item is answered, and the answer is "no drag".** The item
worried about the drag affordance under the no-component-kit, no-animation-library
constraint. There is no drag: reorder is **move up / move down buttons**, *"keyboard-operable
with no pointer, needs no library, needs no motion — the product has exactly one transition
and `styles/motion.test.ts` fails the suite on any other animation."* That is the decision,
it is already correct, and the design records it rather than re-opening it.

### Files to Create

| File | Purpose |
|------|---------|
| `mockups/collections-desktop.html` | Self-tagged `FR-49`. All four PRD verbs visible — create, rename, **reorder**, delete — plus a collection's contents, assign/unassign, the delete-confirms-in-place state, and the free-tier inline cap prompt. |

### Files to Modify

| File | Changes |
|------|---------|
| `DESIGN.md` | `component.manager.collections` citing `FR-49`: move-up/down reorder, in-place delete confirmation, the assembled-from-existing-vocabulary rule |
| `EXPERIENCE.md` | New coverage row; **strike FR-49 from row 10** with the reason inline |

### Tests

None. Every FR-49 consequence already has a named, passing test, and the reorder route trap
is already pinned behaviourally. The acceptance criteria are met by existing tests, cited by
name in the test report rather than duplicated.

### Technical Details

The mockup must show **four things a reader would otherwise get wrong**:

1. **Reorder is buttons, not drag.** A mockup showing a grab handle would licence a drag
   implementation, which would need a library and motion the product forbids.
2. **Delete confirms in place, and the copy names what survives.** *"'Delete' sitting above a
   list of events reads as deleting the events, so the confirmation names the truth: the
   saves stay saved."* No overlay, no focus trap — a grouping being removed does not warrant
   the weight Amendment A-16 specifies for deleting an account.
3. **The tier gate is on `create` and `assign` only.** Rename, reorder, delete, unassign and
   read are open on every tier, so *"a lapsed Pro user keeps using what they have at its
   current size."* A mockup that locked the whole surface behind Pro would be wrong, and the
   backend has 7 tests pinning the lapsed-user paths.
4. **The cap prompt is inline and carries no modal-shaped field.** The server's refusal is
   `{cap, upgrade_hint}` with *"no `modal`, no `title`"* — `components/upgrade/upgrade-prompt.tsx`
   renders the server's `upgrade_hint` as it arrived.

House style as before. The empty state reuses `component.emptystate.quiet` — this one *is* a
found absence (no collections yet), unlike FR-20's chosen-empty, so the existing component is
correct here and a new one would be wrong.

### Risk to flag early

This mockup is the first to render a surface built **without** a design, rather than one
built from a mockup. The risk is backwards from the usual: the design must describe what
exists, and any improvement I notice while drawing is a *change request*, not a correction to
fold in silently. Anything that looks wrong gets flagged at the checkpoint, not fixed in the
mockup — otherwise the mockup documents a product that does not exist, which is the exact
failure mode this intent is repairing.

---

## Work Item: fr-55-conflict-on-state-change

*mode: confirm · checkpoint: plan-approval · approved_at: pending*

### Approach

FR-55 had **nothing tagged anywhere** — not a mockup, not a DESIGN.md component, not an
EXPERIENCE.md flow. The matrix's exact complaint was *"only overlap with FR-58's conflict UI,
**with no documented acknowledgment it also serves this trigger**"*.

That phrasing is precise, and investigating it confirms the matrix was right about the
*documentation* and that the **reuse itself is correct**:

- A postponement that creates an overlap writes a `CONFLICT_PAIR` row like any other
  (`services/saved_events.py:340`: *"one that no longer overlaps closes, one that still
  overlaps stays, and a new overlap creates a…"*).
- AD-21 makes that one record the single source for every surface: *"The Pulse Card
  indicator, the Timeline event-block indicator and `/conflicts` all read the same rows, so
  the indicator is symmetric by construction."*

So FR-55 and FR-58 **share a surface because they share a record**. That is architecture, not
coincidence — and it has simply never been written down. This item writes it down and tags
FR-58's mockups with the second trigger they already serve.

**FR-55's PRD copy requirement is already met, better than the matrix implies.** FR-55 asks
for a calm *"this overlaps with [other event]"* message. `conflict-resolution.tsx:112` has a
kind-keyed heading — *"This overlaps with another event."* — and `:162` follows it with the
naming line: ``It overlaps "${other.name}" on your calendar. Choose how to handle it.`` The
bracketed "[other event]" of the PRD is the body line, not the heading. No divergence.

**Three of four consequences already have named tests:**

| PRD consequence | Covered by |
|---|---|
| Cancelled, no saved personal event → notified, removed from digest | `test_digest_candidates.py:318` — *"FR-55: 'event is removed from the digest'"* |
| Cancelled conflicting with a personal event → **personal event preserved** | `test_saved_events.py:553` — *"a cancelled public event never auto-cancels a personal event"* |
| Per-event mute of state-change notices | `test_the_detail_reports_the_mute_state` (`:907`) |
| Postponed conflicting → notified + overlap message on Detail | the sheet exists and names the other event; the state-change→sheet path is **not** directly asserted |

**The one real test gap is the independence of the mute and the notice.** `make_mute` appears
at exactly two places in `test_event_detail_api.py` — the mute-state test and the cross-user
test. **No test puts a mute and a notice on the same event.** That is precisely the invariant
the code goes out of its way to insist on:

> `detail_read.py:114` — *"They are two more independent facts: a notice and a mute are
> different things, and a client must not read 'muted' as 'there is nothing to say'."*
> `schemas.py:982` — *"`False` means 'not muted'… a client must not read 'muted' as…"*

Two docstrings defending an invariant that nothing proves. Collapsing them is the specific
bug those comments exist to prevent, and it would ship silently.

### Files to Create

| File | Purpose |
|------|---------|
| `mockups/event-state-conflict-desktop.html` | Self-tagged `FR-55`. All three triggers — cancelled-no-conflict, cancelled-with-personal-conflict, postponed-into-conflict — plus the per-event mute control and the muted-with-notice state. |

### Files to Modify

| File | Changes |
|------|---------|
| `DESIGN.md` | `component.control.notice-mute` citing `FR-55`; record the FR-58 surface reuse and the `cleared_by_state_change` rule |
| `EXPERIENCE.md` | New coverage row; **add `FR-55` to rows 8 and 13** (the FR-58 conflict surfaces), which is the "documented acknowledgment" the matrix found missing |
| `mockups/conflict-prompt-desktop.html` | Add `FR-55` to its header comment beside `FR-58` — the second trigger it already serves |
| `backend/tests/personalization/test_event_detail_api.py` | Add the mute-and-notice independence test |

### Tests

| Test File | Coverage |
|-----------|----------|
| `tests/personalization/test_event_detail_api.py` | New: a **muted** event still reports its notice — the two facts are independent and must not collapse |

Not duplicating the three already-covered consequences. The postponed-into-conflict path is
covered in pieces (the pair is written by `saved_events`, the sheet renders from it); an
end-to-end assertion of that specific route belongs with the e2e conflict proofs, which are
currently **failing for unrelated time-bomb reasons** — adding to that file now would bury a
new test in a red suite. Flagged rather than forced.

### Technical Details

**AD-21's distinction is the thing the design must carry**: when propagation removes an
overlap — a cancel, or a postpone past the partner — *"the pair closes as
`cleared_by_state_change`, which is **not** a user resolution"*, and a resolved pair is
immutable and never re-prompted. `models.py:357` has that value in the enum and `:462` has a
check constraint (`conflict_pair_resolution_kind_ck`) pinning it.

So the mockup must show that a conflict which **disappears because the event was cancelled**
looks different from one the user **resolved** — and must not re-prompt. A designer who
treated them the same would produce a UI that congratulates the user for a decision they
never made.

**The mute is `delivery`-owned** (`apps/delivery/services/mutes.py`: `mute_event_notices`,
`unmute_event_notices`, `is_muted`, `muted_event_ids`) while the notice is read through
`personalization`'s detail read. Two apps, two facts, one screen — which is exactly why the
independence is worth a test.

House style as before.

### Risk to flag early

This item adds `FR-55` tags to **existing** FR-58 mockups. That edits files this run did not
create, and the edit is deliberately additive — `FR-58` stays, `FR-55` is appended with the
reason. If a later reader strips the second tag as a duplicate, the matrix gap reopens
exactly as it was. The reason goes in the header comment, not just the tag.

---

## Work Item: matrix-regeneration-and-ledger

*mode: confirm · checkpoint: plan-approval · approved_at: pending*

### Approach

Invoke `doc-trace` explicitly (it is `disable-model-invocation: true`), regenerate
`TRACEABILITY.md` from its output, and settle the three things the previous five items
carried forward.

**The mockup inventory has changed materially since the September scan**, which matters
because `doc-trace` instructs cross-checking claimed counts against `ls`:

| | Sep 2026 matrix | Now |
|---|---|---|
| Files scanned | "all 32 files (26 desktop + 6 mobile)" | **50 HTML** — 39 desktop, 6 mobile, 5 in `light-archive/` |

The `light-archive/` subdirectory is not mentioned anywhere in the old matrix. Whether its
5 files count as evidence is a judgement the regeneration must make and state, not inherit.

**A scanning discipline the old matrix may have got wrong.** Reading each mockup's *full*
leading comment rather than its first few lines surfaces tags that a shallow read misses —
`onboarding-skip-all-state-desktop.html` carries **FR-10**, which appears nowhere in the old
matrix's evidence column. The regeneration reads whole header comments, and any FR whose
status improves purely because of better scanning gets that said plainly rather than being
quietly upgraded.

**Three carried-forward items, all from this run's own reviews:**

1. **Amendment A-23** — claimed by `EXPERIENCE.md` rows 21–24, absent from `DESIGN.md` and
   the PRD despite nine new `DESIGN.md` component entries made under it. Flagged in all four
   design-item reviews. **This needs a decision, not a default** — see the checkpoint.
2. **The Surface Coverage Map FR column** — two confirmed errors (row 10's false FR-49 claim,
   row 11's `UJ-5`/FR-28 mis-read). Two in ~20 rows is a defect rate worth measuring, so the
   whole column gets audited rather than only the rows this run touched.
3. **The postponed-into-conflict e2e test** — deferred to the time-bomb fix, recorded as an
   open item rather than silently dropped.

**The stale findings to retire, with evidence:**

- The old matrix's *"single highest-value finding"* — that Architecture never accounted for
  FR-32/FR-33 after Amendment A-8 — is **false**. `AD-21` exists, its `**Binds:**` line reads
  `FR-32, FR-33, FR-58, FR-53–55; PRD Amendment A-8`, and Capability-Map rows 457–458 cover
  both. Its claim that *"the word 'Amendment' appears nowhere in `ARCHITECTURE-SPINE.md`"* is
  contradicted by lines 11, 218 and 282.
- The Epic/Story section still reads *"none found yet — expected pre-epics"*, written before
  28 FIRE runs existed.

### Files to Modify

| File | Changes |
|------|---------|
| `TRACEABILITY.md` | Regenerated from `doc-trace`, overwriting |
| `traceability/.memlog.md` | Append one scan line (create with header if absent) |
| `EXPERIENCE.md` | Any further FR-column corrections the audit finds |
| `DESIGN.md` / `prd.md` | **Only if** the A-23 decision requires it — see checkpoint |

### Tests

None. This item produces documentation. Its correctness check is that `doc-trace`'s own
output reaches the target counts, and the acceptance criterion is explicit that a shortfall
is **reported rather than papered over**.

### Technical Details

Target for Section A is **36 FULL · 0 PARTIAL · 0 MISSING · 9 N/A** across the 45 MVP FRs —
the old 32 FULL plus the four this run designed. If the regeneration does not reach that, the
shortfall is reported and the reason named. A matrix hand-edited to the number we wanted
would be worse than the stale one it replaces, because it would *look* current.

The four FRs this run closed should now score FULL from tier-1 evidence (self-tagged mockup
headers): FR-20 (`personal-event-reminders-desktop`), FR-28 (`share-affordance-desktop`),
FR-49 (`collections-desktop`), FR-55 (`event-state-conflict-desktop` **plus** the two
re-tagged FR-58 mockups).

### Risk to flag early

**This run has created one ledger inconsistency while closing four coverage gaps**, and the
regenerated Amendment Ledger will print it. That is the honest outcome and it is the right
one — but it is better to resolve A-23 deliberately now than to ship a matrix that reports
our own debt in its first row.
