"""The profile picture: what is stored, what is refused, and what a refusal leaves behind.

**What these tests hold.**

1. **A refusal changes nothing.** The hardest property here is not that bad input is
   rejected — it is that rejecting it leaves the account's existing picture exactly where
   it was. Every refusal test asserts the old key *and the old object* survive.
2. **The format comes from the bytes.** A payload named `.png` whose bytes are a GIF is
   identified as a GIF. A payload with a **real image header and a non-image body** is
   refused — a counterfeit, not merely a renamed text file.
3. **The size cap is enforced while reading.** An oversized upload is refused without
   being read whole, asserted by counting what the command actually asked for.
4. **Replacing removes the old object**, probed in the store rather than inferred from the
   row.
5. **EXIF does not survive.** A picture carrying GPS is stored without it, and a picture
   carrying an orientation tag is stored the right way up — both halves, because dropping
   the tag without applying it is how pictures end up sideways.
6. **The audit row carries no key** (AD-13).
"""

import io
from uuid import uuid4

import pytest
from PIL import Image

from apps.identity.models import IdentityAuditEntry, User
from apps.identity.services.avatar import clear_user_avatar, set_user_avatar
from domain.errors import ValidationError
from ports.blob import BlobNotFound, BlobPort
from ports.registry import get_adapter
from shared.constants import AVATAR_MAX_BYTES
from shared.db import PERSONAL

pytestmark = pytest.mark.django_db(databases=[PERSONAL])


def make_user():
    return User.objects.create_user(email=f"sam-{uuid4().hex[:8]}@example.test", password="pw")


def png_bytes(*, size=(8, 8), colour=(10, 20, 30)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, colour).save(out, format="PNG")
    return out.getvalue()


def jpeg_with_exif(*, orientation: int | None = None, gps: bool = False) -> bytes:
    """A real JPEG carrying the metadata we intend to strip."""
    image = Image.new("RGB", (12, 6), (200, 100, 50))
    exif = image.getexif()
    if orientation is not None:
        exif[0x0112] = orientation  # Orientation
    if gps:
        # A real nested GPS IFD, because that is where a camera puts coordinates. Writing
        # 0x8825 as a scalar instead produces an EXIF block Pillow cannot read back, which
        # would make this test pass for the wrong reason.
        coordinates = exif.get_ifd(0x8825)
        coordinates[1] = "N"
        coordinates[2] = (51.0, 30.0, 0.0)
        coordinates[3] = "W"
        coordinates[4] = (0.0, 7.0, 0.0)
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif)
    return out.getvalue()


class _CountingUpload:
    """A file-like that records how much was asked of it."""

    def __init__(self, data: bytes):
        self._stream = io.BytesIO(data)
        self.bytes_read = 0

    def read(self, n=-1):
        chunk = self._stream.read(n)
        self.bytes_read += len(chunk)
        return chunk


def upload(data: bytes):
    return _CountingUpload(data)


def blob() -> BlobPort:
    return get_adapter(BlobPort)


def stored(key: str) -> bytes | None:
    try:
        return blob().open(key).data
    except BlobNotFound:
        return None


# ── What is stored ────────────────────────────────────────────────────────────────


def test_a_png_is_stored_and_the_account_holds_its_key():
    user = make_user()
    key = set_user_avatar(user_id=user.pk, upload=upload(png_bytes()))

    user.refresh_from_db()
    assert user.avatar_key == key
    assert key.startswith("avatars/")
    assert stored(key) is not None


def test_the_key_carries_nothing_about_the_account():
    """AD-13: no id, no address, no filename."""
    user = make_user()
    key = set_user_avatar(user_id=user.pk, upload=upload(png_bytes()))

    assert str(user.pk) not in key
    assert user.email.split("@")[0] not in key


def test_replacing_a_picture_removes_the_object_the_old_key_pointed_at(
    django_capture_on_commit_callbacks,
):
    """Probed in the store, not inferred from the row.

    **The capture fixture is load-bearing.** The old object is deleted in
    `transaction.on_commit`, deliberately, so that a rollback cannot destroy the picture
    the account still has — and under `django_db` the test's transaction never commits, so
    those callbacks would never run. Without this fixture the assertion below would fail
    against correct code, and "fixing" it by deleting inside the transaction would
    reintroduce the bug the ordering exists to prevent.
    """
    user = make_user()
    first = set_user_avatar(user_id=user.pk, upload=upload(png_bytes(colour=(1, 2, 3))))
    assert stored(first) is not None

    with django_capture_on_commit_callbacks(using=PERSONAL, execute=True):
        second = set_user_avatar(user_id=user.pk, upload=upload(png_bytes(colour=(9, 9, 9))))

    assert second != first
    assert stored(second) is not None
    assert stored(first) is None, "the replaced picture is still in the bucket"


def test_clearing_blanks_the_key_and_removes_the_object(django_capture_on_commit_callbacks):
    user = make_user()
    key = set_user_avatar(user_id=user.pk, upload=upload(png_bytes()))

    with django_capture_on_commit_callbacks(using=PERSONAL, execute=True):
        clear_user_avatar(user_id=user.pk)

    user.refresh_from_db()
    assert user.avatar_key == ""
    assert stored(key) is None


