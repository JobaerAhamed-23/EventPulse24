"""An `IncomingEvent` builder for tests that call `event_writes` directly (no pipeline run)."""

from datetime import UTC, datetime
from decimal import Decimal

from apps.ingestion.services.event_writes import IncomingEvent
from domain.lifecycle import EventStatus


def incoming(**overrides) -> IncomingEvent:
    defaults = {
        "title": "Jazz Night",
        "description": "",
        "canonical_url": "",
        "venue_id": None,
        "venue_fingerprint": "",
        "title_fingerprint": "v1:jazz night",
        "start_utc": datetime(2026, 11, 6, 3, 30, tzinfo=UTC),
        "end_utc": None,
        "start_time_local": "2026-11-05T19:30:00",
        "start_time_tz": "America/Los_Angeles",
        "status": EventStatus.SCHEDULED,
        "is_sold_out": False,
        "series_id": None,
        "tz_inference_confidence": Decimal("1.00"),
        "extraction_confidence": Decimal("1.00"),
        "publication_status": "published",
        "tz_review_pending": False,
    }
    return IncomingEvent(**(defaults | overrides))
