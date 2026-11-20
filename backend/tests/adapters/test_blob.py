"""The blob port's contract, run against **every** adapter that claims to implement it.

**One suite, parameterised over the adapters** — not a suite for the fake and another for
the real one. A fake that answers a differently-shaped question is worse than no fake: a
test written against it pins behaviour production does not have, and it passes right up
until a deploy. The in-memory adapter exists to stand in for the store, so it is held to
the store's contract here.

**The S3 adapter runs only when a store is actually listening.** It is skipped otherwise,
and the skip says why. A suite that silently dropped the real adapter would leave the
contract proven against the fake alone, which is the failure this file exists to prevent.
"""

import socket
from urllib.parse import urlparse

import pytest
from django.test import override_settings

from adapters.blob.memory import InMemoryBlobAdapter
from adapters.blob.s3 import S3BlobAdapter
from ports.blob import MAX_KEY_LENGTH, BlobNotFound, BlobPort, StoredBlob

PNG = StoredBlob(data=b"\x89PNG\r\n\x1a\n" + b"pretend-pixels", content_type="image/png")


def _store_is_listening(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    if not parsed.hostname:
        return False
    try:
        with socket.create_connection((parsed.hostname, parsed.port or 80), timeout=0.5):
            return True
    except OSError:
        return False


@pytest.fixture(params=["memory", "s3"])
def adapter(request, settings) -> BlobPort:
    if request.param == "memory":
        # Its own store, so one test cannot see another's objects.
        return InMemoryBlobAdapter(store={})

    from django.conf import settings as django_settings

    endpoint = django_settings.BLOB_STORAGE["endpoint"]
    if not endpoint or not _store_is_listening(endpoint):
        pytest.skip(f"no object store listening at {endpoint or '(unconfigured)'} — run `make up`")
    return S3BlobAdapter()


class TestTheContractEveryAdapterKeeps:
    def test_an_object_comes_back_as_it_went_in(self, adapter, blob_key):
        adapter.put(blob_key, PNG)
        stored = adapter.open(blob_key)
        assert stored.data == PNG.data
        assert stored.content_type == PNG.content_type

    def test_opening_a_key_that_holds_nothing_raises_not_found(self, adapter, blob_key):
        with pytest.raises(BlobNotFound):
            adapter.open(blob_key)

    def test_a_put_over_an_existing_key_replaces_it(self, adapter, blob_key):
        adapter.put(blob_key, PNG)
        adapter.put(blob_key, StoredBlob(data=b"second", content_type="text/plain"))
        stored = adapter.open(blob_key)
        assert stored.data == b"second"
        assert stored.content_type == "text/plain"

    def test_a_deleted_object_is_gone(self, adapter, blob_key):
        adapter.put(blob_key, PNG)
        adapter.delete(blob_key)
        with pytest.raises(BlobNotFound):
            adapter.open(blob_key)

    def test_deleting_what_is_not_there_is_not_an_error(self, adapter, blob_key):
        # The port says so: the caller wants it gone, and it is gone.
        adapter.delete(blob_key)

    def test_a_url_is_minted_for_the_key(self, adapter, blob_key):
        url = adapter.url_for(blob_key, ttl_seconds=60)
        assert blob_key in url

    def test_two_urls_for_one_key_are_not_promised_to_be_equal(self, adapter, blob_key):
        """**This is the finding that shaped the design, pinned as a test.**

        A presigned URL carries the moment it was signed, so two signatures a second
        apart differ. The port therefore promises a *working* URL, never a *stable* one,
        and the app puts its own stable URL in front. If this ever starts asserting
        equality, the app's redirect has become dead weight — and if an adapter starts
        returning something stable, that is a change to reason about, not to assume.
        """
        first = adapter.url_for(blob_key, ttl_seconds=60)
        second = adapter.url_for(blob_key, ttl_seconds=60)
        assert isinstance(first, str) and isinstance(second, str)


class TestTheKeyRulesTheAdaptersCannotSkip:
    """The rules live on the port's `@final` methods, so every adapter gets them."""

    @pytest.mark.parametrize(
        "key",
        [
            "",
            "/leading-slash",
            "../escape",
            "a/../b",
            "has space",
            "has\nnewline",
            "x" * (MAX_KEY_LENGTH + 1),
        ],
    )
    def test_a_bad_key_is_refused_before_the_store_is_touched(self, key):
        store: dict = {}
        adapter = InMemoryBlobAdapter(store=store)
        with pytest.raises(ValueError):
            adapter.put(key, PNG)
        assert store == {}, "a refused key must not have been written"

    def test_an_object_without_a_content_type_is_refused(self, blob_key):
        store: dict = {}
        adapter = InMemoryBlobAdapter(store=store)
        with pytest.raises(ValueError):
            adapter.put(blob_key, StoredBlob(data=b"x", content_type=""))
        assert store == {}

    def test_a_url_with_no_life_left_is_refused(self, blob_key):
        adapter = InMemoryBlobAdapter(store={})
        with pytest.raises(ValueError):
            adapter.url_for(blob_key, ttl_seconds=0)


class TestTheProcessWideStore:
    """The bug this shape exists to avoid, pinned so it cannot come back."""

    def test_two_registry_built_adapters_see_one_set_of_objects(self, blob_key):
        from adapters.blob.memory import clear_objects

        clear_objects()
        try:
            InMemoryBlobAdapter().put(blob_key, PNG)
            # A second adapter, as `ports.registry.get_adapter` would build it.
            assert InMemoryBlobAdapter().open(blob_key).data == PNG.data
        finally:
            clear_objects()

    def test_an_adapter_given_its_own_store_keeps_to_itself(self, blob_key):
        from adapters.blob.memory import clear_objects

        clear_objects()
        try:
            InMemoryBlobAdapter(store={}).put(blob_key, PNG)
            with pytest.raises(BlobNotFound):
                InMemoryBlobAdapter().open(blob_key)
        finally:
            clear_objects()


class TestTheClientIsBuiltOncePerConfiguration:
    """**`url_for` runs on the path that serves a picture**, and building a boto3 client
    parses the whole S3 service model. The registry builds a fresh *adapter* per call, so
    without this the cost would be paid per request to produce a string that is otherwise
    pure local computation."""

    def test_two_adapters_with_one_configuration_share_a_client(self):
        from adapters.blob.s3 import _client_for

        _client_for.cache_clear()
        first = _client_for(
            endpoint="http://s:9000", region="us-east-1", access_key="a", secret_key="s"
        )
        second = _client_for(
            endpoint="http://s:9000", region="us-east-1", access_key="a", secret_key="s"
        )

        assert first is second

    def test_the_two_endpoints_get_their_own_clients(self):
        """The address this process dials and the address a signature is minted for are
        different hosts, and a signature is bound to the host it was signed for."""
        from adapters.blob.s3 import _client_for

        _client_for.cache_clear()
        internal = _client_for(
            endpoint="http://store:9000", region="us-east-1", access_key="a", secret_key="s"
        )
        public = _client_for(
            endpoint="http://127.0.0.1:9000", region="us-east-1", access_key="a", secret_key="s"
        )

        assert internal is not public

    def test_a_changed_credential_yields_a_different_client(self):
        """A stale client signing with a rotated key would fail in a way that looks like
        a storage outage."""
        from adapters.blob.s3 import _client_for

        _client_for.cache_clear()
        before = _client_for(
            endpoint="http://s:9000", region="us-east-1", access_key="a", secret_key="old"
        )
        after = _client_for(
            endpoint="http://s:9000", region="us-east-1", access_key="a", secret_key="new"
        )

        assert before is not after


class TestTheRegistryResolvesThePort:
    def test_the_test_suite_resolves_to_the_in_memory_adapter(self):
        """The suite must dial no object store — `make test-backend` passes with it stopped."""
        from ports.blob import BlobPort as Port
        from ports.registry import get_blob_port

        with override_settings(
            ADAPTERS={**_adapters(), "blob": "adapters.blob.memory.InMemoryBlobAdapter"}
        ):
            port = get_blob_port()
        assert isinstance(port, Port)
        assert isinstance(port, InMemoryBlobAdapter)


def _adapters() -> dict:
    from django.conf import settings as django_settings

    return dict(django_settings.ADAPTERS)
