"""Plain text from untrusted source content (AD-9).

Source content is untrusted: markup is stripped (never rendered), `<script>` and
`<style>` content is dropped, and only absolute http(s) URLs survive.

**This module is format-agnostic.** RSS, JSON-LD and iCalendar all carry a title, a
description and a venue name, and all three are capped the same way — so the caps and the
stripper live here, once, rather than in each format's own module.

The catalog's `apps/ingestion/parsers/text.py` keeps the parts that are the *catalog's*
business — the derived and hashed ids, the relative-URL resolution against a source's
base URL. This module holds only what a format needs, so a format consumer that is not
the catalog can use it without adopting the catalog's identity rules.
"""

import re
import unicodedata
from html import unescape
from html.parser import HTMLParser

#: The caps the catalog's columns impose. They are every format's, too: a title longer
#: than this is truncated rather than stored.
MAX_TITLE = 500
MAX_DESCRIPTION = 10_000
MAX_VENUE_NAME = 200

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
