---
run: run-eventpulse24-054
work_item: account-delete-confirmation-surface
intent: account-profile-expansion
mode: confirm
tested_at: 2026-11-20
---

# Test Report: The Confirmation Modal — the Moment Before the Account Goes

## What Was Tested

| File | Tests | Covers |
|------|-------|--------|
| `backend/tests/identity/test_deletion_copy.py` | 9 | The endpoint **publishes** the copy — both paragraphs present, the *same objects* the mail renders, the answer carries them too, a second request says the same thing, **the preview changes nothing**, an anonymous caller is refused; and the copy is **true of the engine** — the three families `purgeable_models()` actually purges, "aggregate" and not "your account", and the one claim the copy must not make |
| `frontend/components/settings/account-delete-modal.test.tsx` | 26 | The anatomy (a real `role="dialog"`, `aria-modal`, labelled and described, 480px, exactly three paragraphs, the input, the two buttons); the gate (exact, case-sensitive, unpadded); the keyboard (focus in, focus back, Escape, the trap, and an ordinary Tab passing through); the request (literal path, the server's date, the failure that keeps the modal open, the API's own refusal); the tokens; axe-core |
| `frontend/components/settings/danger-zone.test.tsx` | 21 (7 new) | The row opens the modal; **the modal is not open before the row is pressed**; the copy is the API's and not the section's own; the read is literal; a landed request moves the section to the pending state with the server's date; a failed request leaves the section where it was; **no modal at all when the copy could not be read** |

**Fifty-six tests across three files, and they run on both sides of the wire.** The
backend file proves the copy is *published and true*; the frontend files prove the
modal *says it and cannot be talked out of it*.

## Results

| Suite | Result |
|-------|--------|
| `backend/tests/identity/test_deletion_copy.py` | 9 passed |
| `backend/tests/identity/test_account_deletion_api.py` | 22 passed (unchanged — the POST's shape is a superset) |
| `backend/tests/api/test_contract.py` | 1 passed — the committed schema equals the live API |
| `account-delete-modal.test.tsx` | 26 passed |
| `danger-zone.test.tsx` | 21 passed |
| `tests/endpoint-coverage.test.ts` | 4 passed — **the `POST` exemption is deleted, not rewritten, and no orphan appeared** |
| `tests/spacing-scale.test.ts` | 3 passed — the dialog is on the closed spacing scale |
| **Full frontend suite** | **2831 passed, 0 failed** (175 files) |
| **Full backend suite** | **7660 passed, 0 failed** (15m14s) — 7651 before this item, plus the 9 new |
| `make lint-backend` (ruff + ruff format + import-linter) | clean — **21 contracts kept, 0 broken** |
| `pnpm tsc --noEmit` | clean |
| `pnpm eslint` on the changed files | clean |
| `pnpm prettier --check` on the changed files | clean |

## Mutation Probes — four, all detected

**A test that cannot fail is not a test.** Every load-bearing claim in this item was
contradicted deliberately, and the suite was asked to notice.

| # | Mutation | Detected by | Result |
|---|----------|-------------|--------|
| 1 | The gate became case-insensitive (`value.toUpperCase() === "DELETE"`) | `stays closed for the wrong case` | **Detected** |
| 2 | The modal called `onClose()` on a failed request | `keeps the modal open when the request fails` | **Detected — after the first attempt survived** |
| 3 | The danger zone rendered its own copy instead of the API's | `shows the copy the API published, and not a copy of its own` | **Detected** |
| 4 | The focus trap's wrap-around was removed | `keeps the Tab inside the dialog` | **Detected** |

### Probe 2 — the probe that survived, and what it cost

**This is the one worth reading.** The first version of the modal's failure test
asserted two things: that the alert was on screen, and that the dialog was still in the
document. **The mutation — the modal closing itself on a failed request — passed
both.** The reason is that the test's `onClose` was a bare `vi.fn()`, so *nothing
observed whether the modal had asked to be closed.* The dialog was still on screen
because **the container** had not closed it, not because the modal had not asked.

That is a real gap and not a cosmetic one: "the modal did not close" and "the modal did
not *ask* to close" are different claims, and only the second one is about this island's
behaviour. The container's behaviour is a different file's business.

**The fix was to assert `onClose` was not called** — in both the API-refusal case and
the offline case. The re-run of the probe then failed, as it should.

**The general lesson, and it is the same one this project's test report keeps
naming:** a test that mocks the collaborator and then never inspects the mock is
testing half the contract. `onRequested` was already asserted with its argument
(`toHaveBeenCalledWith(SCHEDULED_FOR)`); `onClose` was not, and the difference is
exactly where the bug was.

### Probe 1 — the gate is a gate, not a suggestion

`value.toUpperCase() === CONFIRM_WORD` looks strict and is not: it lets `delete` and
`Delete` through. The mutation was caught by one test, `stays closed for the wrong
case`. **The padded case — `" DELETE "` — is a separate assertion** (`stays closed for a
padded word`), because a trimmed comparison would also pass a case-sensitive one, and
one test cannot hold both claims.

### Probe 3 — one sentence, one place

The danger zone's copy was replaced with two literals of its own. The mutation was
caught by `shows the copy the API published, and not a copy of its own`. **This is the
claim the whole item turns on**: the modal and the mail must not be able to tell the
person two different stories about the same destruction, and the way that is guaranteed
is that there is only one spelling of the sentence — in Python.

### Probe 4 — the trap is the difference between a modal and a decoration

The wrap-around was removed from the focus trap. `keeps the Tab inside the dialog`
failed. **The companion test — `lets an ordinary Tab pass through the middle of the
dialog` — is what stops the trap from being a blunt instrument**: a trap that swallowed
every Tab would break the dialog rather than contain it, and that would also pass a
test that only checked "the trap exists".

## One Unreproduced Flake, Recorded

**On one of the eight full-suite runs, one test failed and the file was not named in
the output.** The suite went on to pass cleanly on **seven consecutive subsequent runs**
(175 files, 2831 tests each), and the two files this item created were run five more
times in isolation — **47 passed, every time**.

**The failure is recorded rather than explained away**, because a test that fails once
and cannot be reproduced is a fact about the suite and not a fact about nothing. Two
things are known: it was **not** in `account-delete-modal.test.tsx` or
`danger-zone.test.tsx` (five isolated re-runs, clean), and it did not recur in seven
full-suite runs afterwards.

**The likely shape of it** — offered as a hypothesis, not a finding — is a
**cross-file interaction in jsdom**: the suite creates 175 jsdom environments, and a
test that asserts on `document.body` or on `document.activeElement` can see a
neighbouring file's DOM if the environments are shared or if a file leaves state
behind. **This item's two files both assert on `document.body`** (the axe-core gate
runs `axe.run(document.body)`), and both assert on `document.activeElement` (the focus
tests). That makes them plausible participants in an interaction, and **not guilty of
one** — they pass in isolation and in seven full runs.

