---
id: avatar-model-and-command
title: The Picture the Account Holds — One Field, Two Commands
intent: account-profile-expansion
complexity: high
mode: validate
status: pending
depends_on:
  - object-storage-and-minio
created: 2026-11-19
---

# Work Item: The Picture the Account Holds — One Field, Two Commands

## Description

**What the account stores is a key, not an image.** The bytes live in the bucket; the
row holds the opaque key that finds them. The field follows `User.name`'s precedent
exactly: **blank, not null** — `""` is the single "no picture set" state, and "cleared"
and "never set" are one state, not two.

**Two commands, in `backend/apps/identity/services/`** (AD-5), beside `set_user_name`:

- `set_user_avatar(*, user_id, upload)` — validates, stores the object, writes the key,
  **and removes the object the previous key pointed at**. A replaced picture that stays
  in the bucket is a picture of a real person the product has promised to stop holding.
- `clear_user_avatar(*, user_id)` — blanks the key and removes the object.

**Validation is the security half of this item, and it is not a file-extension check.**
A filename says nothing; the bytes do. The content type is **sniffed from the bytes**,
the dimensions are read before anything is written, and the declared size cap is
enforced **while reading**, not after — a cap checked after a read is not a cap. A file
that is not an image, or is too large, is refused with a `domain.errors.ValidationError`
(mapped to 422) **before** anything is stored and **before** the old key is touched.

**Retention and export are part of this item, not a follow-up** (AD-15, FR-52):
deleting an account removes the object, and the user's data export includes the picture
or a reference to it. A picture that survives account deletion is the single worst
outcome available here.

## Acceptance Criteria

- [ ] `User` gains an avatar key field: **blank, not null**, with `""` meaning "no
      picture set", documented in the model docstring with that rationale
- [ ] One forward-only migration, declaring the field's retention category (AD-15)
- [ ] `set_user_avatar` stores the object and writes the key **inside
      `transaction.atomic(using=PERSONAL)`** (AD-3)
- [ ] Replacing a picture **removes the previously stored object**; a probe asserts the
      old key is gone from the bucket
- [ ] `clear_user_avatar` blanks the key **and** removes the object
- [ ] A non-image payload is refused with a 422-mapped `ValidationError`, **nothing is
      stored**, and an existing picture is **left intact**
- [ ] A payload over the cap is refused **without being read whole into memory**
- [ ] A payload whose extension says image and whose bytes do not is **refused** —
      asserted with a real counterfeit, not a renamed text file alone
- [ ] Both commands write an audit row in the same transaction, and the details carry
      **the action and the target id only** — no key, no filename, no email (AD-13)
- [ ] Account deletion removes the stored object
- [ ] The user's data export covers the picture
- [ ] `tests/architecture/test_no_direct_writes.py` stays green
- [ ] Every test can fail — verified by a mutation probe per test

## Technical Notes

- **Copy `services/profile.py`'s shape**, which holds `set_user_name` and is the house
  pattern: one module, named commands, the rationale in the docstring, the audit write
  inside the same transaction.
- **The storage write and the database write cannot both be transactional.** The bucket
  has no rollback. Decide and record which happens first and what the failure leaves
  behind — a committed key pointing at an object that was never stored is a broken
  avatar on every page, and an orphaned object is a leak. **State the choice in the
  docstring.**
- **Decide whether the image is re-encoded.** Stripping EXIF removes GPS coordinates
  from a photograph of a real person; it also removes orientation, which is why
  re-encoded pictures appear sideways. Both consequences are real; pick one and say why.
- **No PII in the object key** (AD-13) — the key is opaque.
- **`personalization` is not reached into** (AD-2/AD-16). This is `identity`'s field.

## Dependencies

- `object-storage-and-minio` — there is nowhere to put the bytes until it lands.
