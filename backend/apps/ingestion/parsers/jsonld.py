"""schema.org Events from `<script type="application/ld+json">` blocks (FR-14 structured path).

The HTML is scanned with the stdlib parser only to collect those script blocks: nothing is
rendered or executed. Every Event node (any subtype, a `@type` list, `@graph`, arrays) becomes a
candidate; an `EventSeries` emits its `subEvent`s with a shared `series_id`. One unreadable
block is skipped and the rest still parse.
"""

import json
from datetime import date, datetime
from html.parser import HTMLParser

from apps.ingestion.parsers.text import absolute_iri, derived_id, http_url, item_id, plain_text
from apps.ingestion.parsers.types import (
    MAX_CITY,
    MAX_DESCRIPTION,
    MAX_TITLE,
    MAX_VENUE_NAME,
    ParsedCandidate,
    ParseResult,
    SourceContext,
    StatusHint,
)
from formats.times import all_day_span, parse_iso, roll_overnight
from shared.ids import series_id

# schema.org Event and its subtypes (https://schema.org/Event, "More specific Types").
EVENT_TYPES = frozenset(
    {
        "Event",
        "BusinessEvent",
        "ChildrensEvent",
        "ComedyEvent",
        "CourseInstance",
        "DanceEvent",
        "DeliveryEvent",
        "EducationEvent",
        "ExhibitionEvent",
        "Festival",
        "FoodEvent",
        "Hackathon",
        "LiteraryEvent",
        "MusicEvent",
        "PublicationEvent",
        "SaleEvent",
        "ScreeningEvent",
        "SocialEvent",
        "SportsEvent",
        "TheaterEvent",
        "VisualArtsEvent",
        "BroadcastEvent",
        "OnDemandEvent",
    }
)
SERIES_TYPES = frozenset({"EventSeries"})
STATUS = {
    "EventCancelled": StatusHint.CANCELLED,
    "EventPostponed": StatusHint.POSTPONED,
    "EventRescheduled": StatusHint.SCHEDULED,  # the classifier sees the new time
    "EventScheduled": StatusHint.SCHEDULED,
    "EventMovedOnline": StatusHint.SCHEDULED,
}
MAX_DEPTH = 20  # nesting guard for hostile documents


class _ScriptCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.blocks: list[str] = []
        self._current: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            kind = (dict(attrs).get("type") or "").split(";", 1)[0].strip().lower()
            if kind == "application/ld+json":
                self._current = []

    def handle_endtag(self, tag):
        if tag == "script" and self._current is not None:
            self.blocks.append("".join(self._current))
            self._current = None

    def handle_data(self, data):
        if self._current is not None:
            self._current.append(data)


def _decode(content: bytes) -> str:
    head = content[:2048].lower()
    for marker in (b'charset="', b"charset='", b"charset="):
        at = head.find(marker)
        if at != -1:
            charset = head[at + len(marker) :].split(b'"')[0].split(b"'")[0].split(b">")[0]
            try:
                return content.decode(charset.strip().decode("ascii") or "utf-8", "replace")
            except (LookupError, UnicodeDecodeError):
                break
    return content.decode("utf-8", "replace")


def _types(node: dict) -> set[str]:
    kind = node.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    return {k.rsplit("/", 1)[-1] for k in kinds if isinstance(k, str)}


def _nodes(value, depth=0):
    """Every dict node reachable through arrays and @graph (not through properties)."""
    if depth > MAX_DEPTH:
        return
    if isinstance(value, list):
        for item in value:
            yield from _nodes(item, depth + 1)
    elif isinstance(value, dict):
        yield value
        if "@graph" in value:
            yield from _nodes(value["@graph"], depth + 1)


def _enum_name(value) -> str:
    return value.rsplit("/", 1)[-1] if isinstance(value, str) else ""


def _sold_out(offers) -> bool:
    items = offers if isinstance(offers, list) else [offers]
    return any(
        isinstance(o, dict) and _enum_name(o.get("availability")) == "SoldOut" for o in items
    )


