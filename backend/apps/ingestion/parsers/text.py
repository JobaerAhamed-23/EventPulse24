"""Plain text, safe URLs and derived ids for parsed candidates (AD-9).

Source content is untrusted: markup is stripped (never rendered), `<script>` and `<style>`
content is dropped, and only absolute http(s) URLs survive.
"""

import re
import unicodedata
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from apps.ingestion.parsers.types import MAX_SOURCE_EVENT_ID, MAX_URL

_WHITESPACE = re.compile(r"\s+")
_DROPPED_ELEMENTS = frozenset({"script", "style", "template", "noscript"})


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._dropping = 0

    def handle_starttag(self, tag, attrs):
        if tag in _DROPPED_ELEMENTS:
            self._dropping += 1
        elif tag in ("br", "p", "div", "li", "tr"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in _DROPPED_ELEMENTS and self._dropping:
            self._dropping -= 1

    def handle_data(self, data):
        if not self._dropping:
            self.parts.append(data)


def plain_text(value: object, limit: int) -> str:
    """Markup stripped, entities decoded, control characters removed, whitespace collapsed,
    truncated to `limit` characters."""
    if value is None:
        return ""
    text = str(value)
    if "<" in text:
        extractor = _TextExtractor()
        extractor.feed(text)
        extractor.close()
        text = "".join(extractor.parts)
    text = unescape(text)
    text = "".join(" " if unicodedata.category(c)[0] == "C" else c for c in text)
    return _WHITESPACE.sub(" ", text).strip()[:limit]


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