**What would settle it:** the failing file's name. The grep that would have captured it
was looking for `❯` and `FAIL`, and the run's own output did not carry the file name
into the summary. **A future occurrence should be captured with the full output rather
than a grep.**

## The axe-core gate

`account-delete-modal.test.tsx` runs axe over the rendered dialog and asserts **zero
serious or critical violations**. `color-contrast` is disabled, for the same reason as
everywhere else in this repo: jsdom computes no layout, so axe cannot measure contrast.
The project's separate gate (`tests/contrast.test.ts`) measures contrast against the
tokens.

## What Is Not Tested, and Why

- **The endpoint's own request-side behaviour** — the grace-period arithmetic, the
  idempotency key, the mail dispatch — is item 1's work and is tested there
  (`backend/tests/identity/test_account_deletion_api.py` and
  `test_account_deletion_mails.py`). **This item calls the endpoint; it does not
  re-test it.**
- **The modal's own copy.** It has none. The two paragraphs are props, and the props
  come from the API. **A test that asserted the modal's copy would be asserting a
  second copy**, which is the drift this item exists to prevent.
- **The third paragraph** — *"You can cancel anytime during the 30-day grace from this
  page or from the email we send."* — is asserted to be **present**, but the truth of it
  is not asserted here. **It is true because item 1 shipped the mail and item 3 shipped
  the cancel surface**, and those two are the ones that would have to change for it to
  become false. A test in this file could only re-assert the string.
- **The danger zone's row copy** (*"Your account is destroyed after a 30-day grace
  period…"*) is unchanged and its own test still asserts it.

## Notes on the Design

**The copy needed a preview endpoint, and that was found mid-implementation.** The
original plan had the copy arriving *with* the POST answer — which is a sequencing
problem: the modal has to say what the deletion does *before* the person has typed
anything, so it cannot wait for the answer to a request it has not made yet.

**So `GET /api/auth/profile/deletion` publishes the copy, and the POST carries it
too.** Three ways were considered and two were rejected:

| Option | Rejected because |
|--------|-----------------|
| Hard-code the two strings in TypeScript | A second spelling of the mail's sentence — the exact drift the backend avoided. |
| Put the prose on `me` | It rides every page's payload, and `me` carries two *dates* and no prose by its own docstring. |
| Fetch inside the modal, on open | A spinner in front of the one screen a person reads before destroying an account. |

**The section fetches the copy when it mounts, and the modal opens only once it is
there.** A dialog with two blank paragraphs in it would say nothing about what is about
to happen — which is the one thing it exists to say. The test
`does not open the modal when the copy could not be read` holds that.

**Two of A-16's three paragraphs are not true of the engine, and the backend's are
used instead.** The mockup's ¶1 says *"permanently delete … within 30 days"* (nothing is
deleted *within* the grace period, and the deletion is not permanent at request time),
and its ¶2 ends *"We can't reverse deletion."* — which contradicts ¶3's promise of a
thirty-day grace in the very next paragraph. `DELETION_REMOVES` and `DELETION_SURVIVES`
already exist in `deletion.py` and already ship in the mail. **The modal uses them, so
the mail and the modal cannot disagree.**

**The backend test asserts the copy is *true of the code*, not just published.**
`test_the_first_paragraph_names_what_is_actually_purged` runs `purgeable_models()` and
checks that each of the three families the paragraph names is on the list — so a copy
that named a family the engine does not purge would fail. **And
`test_neither_paragraph_claims_the_deletion_cannot_be_reversed` asserts the one claim
the copy must not make**, because the mockup makes it and the grace period reverses it.

**The spacing scale caught two real values.** `mt-5` and `pt-5` generate no CSS at all
in this project — `tokens.css` resets Tailwind's spacing multiplier and declares only
DESIGN.md's steps — so a dialog with those classes would have had a button with no
padding above it and no padding below the rule. `tests/spacing-scale.test.ts` failed on
both, and they were moved to `mt-6`/`pt-6`.

## The One Thing Not Changed

**The section's two-state logic.** `account-danger-zone` owns it, and this item adds a
third state — the modal — without restructuring the other two. **The modal is a sibling
of the section's content, not a child of the row**: the row unmounts when the request
lands, and a dialog that lived inside the row would unmount with it, taking the pending
state it had just asked for.

---
*Test report for `account-delete-confirmation-surface`. The item is ready for review.*
