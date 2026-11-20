---
run: run-eventpulse24-054
work_item: account-delete-confirmation-surface
intent: account-profile-expansion
generated: 2026-11-20T10:06:27.173Z
mode: confirm
---

# Implementation Walkthrough: The Account Deletion Surfaces — Four Screens That Were Missing

## Summary

**The account-deletion engine shipped with no user-reachable surface.** The command, the
grace period, the mail renderer, the cancel command and the endpoints all existed — and
`frontend/tests/endpoint-coverage.test.ts` was carrying an exemption for
`POST /api/auth/profile/deletion` that said so in as many words: *"A-16's confirmation
modal is not built."*

**This run built the four missing surfaces.** A person can now ask for their account to
be deleted from `/settings/privacy`, read what the deletion will do and what will
survive it, cancel from the same page or from the email, and see the destruction date
the server computed.

**The thread through all four is one sentence.** A-16's third paragraph promises *"You
can cancel anytime during the 30-day grace from this page or from the email we send."*
— and a modal in front of that promise, with a cancel surface and a mail behind it, is
a promise the product can actually keep. **The order of the work items was the order of
that sentence**: the mail first, then the section, then the cancel surface, then the
modal.

## Structure Overview

**Four work items, one dependency chain, and a deliberate decision about where the
copy lives.**

The account-deletion engine is a service layer: named commands own writes (AD-5), and
the API layer never writes. The four surfaces this run built are all *readers* of that
engine except the request, which calls it.

```
   /settings/privacy  →  DangerZone (container, client)
                            │
                            ├── AccountDeleteModal (island)  ──POST──▶  request_account_deletion
                            │        └── shows the API's copy             (30-day grace starts)
                            │
                            └── DangerZonePending (island)  ──DELETE──▶  cancel_account_deletion
                                     └── shows the server's date
                                     (the way back)

   the mail           ──▶ account_deletion.txt  ──▶ the cancel token's link
                              └── AccountDeletionCopyOut (GET /profile/deletion)
                                     └── the same two strings the mail renders
```

**The container is the thing all three frontend pieces hang on.** It owns three states
now — request row, pending row, modal-open — and it owns the *decision* about which
one shows. Each island owns the state inside itself: the modal owns the typed word and
the focus trap; the pending row owns the cancel request.

**The backend's copy is published, not duplicated.** `DELETION_REMOVES` and
`DELETION_SURVIVES` live in `backend/apps/identity/services/deletion.py`. The mail
renders them. `AccountDeletionCopyOut` publishes them on the wire. The modal renders
what it is given. **There is exactly one spelling of the sentence that describes what
the deletion does, and it is in Python.**

## Architecture

### Pattern Used

**Service layer with named commands, and a published read model.** The engine was
already built; this run added no new write paths and no new domain rules. It added
*surfaces* over an existing engine, and one read endpoint whose only job is to carry
two constants to a screen that needs them.

### Layer Structure

