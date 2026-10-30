"""Seed the local stack: proof sources, their venue, the editorial group and the operator.

The command is a client of the published ingestion services (AD-5, AD-14): it never writes a
Source, Venue or ToS review directly. It is idempotent, so it is safe to run on every machine
and in CI.

Two feed sets live in committed data files, so the ToS/robots note and the cadence stay with
the feed:

* `config/local_feeds.json` — the real MMFA JSON-LD and ICS feeds. Fetching them needs
  `SOURCE_FETCH=http`; this command only registers them.
* `config/local_feeds.fixtures.json` — recorded fixtures for the fake fetch adapter, so CI
  never touches the network.

The `editorial` group holds exactly the twelve ingestion permissions the editorial role needs:
add/change/view on Source, Venue and TosReview, and view on Event, EventStateChange and
IngestionAuditEntry. Delete is deliberately absent: sources are paused, never deleted (FR-13).
"""

import json
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError

from apps.ingestion.services.source_registry import (
    TosReviewInput,
    find_source_by_url,
    record_tos_review,
    register_source,
    update_source,
)
from apps.ingestion.services.venue_registry import find_venue, register_venue, set_venue_timezone
from domain.errors import DomainError
from shared.actor import Actor
from shared.db import PERSONAL

CONFIG_DIR = Path(__file__).resolve().parents[2]
REAL_FEEDS_FILE = CONFIG_DIR / "local_feeds.json"
FIXTURE_FEEDS_FILE = CONFIG_DIR / "local_feeds.fixtures.json"

GROUP_NAME = "editorial"

# (model name, actions). The codenames are derived from ContentType, never hard-coded:
# `TosReview` becomes `add_tosreview`, `EventStateChange` becomes `view_eventstatechange`.
EDITORIAL_GRANTS: dict[str, tuple[str, ...]] = {
    "source": ("add", "change", "view"),
    "venue": ("add", "change", "view"),
    "tosreview": ("add", "change", "view"),
    "event": ("view",),
    "eventstatechange": ("view",),
    "ingestionauditentry": ("view",),
}

_DURATION_UNITS = {"D": 86400.0, "H": 3600.0, "M": 60.0, "S": 1.0}


def _duration(value: str) -> timedelta:
    """An ISO-8601 duration such as `PT4H`, as a timedelta.

    Only the time part is read (`PT`), each unit appears at most once, and there must be at
    least one component: `PT` and `PT4H4H` are refused rather than read as zero or as
    eight hours.
    """
    text = value.strip()
    if not text.startswith("PT"):
        raise ValueError(f"{value!r} is not an ISO-8601 duration")
    total = 0.0
    number = ""
    seen_units: set[str] = set()
    for character in text[2:]:
        if character.isdigit() or character == ".":
            number += character
            continue
        if character not in _DURATION_UNITS or not number or character in seen_units:
            raise ValueError(f"{value!r} is not an ISO-8601 duration")
        total += float(number) * _DURATION_UNITS[character]
        number = ""
        seen_units.add(character)
    if number or not seen_units:
        raise ValueError(f"{value!r} is not an ISO-8601 duration")
    return timedelta(seconds=total)


