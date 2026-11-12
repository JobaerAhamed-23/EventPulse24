---
run: run-eventpulse24-028
work_item: duplicate-file-cleanup
intent: traceability-reconciliation
---

# Code Review: Clear 1,323 filesystem conflict copies out of the tree

## Scope

This item wrote almost no code. Reviewable surface:

| File | Change |
|---|---|
| `.gitignore` | +5 lines (comment + one pattern) |
| `.env` | +9 lines, local gitignored config, placeholders copied from `.env.example` |
| 1,328 files | deleted |

No application code was created or modified. Nothing to review for architecture conformance,
security or coding standards in the usual sense.

## Finding 1 — the ignore pattern over-matches legitimate filenames `[needs decision]`

**Severity: medium. Not auto-fixed — this is a behavioural change and the call is the user's.**

The committed pattern is `*\ 2.*`, which ignores *any* file whose name contains a space, a
`2` and a dot. Probed against plausible names:

| Candidate | Ignored? | Verdict |
|---|---|---|
| `backend/app 2.py` | **yes** | correct — this is the target |
| `docs/Draft 2.md` | **yes** | **false positive** |
| `docs/Phase 2.md` | **yes** | **false positive** |
| `docs/notes v2.md` | no | correct |

`Phase 2.md` is not a hypothetical in a repo that carries `_bmad-output/planning-artifacts/`
full of hand-written planning documents. The failure mode is quiet: the file is created,
never staged, and its absence is noticed later rather than at the time.

**The tension is real and a plain glob cannot resolve it.** Narrowing the rule to code
extensions (`* 2.py`, `* 2.ts`, `* 2.tsx`, `* 2.mjs`, `* 2.pyc`) removes every false positive
— but four of the duplicates actually deleted in this run were **Markdown**:
`.specs-fire/runs/run-eventpulse24-027/{run,walkthrough,review-report,test-report} 2.md`. A
code-only rule would have let those through, and those are FIRE's own records.

Three ways out, none free:

1. **Keep the broad pattern.** Catches everything, risks silently ignoring `Phase 2.md`.
2. **Narrow to code extensions.** Zero false positives, misses Markdown conflict copies.
3. **Scope by directory** — broad inside `backend/`, `frontend/` and `.specs-fire/`, absent in
   `docs/` and `_bmad-output/` where prose lives and conflict copies are least likely to
   matter. More lines, but it matches where the risk actually sits.

**Decision (user, 2026-11-12): keep the broad pattern (option 1).** Over-ignoring is
recoverable by `git add -f`, whereas under-ignoring lets a duplicate migration back into the
tree, which is the hazard this item exists to remove. The false-positive risk on
`Phase 2.md`-style names is accepted and recorded here so that a later "why wasn't my file
committed?" has an answer.

## Finding 2 — the `.gitignore` rule treats a symptom `[informational]`

The conflict copies come from a syncing file system writing `name 2.ext` on collision. The
ignore rule stops them polluting git; it does not stop them appearing on disk, where the real
hazard lives — Django's migration loader walks the directory, and git has no say in that.

Nothing to fix in this repo. Worth knowing that if the sync keeps running, `* 2.py` files will
keep materialising in `migrations/` and will simply be invisible to `git status` from now on,
which is marginally *more* dangerous than before. Excluding the project directory from the
syncing tool is the actual fix and is outside this repo.

## Finding 3 — `.env` drift is a repeating defect `[informational]`

The backend could not start because run 027 added two required settings to `config/env.py` and
to `.env.example`, but nothing updates a developer's existing `.env`. This will recur on every
future intent that adds a required setting, and the symptom — a pydantic `ValidationError` at
import time — looks alarming and unrelated to whatever the developer was doing.

`make doctor` exists in the Makefile. A check comparing the keys in `.env.example` against
`.env` and naming the missing ones would convert a confusing stack trace into one line. Not
done here; out of scope.

## Auto-fixes applied

None. The only mechanical candidate was the ignore pattern, and narrowing it changes
behaviour, so it is Finding 1 rather than a fix.

## Verdict

**Pass.** No code defects. One decision for the user (Finding 1), two observations recorded
for later (Findings 2 and 3).

---

# Code Review: FR-20 — design the reminder default, and prove you can clear it

## Scope

| File | Change |
|---|---|
| `mockups/personal-event-reminders-desktop.html` | created, 380 lines |
| `DESIGN.md` | +2 component entries, +1 Do's-and-Dont's row |
| `EXPERIENCE.md` | +1 coverage row |
| `backend/tests/delivery/test_scheduled_sends.py` | +1 test |