```text
┌─────────────────────────────────────────────────────────────┐
│  Presentation                                               │
│  danger-zone.tsx (container)                                │
│  account-delete-modal.tsx (island)                          │
│  danger-zone-pending.tsx (island)                           │
├─────────────────────────────────────────────────────────────┤
│  Application — API                                          │
│  GET  /api/auth/profile/deletion   → the copy (a preview)  │
│  POST /api/auth/profile/deletion   → request the deletion   │
│  DELETE /api/auth/profile/deletion → call it off           │
├─────────────────────────────────────────────────────────────┤
│  Domain — services/deletion.py                              │
│  the commands · the grace period · DELETION_REMOVES        │
│  DELETION_SURVIVES · purgeable_models()                     │
├─────────────────────────────────────────────────────────────┤
│  Infrastructure                                             │
│  Celery (the destruction runs later) · the mail renderer    │
└─────────────────────────────────────────────────────────────┘
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `frontend/components/settings/account-delete-modal.tsx` | A-16's confirmation modal — the type-to-confirm gate, the focus trap, the request, the failure that keeps it open |
| `frontend/components/settings/account-delete-modal.test.tsx` | The modal's own tests — the anatomy, the case-sensitive gate, the keyboard, the request, the failure (26 tests) |
| `frontend/components/settings/danger-zone.tsx` | The section — three states, and the container the modal and the pending row hang on |
| `frontend/components/settings/danger-zone.test.tsx` | The section's tests, including the modal wiring (21 tests) |
| `frontend/components/settings/danger-zone-pending.tsx` | The way back — the cancel surface, the server's dates, the failure that keeps the pending state (15 tests) |
| `frontend/components/settings/danger-zone-pending.test.tsx` | The pending island's tests |
| `frontend/tests/privacy-danger-zone-pending.test.tsx` | The *page* — the pending state reaches the screen in both branches |
| `frontend/tests/privacy-danger-zone.test.tsx` | The page with nothing pending |
| `backend/tests/identity/test_deletion_copy.py` | The endpoint publishes the copy, and the copy is true of the engine (9 tests) |
| `backend/tests/identity/test_deletion_read.py` | The read — the two moments, and no cancel token on the wire |
| `backend/tests/identity/test_account_deletion_mails.py` | The confirmation mail's copy and its cancel token |
| `backend/tests/identity/test_account_deletion_token_concurrency.py` | The token's single use and its concurrency guard |
| `backend/apps/identity/services/deletion_read.py` | The read model — the two moments, without the token |
| `backend/apps/identity/templates/identity/account_deletion.txt` | The confirmation mail's template |
| `backend/apps/identity/migrations/0009_deletionrequest_cancel_token.py` | The token's columns |

### Modified

| File | Changes |
|------|---------|
| `backend/apps/identity/api.py` | `GET /profile/deletion` publishes the copy; the POST carries it too |
| `backend/apps/identity/schemas.py` | `AccountDeletionCopyOut` added; `AccountDeletionRequestOut` inherits from it |
| `backend/apps/identity/models.py` | The cancel token's columns |
| `backend/apps/identity/services/deletion.py` | The commands, the grace period, the two canonical strings |
| `backend/apps/identity/services/emails.py` | The confirmation mail's renderer |
| `backend/apps/identity/services/__init__.py` | The new service exports |
| `backend/tests/identity/test_account_deletion_api.py` | The POST's shape, the read's shape |
| `backend/tests/identity/test_auth_api.py`, `test_profile_api.py`, `test_account_deletion.py`, `conftest.py` | The fixtures the new surfaces needed |
| `frontend/app/settings/privacy/page.tsx` | The danger zone is mounted in both branches |
| `frontend/lib/settings-sections.ts` | The section's registration |
| `frontend/tests/endpoint-coverage.test.ts` | **The `POST` exemption is deleted, not rewritten** |
| `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` | Regenerated by `make client` |

## Key Implementation Details

### 1. The canonical copy is published, not duplicated

`DELETION_REMOVES` and `DELETION_SURVIVES` already existed in
`backend/apps/identity/services/deletion.py` and already shipped in the confirmation
mail. **A frontend that paraphrased them would be telling the person one thing on the
screen and another in their inbox** — which is the exact failure this project's test
report keeps naming.

**So the backend publishes them.** `AccountDeletionCopyOut` is a new base schema, and
`AccountDeletionRequestOut` inherits from it — which makes "the same two strings"
structural rather than a convention. The frontend keeps no second spelling.

**The backend test asserts both halves.** `test_the_paragraphs_are_the_ones_the_mail_renders`
asserts the endpoint carries the *same objects* the mail renders, and
`test_the_first_paragraph_names_what_is_actually_purged` runs `purgeable_models()` and
checks each of the three families the paragraph names is actually on the list.

### 2. The copy needed a preview endpoint, and that was found mid-implementation

**The original plan had the copy arriving with the POST answer.** That is a sequencing
problem: the modal has to say what the deletion does *before* the person has typed
anything, so it cannot wait for the answer to a request it has not made yet.

**So `GET /api/auth/profile/deletion` publishes the copy, and the POST carries it too.**
Two alternatives were rejected:

| Option | Rejected because |
|--------|-----------------|
| Hard-code the two strings in TypeScript | A second spelling of the mail's sentence — the drift the backend avoided. |
| Put the prose on `me` | It rides every page's payload, and `me` carries two *dates* and no prose by its own docstring. |

**The section fetches the copy when it mounts**, not when the modal opens — a dialog
that had to load before it could say anything would put a spinner in front of the one
screen a person reads before destroying an account. **And the modal renders only when
the copy is there**, because a dialog with two blank paragraphs in it would say nothing
about what is about to happen.

### 3. Two of A-16's three paragraphs are not true of the engine

**This is the finding that changed the shipped copy.**

| ¶ | A-16's mockup | The engine | Verdict |
|---|---|---|---|
| 1 | *"We'll permanently delete your account, personal events, saved events, and preference graph within **30 days**."* | `purgeable_models()` purges the personal events, the saved events and the four preference-graph models. The account itself is deleted last, by hand. | **The nouns are right. The verb is wrong.** "Permanently delete … within 30 days" says two things at once and neither is the engine's: nothing is deleted *within* the grace period, and the deletion is not permanent at request time. |
| 2 | *"**Anonymized aggregates** … survive. **We can't reverse deletion.**"* | `DELETION_SURVIVES` — *"Anonymised aggregate figures survive … They are not linked to your account and cannot be traced back to you."* | **Half a promise the engine does not keep.** "We can't reverse deletion" contradicts the grace period *in the very next paragraph*. |
| 3 | *"You can cancel anytime during the 30-day grace from this page or from the email we send."* | Both halves now exist. | **True, and shippable as written.** |

**So the modal's first two paragraphs are the backend's strings, and the mockup's
wording is not what ships.** The third is the only paragraph written in the frontend —
it describes what *the product offers*, and only this screen can make it true.

**The backend test holds the copy to the promise.** `test_neither_paragraph_claims_the_deletion_cannot_be_reversed`
asserts the one claim the copy must not make, because the mockup makes it.

### 4. The gate is `=== "DELETE"`, and the trimmed comparison was rejected

A-16 says case-sensitive, and says it in the mockup's own variant strip. **So the
comparison is `=== "DELETE"`** — not trimmed, not case-folded.

**A trimmed comparison would make the gate a suggestion**, and the gate is the last
thing standing between an accident and a destroyed account. Both failure modes have
their own test, because one test cannot hold both claims: `stays closed for the wrong
case` and `stays closed for a padded word`.

### 5. The focus trap is the difference between a modal and a decoration

**No component in this repository has a focus trap.** `MutePrompt` needs none — it is
a bottom sheet over a digest, and the digest behind it has nothing to tab to. **This
modal sits over the settings screen, which is full of interactive controls**, so a Tab
that walked out of the dialog would put a keyboard user into the page behind it,
editing settings they did not come to edit.

**The trap asks the DOM where the edges are** rather than keeping a list that would go
stale the moment a button was added. The handler is on the document, because the
browser moves the focus itself and the `keydown` still fires on whatever now holds it.

**And the trap only holds the edges** — a Tab between two elements is ordinary tabbing,
and intercepting it would break the dialog rather than contain it. There is a test for
that too.

### 6. A second request is idempotent, and the UI does not present it as an error

The endpoint answers 200 with the *same* date on a second request, so the modal shows
the same success state. **The date is the server's moment, computed once**, and it
travels to the frontend as `scheduled_for` — never as a duration typed into a
component.

### 7. The cancel surface reads the pending state off `me`, as two moments

`CurrentUserOut` gains `deletion_scheduled_for` and `deletion_requested_at`. **A
`"pending": true` cannot answer *"when does my account die?"*, and a duration cannot
either** — the grace period is computed once, at request time.

**The read carries no cancel token.** The token is in the mail and nowhere else; the
read's dataclass has exactly two datetime fields, and `DeletionRequest`'s
`token_hash`/`token_salt` have no path to the wire through it.

## Security Considerations

| Concern | Approach |
|---------|----------|
| The cancel token's exposure | **The token is in the mail and nowhere else.** The read's dataclass has exactly two datetime fields, and `token_hash`/`token_salt` have no path to the wire. Asserted at both layers — the dataclass and the raw `me` response. |
| The token's single use | The token is consumed on use, and a concurrency guard makes a replay a refusal rather than a second cancellation. Tested in `test_account_deletion_token_concurrency.py`. |
| The copy endpoint's authorisation | `current_user(request)` is called and its result discarded — **the resolver raises for an anonymous caller, and that is the point of the call.** The preview is behind the same session wall as the thing it previews. |
| CSRF | **A `GET` needs no token and a `POST` does.** The POST calls `require_csrf(request)` first, as on every write on that router. |
| What the preview leaks | Nothing personal — two product-level sentences and no user data. `test_the_preview_changes_nothing` also proves it writes no `DeletionRequest`. |
| Account enumeration | The account is resolved but **not consulted**: the two strings describe what the engine does and are the same for everybody. |
| The picture | Removed **at destruction**, not at request time — so cancelling inside the grace period leaves the picture where it was. |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| The copy must be available before the modal opens | Fetched once when the section mounts, not on every open. **The two strings are constants of the product, so there is nothing to refresh and nothing to cache.** |
| The read must not ride every page | The pending state rides `me` (two dates); the copy does not — it has its own endpoint, read only on `/settings/privacy`. |
| The modal must not re-fetch | The container holds the copy in state. **The modal fetches nothing** — it is handed the two strings. |
| The request must not cost a page render | `router.refresh()` is the project's pattern for a write that changes server-rendered state, but **the endpoint returns `scheduled_for`** and the container already holds it. **The container is told the date, and it renders the pending state itself.** |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Where the canonical copy lives | The API publishes it; the frontend keeps no second spelling | `DELETION_REMOVES` and `DELETION_SURVIVES` already exist and already ship in the mail. A paraphrase would be a second version of the same story. |
| How the modal gets the copy before the person types | A `GET` preview endpoint; the section fetches it on mount | The copy cannot ride the POST answer — the modal has to speak before the request is made. Hard-coding it is the drift the backend avoided; putting it on `me` rides every page. |
| Which of A-16's three paragraphs ship | The two from the backend; the third verbatim | Two of the mockup's three are not true of the engine, and one of them contradicts the promise in the paragraph after it. |
| The gate comparison | `value === "DELETE"`, exactly | A trimmed comparison would let `" DELETE "` through — a comparison that looks strict and is not. |
| The focus trap | Written in the modal file, not extracted as a shared primitive | A one-caller hook is not an abstraction yet, and there is nothing in the repository to reuse. |
| The modal's role | `role="dialog"`, not the house `Sheet` | The house `Sheet` is a native `<dialog>`, and `mute-prompt.tsx` records why that matters: **a native dialog has no `aria-describedby` slot**, because its description is the element's own text content — and A-16's description is three paragraphs, separate from the title. |
| The focus target on open | The input, not the primary button | The primary is disabled until the input matches, so focusing it would put a keyboard user on a control that does nothing. |
| The primary's label | "Start 30-day deletion", not "Delete account" | The engine *schedules*; it does not delete on this call. **The label tells the truth about what the button does.** |
| The container's reaction to a success | It renders the pending state itself | A `router.refresh()` would be a second round trip for a value the client is already holding. |
| The endpoint coverage exemption | **Deleted, not rewritten** | A rewritten exemption would be a second sentence about an endpoint that now has a caller — and the file's own "declared uncalled but in fact called" check would fail it. |
| The danger zone's row copy | Unchanged | The mockup says *"Permanent. Cannot be undone."*, and that is **false** — the engine holds a thirty-day grace period. The shipped copy says what is true. |

## Deviations from Plan

**One, and it was forced by a sequencing problem the plan did not anticipate.**

The plan said the copy would reach the modal *with the POST answer*. **That cannot
work** — the modal has to say what the deletion does before the person has typed
anything, so it cannot wait for the answer to a request it has not made yet.

**The resolution: a `GET /api/auth/profile/deletion` preview endpoint.** The POST
still carries the copy too, so a client that has just asked can say what it did without
asking again. Two alternatives were considered and rejected — hard-coding the strings in
TypeScript (the drift the backend avoided) and putting the prose on `me` (it rides every
page's payload).

**The plan also said the copy would not be duplicated.** That held — but the plan did
not anticipate that *publishing* it needed a new endpoint, because it assumed the
frontend could read it from somewhere.

**A smaller deviation: the plan's DOM sketch showed `disabled={value !== "DELETE"}`.**
The shipped code is `disabled={!matches || busy}`, because the button must also be
disabled while the request is in flight — **otherwise a second press would fire a
second request.**

## Dependencies Added

**None.** No new package, no new runtime dependency, no new system dependency. The
modal uses React's own `useEffect`/`useRef`/`useId` and the project's existing
`api` client.

## How to Verify

1. **The backend publishes the copy, and it is true of the engine**

   ```bash
   cd backend && uv run pytest tests/identity/test_deletion_copy.py -v
   ```

   Expected: 9 passed. The first class proves the endpoint publishes the copy and that
   a preview writes nothing; the second proves the copy names what
   `purgeable_models()` actually purges and does not claim the deletion cannot be
   reversed.

2. **The modal's anatomy, the gate, the keyboard and the failure**

   ```bash
   cd frontend && pnpm vitest run components/settings/account-delete-modal.test.tsx
   ```

   Expected: 26 passed. In particular `stays closed for the wrong case`,
   `stays closed for a padded word`, `keeps the Tab inside the dialog`, and
   `keeps the modal open when the request fails`.

3. **The section opens the modal and moves to the pending state**

   ```bash
   cd frontend && pnpm vitest run components/settings/danger-zone.test.tsx
   ```

   Expected: 21 passed. The modal is not open before the row is pressed; a landed
   request moves the section to the pending state with the server's date.

4. **The endpoint now has a caller, and the exemption is gone**

   ```bash
   cd frontend && pnpm vitest run tests/endpoint-coverage.test.ts
   ```

   Expected: 4 passed. `DECLARED_UNCALLED` no longer mentions
   `POST /api/auth/profile/deletion`, and no orphan appeared.

5. **The whole frontend suite**

   ```bash
   cd frontend && pnpm vitest run
   ```

   Expected: **2831 passed, 0 failed** (175 files). The spacing scale, the token
   contract, the endpoint coverage and the axe-core gates are all in this run.

6. **The whole backend suite, and the import contracts**

   ```bash
   cd backend && uv run pytest -q && cd .. && make lint-backend
   ```

   Expected: **7660 passed, 0 failed**, and **21 contracts kept, 0 broken**.

7. **The contract is the committed OpenAPI**

   ```bash
   cd backend && uv run pytest tests/api/test_contract.py -v
   ```

   Expected: 1 passed. The committed schema equals the live API.

8. **By hand, at `/settings/privacy`**

   - Click **"Delete account →"**. **A centred dialog opens, dimmed and blurred, with
     three paragraphs, a "Type DELETE to confirm" input and two buttons.**
   - Type `delete` (lowercase). **The primary stays disabled.** Type `delete ` with a
     trailing space — **still disabled.** Type `DELETE` — **it enables.**
   - Press Tab at the last control and Shift+Tab at the first. **The focus stays inside
     the dialog.**
   - Press Escape. **The dialog closes and the focus returns to the row you came from.**
   - Open it again, type `DELETE`, press **"Start 30-day deletion"**. **The section
     becomes "Deletion scheduled", naming the date the server computed, with a "Keep my
     account" button.**
   - Press **"Keep my account"**. **The request row comes back, and the reassurance
     says nothing was deleted.**
   - **Check your inbox.** The confirmation mail says what the deletion removes and
     what survives, using **the same two sentences the modal showed**, and its link
     cancels the deletion.

## Test Coverage

- **Tests added across the run: 56 in this item** (9 backend, 47 frontend), and 131
  across the four items.
- **Full frontend suite: 2831 passed, 0 failed** (175 files).
- **Full backend suite: 7660 passed, 0 failed** (15m14s) — 7651 before this item, plus
  the 9 new.
- **`make lint-backend`: 21 contracts kept, 0 broken.**
- **`tsc --noEmit`, `eslint`, `prettier`: clean** on this item's files.
- **Mutation probes: four, all detected** — the case-insensitive gate, the modal
  closing itself on a failure, the copy drifting from the API, and the focus trap
  removed.

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] The contract regenerated and the endpoint coverage checked
- [x] Developer notes captured
- [ ] **One follow-up recorded, not fixed** — after a successful deletion, the row that
      held the focus unmounts and the reader is dropped to the top of the document. The
      same shape applies to the cancellation path. **Changing the focus management
      inside this item would be a silent behavioural change to a surface that was
      already shipped and reviewed**, so it is recorded in
      `review-report-confirmation-surface.md` rather than taken.

## Developer Notes

**The mutation probe that survived, and what it cost.** The first version of the
modal's failure test mocked `onClose` and never inspected the mock — so a modal that
closed itself on a failed request **passed**. The dialog was still on screen because
the *container* had not closed it, not because the modal had not asked. **"The modal
did not close" and "the modal did not *ask* to close" are different claims**, and only
the second one is about this island's behaviour.

The general form of it is worth carrying forward: **a test that mocks a collaborator
and then never inspects the mock is testing half the contract.** `onRequested` was
already asserted with its argument; `onClose` was not — and the difference is exactly
where the bug was.

**Other gotchas this run paid for:**

- **`mt-5` and `pt-5` generate no CSS at all.** `styles/tokens.css` resets Tailwind's
  spacing multiplier and declares only DESIGN.md's steps (0, 1, 2, 3, 4, 6, 8, 12, 16,
  20, 30). A dialog with those classes would have had a button with no padding above
  it. **`tests/spacing-scale.test.ts` caught it** — and it is worth running on any new
  component before the suite, because the failure is invisible in a browser.
- **`@testing-library/user-event` is not installed.** `fireEvent` is the house tool.
- **The API's error shape is `{ code, message }`, not `{ detail }`.** `readApiError`
  recognises the project's shape and returns the offline fallback for anything else —
  so a test that mocks `{ detail: "..." }` sees the *offline* message and will look
  like a quoting bug when it is a fixture bug.
- **Non-null assertions are forbidden** by the eslint config, including in tests.
  `document.getElementById(id)` returns `HTMLElement | null`, so the id has to be
  checked, not asserted.
- **Two pytest runs against the same test database will collide.** A background suite
  still alive when a foreground one starts produces thousands of errors that look like
  broken code. **The symptom is 7000+ errors and zero failures; the individual files
  all pass in isolation.**
- **One frontend test failed once in eight full-suite runs and did not reproduce.** The
  file was not named in the output; **seven subsequent full runs and five isolated runs
  of this item's two files were all clean.** Both new files assert on `document.body`
  (the axe-core gate) and on `document.activeElement` (the focus tests), so a
  cross-file jsdom interaction is the plausible shape — **but that is a hypothesis, not
  a finding.** **Capture the failing file's name if it happens again; a grep that
  filters on `❯` and `FAIL` is not enough.**
- **The endpoint-coverage matcher needs the method and the path adjacent** —
  `\.${method}\s*\(\s*"${route}"`. A path held in a variable is invisible to it, and
  the exemption it replaces would then be hiding a real gap.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-054*
