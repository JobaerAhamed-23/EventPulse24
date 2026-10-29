"""Public Event slugs (design D15, pipeline design D18)."""

from uuid import UUID

import pytest
from django.db import IntegrityError

from apps.ingestion.services.event_writes import create_event
from apps.ingestion.services.slugs import mint_slug
from shared.db import CATALOG, PERSONAL
from tests.ingestion.event_writes_support import incoming
from tests.ingestion.factories import EventFactory, SourceFactory

EVENT_ID = UUID("01a18270-0000-7000-8000-00000000abcd")


def test_slug_has_title_local_date_and_id_tail():
    assert mint_slug("Jazz Night at the Fillmore!", "2026-11-05T19:30:00", EVENT_ID) == (
        "jazz-night-at-the-fillmore-2026-11-05-00abcd"
    )


def test_long_tail_on_request():
    slug = mint_slug("Jazz", "2026-11-05T19:30:00", EVENT_ID, long=True)

    assert slug == "jazz-2026-11-05-00000000abcd"  # the last 12 hex characters


@pytest.mark.parametrize("title", ["Концерт", "演唱会", "!!!", ""])
def test_title_without_latin_letters_falls_back_to_event(title):
    assert mint_slug(title, "2026-11-05T19:30:00", EVENT_ID) == "event-2026-11-05-00abcd"


def test_title_part_is_capped():
    slug = mint_slug("word " * 50, "2026-11-05T19:30:00", EVENT_ID)

    assert len(slug.split("-2026-")[0]) <= 80
    assert not slug.startswith("-")


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
def test_slug_collision_retries_with_the_long_tail():
    taken = mint_slug("Jazz Night", "2026-11-05T19:30:00", EVENT_ID)
    EventFactory(slug=taken)

    event = create_event(
        source=SourceFactory(),
        source_event_id="x-1",
        incoming=incoming(title="Jazz Night", start_time_local="2026-11-05T19:30:00"),
        now=incoming().start_utc,
        event_id=EVENT_ID,
    )

    assert event.slug == mint_slug("Jazz Night", "2026-11-05T19:30:00", EVENT_ID, long=True)


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
def test_second_slug_collision_raises():
    for long in (False, True):
        EventFactory(slug=mint_slug("Jazz Night", "2026-11-05T19:30:00", EVENT_ID, long=long))

    with pytest.raises(IntegrityError):
        create_event(
            source=SourceFactory(),
            source_event_id="x-1",
            incoming=incoming(title="Jazz Night", start_time_local="2026-11-05T19:30:00"),
            now=incoming().start_utc,
            event_id=EVENT_ID,
        )


@pytest.mark.django_db(databases=[PERSONAL, CATALOG])
def test_other_integrity_errors_are_not_retried():
    with pytest.raises(IntegrityError) as excinfo:
        create_event(
            source=SourceFactory(),
            source_event_id="",  # event_source_event_id_nonempty_ck
            incoming=incoming(),
            now=incoming().start_utc,
            event_id=EVENT_ID,
        )

    assert excinfo.value.__cause__.diag.constraint_name == "event_source_event_id_nonempty_ck"
