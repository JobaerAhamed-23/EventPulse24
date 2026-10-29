"""Domain logic and shared constants stay in step with the catalog model they feed (AD-4, AD-17,
FR-13).
"""

from apps.ingestion.models import AcquisitionMethod, Event, EventStateChange
from domain.lifecycle import LIFECYCLE_FACTS, NOT_YET_STORED, ChangeKind
from shared.constants import DEFAULT_INGESTION_CADENCE, INGESTION_CADENCE_MIN

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


def test_every_acquisition_method_has_a_default_cadence_above_the_floor():
    # shared.constants is stdlib-only, so it keys by the method's string value.
    assert set(DEFAULT_INGESTION_CADENCE) == set(AcquisitionMethod.values)
    assert all(c >= INGESTION_CADENCE_MIN for c in DEFAULT_INGESTION_CADENCE.values())