No application code. Review is of the design artifacts against the house style, and of the
one test against the suite's conventions.

## Finding 1 — the mockup stacks three states on one page `[accepted]`

`reminder-picker-desktop.html` and every other mockup in this directory render **one** state.
This file renders three, with mockup-only `.state-label` chrome (A / B / C) separating them.

That is a deliberate break from the house pattern, and the alternative is worse. FR-20's two
testable consequences are a value and its opposite — "inherits 1d + 1hr" and "can remove all
reminders" — and a single-state mockup can only show one of them. Splitting into three files
would triple the shell duplication for one requirement. The `.state-label` chrome is clearly
scaffolding rather than product UI, and the header comment says so.

Precedent exists: `export-request-modal-desktop.html` is described in EXPERIENCE.md as a
"3-state showcase". This follows it.

## Finding 2 — the empty state introduces a component rather than reusing one `[correct]`

`component.emptystate.chosen` is new, and the temptation was to reuse
`component.emptystate.quiet`. Reusing it would have been wrong, and the distinction is the
substance of FR-20's second consequence:

- `emptystate.quiet` — an absence **the system found** (no qualifying events in the digest).
- `ReminderStates` `missing` / `unavailable` — **failures** (404, read error).
- `emptystate.chosen` — a state **the user chose**.

The backend already holds this distinction and would have contradicted a reused component:
`remove_all_reminders` keeps the plan row with zero slots precisely because *"'no reminders'
is a state the user chose, not the absence of a plan"*, and `remove_plans_for_targets`
**deletes** rows for the genuinely-absent case. The design now matches the data model.

No new palette tokens, no new CSS variables — `{color.warm.personal}` is the existing FR-19
token, and every use is paired with a visible text label per WCAG 1.4.1.

## Finding 3 — the new test's assertion is weaker than it could be `[accepted]`

`assert pending_of(user).count() == 0` proves no **pending** send survives. It does not
distinguish a send that was *cancelled* from one that was *deleted*, and the two are
meaningfully different in a system with an append-only audit discipline.

Left as is, matching its sibling `test_a_plan_edited_to_zero_slots_cancels_every_send`
exactly. A stronger assertion here than in the test it is deliberately mirroring would be
inconsistent, and the cancellation-versus-deletion semantics are already pinned elsewhere in
the same file. Mirroring the sibling is the point: the two tests differ in exactly one
variable, the target kind.

## Finding 4 — `EXPERIENCE.md` row 21 claims Amendment A-23 `[needs confirmation at the matrix item]`

The new coverage row is labelled "(Amendment A-23)". A-22 is the highest amendment currently
in `DESIGN.md`, so A-23 is the next free number — but amendment IDs are a **cross-document
convention**: per the `doc-trace` skill, *"whenever a change gets an Amendment ID, that same
ID must appear in every doc the change actually touches."*

A-23 currently appears in `EXPERIENCE.md` only. Either it propagates to `DESIGN.md` and the
PRD, or the row should not claim an amendment ID at all. Deferred deliberately to
`matrix-regeneration-and-ledger`, which owns the Amendment Ledger and is the right place to
settle it — but it must not be forgotten there, or this item will have *created* a new
ledger inconsistency while closing a coverage gap.

## Auto-fixes applied

None.

## Verdict

**Pass**, with one item carried forward: Finding 4 must be resolved by
`matrix-regeneration-and-ledger`.

---

# Code Review: FR-28 — design the share action itself, not the page it lands on

## Scope

| File | Change |
|---|---|
| `mockups/share-affordance-desktop.html` | created |
| `DESIGN.md` | +2 component entries, +1 Do's-and-Dont's row |
| `EXPERIENCE.md` | +1 coverage row, 1 row corrected |
| `app/events/[id]/page.branch.test.tsx` | +3 tests |

## Finding 1 — the new tests assert exact strings from the fixture `[accepted]`

`expect(metadata.openGraph?.description).toBe("A short, opinionated panel on building
products that respect attention.")` couples the test to `publicPage()`'s fixture text. A
looser assertion (`toBeTruthy()`, or a length check) would not break when the fixture changes.

Kept exact, deliberately. `toBeTruthy()` would pass on the *fallback* string too — and the
whole point of the first test is that the **event's own** description reaches the tag, while
the second test proves the fallback fires only when it should. Two tests that both pass on
either branch would prove nothing about which branch ran. The fixture is local to the file
and changing it will fail the test loudly, which is the correct outcome.

