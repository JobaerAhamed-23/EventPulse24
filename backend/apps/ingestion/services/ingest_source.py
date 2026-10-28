"""`ingest_source`: one run of one Source (FR-14 structured path, AD-4, AD-6, AD-9, AD-17).

lock the run -> FR-17 guard on a locked read -> fetch (conditional) -> parse -> one transaction
per candidate (`ingest_item`) -> close: source state, last-seen marks, one audit row of counts.
Design: .specs-fire/intents/event-catalog-ingestion/work-items/
ingest-pipeline-and-lifecycle-design.md
"""

import logging
import time
from dataclasses import dataclass, field
from hashlib import blake2b
from uuid import UUID

from django.db import connections, transaction
from django.utils import timezone

from apps.ingestion.models import Event, ExtractedRecord, Source
from apps.ingestion.parsers import SourceContext, parse
from apps.ingestion.services.audit import write_audit
from apps.ingestion.services.ingest_item import IngestRun, ingest_item
from apps.ingestion.services.source_registry import SourceNotFoundError, ensure_can_ingest
from ports.fetch import FetchBlockedError, FetchError, FetchResult, SourceFetchPort
from ports.registry import get_fetch_port
from shared.actor import Actor
from shared.db import CATALOG

logger = logging.getLogger(__name__)

PIPELINE_ACTOR = Actor.system("ingest_pipeline")
_RUN_LOCK_PERSON = b"ep-source-run"  # never equal to domain.dedup's identity-lock person


@dataclass(frozen=True)
class IngestReport:
    """What a run did. `outcome`: ok | not_modified | fetch_failed | parse_failed |
    already_running. Celery tasks don't return it (they return None); callers and tests do.
    """

    outcome: str
    error_code: str = ""
    counts: dict[str, int] = field(default_factory=dict)


def source_run_key(source_id: UUID) -> int:
    """The session advisory-lock key for one source's runs (D2), stable across processes."""
    digest = blake2b(source_id.bytes, digest_size=8, person=_RUN_LOCK_PERSON).digest()
    return int.from_bytes(digest, "big", signed=True)


def _advisory(function: str, source_id: UUID) -> bool:
    with connections[CATALOG].cursor() as cursor:
        cursor.execute(f"SELECT {function}(%s)", [source_run_key(source_id)])
        return cursor.fetchone()[0]


def ingest_source(
    source_id: UUID,
    *,
    actor: Actor = PIPELINE_ACTOR,
    fetch_port: SourceFetchPort | None = None,
) -> IngestReport:
    """Ingest one source now. Raises SourcePausedError / CrawlNeedsTosReviewError (FR-13,
    FR-17) and SourceNotFoundError; every other failure is recorded on the source and audited.

    A second run of the same source while one is in progress returns `already_running` and
    writes nothing (D2).
    """
    if not _advisory("pg_try_advisory_lock", source_id):
        return IngestReport("already_running")
    try:
        return _run(source_id, actor, fetch_port or get_fetch_port())
    finally:
        _advisory("pg_advisory_unlock", source_id)


