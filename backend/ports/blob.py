"""Blob port: the bytes an account owns that are too big to be a column.

**Why object storage is a port and not Django's `STORAGES`.** Every external system this
codebase touches — email, billing, calendars, geo, the throttle, revalidation, the LLM,
source fetches — is reached through a port resolved by `ports.registry` out of
`settings.ADAPTERS`, and the `apps | adapters` import contract forbids an app from
importing an adapter at all. Django's storage API would have been the one external system
sitting inside the app layer, un-fakeable in tests and un-swappable at deploy. So this is
a port, and the in-memory adapter is what lets the suite run with no object store at all.

**A key is opaque.** It carries no address, no name and no user id (AD-13): a key is a
second place PII would live at rest, and it is also the thing that ends up in a URL. The
app that mints keys owns their shape, exactly as the app that builds throttle keys owns
theirs; this port only stores bytes under them.

**`url_for` returns a presigned, expiring URL, and the bucket is private.** Nothing is
anonymously readable: the signature *is* the read permission, it is minted per object and
it runs out. **It is not stable** — a signature made now and a signature made a second
later differ, which was measured against the pinned boto3 rather than assumed. So a
caller that needs a stable address for a browser to cache must put its own URL in front
of this one; `url_for` is the short-lived inside of that, never the thing rendered into
every page.

**`open` returns the whole object.** That is honest for what this port is for — profile
pictures, measured in kilobytes — and dishonest for anything large. A caller that wants
to store something that does not fit in memory needs a streaming method, and adding one
is a deliberate act, not an accident of reuse.

Like every other port here, this is an ABC over frozen dataclasses and imports no Django.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import final


class BlobError(Exception):
    """The object store could not answer. Reaching it is a network call, and it can fail."""


class BlobNotFound(BlobError):
    """No object is stored under that key."""


@dataclass(frozen=True)
class StoredBlob:
    """One object's bytes and the type they were stored as."""

    data: bytes
    content_type: str


# The widest key a caller may use. Not a storage limit — S3 allows 1024 bytes — but the
# point at which a key has stopped being opaque and started carrying information.
MAX_KEY_LENGTH = 128


class BlobPort(ABC):
    """An object store. Adapters implement the four underscore methods.

    The key rules live here, once, for every adapter — the same arrangement `EmailPort`
    uses for the AD-20 stream rules. An adapter cannot skip them, because the public
    methods are `@final`.
    """

    @final
    def put(self, key: str, blob: StoredBlob) -> None:
        self._validate_key(key)
        if not blob.content_type:
            raise ValueError("content_type is required: a stored object declares its type")
        self._put(key, blob)

    @final
    def open(self, key: str) -> StoredBlob:
        """The object's bytes.

        Raises:
            BlobNotFound: nothing is stored under `key`.
        """
        self._validate_key(key)
        return self._open(key)

    @final
    def delete(self, key: str) -> None:
        """Remove the object. **Deleting what is not there is not an error** — the caller
        wants the object gone, and it is gone. A delete that raised on a missing key would
        make every cleanup path carry an exists-check it does not need."""
        self._validate_key(key)
        self._delete(key)

    @final
    def url_for(self, key: str, *, ttl_seconds: int) -> str:
        """A presigned URL for `key`, good for `ttl_seconds`.

        **It is not checked that the object exists.** Minting a URL is a local
        computation; checking would be a network round trip on a path that runs per
        request, and the store answers 404 by itself for a key that holds nothing.
        """
        self._validate_key(key)
        if ttl_seconds <= 0:
            raise ValueError(
                "ttl_seconds must be positive: a URL that is already expired is not a URL"
            )
        return self._url_for(key, ttl_seconds=ttl_seconds)

    @staticmethod
    def _validate_key(key: str) -> None:
        """**The key rules, and each one is a refusal that protects the store.**

        An empty key names nothing. A leading slash and a `..` segment are both path
        traversal — harmless against S3's flat namespace, dangerous against any adapter
        that ever writes to a filesystem, and there is no reason to let one through on
        the grounds that today's adapter happens to survive it. Whitespace and control
        characters do not survive a round trip through a URL intact.
        """
        if not key:
            raise ValueError("key is required")
        if len(key) > MAX_KEY_LENGTH:
            raise ValueError(f"key is longer than {MAX_KEY_LENGTH} characters")
        if key.startswith("/") or ".." in key.split("/"):
            raise ValueError("key must be relative and must not traverse")
        if any(character.isspace() or ord(character) < 0x20 for character in key):
            raise ValueError("key must not contain whitespace or control characters")

    @abstractmethod
    def _put(self, key: str, blob: StoredBlob) -> None: ...

    @abstractmethod
    def _open(self, key: str) -> StoredBlob: ...

    @abstractmethod
    def _delete(self, key: str) -> None: ...

    @abstractmethod
    def _url_for(self, key: str, *, ttl_seconds: int) -> str: ...
