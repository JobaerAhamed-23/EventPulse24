"""One candidate, from timezone resolution to the write (ingest-pipeline-and-lifecycle-design.md).

The stage takes a `ParsedCandidate`, so a later producer (the LLM/HTML path) can feed it
unchanged. Each call runs in its own `atomic(using=CATALOG)` (D1) under the identity advisory
locks (D4). Every decision comes from `domain`: `resolve_tz`, the gates, `dedup.resolve` and
`classify_change`. This module only looks things up and writes.
"""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from django.db import connections, transaction
from django.db.models import Q

from apps.ingestion.models import Event, ExtractedRecord, Source, Venue
from apps.ingestion.parsers import ParsedCandidate
from apps.ingestion.services.event_writes import (
    IncomingEvent,
    apply_lifecycle_change,
    apply_silent_update,
    create_event,
    facts_of,
    supersede_event,
)
from domain import dedup
from domain.confidence import Gate, combine_gates, extraction_gate
from domain.lifecycle import ChangeKind, EventStatus, classify_change
from domain.timezones import TzRejection, resolve_tz
from shared.actor import Actor
from shared.constants import EXTRACTION_CONFIDENCE_STRUCTURED
from shared.db import CATALOG

MAX_CANONICAL_URL = 2048  # Event.canonical_url; longer normalized URLs switch rule (c) off (D19)
# Every gate a structured candidate can reach. REJECT needs extraction confidence below 0.50,
# which only the later LLM path produces.
_PUBLICATION = {
    Gate.PUBLISH: (Event.PublicationStatus.PUBLISHED, False),
    Gate.PUBLISH_FLAGGED: (Event.PublicationStatus.PUBLISHED, True),
    Gate.IN_REVIEW: (Event.PublicationStatus.IN_REVIEW, False),
}


@dataclass
class IngestRun:
    """What one `ingest_source` run shares across its items."""

    source: Source
    actor: Actor
    now: datetime
    counts: Counter = field(default_factory=Counter)
    unchanged_record_ids: list[UUID] = field(default_factory=list)
    _venues: dict[tuple[str, str, str], Venue | None] = field(default_factory=dict)
    _countries: list[str] | None = None

    def registry_countries(self) -> list[str]:
        if self._countries is None:
            rows = Venue.objects.using(CATALOG).values_list("country_code", flat=True)
            self._countries = sorted(rows.distinct())
        return self._countries


def _venue_for(run: IngestRun, candidate: ParsedCandidate) -> Venue | None:
    """The registry venue this candidate names, or None (D5). The pipeline never creates one.

    Without a country, the fingerprint is tried with every registry country; only a single
    match counts.
    """
    if not candidate.venue_name:
        return None
    city = candidate.venue_city or run.source.city
    key = (candidate.venue_name, city, candidate.venue_country)
    if key not in run._venues:
        countries = (
            [candidate.venue_country] if candidate.venue_country else run.registry_countries()
        )
        prints = {dedup.venue_fingerprint(candidate.venue_name, city, cc) for cc in countries}
        matches = list(Venue.objects.using(CATALOG).filter(venue_fingerprint__in=prints - {""})[:2])
        run._venues[key] = matches[0] if len(matches) == 1 else None
    return run._venues[key]


def _payload(candidate: ParsedCandidate) -> dict:
    """The candidate as the source wrote it: text-only evidence, never rendered (AD-9)."""
    return {
        "title": candidate.title,
        "canonical_url": candidate.canonical_url,
        "start_raw": candidate.start_raw,
        "start_zone": candidate.start_zone,
        "end_raw": candidate.end_raw,
        "all_day": candidate.all_day,
        "venue_name": candidate.venue_name,
        "venue_city": candidate.venue_city,
        "venue_country": candidate.venue_country,
        "description": candidate.description,
        "status": candidate.status.value,
        "sold_out": candidate.sold_out,
        "series_id": str(candidate.series_id) if candidate.series_id else None,
        "raw": dict(candidate.raw),
    }


