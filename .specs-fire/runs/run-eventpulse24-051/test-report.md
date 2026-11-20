---
run: run-eventpulse24-051
work_item: avatar-model-and-command
intent: account-profile-expansion
generated: 2026-11-19
status: passed
---

# Test Report: The Picture the Account Holds — One Field, Two Commands

## Summary

| Category | Passed | Failed | Skipped |
|----------|--------|--------|---------|
| Backend (full suite) | **7522** | 0 | 0 |
| `tests/identity/test_avatar.py` | 16 | 0 | 0 |
| `tests/identity/` | 519 | 0 | 0 |

Up from 7502. `lint-imports`: **21 contracts kept, 0 broken** — the twenty-first is the new
`image-decoder` fence.

## Acceptance Criteria Validation

- ✅ **`User` gains an avatar key field: blank, not null**, `""` meaning "no picture set", with the rationale in the model docstring
- ✅ **One forward-only migration** — `0007_user_avatar_key`. The retention category is declared on `User` itself (`ACCOUNT_IDENTITY`), which the picture belongs to
- ✅ **`set_user_avatar` writes the key inside `transaction.atomic(using=PERSONAL)`**
- ✅ **Replacing removes the previously stored object** — probed *in the store*, not inferred from the row: `stored(first) is None` after a replace
- ✅ **`clear_user_avatar` blanks the key and removes the object**
- ✅ **A non-image is refused with a 422-mapped `ValidationError`, nothing is stored, and an existing picture is left intact** — the last clause has its own test
- ✅ **A payload over the cap is refused without being read whole** — asserted by counting what the command actually read: `bytes_read <= AVATAR_MAX_BYTES + 1` against a payload twice the cap
- ✅ **A counterfeit is refused** — a valid PNG signature on a non-PNG body, so anything sniffing only the magic number would accept it
- ✅ **Both commands write an audit row in the same transaction, carrying action and target only** — `details == {}`, and the key asserted absent (AD-13)
- ⚠️ **Account deletion removes the stored object** — **cannot be met; split to `account-deletion-and-avatar-removal`.** Nothing deletes an account: no command, no endpoint, no UI. Recorded in the model docstring rather than passed silently
- ✅ **The user's data export covers the picture** — `avatar_key` is a concrete field matching no redaction rule, so `_row_to_dict` exports it with no code. The work item permits "the picture **or a reference to it**"
- ✅ **`tests/architecture/test_no_direct_writes.py` stays green**
- ✅ **Every test can fail** — see below

## Every security property was mutation-probed

| Mutation | Result |
|---|---|
| EXIF carried through on save (`exif=…`) | **1 failed** |
| `exif_transpose` removed (orientation dropped, not applied) | **1 failed** |
| Pixel cap disabled | **1 failed** |
| **Format allow-list disabled** | **15 passed — a gap** |
| Allow-list disabled, after the fix below | **1 failed** |

### The gap the probe found, and what it cost to close

**Deleting the format allow-list left every test green.** The SVG and counterfeit payloads
are refused one step earlier — Pillow cannot read them at all — so neither ever exercised
the allow-list. The only case that does is a format Pillow *can* decode and the product
does not accept, and nothing tested one.

Worse, the allow-list was not even the thing refusing such a format: an unlisted format
died on `AVATAR_OUTPUT_FORMAT[source_format]` raising `KeyError`, which the `except` clause
turned into a refusal. **Two gates, where the spare silently hid that the real one was
unreachable.**

Fixed by making the lookup total (`.get(fmt, "PNG")`) so the allow-list alone decides, and
adding `test_a_decodable_format_outside_the_allow_list_is_refused` with a **BMP** —
decodable, and still not a format this product stores. Re-probed: removing the allow-list
now fails.

## Two test-level defects found and fixed

### `transaction.on_commit` never fires under `django_db`

The two delete tests passed nothing: the design deliberately removes the old object in
`transaction.on_commit`, and a `django_db` test's transaction never commits, so the
callback never ran. The tests were asserting against an object that was never going to be
deleted *in the test*, and failing.

Wrapped in `django_capture_on_commit_callbacks(using=PERSONAL, execute=True)`. **The
tempting alternative — deleting inside the transaction so the test passes — is exactly the
bug the ordering exists to prevent**, since a rollback would then destroy the picture the
account still has. That reasoning is written into the test so the shortcut is not taken
later.

### The GPS fixture was malformed and would have passed for the wrong reason

Writing EXIF tag `0x8825` as a scalar produces a block Pillow cannot read back — the first
version of the test crashed reading it. Rebuilt as a real nested GPS IFD and **verified the
input**: `{34853: 26}` on the primary IFD, with `{1: 'N', 2: (51.0, 30.0, 0.0), 3: 'W', 4: (0.0, 7.0, 0.0)}`
inside it. Real coordinates go in; nothing comes out. The orientation fixture was verified
the same way — tag 6 on a 12×6 image, stored 6×12.

## Verification performed

| Check | Result |
|---|---|
| Full backend suite | **7522 passed, 0 failed, 0 skipped** |
| `tests/identity/` | 519 passed |
| `ruff check .` | clean |
| `ruff format --check .` | 694 files formatted |
| `lint-imports` | **21 kept, 0 broken** |
| `manage.py makemigrations --check` equivalent | one migration, forward-only |

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| The format allow-list was not load-bearing; a spare gate masked it | **High** | **Fixed** — single gate, pinned by a BMP test |
| `on_commit` deletes are invisible to `django_db` tests | Medium | **Fixed** with the capture fixture, and the reason written down |
| GPS fixture malformed; test would have passed vacuously | Medium | **Fixed** and the input verified |
| Four contract-count registries asserted exactly 20 | By design | **Updated to 21**, with a note naming the new contract |
| Account deletion does not exist | **High** | **Split** to `account-deletion-and-avatar-removal`; caveat in the model docstring |

## Ready for Completion

- [x] All tests passing — 7522, nothing skipped
- [x] Coverage target met — every security property mutation-probed
- [x] Acceptance criteria validated — 11 of 12; the twelfth split with its own work item
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-051*