## Finding 2 — the mockup documents behaviour that is invisible in a mockup `[correct, and the point]`

Three of the mockup's rules cannot be *seen*: that silence is a state, that the confirmation
is a bare `aria-live` region rather than `role="status"`, and that "Shared." and "Link
copied." must never collapse into one message.

A mockup that showed only the visible states would be actively harmful here — a reader would
see a line of text under a button, recognise a toast, and reach for `role="status"`, which
the component's own docstring explains at length would break the surface's single status
region. The prose panels earn their place for that reason, and the same three rules are
carried into `DESIGN.md` so they survive independently of the mockup.

## Finding 3 — `EXPERIENCE.md` row 11 was corrected, not just annotated `[flag]`

The plan said "annotate"; the change is a correction. Row 11's `UJ-5` scope is now stated
inline, with the reason.

This is the second row in this run found to be misleading about coverage (`FR-49`'s claim on
`settings-desktop.html` is the other, and is item 4's work). Two in one document is a
pattern, not a coincidence: the Surface Coverage Map's FR column has been maintained by hand
and has drifted. **Recommend `matrix-regeneration-and-ledger` audit the FR column of every
row in that table**, not only the rows this run happened to touch. Logged here so it is not
lost.

## Finding 4 — Amendment A-23 is now claimed by two rows in one document `[carried forward]`

Rows 21 (FR-20) and 22 (FR-28) both carry "(Amendment A-23)". That is defensible — one
amendment closing the traceability design gaps — but it compounds Finding 4 of the FR-20
review: A-23 still appears in `EXPERIENCE.md` only, and the amendment convention requires the
same ID in every document the change touches.

The decision is now larger than when it was first raised: either A-23 is **one** amendment
covering all four FR design gaps (and must be recorded in `DESIGN.md` and the PRD as such),
or each gap takes its own ID. `matrix-regeneration-and-ledger` owns the Amendment Ledger and
must settle it. **Unresolved, this run will have added a new ledger inconsistency while
closing four coverage gaps** — which would be a poor trade.

## Auto-fixes applied

None.

## Verdict

**Pass**, with two items carried to `matrix-regeneration-and-ledger`: the A-23 amendment
decision (Finding 4, now spanning two items) and the full Surface Coverage Map audit
(Finding 3).

---

# Code Review: FR-49 — design saved collections, and correct the coverage claim that hid them

## Scope

| File | Change |
|---|---|
| `mockups/collections-desktop.html` | created |
| `DESIGN.md` | +1 component entry |
| `EXPERIENCE.md` | +1 coverage row, **1 row corrected** |

No code, no tests. The reviewable question is whether the design is faithful to the build,
since the whole risk of this item runs that way.

## Finding 1 — the mockup is faithful, and that was checked line by line `[pass]`

Every string in the mockup was taken from the component rather than written fresh:

| Mockup | Source |
|---|---|
| "Delete '{name}'? Your saved events stay saved." | `collection-manager.tsx` delete confirm |
| "Delete it" / "Keep it" | same |
| "No collections yet." / "Group your saves into something like…" | the quiet empty state |
| "Nothing in here yet. Add saves to it from your saved events." | the opened-empty branch |
| "Music this month" placeholder, `maxlength=80` | the create input |
| ↑ / ↓ with `disabled` at the ends, 44×44 | the reorder buttons |
| Rename / Delete as underlined 44px-high text links | the row tools |

The faithfulness risk the plan flagged did not materialise into a silent improvement. The
one place the mockup *adds* rather than records is the two explanatory panels (section E),
which carry rules rather than UI.

## Finding 2 — section E's tier table is the mockup's most load-bearing content `[correct]`

The seven-row "what is gated" table is the part a future implementer is most likely to get
wrong, because the intuitive reading of "Collections are a Pro feature" is that the surface
is Pro. It is not: only `create` and `assign` are gated, and seven backend tests pin the
lapsed-user paths.

Getting this wrong has a specific, bad consequence — a downgrade would destroy access to the
user's own data. Worth the space it takes.

## Finding 3 — row 10's correction sets a precedent the final item should follow `[carried forward]`

The correction does not merely strike `FR-49`; it records the counted evidence
(`collection` ×0 against `quiet` ×10, `Pro` ×7, `export` ×4) and the reason. That is
deliberate: a bare strike leaves the next maintainer free to re-add the claim.

This is now the **second** corrected row in this table (row 11's `UJ-5` scope was the first,
in the FR-28 item). Both were wrong in the same way — a hand-maintained FR column claiming
coverage the file does not have. The recommendation from the FR-28 review stands and is now
better evidenced: **`matrix-regeneration-and-ledger` should audit the FR column of every row
in the Surface Coverage Map**, not only rows this run happened to touch. Two confirmed errors
out of ~20 rows is a defect rate worth measuring rather than assuming.

## Finding 4 — Amendment A-23 now spans three rows `[carried forward, growing]`

Rows 21 (FR-20), 22 (FR-28) and 23 (FR-49) all carry "(Amendment A-23)", and A-23 still
appears in **`EXPERIENCE.md` only**.

This has been flagged in all three item reviews and is now the single largest piece of debt
this run has created. `matrix-regeneration-and-ledger` must either record A-23 in `DESIGN.md`
and the PRD as one amendment covering the traceability design gaps, or split it. **If it does
neither, this run will have closed four design gaps and opened one ledger gap**, and the
regenerated matrix's own Amendment Ledger will say so.

## Auto-fixes applied

None.

## Verdict

**Pass.** Two items carried to `matrix-regeneration-and-ledger`, both now stronger than when
first raised: the A-23 amendment decision (spanning three rows) and the full Surface Coverage
Map FR-column audit (two confirmed errors).

---

# Code Review: FR-55 — design the cancelled-event conflict path, and prove nothing auto-cancels

## Scope

| File | Change |
|---|---|
| `mockups/event-state-conflict-desktop.html` | created |
| `mockups/conflict-prompt-desktop.html` | header: `FR-55` added beside `FR-58` |
| `mockups/conflict-indicator-card-state-desktop.html` | header: same |
| `DESIGN.md` | +3 component entries |
| `EXPERIENCE.md` | +1 row, 2 rows amended |
| `tests/personalization/test_event_detail_api.py` | +1 test |

## Finding 1 — the new test asserts a cancellation specifically, and that is load-bearing `[correct]`

`make_notice(..., kind="cancelled")` rather than the fixture's default `sold_out`. That looks
incidental and is not.

`sold_out` is a notice the mute **does** silence at the banner. `cancelled` is one the
backend raises **despite** the mute. So a test written with the default would assert the two
facts coexist in the easy case — where nothing is in tension — while the cancelled case is
the one where a careless "if muted, return no notice" optimisation would actually destroy
information the user cannot get anywhere else. The test is pointed at the case that matters.

## Finding 2 — `component.indicator.conflict.cleared` was added rather than reusing the live indicator `[correct]`

The existing `component.indicator.conflict` is *"a 6px filled circle in `{color.warn.amber}`"*.
The cleared state is a hollow `{color.ink.faint}` ring on a dashed container.

A new visual was justified here and resisted elsewhere in this run (FR-49 deliberately reused
`emptystate.quiet`). The difference: AD-21 and a database check constraint
(`conflict_pair_resolution_kind_ck`) both insist `cleared_by_state_change` is **not** a user
resolution, so rendering it identically to a resolved pair would contradict the data model —
and would congratulate the user for a decision they never made. The design now matches the
constraint.

Note the hollow-vs-filled distinction follows the precedent Amendment A-22 already set in
this document, where the sold-out glyph went hollow (`⊘`) specifically so it could not be
confused with the filled conflict dot in the same card. Same hue, different figure. This is
the same move applied to the same indicator's own two states.

## Finding 3 — editing two mockups this run did not create is the right call, but it is the fragile one `[flag]`

Both headers carry an explicit *"Do not strip this tag as a duplicate"* instruction with the
matrix quote as justification. That is the strongest available defence in a comment, and it
is still only a comment.

The durable version is the one the final item owns: once `doc-trace` regenerates, FR-55 will
score `FULL` from three mockup headers rather than one, and the matrix itself becomes the
record. **If `matrix-regeneration-and-ledger` does not regenerate, these tags are the only
thing holding FR-55 closed**, and a future tidy-up would silently reopen it.

## Finding 4 — Amendment A-23 now spans four rows `[carried forward, final]`

Rows 21, 22, 23 and 24 all carry "(Amendment A-23)", and A-23 appears in **`EXPERIENCE.md`
only** — not in `DESIGN.md`, not in the PRD, despite this run having added nine component
entries to `DESIGN.md` under it.

Raised in all four item reviews. This is the last item before regeneration, so it is now
unavoidable: `matrix-regeneration-and-ledger` either records A-23 across the documents it
touched or splits it. **The regenerated Amendment Ledger will print the inconsistency either
way** — which is the honest outcome, but a poor one to have manufactured while closing four
gaps.

## Auto-fixes applied

None.

## Verdict

**Pass.** Three items carried to `matrix-regeneration-and-ledger`: the A-23 amendment
decision (now four rows), the Surface Coverage Map FR-column audit (two confirmed errors),
and the postponed-into-conflict e2e test, which waits on the time-bomb fix.

---

# Code Review: Regenerate the matrix, retire the findings that are no longer true

## Scope

| File | Change |
|---|---|
| `traceability/TRACEABILITY.md` | regenerated, 253 lines |
| `traceability/.memlog.md` | created |
| `prd.md` | +1 amendment entry (A-23) |
| `DESIGN.md` | +A-23 in `updated_note` |
| `EXPERIENCE.md` | row 9 filename corrected |

## Finding 1 — the matrix reports its own target as missed `[correct, and the point]`

The acceptance criterion named 36 FULL; the document reports 35 FULL · 1 PARTIAL and says so
in its summary table, not a footnote.

Reaching 36 was one line of work — a tag in `settings-sources-desktop.html` or an FR-16
citation in EXPERIENCE.md row 15. Doing it would have been wrong: the same pass that
*measures* coverage must not *edit* the thing it measures, or the number stops meaning
anything. The matrix would have read "36 FULL" and been less true than the 35 it reports.

FR-16 is recorded as open item 1 with the exact fix, so closing it is a one-line change in a
later pass that is not also the measuring pass.

## Finding 2 — the regeneration found a rule the previous matrix applied inconsistently `[substantive]`

FR-16's downgrade is not a product regression; it is the previous matrix having rated one FR
`FULL` on precisely the evidence it called `PARTIAL (inferred only)` for three others. Both
were adjacency: "reliability dots exist near a settings mockup" is the same tier of evidence
as "FR-20 can be inferred from FR-9's picker".

That is worth more than the single row it changes. It means the September matrix's **counts
were not internally consistent**, so "32 FULL" was never a figure to compare against. The new
document says this explicitly rather than quietly producing a different number.

## Finding 3 — three errors in ~24 Surface Coverage Map rows `[validated recommendation]`

The FR-28 and FR-49 reviews both recommended auditing the whole FR column rather than the
rows this run touched. That recommendation paid: row 9 named a mockup file **that has never
existed**, and nothing but a filename-by-filename check against `ls` would have found it —
its FR claim was correct, its design was present, only the pointer was wrong.

A 3-in-24 defect rate in a hand-maintained column is the finding, not the three rows. The
durable fix is that the matrix is now regenerated rather than hand-maintained, and
`.memlog.md` makes the next drift measurable from the gap between scan dates.

## Finding 4 — `prd.md` was edited, which deserves a second look `[accepted]`

This run otherwise touched only UX documents and tests. The PRD edit adds one frontmatter
amendment entry and changes **no requirement text** — and the entry says so in its first
sentence (*"Changes no requirement"*).

It also carries the two as-built divergences found during the run — FR-20's configurable
default, and FR-55's shared conflict surface — into the document that owns requirements,
where the first is a candidate for a real future amendment to FR-20's text. Recording them
only in UX docs would have left the PRD quietly wrong about its own FR-20.

Frontmatter re-parsed after the edit: valid, 4 amendment entries, A-23 present.

## Finding 5 — an unrelated pre-existing defect was found and deliberately not fixed `[correct]`

`DESIGN.md`'s YAML frontmatter does not parse — Amendment A-22 (2026-11-10) embedded
unescaped `"` in a double-quoted scalar. Verified against a pre-edit backup that this
predates this run; the A-23 text added here escapes its own quotes correctly.

Not fixed, and that is the right call: it is unrelated to traceability, the fix touches a
3,000-character scalar belonging to another amendment, and folding it into this item would
hide a real defect inside a documentation change. Recorded as open item 5 where it will be
seen.

## Auto-fixes applied

None.

## Verdict

**Pass**, with the headline criterion honestly reported as missed. Nothing is carried forward
to a later item — this was the last — so all five open items live in the matrix's own
"Open items carried out of this regeneration" section, which is where the next reader will
look.