def _content_hash(payload: dict, venue: Venue | None) -> str:
    # The resolution inputs are hashed too: a venue tz added later re-resolves the item (D7).
    material = {
        "payload": payload,
        "venue_id": str(venue.id) if venue else None,
        "venue_tz": venue.tz if venue else None,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _lock(keys: tuple[int, ...]) -> None:
    # Sorted by identity_lock_keys, so every worker takes them in the same order (D4).
    with connections[CATALOG].cursor() as cursor:
        for key in keys:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


def _bound_event(record: ExtractedRecord | None) -> Event | None:
    """The Event this item is bound to, followed along `superseded_by` to the live one (D8)."""
    if record is None or record.event_id is None:
        return None
    event = Event.objects.using(CATALOG).select_for_update().get(pk=record.event_id)
    while event.status == Event.Status.SUPERSEDED:
        event = Event.objects.using(CATALOG).select_for_update().get(pk=event.superseded_by_id)
    return event


def _live_events(candidate: dedup.Candidate) -> list[dedup.LiveEvent]:
    """Non-superseded Events that rules (b) or (c) could match, with their bound sources."""
    query = Q()
    if candidate.venue_fingerprint:
        query |= Q(
            venue_fingerprint=candidate.venue_fingerprint, start_time_utc=candidate.start_utc
        )
    if candidate.canonical_url:
        query |= Q(canonical_url=candidate.canonical_url, start_time_utc=candidate.start_utc)
    if not query:
        return []
    events = list(
        Event.objects.using(CATALOG)
        .filter(query)
        .exclude(status=Event.Status.SUPERSEDED)
        .values("id", "venue_fingerprint", "start_time_utc", "title_fingerprint", "canonical_url")
    )
    bound: dict[UUID, set[UUID]] = {e["id"]: set() for e in events}
    for event_id, source_id in (
        ExtractedRecord.objects.using(CATALOG)
        .filter(event_id__in=bound, resolution=ExtractedRecord.Resolution.RESOLVED)
        .values_list("event_id", "source_id")
    ):
        bound[event_id].add(source_id)
    return [
        dedup.LiveEvent(
            event_id=e["id"],
            venue_fingerprint=e["venue_fingerprint"],
            start_utc=e["start_time_utc"],
            title_fingerprint=e["title_fingerprint"],
            canonical_url=e["canonical_url"],
            bound_source_ids=frozenset(bound[e["id"]]),
        )
        for e in events
    ]


def _save_record(
    run: IngestRun,
    record: ExtractedRecord | None,
    candidate: ParsedCandidate,
    *,
    payload: dict,
    content_hash: str,
    resolution: str,
    event_id: UUID | None = None,
    reject_reason: str = "",
    tz_confidence=None,
    notes: dict | None = None,
) -> None:
    values = {
        "payload": payload,
        "content_hash": content_hash,
        "extraction_confidence": EXTRACTION_CONFIDENCE_STRUCTURED,
        "tz_inference_confidence": tz_confidence,
        "resolution": resolution,
        "reject_reason": reject_reason,
        "event_id": event_id,
        "match_notes": notes or {},
        "last_seen_at": run.now,
    }
    if record is None:
        ExtractedRecord.objects.using(CATALOG).create(
            source=run.source,
            source_event_id=candidate.source_event_id,
            first_seen_at=run.now,
            last_changed_at=run.now,
            **values,
        )
        return
    if record.content_hash != content_hash:
        values["last_changed_at"] = run.now
    ExtractedRecord.objects.using(CATALOG).filter(pk=record.pk).update(**values)


def _flags(incoming: IncomingEvent) -> list[str]:
    flags = []
    if incoming.publication_status == Event.PublicationStatus.IN_REVIEW:
        flags.append("in_review")
    if incoming.tz_review_pending:
        flags.append("tz_review_pending")
    return flags


def ingest_item(run: IngestRun, candidate: ParsedCandidate) -> list[str]:
    """Resolve and write one candidate; returns the count keys for the run's audit row."""
    venue = _venue_for(run, candidate)
    payload = _payload(candidate)
    content_hash = _content_hash(payload, venue)
    record = (
        ExtractedRecord.objects.using(CATALOG)
        .filter(source=run.source, source_event_id=candidate.source_event_id)
        .first()
    )
    # Only this source's runs write its records, and D2 lets one run at a time: no lock needed.
    if (
        record is not None
        and record.content_hash == content_hash
        and record.resolution != ExtractedRecord.Resolution.AMBIGUOUS
    ):
        run.unchanged_record_ids.append(record.pk)
        return ["unchanged"]

    with transaction.atomic(using=CATALOG):
        return _resolve_and_write(run, candidate, venue, record, payload, content_hash)


def _resolve_and_write(run, candidate, venue, record, payload, content_hash) -> list[str]:
    save = {"payload": payload, "content_hash": content_hash}
    tz = resolve_tz(
        candidate.start,
        source_zone=candidate.start_zone,
        venue_tz=venue.tz if venue else None,
        end=candidate.end,
    )
    if isinstance(tz, TzRejection):
        if record is not None and record.resolution == ExtractedRecord.Resolution.RESOLVED:
            # Keep the last good facts; a resolved row can't carry a reject reason (D13). The
            # item was still seen.
            records = ExtractedRecord.objects.using(CATALOG).filter(pk=record.pk)
            records.update(last_seen_at=run.now)
            return [f"rejected_update:{tz.reason}"]
        _save_record(run, record, candidate, resolution="rejected", reject_reason=tz.reason, **save)
        return [f"rejected:{tz.reason}"]

    gate = combine_gates(tz.gate, extraction_gate(EXTRACTION_CONFIDENCE_STRUCTURED))
    publication, tz_review_pending = _PUBLICATION[gate]
    url = dedup.canonical_url(candidate.canonical_url)
    city = candidate.venue_city or run.source.city
    incoming = IncomingEvent(
        title=candidate.title,
        description=candidate.description,
        canonical_url=url if len(url) <= MAX_CANONICAL_URL else "",
        venue_id=venue.id if venue else None,
        venue_fingerprint=venue.venue_fingerprint
        if venue
        else dedup.venue_fingerprint(candidate.venue_name, city, candidate.venue_country),
        title_fingerprint=dedup.title_fingerprint(candidate.title),
        start_utc=tz.start_utc,
        end_utc=tz.end_utc,
        start_time_local=tz.start_time_local,
        start_time_tz=tz.zone,
        status=EventStatus(candidate.status.value),
        is_sold_out=candidate.sold_out,
        series_id=candidate.series_id,
        tz_inference_confidence=tz.confidence,
        extraction_confidence=EXTRACTION_CONFIDENCE_STRUCTURED,
        publication_status=publication,
        tz_review_pending=tz_review_pending,
    )
    save["tz_confidence"] = tz.confidence
    identity = dedup.Candidate(
        source_id=run.source.id,
        source_event_id=candidate.source_event_id,
        venue_fingerprint=incoming.venue_fingerprint,
        start_utc=incoming.start_utc,
        title_fingerprint=incoming.title_fingerprint,
        canonical_url=incoming.canonical_url,
    )
    _lock(dedup.identity_lock_keys(identity))
    bound = _bound_event(record)
    resolution = dedup.resolve(identity, bound.pk if bound else None, _live_events(identity))

    if isinstance(resolution, dedup.Ambiguous):
        notes = {"ambiguous": sorted(str(i) for i in resolution.event_ids)}
        _save_record(run, record, candidate, resolution="ambiguous", notes=notes, **save)
        return ["ambiguous"]

    if isinstance(resolution, dedup.New):
        event = create_event(
            source=run.source,
            source_event_id=candidate.source_event_id,
            incoming=incoming,
            now=run.now,
        )
        _save_record(run, record, candidate, resolution="resolved", event_id=event.pk, **save)
        return ["new", *_flags(incoming)]

    notes = {
        "rule": resolution.rule.value,
        "review_signals": sorted(str(i) for i in resolution.review_signals),
    }
    event = bound if bound is not None and bound.pk == resolution.event_id else None
    event = event or Event.objects.using(CATALOG).select_for_update().get(pk=resolution.event_id)
    resolved = {"resolution": "resolved", "notes": notes, **save}
    if event.source_id != run.source.id or resolution.rule != dedup.Rule.SOURCE_ITEM:
        # Only an Event's origin source changes its facts; other sources bind to it (D8).
        _save_record(run, record, candidate, event_id=event.pk, **resolved)
        return ["bound_other_source"]

    change = classify_change(facts_of(event), incoming.facts(), event.original_start_utc)
    if change is not None and ChangeKind.SUPERSEDED in change.kinds:
        new, _ = supersede_event(
            old=event, incoming=incoming, record_id=record.pk, actor=run.actor, now=run.now
        )
        _save_record(run, record, candidate, event_id=new.pk, **resolved)
        return ["superseded", *_flags(incoming)]
    if change is not None and change.is_lifecycle:
        apply_lifecycle_change(
            event=event, incoming=incoming, change=change, actor=run.actor, now=run.now
        )
        outcome = "updated"
    else:
        # Title, description, URL or the gates only, or nothing the Event shows (D9, P1).
        apply_silent_update(event=event, incoming=incoming, now=run.now)
        outcome = "silent_updated" if change is not None else "unchanged"
    _save_record(run, record, candidate, event_id=event.pk, **resolved)
    return [outcome] if outcome == "unchanged" else [outcome, *_flags(incoming)]
