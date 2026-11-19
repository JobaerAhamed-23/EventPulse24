"""The account's profile picture: the two commands that write it (AD-5).

`set_user_avatar` stores a picture and `clear_user_avatar` removes it. They sit beside
`set_user_name` because they change the same thing — what an account says about itself —
and they are the only doors to the `avatar_key` column.

**What is stored is a key, not an image.** The bytes go to the bucket through
`ports.blob`; the row holds the opaque key that finds them.

## The dangerous part is the decode, not the write

This is the only place in the codebase that takes a file from the internet and asks a C
library to parse it. Everything in `_decoded` exists to bound that:

1. **The size cap is enforced while reading.** `_read_capped` asks for at most
   `AVATAR_MAX_BYTES + 1` bytes and refuses if that last byte arrived. A cap checked after
   a read is not a cap — it is a way to find out you have already allocated two gigabytes.
2. **The format comes from the decoder, never from the caller.** Not the filename, not the
   declared content type: both are chosen by whoever is uploading. A payload whose name
   says `.png` and whose bytes are a GIF is identified as a GIF; a payload whose bytes are
   not an image at all is refused.
3. **The pixel count is checked before the pixels are produced.** `Image.open` reads a
   header and does not decode; `im.size` is therefore known before `load()` would allocate.
   A 1 x 50,000,000 image passes every per-side check and is the classic decompression
   bomb, which is why the limit is a **total pixel count**.
4. **SVG is refused by not being in the allow-list.** It is a document that can carry
   script and fetch external references. The word "image" in a filename does not make it
   one.

## The picture is re-encoded, and the EXIF is dropped

**Both consequences the work item names are real, and both are handled rather than
traded.** Stripping EXIF removes GPS coordinates from a photograph of a real person; it
also removes the orientation tag, which is why naively re-encoded pictures appear
sideways. So the orientation is **applied to the pixels** (`ImageOps.exif_transpose`)
*before* the metadata is discarded: the picture is the right way up and carries no
location.

**Why dropping the location is not optional here.** This product already lets a user say
their precise locations must not leave — `export_serializer` redacts a personal event's
`location` for exactly that preference (FR-52). An EXIF GPS tag inside an avatar would
carry that person's coordinates into the bucket and out through any later export, *past
the preference they set*. A product that redacts a typed location while storing a
photographed one is not keeping its promise.

**What is stored is therefore not byte-identical to what was uploaded**, and that is
deliberate. Do not "fix" it.

## Two stores, one of which cannot roll back

The bucket has no transaction. A write to it and a write to Postgres cannot both be undone
together, so one failure mode must be chosen deliberately:

- **Row first, object second** — a commit that names an object which was never stored. The
  key is live, every page asks for it, and every page gets a broken picture. User-visible,
  permanent, and only fixable by hand.
- **Object first, row second** — a stored object that nothing references. Invisible to the
  user, costs a few kilobytes, and is removable by a sweep.

**The second is chosen.** The order is: store the new object, then write the key inside
`transaction.atomic`. If the transaction fails, the new object is an orphan and the account
keeps the picture it had.

**And the old object is deleted only after the row commits** — `transaction.on_commit`.
Deleting it inside the transaction would destroy the account's live picture if that
transaction then rolled back, which is the one failure worse than an orphan: it takes
something the user still has.
"""

import hashlib
import io
from uuid import UUID, uuid4

from django.db import transaction

from apps.identity.models import User
from apps.identity.services import audit as audit_service
from domain.errors import ValidationError
from ports.blob import BlobPort, StoredBlob
from ports.registry import get_adapter
from shared.actor import Actor
from shared.constants import (
    AVATAR_ALLOWED_FORMATS,
    AVATAR_CONTENT_TYPE,
    AVATAR_KEY_PREFIX,
    AVATAR_MAX_BYTES,
    AVATAR_MAX_PIXELS,
    AVATAR_OUTPUT_FORMAT,
)
from shared.db import PERSONAL