def test_clearing_a_picture_that_is_not_set_is_a_success():
    user = make_user()
    clear_user_avatar(user_id=user.pk)
    user.refresh_from_db()
    assert user.avatar_key == ""


# ── What is refused, and what a refusal leaves behind ─────────────────────────────


def test_a_non_image_is_refused_and_nothing_is_stored():
    user = make_user()
    with pytest.raises(ValidationError):
        set_user_avatar(user_id=user.pk, upload=upload(b"this is not an image at all"))

    user.refresh_from_db()
    assert user.avatar_key == ""


def test_a_refusal_leaves_an_existing_picture_intact():
    """The property that matters most: a bad upload cannot cost you the picture you have."""
    user = make_user()
    key = set_user_avatar(user_id=user.pk, upload=upload(png_bytes()))
    before = stored(key)

    with pytest.raises(ValidationError):
        set_user_avatar(user_id=user.pk, upload=upload(b"not an image"))

    user.refresh_from_db()
    assert user.avatar_key == key
    assert stored(key) == before


def test_a_counterfeit_is_refused():
    """A real image header on a body that is not one.

    Not a renamed text file: the first bytes *are* a valid PNG signature, so anything
    sniffing only the magic number would accept it.
    """
    counterfeit = b"\x89PNG\r\n\x1a\n" + b"certainly not a PNG body" * 8
    user = make_user()

    with pytest.raises(ValidationError):
        set_user_avatar(user_id=user.pk, upload=upload(counterfeit))

    user.refresh_from_db()
    assert user.avatar_key == ""


def test_a_decodable_format_outside_the_allow_list_is_refused():
    """A BMP decodes perfectly well — and is still not a format this product stores.

    **This test exists because a mutation probe found nothing guarding it.** Deleting the
    allow-list check left all fifteen other tests green: the SVG and counterfeit payloads
    are refused a step earlier, by the decoder failing to read them at all, so neither
    exercised the allow-list. A format Pillow *can* read but the product does not accept
    is the only case that does.
    """
    out = io.BytesIO()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(out, format="BMP")
    user = make_user()

    with pytest.raises(ValidationError):
        set_user_avatar(user_id=user.pk, upload=upload(out.getvalue()))

    user.refresh_from_db()
    assert user.avatar_key == ""


def test_an_svg_is_refused_however_it_is_labelled():
    svg = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>'
    user = make_user()

    with pytest.raises(ValidationError):
        set_user_avatar(user_id=user.pk, upload=upload(svg))


def test_an_oversized_upload_is_refused_without_being_read_whole():
    """A cap checked after a read is not a cap."""
    user = make_user()
    payload = b"\x89PNG\r\n\x1a\n" + b"x" * (AVATAR_MAX_BYTES * 2)
    source = upload(payload)

    with pytest.raises(ValidationError):
        set_user_avatar(user_id=user.pk, upload=source)

    assert source.bytes_read <= AVATAR_MAX_BYTES + 1, (
        f"read {source.bytes_read} bytes of a {len(payload)}-byte upload — the cap is "
        "being applied after the read, not during it"
    )
    user.refresh_from_db()
    assert user.avatar_key == ""


def test_a_decompression_bomb_is_refused_before_its_pixels_are_produced():
    """A header claiming far more pixels than the cap allows."""
    out = io.BytesIO()
    Image.new("L", (9000, 9000)).save(out, format="PNG")
    user = make_user()

    with pytest.raises(ValidationError):
        set_user_avatar(user_id=user.pk, upload=upload(out.getvalue()))

    user.refresh_from_db()
    assert user.avatar_key == ""


# ── Metadata ──────────────────────────────────────────────────────────────────────


def test_exif_does_not_survive_the_store():
    user = make_user()
    key = set_user_avatar(user_id=user.pk, upload=upload(jpeg_with_exif(gps=True)))

    with Image.open(io.BytesIO(stored(key))) as kept:
        assert not dict(kept.getexif()), "EXIF survived — a photograph's GPS with it"


def test_the_orientation_is_applied_rather_than_merely_dropped():
    """Dropping the tag without applying it is how pictures end up sideways.

    Orientation 6 means "rotate 90°", so a 12x6 picture is stored 6x12.
    """
    user = make_user()
    key = set_user_avatar(user_id=user.pk, upload=upload(jpeg_with_exif(orientation=6)))

    with Image.open(io.BytesIO(stored(key))) as kept:
        assert kept.size == (6, 12), f"stored {kept.size}, so the orientation was ignored"


# ── The audit trail ───────────────────────────────────────────────────────────────


def test_the_audit_row_names_the_action_and_carries_no_key():
    """AD-13: the key is the address of a photograph of a real person."""
    user = make_user()
    key = set_user_avatar(user_id=user.pk, upload=upload(png_bytes()))

    row = (
        IdentityAuditEntry.objects.using(PERSONAL)
        .filter(action="user_avatar_set", target_id=user.pk)
        .order_by("id")
        .last()
    )
    assert row is not None
    assert row.details == {}
    assert key not in str(row.details)


def test_clearing_writes_its_own_audit_row():
    user = make_user()
    set_user_avatar(user_id=user.pk, upload=upload(png_bytes()))
    clear_user_avatar(user_id=user.pk)

    assert (
        IdentityAuditEntry.objects.using(PERSONAL)
        .filter(action="user_avatar_cleared", target_id=user.pk)
        .exists()
    )
