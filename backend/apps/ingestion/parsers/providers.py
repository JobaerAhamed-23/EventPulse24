"""`api`-method sources: dispatch to a per-provider reader (FR-17).

A provider API answers in its own JSON shape, not schema.org, so there is no one parser for
the method — there is a parser *per provider*. The source's host picks it.

**Exact hosts, never suffixes.** `app.ticketmaster.com.evil.test` ends with
"ticketmaster.com", and a suffix match would hand an attacker-chosen document to a reader
that trusts its shape. `apps.ingestion.services.provider_keys` matches the same way, for
the sharper version of the same reason: it decides who gets our API key.

Adding a provider is a reader module and one entry in `READERS`. Nothing else moves.

**Not named `api.py`**, though it is the `api` method's parser. `tests/architecture`
discovers the AD-5 surface by shape — a file called `api.py` or `*_api.py` under `apps/`
is an HTTP router that may not write directly — and a parser enrolled in that list would
have weakened a real guard to accommodate a filename.
"""

from collections.abc import Callable
from urllib.parse import urlsplit

from apps.ingestion.parsers import ticketmaster
from apps.ingestion.parsers.types import ParseResult, SourceContext

Reader = Callable[[bytes, SourceContext], ParseResult]

READERS: dict[str, Reader] = {
    "app.ticketmaster.com": ticketmaster.read,
}


def parse_api(content: bytes, context: SourceContext) -> ParseResult:
    """Read `content` with the reader for the source's host, or report that we have none.

    An unknown host is a `ParseResult` with an error, never an exception: the package's
    promise is bytes in, candidates out. The pipeline turns it into
    `parse_failed`/`parse_unknown_api_provider` on the run, which is a fact an editor can
    act on — someone registered an `api` source we cannot read.
    """
    try:
        host = (urlsplit(context.source_url).hostname or "").lower()
    except ValueError:
        return ParseResult(error="unknown_api_provider")
    reader = READERS.get(host)
    if reader is None:
        return ParseResult(error="unknown_api_provider")
    return reader(content, context)
