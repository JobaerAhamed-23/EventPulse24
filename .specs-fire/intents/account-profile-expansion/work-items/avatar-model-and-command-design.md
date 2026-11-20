---
work_item: avatar-model-and-command
intent: account-profile-expansion
created: 2026-11-19
mode: validate
checkpoint_1: approved
---

# Design: The Picture the Account Holds — One Field, Two Commands

## Summary

One `blank=True` field on `User` holding an **opaque key**, and two commands beside
`set_user_name` in `apps/identity/services/`. The bytes live in the bucket that
`object-storage-and-minio` just proved; the row holds only the key that finds them.

The hard part is not the field. It is that **this command accepts a file from the
internet and decodes it** — the most dangerous thing this codebase does — and that **two
stores must agree with no shared transaction.**

## Scope

**In Scope:** the `avatar_key` field and its migration; `set_user_avatar` and
`clear_user_avatar`; byte-level validation; the re-encode decision; the write-ordering
decision; audit rows; export coverage.

**Out of Scope:** the HTTP endpoint and its contract (`avatar-endpoint-and-contract`);
any UI; **account deletion**, which does not exist — see below.

## Two findings that change this item

### 1. One acceptance criterion cannot be met: there is no account deletion

> - [ ] Account deletion removes the stored object

**Nothing deletes an account.** No service in `apps/identity/services/`, no endpoint, no
UI — `grep` finds no `delete_account`, and `frontend/components/settings/` has no delete
or danger-zone component. Amendment A-16 designed a confirmation modal with a 30-day
grace period; it was never built.

So this criterion has nothing to hook into. **It is not dropped** — it is split to
`account-deletion-and-avatar-removal`, because *"a picture that survives account deletion
is the single worst outcome available here"* is exactly right, and the way to honour it is
to make it the explicit acceptance criterion of the item that builds deletion, rather than
a checkbox that silently passes here because the feature it guards does not exist.

**This item must not pretend otherwise.** The model docstring states that the key's
lifetime is bounded by an account-deletion path that is not yet built.

### 2. There is no image decoder, and the stdlib no longer has one

`import PIL` fails, and **`imghdr` was removed in Python 3.13** (this project runs
3.13.15). The object-storage design already flagged this as this item's bill: *"a decoder
for sniffing and dimensions, and that is a second dependency decision with its own CVE
history."*

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Image decoding | **Pillow, version-pinned** | The item requires sniffing *from the bytes*, dimensions *before storing*, and an EXIF decision — all three need a decoder. Hand-rolled header parsing gives sniffing and dimensions but **no re-encode and no decompression-bomb guard**, and a bespoke parser that mis-handles a crafted PNG is a worse outcome than a well-known dependency with a known CVE history and a patch stream. Pillow's `MAX_IMAGE_PIXELS` and `verify()` are precisely the defences this needs. |
| Re-encode? | **Yes — transpose by EXIF orientation, then drop all metadata** | The work item says both consequences are real and to pick one. **Both are addressed instead of traded:** orientation is *applied* to the pixels before the metadata is discarded, so re-encoded pictures are not sideways, and GPS leaves with everything else. |
| Why stripping EXIF is not optional | **The export already honours a location preference** | `export_serializer._row_to_dict` redacts `location` when the user opted out of sharing precise location (FR-52). An EXIF GPS tag inside an avatar would carry a real person's coordinates into the bucket and out through any later export, **past the preference they set**. A product that redacts a typed location while storing a photographed one is not keeping its promise. |
| Allowed types | **PNG, JPEG, WebP, GIF — raster only. SVG refused.** | SVG is a document that can carry script and external references. It is not in the same category as the others, and "image" in a filename does not make it one. |
| Write order | **Object first; key written inside the transaction; old object deleted *after* commit** | The bucket has no rollback, so one of two failures must be chosen. DB-first leaves a key pointing at nothing — **a broken avatar on every page, user-visible and permanent**. Storage-first leaves an orphaned object — invisible, harmless, and sweepable. Choose the invisible failure. Deleting the *old* object before commit would destroy the live picture if the transaction then rolled back, so that delete waits for `transaction.on_commit`. |
| Key scheme | **`avatars/<uuid4 hex>`, fresh on every upload** | Opaque, carries no user id, no email and no filename (AD-13). Unguessable. **Never overwritten in place**, so there is no window in which the stable app-owned URL could serve a half-written object, and a replace is always store-new-then-delete-old. |
| The field | `avatar_key = CharField(max_length=…, blank=True, default="")` | `User.name`'s precedent exactly: `""` is the single "no picture set" state, so "cleared" and "never set" are one state. The length is read from `ports.blob.MAX_KEY_LENGTH`, not written out again, for the same reason `NAME_MAX_LENGTH` is read from the field. |
| Cap enforcement | **Read at most `cap + 1` bytes; refuse if `cap + 1` arrived** | *"A cap checked after a read is not a cap."* The command never materialises more than one byte over the limit, so a 2 GB upload costs 5 MiB of memory and a refusal. |
| Size and dimension caps | **5 MiB, 4096 × 4096** | A profile picture rendered at 96 px has no honest need of more, and both numbers bound the decoder's work on untrusted input. Declared in `shared/constants.py` so the API layer and the UI copy quote the same figure. |
| Export coverage | **The key, automatically** | `_row_to_dict` walks concrete fields and `avatar_key` matches no redaction rule, so it exports with no code. The work item allows *"the picture **or a reference to it**"*; the key is that reference. |
| Audit details | `details={}` | `set_user_name`'s precedent and AD-13: the action names the account, the row is one lookup away. **The key must not appear** — it is the address of a photograph of a real person. |

