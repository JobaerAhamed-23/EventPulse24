"""RSS 2.0 and Atom feeds whose items carry explicit event times (FR-56).

Parsed with defusedxml (feeds are untrusted XML: entity declarations and external entities are
refused). An item's event start comes only from the RSS event module (`ev:startdate`) or xCal
(`xcal:dtstart`), never from `pubDate`/`updated`: a publication time is not an event time, and
guessing would create wrong-time events. Items without one are counted as `no_event_start`.
"""

from datetime import date, datetime
from xml.etree.ElementTree import Element, ParseError

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring

from apps.ingestion.parsers.text import derived_id, http_url, item_id, plain_text
from apps.ingestion.parsers.times import all_day_span, parse_iso, roll_overnight
from apps.ingestion.parsers.types import (
    MAX_DESCRIPTION,
    MAX_TITLE,
    MAX_VENUE_NAME,
    ParsedCandidate,
    ParseResult,
    SourceContext,
)

ATOM = "{http://www.w3.org/2005/Atom}"
EVENT_NS = "{http://purl.org/rss/1.0/modules/event/}"
XCAL_NS = "{urn:ietf:params:xml:ns:xcal}"
CONTENT_NS = "{http://purl.org/rss/1.0/modules/content/}"


def _text(element: Element | None) -> str | None:
    if element is None:
        return None
    return "".join(element.itertext()).strip() or None


def _first(item: Element, *names: str) -> str | None:
    for name in names:
        value = _text(item.find(name))
        if value:
            return value
    return None


def _atom_link(entry: Element) -> str | None:
    for link in entry.findall(f"{ATOM}link"):
        if link.get("rel", "alternate") == "alternate" and link.get("href"):
            return link.get("href")
    return None


def _item(item: Element, atom: bool, context: SourceContext, result: ParseResult) -> None:
    start_raw = _first(item, f"{EVENT_NS}startdate", f"{XCAL_NS}dtstart")
    start = parse_iso(start_raw)
    if start is None:
        result.skip("no_event_start" if not start_raw else "unparseable_start")
        return
    title = plain_text(_first(item, f"{ATOM}title" if atom else "title"), MAX_TITLE)
    if not title:
        result.skip("no_title")
        return
    end_raw = _first(item, f"{EVENT_NS}enddate", f"{XCAL_NS}dtend")
    end = parse_iso(end_raw)
    all_day = isinstance(start, date) and not isinstance(start, datetime)
    if all_day:
        start, end = all_day_span(start, end if isinstance(end, date) else None)
    elif isinstance(end, date) and not isinstance(end, datetime):
        end = None
    end, dropped = roll_overnight(start, end)
    if dropped:
        result.skip("end_before_start")

    if atom:
        link = _atom_link(item)
        native_id = _first(item, f"{ATOM}id")
        description = _first(item, f"{ATOM}summary", f"{ATOM}content")
    else:
        link = _first(item, "link")
        native_id = _first(item, "guid")
        description = _first(item, "description", f"{CONTENT_NS}encoded")
    url = http_url(link, context.source_url)
    result.add(
        ParsedCandidate(
            source_event_id=item_id(native_id) if native_id else derived_id(url, title, start_raw),
            title=title,
            canonical_url=url,
            start=start,
            start_zone=None,
            start_raw=start_raw,
            end=end,
            end_raw=end_raw,
            all_day=all_day,
            venue_name=plain_text(
                _first(item, f"{EVENT_NS}location", f"{XCAL_NS}location"), MAX_VENUE_NAME
            ),
            description=plain_text(description, MAX_DESCRIPTION),
            raw={"start": start_raw, **({"end": end_raw} if end_raw else {})},
        )
    )


def parse_feed(content: bytes, context: SourceContext) -> ParseResult:
    result = ParseResult()
    try:
        root = fromstring(content)
    except DefusedXmlException:
        result.error = "forbidden_xml"
        return result
    except (ParseError, ValueError):
        result.error = "invalid_xml"
        return result

    if root.tag == "rss":
        channel = root.find("channel")
        items, atom = (channel.findall("item") if channel is not None else []), False
    elif root.tag == f"{ATOM}feed":
        items, atom = root.findall(f"{ATOM}entry"), True
    else:
        result.error = "not_a_feed"
        return result

    for item in items:
        if result.full:
            result.skip("too_many_items")
            continue
        _item(item, atom, context, result)
    return result