#: What the person who typed it is told. One sentence, no jargon, no byte counts in
#: machine units — the caller knows the cap and can say "5 MB" in the words it chose.
_NOT_AN_IMAGE = "That file isn't an image we can read. Try a PNG, JPEG, WebP or GIF."
_TOO_LARGE = "That picture is too large."
_TOO_MANY_PIXELS = "That picture's dimensions are too large."


def _refuse(message: str, field: str = "avatar") -> ValidationError:
    """A refusal shaped the way `config/errors.py` maps to a 422."""
    return ValidationError(
        message,
        details={"errors": [{"loc": [field], "msg": message}]},
    )


def _read_capped(upload) -> bytes:
    """At most `AVATAR_MAX_BYTES + 1` bytes, then a refusal if that last byte arrived.

    **The extra byte is the whole point.** Reading exactly the cap cannot distinguish a
    file that is exactly at the limit from one that is far over it; reading one more can,
    and costs one more byte.

    Raises:
        ValidationError: The upload is over the cap. Nothing has been stored.
    """
    data = upload.read(AVATAR_MAX_BYTES + 1)
    if len(data) > AVATAR_MAX_BYTES:
        raise _refuse(_TOO_LARGE)
    return data


def _decoded(data: bytes) -> tuple[bytes, str]:
    """The picture as it will be stored, and its content type.

    Identifies the format from the bytes, bounds the pixels, applies the orientation and
    drops every piece of metadata.

    Raises:
        ValidationError: The bytes are not a readable image of an allowed format, or the
            image is too large to decode. Nothing has been stored.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        probe = Image.open(io.BytesIO(data))
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise _refuse(_NOT_AN_IMAGE) from exc

    source_format = (probe.format or "").upper()
    if source_format not in AVATAR_ALLOWED_FORMATS:
        raise _refuse(_NOT_AN_IMAGE)

    # `Image.open` has read a header, not the pixels — so the size is known before
    # anything the size would cost has been spent. This is the bomb guard.
    width, height = probe.size
    if width * height > AVATAR_MAX_PIXELS:
        raise _refuse(_TOO_MANY_PIXELS)

    try:
        # Re-opened because `exif_transpose` needs an image that has not been consumed by
        # a verify pass, and because the probe above is only trusted for its header.
        with Image.open(io.BytesIO(data)) as image:
            upright = ImageOps.exif_transpose(image) or image
            # **`.get` with a default, not `[...]`, and that is deliberate.** A
            # `KeyError` here would also refuse an unlisted format — but by accident,
            # as a second gate masking the first. A mutation probe showed exactly that:
            # deleting the allow-list check above left every test passing, because a
            # decodable-but-unlisted format (BMP, TIFF) died on this lookup instead. One
            # gate that is tested beats two where the spare hides the failure of the real
            # one, so the allow-list is now the only thing deciding, and
            # `test_a_decodable_format_outside_the_allow_list_is_refused` pins it.
            target = AVATAR_OUTPUT_FORMAT.get(source_format, "PNG")
            if target == "JPEG" and upright.mode not in ("RGB", "L"):
                # JPEG has no alpha channel. Flattening onto white is a decision: the
                # alternative is black, which turns a transparent corner into a blot.
                upright = upright.convert("RGB")
            elif target == "PNG" and upright.mode == "P":
                upright = upright.convert("RGBA")

            out = io.BytesIO()
            # No `exif=`, no `icc_profile=`, no `pnginfo=`: the metadata is dropped by not
            # being carried over. The orientation already moved into the pixels above.
            upright.save(out, format=target)
    except (OSError, ValueError) as exc:
        raise _refuse(_NOT_AN_IMAGE) from exc

    return out.getvalue(), AVATAR_CONTENT_TYPE[target]


#: How many hex characters of the digest make a version segment.
#:
#: Sixteen is 64 bits — far more than enough to make two of a user's own successive
#: pictures differ, which is the only collision that matters here. The version is not a
#: secret and not an authorisation: the handler checks it against the caller's *own*
#: stored key, so guessing one buys nothing.
_VERSION_LENGTH = 16


def version_of(key: str) -> str:
    """The URL segment that stands for this stored key.

    **A digest of the key, not the key itself.** The key is already opaque and the bucket
    is private, so publishing it would probably be harmless — but "probably harmless" is
    not a reason to put the address of a stored object into every page's HTML. A digest
    costs nothing and means a URL that leaks tells an attacker nothing about where the
    bytes are.

    **It derives from the key, which is what makes the cache correct.** Replacing a
    picture mints a new key, so the version changes, so the URL changes, so the browser
    fetches the new picture without any cache-busting query string. A version derived from
    the *user* instead would be stable across a replace, and every reader would keep the
    old picture until their cache expired.

    `""` for no key: an account with no picture has no version, not a version of nothing.
    """
    if not key:
        return ""
    return hashlib.blake2s(key.encode("utf-8"), digest_size=_VERSION_LENGTH // 2).hexdigest()


def _new_key() -> str:
    """An opaque key: the prefix and a random hex string, and nothing about the account."""
    return f"{AVATAR_KEY_PREFIX}{uuid4().hex}"


def set_user_avatar(*, user_id: UUID, upload) -> str:
    """Store this account's profile picture, and record the change (AD-5).

    Args:
        user_id: The account to change. The row is looked up inside the transaction.
        upload: A file-like with `.read(n)`. Read at most `AVATAR_MAX_BYTES + 1` bytes.

    Returns:
        The key the account now holds.

    Raises:
        ValidationError: The upload is not a readable image of an allowed format, is over
            the size cap, or is over the pixel cap. **Nothing is stored and the account's
            existing picture is untouched.**
        User.DoesNotExist: No account carries that id.
    """
    # Everything that can refuse, refuses here — before a byte is stored and before the
    # old key is read, let alone deleted.
    data = _read_capped(upload)
    encoded, content_type = _decoded(data)

    blob = get_adapter(BlobPort)
    key = _new_key()
    # The object first. If this raises, nothing has changed anywhere.
    blob.put(key, StoredBlob(data=encoded, content_type=content_type))

    with transaction.atomic(using=PERSONAL):
        user = User.objects.using(PERSONAL).get(pk=user_id)
        previous = user.avatar_key
        user.avatar_key = key
        user.save(using=PERSONAL, update_fields=["avatar_key"])

        # The details carry the action and the target only (AD-13). **Not the key** — it is
        # the address of a photograph of a real person, and an audit log is a thing that
        # survives the account.
        audit_service.write_audit(
            actor=Actor.user(user.pk),
            action="user_avatar_set",
            target_type="User",
            target_id=user.pk,
            details={},
        )

        # Only once the row is committed is the old picture safe to remove. Inside the
        # transaction, a rollback would leave the account pointing at an object this had
        # already deleted.
        if previous and previous != key:
            transaction.on_commit(lambda: _delete_quietly(previous), using=PERSONAL)

    return key


def clear_user_avatar(*, user_id: UUID) -> None:
    """Remove this account's profile picture, and record the change (AD-5).

    Clearing a picture that is not set is a success, not an error: the account ends in the
    state the caller asked for, which is what an idempotent command means.

    Raises:
        User.DoesNotExist: No account carries that id.
    """
    with transaction.atomic(using=PERSONAL):
        user = User.objects.using(PERSONAL).get(pk=user_id)
        previous = user.avatar_key
        if previous:
            user.avatar_key = ""
            user.save(using=PERSONAL, update_fields=["avatar_key"])

        audit_service.write_audit(
            actor=Actor.user(user.pk),
            action="user_avatar_cleared",
            target_type="User",
            target_id=user.pk,
            details={},
        )

        if previous:
            transaction.on_commit(lambda: _delete_quietly(previous), using=PERSONAL)


def _delete_quietly(key: str) -> None:
    """Remove an object, treating a failure as a leak rather than an error.

    **This runs after the transaction has committed**, so there is nothing left to undo:
    the account already holds the right key, and the user already has the right picture.
    A store that refuses the delete leaves an orphaned object, which costs kilobytes and
    is removable by a sweep — raising here would turn a successful change into a failed
    one in the caller's eyes, which is a worse answer than a leak.
    """
    from ports.blob import BlobError

    try:
        get_adapter(BlobPort).delete(key)
    except BlobError:
        pass


__all__ = ["clear_user_avatar", "set_user_avatar", "version_of"]
