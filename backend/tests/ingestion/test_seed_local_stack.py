"""The seed command's own logic, tested apart from the end-to-end proof.

The end-to-end suite proves the command works; this file pins the parts that are easy to
get wrong on their own: the ISO-8601 duration parser, the `--list` output, and the refusals
(the unreadable feed file, a missing content type, a missing permission).
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from config.management.commands.seed_local_stack import (
    FIXTURE_FEEDS_FILE,
    REAL_FEEDS_FILE,
    _duration,
)
from shared.db import CATALOG, PERSONAL

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])


# --- the ISO-8601 duration parser ------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("PT4H", timedelta(hours=4)),
        ("PT30M", timedelta(minutes=30)),
        ("PT45S", timedelta(seconds=45)),
        ("PT1H30M", timedelta(hours=1, minutes=30)),
        ("P1D", None),  # not a time-only duration
    ],
)
def test_the_duration_parser_reads_the_iso_form(text, expected):
    if expected is None:
        with pytest.raises(ValueError):
            _duration(text)
    else:
        assert _duration(text) == expected


@pytest.mark.parametrize("text", ["", "4H", "PT", "PTH", "PT4X", "PT4H30", "PT.5H4H"])
def test_the_duration_parser_refuses_anything_else(text):
    with pytest.raises(ValueError):
        _duration(text)


# --- --list ----------------------------------------------------------------------------------


def test_list_prints_the_feed_set_and_the_tos_notes(capsys):
    call_command("seed_local_stack", "--list")

    out = capsys.readouterr().out
    assert "Operator: operator@example.test" in out
    assert "fixture-jsonld" in out
    assert "fixture-rss" in out
    assert "fixture-ics" in out
    assert "https://" in out  # the evidence url of each review
    assert "PT4H" in out  # the cadence


def test_list_prints_nothing_into_the_database():
    from apps.ingestion.models import Source

    call_command("seed_local_stack", "--list")

    assert not Source.objects.using(CATALOG).exists()


# --- the refusals ---------------------------------------------------------------------------


def test_an_unreadable_feed_file_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "config.management.commands.seed_local_stack.FIXTURE_FEEDS_FILE",
        tmp_path / "missing.json",
    )

    with pytest.raises(CommandError, match="Can't read the feed file"):
        call_command("seed_local_stack")


def test_a_feed_file_that_is_not_json_is_refused(tmp_path, monkeypatch):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    monkeypatch.setattr("config.management.commands.seed_local_stack.FIXTURE_FEEDS_FILE", broken)

    with pytest.raises(CommandError, match="Can't read the feed file"):
        call_command("seed_local_stack")


def test_a_missing_ingestion_content_type_is_refused():
    """The command refuses rather than seeding a group with the wrong permissions."""
    from django.contrib.contenttypes.models import ContentType

    ContentType.objects.db_manager(PERSONAL).filter(app_label="ingestion").delete()

    with pytest.raises(CommandError, match="content types are missing"):
        call_command("seed_local_stack")


def test_a_missing_permission_is_refused():
    """A model with no `add` permission is a half-migrated database, not a half-seeded group."""
    from django.contrib.auth.models import Permission

    Permission.objects.using(PERSONAL).filter(codename="add_source").delete()

    with pytest.raises(CommandError, match="permissions for ingestion"):
        call_command("seed_local_stack")


# --- the two feed sets -----------------------------------------------------------------------


def test_both_feed_sets_are_readable_and_name_a_method():
    import json

    for path in (FIXTURE_FEEDS_FILE, REAL_FEEDS_FILE):
        config = json.loads(path.read_text())
        assert config["operator"]["email"] == "operator@example.test"
        assert config["venues"]
        assert config["feeds"]
        for feed in config["feeds"]:
            assert feed["acquisition_method"] in ("jsonld", "rss", "ics", "crawl")
            assert feed["tos"]["decision"] == "approved"
            assert feed["tos"]["evidence_url"].startswith("https://")
            assert _duration(feed["ingestion_cadence"]) >= timedelta(minutes=15)


def test_the_command_reports_what_it_seeded(capsys):
    call_command("seed_local_stack")

    out = capsys.readouterr().out
    assert "Seeded 3 source(s)" in out
    assert "the editorial group and the operator account" in out


def test_the_real_feed_set_is_the_one_the_real_flag_asks_for():
    """`--real` swaps the feed set, not the behaviour."""
    from apps.ingestion.models import Source

    call_command("seed_local_stack", "--real")

    urls = list(Source.objects.using(CATALOG).values_list("url", flat=True))
    assert urls, "the real feed set should register its sources"
    assert all("mmfa.org" in url for url in urls)