## Data Models Affected

### Modifies

- **`User`**: `+ avatar_key` — `CharField(max_length=MAX_KEY_LENGTH, blank=True, default="")`.
  One forward-only migration. The model already declares
  `retention_category = RetentionCategory.ACCOUNT_IDENTITY` (AD-15), and the picture
  belongs to that category: it is account identity, not account content.

## Technical Approach

```
  set_user_avatar(user_id, upload)
      │
      ├─ 1. read ≤ cap+1 bytes ............... refuse 422 if cap+1 arrived
      ├─ 2. Pillow: open + verify ............ refuse 422 if not a decodable raster
      ├─ 3. check format in allow-list ....... refuse 422 (SVG, PDF, anything else)
      ├─ 4. check dimensions ................. refuse 422 if over 4096²
      ├─ 5. exif_transpose, re-encode ........ orientation applied, metadata dropped
      │        ── nothing has been stored and the old key is untouched ──
      ├─ 6. blob.put(new_key, bytes) ......... the bucket now holds the new object
      ├─ 7. transaction.atomic(PERSONAL):
      │        user.avatar_key = new_key
      │        write_audit(action="user_avatar_set", details={})
      │     ── commit ──
      └─ 8. on_commit: blob.delete(old_key) .. only now is the old picture gone

  Failure at 1-5  → nothing stored, old picture intact, 422 to the caller
  Failure at 6    → nothing stored, old picture intact
  Failure at 7    → the new object is an ORPHAN; the old key is still live and correct
  Failure at 8    → the old object is an ORPHAN; the row is correct
```

**Every failure leaves the user with a working picture.** The only cost of a failure is an
orphaned object, which is invisible to the user and removable by a sweep.

`clear_user_avatar` is the same shape without steps 1–6: blank the key and audit inside
the transaction, delete the object on commit.

## Affected Files

| File | Action | Purpose |
|------|--------|---------|
| `backend/apps/identity/models.py` | Modify | `avatar_key`, with the blank-not-null rationale and the deletion caveat |
| `backend/apps/identity/migrations/00XX_user_avatar_key.py` | Create | Forward-only |
| `backend/apps/identity/services/avatar.py` | Create | `set_user_avatar`, `clear_user_avatar` |
| `backend/apps/identity/services/__init__.py` | Modify | Publish the two commands |
| `backend/shared/constants.py` | Modify | `AVATAR_MAX_BYTES`, `AVATAR_MAX_PIXELS`, `AVATAR_ALLOWED_FORMATS` |
| `backend/pyproject.toml` | Modify | Pillow, pinned; an import contract keeping PIL out of `domain/` |
| `backend/tests/identity/test_avatar.py` | Create | Including a real counterfeit and a bomb |
| `.specs-fire/.../work-items/account-deletion-and-avatar-removal.md` | Create | The split criterion |

## Security Considerations

- **Decoding untrusted bytes**: bounded before the decoder runs (cap), bounded during
  (`Image.MAX_IMAGE_PIXELS` against decompression bombs), bounded after (dimension check).
- **Counterfeits**: the format comes from Pillow's own identification, never the filename
  or the declared content type. A test uses a **real counterfeit** — a valid image header
  on a payload that is not that image — not merely a renamed `.txt`.
- **EXIF**: stripped, as argued above.
- **Keys carry nothing**: no user id, no filename, no email (AD-13).
- **Pillow is a C extension with CVE history**: pinned, confined to `identity` by an
  import contract, and never handed bytes that have not already passed the size cap.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Orphaned objects accumulate | Low | Deliberate and named: the chosen failure mode. A sweep is a later item; the alternative (broken avatars) is worse and user-visible. |
| Pillow CVE | Medium | Pinned; untrusted bytes are size-capped before it sees them; pixel cap set; confined by an import contract. |
| Re-encoding changes the user's bytes | Low | True and intended — what is stored is not byte-identical to what was uploaded. Stated in the docstring so nobody later "fixes" it. |
| A picture outlives a deleted account | **High** | **Not solved here, and said so.** No deletion path exists. Split to its own work item with this as its criterion, and recorded in the model docstring. |
| Avatars in the export are opaque keys | Low | The work item permits a reference. If the picture itself is later wanted in the export, that is an export-machinery item. |

## Implementation Checklist

- [ ] Add Pillow to `pyproject.toml`, pinned, with an import contract keeping it out of `domain/`
- [ ] `AVATAR_MAX_BYTES`, `AVATAR_MAX_PIXELS`, `AVATAR_ALLOWED_FORMATS` in `shared/constants.py`
- [ ] `User.avatar_key`, blank-not-null, docstring carrying the rationale **and** the deletion caveat
- [ ] One forward-only migration
- [ ] `services/avatar.py`: both commands, the ordering argument in the module docstring
- [ ] Validation: cap while reading, decode, format allow-list, dimensions, transpose, strip
- [ ] Old object deleted in `transaction.on_commit`, never before
- [ ] Audit rows inside the transaction, `details={}`
- [ ] Tests: refusal leaves the old picture intact; replace removes the old object (probed in the bucket); a real counterfeit; a decompression bomb; an oversized payload never read whole
- [ ] Every test probed by mutation
- [ ] `tests/architecture/test_no_direct_writes.py` green; `lint-imports` green
- [ ] Create `account-deletion-and-avatar-removal` work item

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-11-19*
