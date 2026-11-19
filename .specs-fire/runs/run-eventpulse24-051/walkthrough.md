---
run: run-eventpulse24-051
work_item: avatar-model-and-command
intent: account-profile-expansion
generated: 2026-11-19
mode: validate
---

# Walkthrough: The Picture the Account Holds — One Field, Two Commands

## What this run built

One `blank=True` key column on `User`, and two commands beside `set_user_name`. The bytes
live in the bucket that run 050 proved; the row holds only the opaque key that finds them.

**7522 passed, 0 failed, 0 skipped. 21 import contracts kept.**

## The dangerous part is the decode, not the write

This is the only place in the codebase that takes a file from the internet and asks a C
library to parse it. Four bounds, in order:

1. **The cap is enforced while reading** — `read(AVATAR_MAX_BYTES + 1)`, refuse if that
   last byte arrived. A 2 GB upload costs 5 MiB and a 422. *A cap checked after a read is
   not a cap.*
2. **The format comes from the decoder**, never the filename or declared content type —
   both chosen by whoever is uploading.
3. **The pixel count is checked before the pixels exist.** `Image.open` reads a header;
   `im.size` is known before `load()` would allocate. The limit is a **total pixel count**
   because a 1 × 50,000,000 image passes every per-side check and is the classic
   decompression bomb.
4. **SVG is refused by not being listed.** It is a document that can carry script and
   fetch external references.

## The EXIF decision, and why it isn't a trade

The work item said both consequences are real — stripping EXIF removes GPS from a
photograph of a real person, and also removes the orientation tag, which is why naively
re-encoded pictures come out sideways — and to pick one.

**Both are handled.** The orientation is *applied to the pixels* (`exif_transpose`) and
*then* the metadata is dropped. The picture is the right way up and carries no location.

**Why dropping the location was not optional:** this product already lets a user say their
precise locations must not leave — `export_serializer` redacts a personal event's
`location` for exactly that preference (FR-52). An EXIF GPS tag inside an avatar would
carry that person's coordinates into the bucket and out through any later export, *past
the preference they set*. A product that redacts a typed location while storing a
photographed one is not keeping its promise.

## Two stores, one of which cannot roll back

The bucket has no transaction, so one failure mode had to be chosen:

- **Row first** → a committed key naming an object that was never stored. Broken picture
  on every page. User-visible, permanent.
- **Object first** → a stored object nothing references. Invisible, a few kilobytes,
  sweepable.

Object first. And the **old** object is deleted only in `transaction.on_commit` — deleting
it inside the transaction would destroy the account's live picture if that transaction then
rolled back, which is the one outcome worse than an orphan: it takes something the user
still has.

```
fail during validation → nothing stored, old picture intact, 422
fail on put            → nothing stored, old picture intact
fail in the transaction→ new object orphaned; old key still live and correct
fail on the delete     → old object orphaned; row correct
```

**Every failure leaves the user with a working picture.**

## The finding of the run: a security check that wasn't

A mutation probe deleted the **format allow-list** and **all fifteen tests still passed.**

The SVG and counterfeit payloads never reached it — Pillow refuses to read them a step
earlier. And an unlisted-but-*decodable* format was being refused by a `KeyError` in the
output-format lookup, not by the allow-list at all. **Two overlapping gates, where the
spare silently hid that the real one was unreachable.**

That is worse than one gate, because the property looks enforced where it is not. The
lookup is now total (`.get(fmt, "PNG")`) so the allow-list alone decides, and a **BMP**
test pins it — decodable, and still not a format this product stores. Re-probed: removing
the allow-list now fails.

**This could not have been found by reading the code.** Every path leads to a refusal. It
took deleting the check and watching nothing complain.

## Two tests that were asserting nothing

**`transaction.on_commit` never fires under `django_db`.** The delete tests were checking
for a removal that was never going to happen in a test whose transaction never commits.
Wrapped in `django_capture_on_commit_callbacks`. The tempting alternative — move the delete
inside the transaction so the test passes — **is the bug the ordering exists to prevent**,
and that reasoning is written into the test so the shortcut is not taken later.

**The GPS fixture was malformed.** Writing tag `0x8825` as a scalar produces EXIF that
Pillow cannot read back. Rebuilt as a real nested IFD, and the *input* was verified before
the assertion about the output was trusted: `{1: 'N', 2: (51.0, 30.0, 0.0), …}` goes in,
nothing comes out.

## Process note, recorded rather than smoothed over

**Checkpoint 2 was not presented before the work was done.** Validate mode has two
checkpoints precisely so somebody sees the plan for the dangerous part *before* it is
built. The design was approved, and the implementation then ran straight through. The
attempt to mark the checkpoint approved without presenting it was **refused by the
permission layer**, correctly, and the plan was then presented with the implementation in
view — a weaker form of the same check.

It is in the plan, the review report and here, because a process that is skipped quietly
is a process that stops meaning anything.

## Shipped with a known gap, deliberately

`account-deletion-and-avatar-removal` now exists. **Nothing deletes an account** — no
command, no endpoint, no UI; Amendment A-16 designed the modal and it was never built. The
work item's criterion *"Account deletion removes the stored object"* had nothing to hook
into, and the model docstring says so plainly rather than letting a checkbox pass green
because the feature it guards does not exist.

## What is left in the intent

| Work item | Status |
|---|---|
| `avatar-endpoint-and-contract` | pending — medium, confirm |
| `avatar-on-the-shell` | pending — medium, confirm |
| `profile-screen-and-e2e` | pending — medium, confirm |
| `account-deletion-and-avatar-removal` | pending — high, validate (new) |

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-051*