def _venue(location) -> tuple[str, str, str, str | None]:
    """(name, city, country, timezone) from a Place, a string, or a list of either."""
    if isinstance(location, list):
        location = next((loc for loc in location if "VirtualLocation" not in _types_of(loc)), None)
    if isinstance(location, str):
        return plain_text(location, MAX_VENUE_NAME), "", "", None
    if not isinstance(location, dict) or "VirtualLocation" in _types(location):
        return "", "", "", None
    address = location.get("address")
    city = country = ""
    if isinstance(address, dict):
        city = plain_text(address.get("addressLocality"), MAX_CITY)
        raw_country = address.get("addressCountry")
        if isinstance(raw_country, dict):
            raw_country = raw_country.get("name")
        country = raw_country.strip().upper() if isinstance(raw_country, str) else ""
        country = country if len(country) == 2 and country.isalpha() else ""
    elif isinstance(address, str):
        city = plain_text(address, MAX_CITY)
    zone = location.get("timezone") if isinstance(location.get("timezone"), str) else None
    return plain_text(location.get("name"), MAX_VENUE_NAME), city, country, zone


def _types_of(value) -> set[str]:
    return _types(value) if isinstance(value, dict) else set()


def _candidate(node: dict, context: SourceContext, series_key: str | None, result) -> None:
    start_raw = node.get("startDate")
    start = parse_iso(start_raw)
    if start is None:
        result.skip("no_event_start" if not start_raw else "unparseable_start")
        return
    title = plain_text(node.get("name"), MAX_TITLE)
    if not title:
        result.skip("no_title")
        return
    end_raw = node.get("endDate") if isinstance(node.get("endDate"), str) else None
    end = parse_iso(end_raw)
    all_day = isinstance(start, date) and not isinstance(start, datetime)
    if all_day:
        start, end = all_day_span(start, end if isinstance(end, date) else None)
    elif isinstance(end, date) and not isinstance(end, datetime):
        end = None  # a date-only end on a timed start can't be placed
    end, dropped = roll_overnight(start, end)
    if dropped:
        result.skip("end_before_start")
    url = http_url(node.get("url"), context.source_url)
    venue_name, city, country, zone = _venue(node.get("location"))
    node_id = absolute_iri(node.get("@id"))
    result.add(
        ParsedCandidate(
            source_event_id=item_id(node_id) if node_id else derived_id(url, title, start_raw),
            title=title,
            canonical_url=url,
            start=start,
            start_zone=zone,
            start_raw=start_raw,
            end=end,
            end_raw=end_raw,
            all_day=all_day,
            venue_name=venue_name,
            venue_city=city,
            venue_country=country,
            description=plain_text(node.get("description"), MAX_DESCRIPTION),
            status=STATUS.get(_enum_name(node.get("eventStatus")), StatusHint.SCHEDULED),
            sold_out=_sold_out(node.get("offers")),
            series_id=series_id(context.source_id, series_key) if series_key else None,
            raw={"startDate": start_raw, **({"endDate": end_raw} if end_raw else {})},
        )
    )


def _series_key(node: dict) -> str:
    node_id = absolute_iri(node.get("@id"))
    if node_id:
        return node_id
    return derived_id(str(node.get("url", "")), str(node.get("name", "")))


def parse_jsonld(content: bytes, context: SourceContext) -> ParseResult:
    result = ParseResult()
    collector = _ScriptCollector()
    try:
        collector.feed(_decode(content))
        collector.close()
    except Exception:  # html.parser is lenient; anything it raises means a bad document
        result.error = "unreadable_html"
        return result
    for block in collector.blocks:
        text = block.strip().removeprefix("<!--").removesuffix("-->").strip()
        try:
            data = json.loads(text)
        except (ValueError, RecursionError):
            result.skip("invalid_jsonld")
            continue
        for node in _nodes(data):
            kinds = _types(node)
            subs = []
            if kinds & SERIES_TYPES:
                key = _series_key(node)
                for name in ("subEvent", "subEvents"):
                    value = node.get(name)
                    subs += value if isinstance(value, list) else [value] if value else []
                for sub in subs:
                    if result.full:
                        result.skip("too_many_items")
                    elif isinstance(sub, dict):
                        _candidate(sub, context, key, result)
            elif kinds & EVENT_TYPES:
                if result.full:
                    result.skip("too_many_items")
                else:
                    _candidate(node, context, None, result)
    return result