class Command(BaseCommand):
    help = "Seed the local stack with proof sources, the editorial group and an operator account."

    def add_arguments(self, parser):
        parser.add_argument(
            "--real",
            action="store_true",
            help="Register the real public feeds (needs SOURCE_FETCH=http to ingest them).",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="Print the feed set and each ToS/robots note, then exit.",
        )

    def handle(self, *args, **options):
        try:
            feeds_file = REAL_FEEDS_FILE if options["real"] else FIXTURE_FEEDS_FILE
            config = json.loads(feeds_file.read_text())
        except (OSError, ValueError) as exc:
            raise CommandError(f"Can't read the feed file: {exc}") from None

        if options["list"]:
            self._list(config)
            return

        try:
            operator = self._operator(config["operator"])
            actor = Actor.user(operator.id)
            group = self._editorial_group()
            operator.groups.add(group)
            for venue in config["venues"]:
                self._venue(actor, venue)
            for feed in config["feeds"]:
                self._source(actor, feed)
        except DomainError as exc:
            raise CommandError(f"{exc.code}: {exc.message}") from None

        self.stdout.write(
            f"Seeded {len(config['feeds'])} source(s), the {GROUP_NAME} group and the operator "
            f"account."
        )

    # --- the operator and the editorial group --------------------------------------------------

    def _operator(self, spec: dict):
        """The local operator: staff, never superuser, and a member of `editorial`.

        The account is keyed on its email: AD-18 makes the email the login, and there is
        no `username` column any more.
        """
        user_model = get_user_model()
        manager = user_model.objects.db_manager(PERSONAL)
        email = spec["email"]
        user = manager.filter(email=email).first()
        if user is None:
            user = manager.create_user(
                email=email,
                password=spec["password"],
                is_staff=True,
                is_superuser=False,
            )
        else:
            changed = []
            if not user.is_staff:
                user.is_staff = True
                changed.append("is_staff")
            if user.is_superuser:
                user.is_superuser = False
                changed.append("is_superuser")
            if changed:
                user.save(using=PERSONAL, update_fields=changed)
        return user

    def _editorial_group(self) -> Group:
        """The `editorial` group, holding exactly the twelve granted permissions."""
        group = Group.objects.using(PERSONAL).filter(name=GROUP_NAME).first()
        if group is None:
            group = Group.objects.using(PERSONAL).create(name=GROUP_NAME)

        content_types = ContentType.objects.db_manager(PERSONAL).filter(
            app_label="ingestion",
            model__in=EDITORIAL_GRANTS,
        )
        by_model = {content_type.model: content_type for content_type in content_types}
        missing = sorted(set(EDITORIAL_GRANTS) - set(by_model))
        if missing:
            raise CommandError(
                "The ingestion content types are missing; run `manage.py migrate` first. "
                f"Missing: {', '.join(missing)}"
            )

        permissions = []
        for model_name, actions in EDITORIAL_GRANTS.items():
            content_type = by_model[model_name]
            codenames = [f"{action}_{model_name}" for action in actions]
            found = Permission.objects.using(PERSONAL).filter(
                content_type=content_type, codename__in=codenames
            )
            if found.count() != len(actions):
                raise CommandError(f"The permissions for ingestion.{model_name} are missing.")
            permissions.extend(found)
        # Assigned, not appended: a stale grant is removed on every run.
        group.permissions.set(permissions)
        return group

    # --- the venue and the sources -------------------------------------------------------------

    def _venue(self, actor: Actor, spec: dict):
        """The proof venue, with the timezone the events resolve against."""
        venue = find_venue(name=spec["name"], city=spec["city"], country_code=spec["country_code"])
        if venue is None:
            venue = register_venue(
                actor=actor,
                name=spec["name"],
                city=spec["city"],
                country_code=spec["country_code"],
                tz=spec["tz"],
            )
        elif venue.tz != spec["tz"]:
            venue = set_venue_timezone(actor=actor, venue_id=venue.id, tz=spec["tz"])
        return venue

    def _source(self, actor: Actor, feed: dict) -> None:
        """One source and its ToS review, registered once."""
        review = TosReviewInput(
            decision=feed["tos"]["decision"],
            evidence_url=feed["tos"]["evidence_url"],
            notes=feed["tos"]["notes"],
        )
        values = {
            "name": feed["name"],
            "source_type": feed["source_type"],
            "url": feed["url"],
            "city": feed["city"],
            "acquisition_method": feed["acquisition_method"],
            "ingestion_cadence": _duration(feed["ingestion_cadence"]),
            "tz_coverage": feed["tz_coverage"],
        }

        source = find_source_by_url(feed["url"])
        if source is None:
            source = register_source(actor=actor, tos_review=review, **values)
        else:
            source = update_source(actor=actor, source_id=source.id, changes=values)
            if source.tos_status != "approved":
                record_tos_review(actor=actor, source_id=source.id, review=review)

        self.stdout.write(f"  {feed['key']}: {source.name} ({source.acquisition_method})")

    # --- listing -------------------------------------------------------------------------------

    def _list(self, config: dict) -> None:
        self.stdout.write(f"Operator: {config['operator']['email']} (staff, not superuser)")
        for venue in config["venues"]:
            self.stdout.write(f"Venue: {venue['name']}, {venue['city']} ({venue['tz']})")
        for feed in config["feeds"]:
            self.stdout.write("")
            self.stdout.write(f"{feed['key']} — {feed['acquisition_method']}")
            self.stdout.write(f"  url: {feed['url']}")
            self.stdout.write(f"  cadence: {feed['ingestion_cadence']}")
            self.stdout.write(f"  tos: {feed['tos']['decision']} ({feed['tos']['evidence_url']})")
            self.stdout.write(f"  note: {feed['tos']['notes']}")
