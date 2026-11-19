"""The avatar endpoints: the upload, the removal, and the redirect that mints the signature.

**What these tests hold.**

1. **The round trip works through the API the client actually uses** — upload, then read
   the URL back off `me`, then follow it.
2. **A stale version is refused, not served.** An old URL may have been shared while it
   was current; resolving it to whatever picture the account holds *now* would leak.
3. **Another account's URL is refused** — the version is checked against the *caller's*
   key, never looked up globally.
4. **`max-age` is strictly less than the presign TTL**, read from **both settings** so the
   two cannot drift apart. A cached redirect outliving its signature is a broken picture
   for exactly the difference.
5. **An over-sized body is refused before it is parsed**, by the middleware, with no
   filename echoed back (AD-13).
6. **Anonymous is 401 and a missing CSRF token is 403**, on both writes.
"""

import io
import json
import socket
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from django.conf import settings
from django.test import Client
from PIL import Image

from apps.identity.models import User
from apps.identity.services.avatar import version_of
from shared.constants import AVATAR_MAX_BYTES
from shared.db import PERSONAL
from tests.csrf import CsrfClient

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

AVATAR = "/api/auth/profile/avatar"
ME = "/api/auth/me"


def make_user():
    return User.objects.create_user(email=f"sam-{uuid4().hex[:8]}@example.test", password="pw")


def signed_in(user=None):
    account = user or make_user()
    client = CsrfClient()
    client.force_login(account)
    client.user = account
    return client


def png(colour=(10, 20, 30)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (8, 8), colour).save(out, format="PNG")
    return out.getvalue()


def upload_file(data: bytes, name="face.png", content_type="image/png"):
    buffered = io.BytesIO(data)
    buffered.name = name
    return buffered


def post_avatar(client, data: bytes, **kwargs):
    return client.post(AVATAR, {"file": upload_file(data, **kwargs)})


def body_of(response):
    return json.loads(response.content)


# ── The round trip ────────────────────────────────────────────────────────────────


def test_an_upload_returns_the_profile_carrying_the_avatar_url():
    client = signed_in()
    response = post_avatar(client, png())

    assert response.status_code == 200, response.content
    body = body_of(response)
    assert body["avatar_url"].startswith(f"{AVATAR}/")
    assert body["email"] == client.user.email


def test_me_carries_the_same_url_so_the_shell_needs_no_second_call():
    client = signed_in()
    uploaded = body_of(post_avatar(client, png()))["avatar_url"]

    assert body_of(client.get(ME))["avatar_url"] == uploaded


def test_me_carries_an_empty_string_when_no_picture_is_set():
    """`""`, not null and not absent — the one "no picture" state."""
    client = signed_in()
    assert body_of(client.get(ME))["avatar_url"] == ""


