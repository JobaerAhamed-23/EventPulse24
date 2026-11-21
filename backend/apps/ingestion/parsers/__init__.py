"""Structured source parsers: bytes in, `ParsedCandidate`s out, never an exception.

`parse(method, content, context)` dispatches on the source's acquisition method. The parsers
are pure: no database, no network, no LLM. They hand times over as written; the pipeline
resolves timezones (`domain.timezones`) and identity (`domain.dedup`).
"""

from collections.abc import Callable

from apps.ingestion.parsers.feeds import parse_feed
from apps.ingestion.parsers.ics import parse_ics
from apps.ingestion.parsers.jsonld import parse_jsonld
from apps.ingestion.parsers.providers import parse_api
from apps.ingestion.parsers.types import ParsedCandidate, ParseResult, SourceContext, StatusHint

Parser = Callable[[bytes, SourceContext], ParseResult]

PARSERS: dict[str, Parser] = {
    # FR-17's top tier. Dispatches again, by host, to a per-provider reader: a provider API
    # answers in its own shape, so there is no one parser for the method.
    "api": parse_api,
    "jsonld": parse_jsonld,
    "rss": parse_feed,
    "ics": parse_ics,
    "email_ics": parse_ics,  # the mailbox path hands over the attachment's bytes
    # `partnership` and `crawl` are deliberately absent: both need an agreement or a ToS
    # review before anything is read, and `parse()` returning `unsupported_method` is how
    # the pipeline says so. Registering one here would quietly widen FR-17's hierarchy.
}


def parse(method: str, content: bytes, context: SourceContext) -> ParseResult:
    """Parse `content` for a source acquired by `method` (an AcquisitionMethod value)."""
    parser = PARSERS.get(str(method))
    if parser is None:
        return ParseResult(error="unsupported_method")
    try:
        return parser(content, context)
    except Exception:  # the parsers don't raise; this keeps the promise if one ever does
        return ParseResult(error="parser_failure")


__all__ = ["PARSERS", "ParseResult", "ParsedCandidate", "SourceContext", "StatusHint", "parse"]
