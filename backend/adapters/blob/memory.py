"""In-memory blob adapter: the one the test suite and CI run against.

**This is what makes the suite independent of MinIO.** Every other fake in this codebase
stands in for a service that needs credentials or the network; this one stands in for a
container, and the reason is the same — a test that needs a running object store is a
test that fails for reasons that have nothing to do with it.

**The store is process-wide by default, and that is deliberate.**
`ports.registry.get_adapter` builds a fresh adapter on every call, so an adapter that
kept its objects in `self` would lose them between the call that stored one and the call
that read it back. That exact bug made the in-memory *throttle* inert for months (see
`adapters/throttle/memory.py`), and the fix there is the fix here: the objects live in a
module-level store, and an adapter handed its own store keeps to itself.

**A test that wants isolation passes a store.** That is the whole mechanism: no settings
flag, no reset hook that a test can forget to call.

**The URL it mints is not a real URL and does not pretend to be.** It is a stable
`memory://` address carrying the key and the expiry, which is enough for a test to assert
*that a URL was minted for this key with this TTL* and impossible to mistake for
something a browser could fetch. A fake that returned a plausible `https://` address
would let a broken configuration pass the suite and fail in a browser.
"""

from ports.blob import BlobNotFound, BlobPort, StoredBlob

# The process-wide store, which is what the registry's per-call adapters share.
_OBJECTS: dict[str, StoredBlob] = {}


class InMemoryBlobAdapter(BlobPort):
    def __init__(self, store: dict[str, StoredBlob] | None = None) -> None:
        # No store given: share the process-wide one, the way the real adapter shares a
        # bucket. A store given: this adapter is somebody's private sandbox.
        self._objects = _OBJECTS if store is None else store

    def _put(self, key: str, blob: StoredBlob) -> None:
        self._objects[key] = blob

    def _open(self, key: str) -> StoredBlob:
        try:
            return self._objects[key]
        except KeyError:
            raise BlobNotFound(key) from None

    def _delete(self, key: str) -> None:
        # Deleting what is not there is not an error — the port says so.
        self._objects.pop(key, None)

    def _url_for(self, key: str, *, ttl_seconds: int) -> str:
        return f"memory://{key}?ttl={ttl_seconds}"


def clear_objects() -> None:
    """Empty the process-wide store. For a test that uses it rather than its own."""
    _OBJECTS.clear()