def _store_is_listening(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    if not parsed.hostname:
        return False
    try:
        with socket.create_connection((parsed.hostname, parsed.port or 80), timeout=0.5):
            return True
    except OSError:
        return False


def test_the_url_redirects_to_a_signed_address(settings):
    """**Against the real store**, because the redirect only exists for stores that can
    mint a fetchable URL.

    The suite runs on the in-memory adapter, whose `url_for` returns `memory://…` — a
    scheme Django refuses to redirect to — so this test switches to S3, exactly as
    `tests/adapters/test_blob.py` does, and skips when no store is listening. Asserting
    the 302 against the memory adapter would assert the fallback, not the redirect.
    """
    endpoint = settings.BLOB_STORAGE["endpoint"]
    if not endpoint or not _store_is_listening(endpoint):
        pytest.skip(f"no object store listening at {endpoint or '(unconfigured)'} — run `make up`")
    settings.ADAPTERS = {**settings.ADAPTERS, "blob": "adapters.blob.s3.S3BlobAdapter"}

    client = signed_in()
    url = body_of(post_avatar(client, png()))["avatar_url"]

    response = client.get(url)

    assert response.status_code == 302
    target = response["Location"]
    assert "X-Amz-Signature" in target or "Signature" in target, target


def test_a_store_that_cannot_mint_a_url_serves_the_bytes_inline():
    """`BLOB_ADAPTER=memory` is a supported mode, and the picture must still arrive.

    Redirecting blindly in that mode answered **400 Suspicious operation** for every user
    — a broken feature reported as a security event. This pins the fallback.
    """
    client = signed_in()
    url = body_of(post_avatar(client, png()))["avatar_url"]

    response = client.get(url)

    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_deleting_clears_the_url_and_the_picture():
    client = signed_in()
    post_avatar(client, png())

    response = client.delete(AVATAR)

    assert response.status_code == 200, response.content
    assert body_of(response)["avatar_url"] == ""
    assert body_of(client.get(ME))["avatar_url"] == ""


def test_deleting_when_nothing_is_set_is_a_success():
    client = signed_in()
    assert client.delete(AVATAR).status_code == 200


# ── The version, and what it refuses ──────────────────────────────────────────────


def test_replacing_a_picture_changes_the_url():
    """Otherwise a cache would keep showing the old one."""
    client = signed_in()
    first = body_of(post_avatar(client, png((1, 2, 3))))["avatar_url"]
    second = body_of(post_avatar(client, png((9, 9, 9))))["avatar_url"]

    assert first != second


def test_a_stale_version_is_refused_rather_than_served_the_current_picture():
    """A URL that was shared while it was current must not follow the account forward."""
    client = signed_in()
    stale = body_of(post_avatar(client, png((1, 2, 3))))["avatar_url"]
    post_avatar(client, png((9, 9, 9)))

    assert client.get(stale).status_code == 404


def test_another_accounts_version_is_refused():
    """The version is checked against the caller's own key, never looked up globally."""
    owner = signed_in()
    owner_url = body_of(post_avatar(owner, png()))["avatar_url"]

    stranger = signed_in()
    assert stranger.get(owner_url).status_code == 404


def test_an_unset_picture_has_no_address_to_fetch():
    client = signed_in()
    assert client.get(f"{AVATAR}/{version_of('avatars/nothing')}").status_code == 404


# ── The cache rule ────────────────────────────────────────────────────────────────


def test_the_redirect_may_not_be_cached_longer_than_its_signature_lives():
    """**Both numbers are read from settings**, so they cannot drift apart.

    A browser holding the redirect longer than the presigned URL lives would show a broken
    picture for exactly the difference — and only after its cache warmed, which is the
    worst kind of failure to find.
    """
    client = signed_in()
    url = body_of(post_avatar(client, png()))["avatar_url"]

    cache_control = client.get(url)["Cache-Control"]

    assert "private" in cache_control
    max_age = int(cache_control.split("max-age=")[1].split(",")[0])
    assert max_age < settings.BLOB_URL_TTL_SECONDS, (
        f"max-age={max_age} outlives the {settings.BLOB_URL_TTL_SECONDS}s signature"
    )


# ── Refusals ──────────────────────────────────────────────────────────────────────


def test_a_non_image_is_refused_with_422_and_no_filename_echoed():
    """AD-13: the details must not reflect what the uploader chose to call their file."""
    client = signed_in()
    response = post_avatar(client, b"not an image", name="my-holiday-photo.png")

    assert response.status_code == 422, response.content
    assert "my-holiday-photo" not in response.content.decode()


def test_an_oversized_body_is_refused_before_it_is_parsed():
    """413 from the middleware, not 422 from the command — the body is never read."""
    client = signed_in()
    oversized = b"x" * (settings.AVATAR_MAX_REQUEST_BYTES + 1)

    response = client.post(
        AVATAR,
        data=oversized,
        content_type="multipart/form-data; boundary=zzz",
    )

    assert response.status_code == 413, response.status_code
    assert "zzz" not in response.content.decode()


def test_a_picture_over_the_cap_but_under_the_request_limit_is_refused_by_the_command():
    """The middleware's limit has slack for the envelope; the command holds the real cap."""
    client = signed_in()
    payload = b"\x89PNG\r\n\x1a\n" + b"x" * (AVATAR_MAX_BYTES + 1024)

    response = post_avatar(client, payload)

    assert response.status_code == 422, response.status_code


# ── Auth and CSRF ─────────────────────────────────────────────────────────────────


def test_an_anonymous_upload_is_refused():
    assert CsrfClient().post(AVATAR, {"file": upload_file(png())}).status_code == 401


def test_an_anonymous_delete_is_refused():
    assert CsrfClient().delete(AVATAR).status_code == 401


def test_an_anonymous_fetch_is_refused():
    assert CsrfClient().get(f"{AVATAR}/{version_of('avatars/x')}").status_code == 401


def test_an_upload_without_a_csrf_token_is_refused():
    """A plain `Client` sends no token; `CsrfClient` is the one that does."""
    user = make_user()
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    assert client.post(AVATAR, {"file": upload_file(png())}).status_code == 403


def test_a_delete_without_a_csrf_token_is_refused():
    user = make_user()
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    assert client.delete(AVATAR).status_code == 403


def test_the_csrf_check_runs_before_the_resolver_on_the_upload():
    """An anonymous request with no token is refused as a cross-site write, not a 401.

    **The ordering is the assertion, and nothing else tests it.** `current_user` checks
    the token too, but *after* it has resolved the caller — so without the explicit
    `require_csrf` first, this request is answered 401 ("you are not signed in") instead
    of 403 ("this could not be shown to come from this site"). A mutation probe deleting
    the explicit call left every other test in this file green, which is how this gap was
    found: the signed-in cases are refused either way, and only the anonymous one can tell
    the two orders apart.

    The same assertion `test_the_csrf_check_runs_before_the_resolver` makes for
    `PUT /profile`.
    """
    response = Client(enforce_csrf_checks=True).post(AVATAR, {"file": upload_file(png())})

    assert response.status_code == 403
    assert body_of(response)["code"] == "csrf_failed"


def test_the_csrf_check_runs_before_the_resolver_on_the_delete():
    """The same ordering, on the other write."""
    response = Client(enforce_csrf_checks=True).delete(AVATAR)

    assert response.status_code == 403
    assert body_of(response)["code"] == "csrf_failed"
