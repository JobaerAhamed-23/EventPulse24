"""Domain lifecycle logic stays in step with the catalog model it feeds (AD-4, AD-17)."""

from apps.ingestion.models import Event, EventStateChange
from domain.lifecycle import LIFECYCLE_FACTS, NOT_YET_STORED, ChangeKind

# Domain fact name -> Event field name.
FACT_TO_FIELD = {
    "start_utc": "start_time_utc",
    "end_utc": "end_time_utc",
    "start_time_tz": "start_time_tz",
    "status": "status",
    "is_sold_out": "is_sold_out",
    "venue_fingerprint": "venue",
}


def test_domain_lifecycle_facts_cover_the_event_lifecycle_fields():
    # superseded_by changes only through ChangeKind.SUPERSEDED, which has no fact of its own.
    assert {FACT_TO_FIELD[fact] for fact in LIFECYCLE_FACTS} | {"superseded_by"} == set(
        Event.LIFECYCLE_FIELDS
    )


def test_every_change_kind_is_stored_or_explicitly_not_yet():
    stored = {kind.value for kind in EventStateChange.Kind}

    assert {kind for kind in ChangeKind if kind.value not in stored} == NOT_YET_STORED
