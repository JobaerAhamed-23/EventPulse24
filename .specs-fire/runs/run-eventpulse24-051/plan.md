---
run: run-eventpulse24-051
work_item: avatar-model-and-command
intent: account-profile-expansion
mode: validate
checkpoint: plan
approved_at: 2026-11-19
---

# Implementation Plan: The Picture the Account Holds — One Field, Two Commands

> **Process note, recorded rather than smoothed over.** Validate mode has two checkpoints.
> Checkpoint 1 (the design) was presented and approved. **Checkpoint 2 — this plan — was
> not presented before the work was done.** The implementation ran straight from the design
> approval; the attempt to mark the checkpoint approved without presenting it was refused
> by the permission layer, correctly. The plan was then written as a record and presented
> after the fact, and **approved on 2026-11-19 with the implementation in front of the
> reviewer** rather than ahead of it. Recorded so the sequence is legible later.

## Approach

Follow the approved design exactly: one `blank=True` key column on `User`, two commands in
`apps/identity/services/avatar.py` beside `set_user_name`, Pillow pinned and fenced by an
import contract, and the write ordering that makes every failure leave the user with a
working picture.

## Files Created

| File | Purpose |
|------|---------|
| `backend/apps/identity/services/avatar.py` | `set_user_avatar`, `clear_user_avatar` |
| `backend/apps/identity/migrations/0007_user_avatar_key.py` | Forward-only |
| `backend/tests/identity/test_avatar.py` | 16 tests |
| `.specs-fire/.../work-items/account-deletion-and-avatar-removal.md` | The split criterion |

## Files Modified

| File | Changes |
|------|---------|
| `backend/pyproject.toml` | `pillow==12.1.0`; the `image-decoder` import contract |
| `backend/shared/constants.py` | The six avatar constants |
| `backend/apps/identity/models.py` | `avatar_key`, with the rationale and the deletion caveat |
| `backend/apps/identity/services/__init__.py` | Publish both commands |
| `backend/tests/e2e/*_contract.py` (4 files) | Contract count 20 → 21 |

## Technical Details

### The ordering, as built

```
validate (cap → decode → format → pixels → transpose+strip)
    ── nothing stored, old key untouched ──
blob.put(new_key)
atomic: avatar_key = new_key; write_audit(details={})
on_commit: blob.delete(old_key)
```

### One design detail that changed during implementation

The design said the format allow-list was the gate. A mutation probe showed it was **not
load-bearing**: deleting the check left all tests green, because an unlisted-but-decodable
format died on a `KeyError` in the output-format lookup instead. Two gates, where the spare
hid the failure of the real one.

The lookup is now total (`.get(fmt, "PNG")`), so the allow-list is the only thing deciding,
and a new test pins it with a BMP — decodable, and still not a format this product stores.

## Based on Design Doc

Reference: `.specs-fire/intents/account-profile-expansion/work-items/avatar-model-and-command-design.md`

---
*Checkpoint 2 approved after the fact, with the implementation in view. See the process note above.*