def _run(source_id: UUID, actor: Actor, port: SourceFetchPort) -> IngestReport:
    started = time.monotonic()
    now = timezone.now()
    with transaction.atomic(using=CATALOG):
        try:
            source = Source.objects.using(CATALOG).select_for_update().get(pk=source_id)
        except Source.DoesNotExist:
            raise SourceNotFoundError(details={"source_id": str(source_id)}) from None
        ensure_can_ingest(source)  # on the locked, fresh row (D3)
        source.last_attempted_at = now
        source.save(using=CATALOG, update_fields=["last_attempted_at", "updated_at"])

    run = IngestRun(source=source, actor=actor, now=now)
    try:
        result = port.fetch(
            source.url,
            etag=source.etag or None,
            last_modified=source.last_modified or None,
            source_id=source.id,
        )
    except FetchError as exc:
        moved = isinstance(exc, FetchBlockedError) and exc.reason == "cross_host_redirect"
        # A moved source is never followed: it is re-registered, which resets its ToS review.
        return _close(run, started, "fetch_failed", "source_moved" if moved else exc.code)
    if result.not_modified:
        return _close(run, started, "not_modified", fetch=result)

    context = SourceContext(source.id, result.final_url)  # the final URL is the base (D16)
    parsed = parse(source.acquisition_method, result.body, context)
    run.counts.update({f"skipped:{reason}": n for reason, n in parsed.skipped.items()})
    if parsed.error:
        return _close(run, started, "parse_failed", f"parse_{parsed.error}", fetch=result)
    for candidate in parsed.candidates:
        try:
            keys = ingest_item(run, candidate)
        except Exception as exc:  # one bad item never aborts the source (D13)
            keys = [f"failed:{type(exc).__name__}"]
            logger.warning(
                "Ingest item failed",
                extra={"source_id": source.id, "error_type": type(exc).__name__},
                exc_info=exc,
            )
        run.counts.update(keys)
    return _close(run, started, "ok", fetch=result)


def _close(
    run: IngestRun,
    started: float,
    outcome: str,
    error_code: str = "",
    *,
    fetch: FetchResult | None = None,
) -> IngestReport:
    """Record the run on the source (D16), mark unchanged items seen, and audit (D17)."""
    counts = dict(sorted(run.counts.items()))
    with transaction.atomic(using=CATALOG):
        source = Source.objects.using(CATALOG).select_for_update().get(pk=run.source.pk)
        if run.unchanged_record_ids:
            records = ExtractedRecord.objects.using(CATALOG).filter(pk__in=run.unchanged_record_ids)
            records.update(last_seen_at=run.now)
            Event.objects.using(CATALOG).filter(
                source=source, extracted_records__in=run.unchanged_record_ids
            ).exclude(status=Event.Status.SUPERSEDED).update(last_seen_at=run.now)
        changed = ["consecutive_failures", "last_error_code", "updated_at"]
        if outcome in ("ok", "not_modified"):
            source.last_ingested_at = run.now
            source.consecutive_failures = 0
            source.last_error_code = ""
            source.stale_since = None  # the scheduler sets it; a success clears it (D16)
            changed += ["last_ingested_at", "stale_since"]
        else:
            source.consecutive_failures += 1
            source.last_error_code = error_code
        if fetch is not None:
            source.fetched_url = fetch.final_url
            if outcome == "ok":  # a fresh body: its validators, or none
                source.etag, source.last_modified = fetch.etag or "", fetch.last_modified or ""
            elif outcome == "not_modified":  # a 304 may omit them; keep what we sent
                source.etag = fetch.etag or source.etag
                source.last_modified = fetch.last_modified or source.last_modified
            else:  # a body that failed to parse must be fetched in full next time (plan P8)
                source.etag, source.last_modified = "", ""
            changed += ["fetched_url", "etag", "last_modified"]
        source.save(using=CATALOG, update_fields=changed)
        details = {"outcome": outcome, "counts": counts}
        if error_code:
            details["error_code"] = error_code
        write_audit(
            actor=run.actor,
            action="ingest_source",
            target_type="source",
            target_id=source.id,
            details=details,
        )
    logger.info(
        "Ingest finished",
        extra={
            "source_id": source.id,
            "outcome": outcome,
            "error_code": error_code,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "new_count": counts.get("new", 0),
            "updated_count": counts.get("updated", 0) + counts.get("superseded", 0),
            "unchanged_count": counts.get("unchanged", 0),
            "rejected_count": _prefixed(counts, "rejected:"),
            "ambiguous_count": counts.get("ambiguous", 0),
            "failed_count": _prefixed(counts, "failed:"),
        },
    )
    return IngestReport(outcome, error_code, counts)


def _prefixed(counts: dict[str, int], prefix: str) -> int:
    return sum(n for key, n in counts.items() if key.startswith(prefix))
