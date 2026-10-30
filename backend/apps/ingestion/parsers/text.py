"""Safe URLs and derived ids for parsed candidates (AD-9).

Source content is untrusted: only absolute http(s) URLs survive, and an id the source did
not give is derived rather than invented.

**`plain_text` moved to `formats/text.py`.** Stripping markup off untrusted content
is a *format* concern, not a catalog one — the ICS parser needs it too — so the
implementation lives in the shared layer and is re-exported here for the catalog's other
parsers (`feeds`, `jsonld`), which are not ICS consumers.
"""

from hashlib import sha256
from urllib.parse import urljoin, urlsplit

from apps.ingestion.parsers.types import MAX_SOURCE_EVENT_ID, MAX_URL
from formats.text import plain_text

__all__ = ["absolute_iri", "derived_id", "http_url", "item_id", "plain_text"]


def http_url(value: object, base: str = "") -> str:
    """An absolute http(s) URL (relative ones resolved against `base`), or ""."""
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        url = urljoin(base, value.strip()) if base else value.strip()
        parts = urlsplit(url)
    except ValueError:
        return ""
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc or len(url) > MAX_URL:
        return ""
    return url


def item_id(value: str) -> str:
    """A source's own id, kept as is unless it won't fit the column: then a stable hash."""
    value = value.strip()
    if len(value) <= MAX_SOURCE_EVENT_ID:
        return value
    return f"long:{sha256(value.encode()).hexdigest()}"


def absolute_iri(value: object) -> str | None:
    """`value` if it's an absolute IRI usable as a global id; blank nodes (`_:b0`) and
    relative or fragment-only references (`#event`) are local to one document."""
    if not isinstance(value, str) or not value.strip() or value.strip().startswith("_:"):
        return None
    try:
        scheme = urlsplit(value.strip()).scheme
    except ValueError:
        return None
    return value.strip() if scheme else None


def derived_id(*parts: str) -> str:
    """A stable `source_event_id` for an item the source gave no id (never empty)."""
    digest = sha256("\x1f".join(parts).encode()).hexdigest()[:32]
    return f"derived:{digest}"
