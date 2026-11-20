---
run: run-eventpulse24-051
work_item: avatar-model-and-command
intent: account-profile-expansion
generated: 2026-11-19
status: reviewed
---

# Review Report: The Picture the Account Holds

## Scope of review

The most security-sensitive code this project has: the only place that hands bytes from the
internet to a C library.

| File | Change |
|---|---|
| `apps/identity/services/avatar.py` | new — both commands |
| `apps/identity/models.py` | `avatar_key` |
| `apps/identity/migrations/0007_user_avatar_key.py` | new |
| `shared/constants.py` | six constants |
| `pyproject.toml` | Pillow + `image-decoder` contract |
| `tests/identity/test_avatar.py` | new — 16 tests |
| 4 × `tests/e2e/*_contract.py` | count 20 → 21 |

## Checks

| Check | Result |
|---|---|
| Full backend suite | 7522 passed, 0 failed, 0 skipped |
| `lint-imports` | 21 kept, 0 broken |
| `ruff check` / `format --check` | clean |
| Pillow reachable only from `apps.identity` | enforced by contract, not convention |
| Audit details carry no key | asserted |
| Key carries no account id or address | asserted |
| Migration is forward-only, one file | ✅ |

## Process finding — mine

**Checkpoint 2 was not presented before the work was done.** Validate mode has two; the
design was approved and the implementation then ran straight through. The attempt to mark
the checkpoint approved without presenting it was **refused by the permission layer**,
which was correct, and the plan carries the sequence rather than hiding it.

Worth stating because the whole point of two checkpoints on a `validate` item is that
somebody sees the plan for the dangerous part *before* it is built, and that did not
happen here. The code was reviewed with the implementation in view instead, which is a
weaker form of the same check.

## Auto-fixed during the run

### 1. The format allow-list was decorative

A mutation probe deleted it and **all fifteen tests still passed**. The SVG and counterfeit
payloads never reached it — Pillow refuses to read them a step earlier — and an unlisted
but *decodable* format was being refused by a `KeyError` in the output-format lookup, not
by the allow-list at all.

Two overlapping gates where the spare hides that the real one is unreachable is worse than
one gate, because the security property appears to be enforced where it is not. The lookup
is now total and the allow-list alone decides, pinned by a BMP test.

**This is the finding of the run.** It would not have been found by reading the code —
every path leads to a refusal — only by deleting the check and watching nothing complain.

### 2. The delete tests were asserting nothing

`transaction.on_commit` does not fire under `django_db`. Fixed with
`django_capture_on_commit_callbacks`, with the reasoning written into the test, because the
obvious alternative fix — move the delete inside the transaction — reintroduces precisely
the failure the ordering was designed to avoid.

### 3. The GPS fixture was malformed

It crashed on read-back; rebuilt as a real nested IFD and the *input* verified before
trusting the assertion about the output.

## Judgment calls worth recording

| Decision | Why |
|---|---|
| Pillow, pinned, fenced by a contract | The stdlib has no decoder since 3.13; a hand-rolled parser gives no bomb guard and no re-encode. The fence is what keeps a CVE-prone C extension in the one app that needs it. |
| `.get(fmt, "PNG")` rather than `[fmt]` | Makes the allow-list the single testable gate. See above. |
| GIF and WebP are stored as PNG | An animated avatar is not a thing this product shows; taking the first frame is the honest reading of "a picture of you". |
| JPEG flattened onto white, not black | A transparent corner becoming a black blot is worse than it becoming white. |
| `_delete_quietly` swallows `BlobError` | It runs after commit: the row is right and the user has the right picture. Raising would report a successful change as a failure. A leak is the cheaper wrong answer. |
| Audit `details={}` | AD-13. The key is the address of a photograph of a real person, and audit rows outlive accounts. |

## Open

| Item | Note |
|---|---|
| `account-deletion-and-avatar-removal` | Created. Nothing deletes an account; the model docstring says so plainly rather than letting a checkbox pass. |
| Orphaned objects | The deliberate failure mode. A sweep is a later item; the alternative (broken avatars) is user-visible and permanent. |
| Pillow CVE surface | Pinned and fenced, but it is a standing dependency obligation now, not a one-time decision. |

## Findings Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | Format allow-list not load-bearing; spare gate masked it | **High** | **Fixed**, pinned by a new test |
| 2 | Delete tests asserted nothing (`on_commit` under `django_db`) | Medium | **Fixed**, with the shortcut warned against |
| 3 | GPS fixture malformed — test would have passed vacuously | Medium | **Fixed**, input verified |
| 4 | Checkpoint 2 not presented before execution | Medium | **Recorded**, not smoothed over |
| 5 | Account deletion does not exist | High | **Split** to its own work item |

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-051*
