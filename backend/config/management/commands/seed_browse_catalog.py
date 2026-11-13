"""Seed the Browse surface's local catalog: a city, a week of events, and four accounts.

**The point of this command is reproducibility.** The Browse walk-through — the one that
checks the surface against the design's own locks, in a real browser — is only worth
anything if the next person can see the same thing I saw. That needs three things:
the data in a **committed file** rather than in hand-inserted rows, a **repeatable
command** rather than a runbook, and an **idempotent** command rather than a script that
can only be run once.

**It is idempotent, and every row is keyed on something stable.** The source is keyed on
its URL, the venues on their fingerprints, the events on `(source, source_event_id)`, and
the accounts on their email. Running it twice leaves the same rows, not twice as many —
and the second run says so, so "it did nothing" and "it did everything" are different
outputs.

**The times in the data file are relative.** `config/browse_seed.json` says "day 0, hour
20", not a date. An absolute date would put the whole catalog in the past the day after
the file was written, and Browse's window is *"tonight through seven days"* — so a stale
file would seed an empty surface and the seed would still report success. The relative
form is resolved against the moment the command runs, in the city's own zone.

**The hours are wall-clock, and day 0 moves by a day when it has to.** The file's hours
mean what they say — a 07:00 yoga class is at seven in the morning — because the
descriptions say so ("doors at seven"). But Browse's window starts at *now*, so a day-0
event whose hour has already passed is in the past and the read leaves it out. The seed
therefore slides the whole week forward by one day when the file's earliest day-0 hour
is behind the clock. One day is enough (the file's day-0 hours are inside one local
day) and one day is all the window has room for. `_base_day` says which day it chose
and why.

**It writes through the published services, never through the models.** AD-2's
`models-ingestion`, `models-identity` and `models-personalization` contracts say only the
owning app may import its models; this command lives in `config`, so it cannot reach a
single row. It calls `apps.ingestion.services.event_writes.create_event` (which mints
the slug and satisfies the `catalog.guard_event_write` trigger), the registry services,
`apps.identity.services.ensure_account` and the published personalization services. The
command is the **schedule**; the services are the **rule**.

**The source's terms-of-service review is signed by a named person, not by the system.**
The ingestion services refuse a system actor for a review, because a review is a human
saying "I read this source's terms and they permit what we are about to do". The seed
file therefore names a `reviewer` account, and the review is attributed to that
account — a fixture, like the rest of the file, but a *person* as the rule requires.

**The chip expectations in the data file are checked, not assumed.** Each event names the
chip its title is supposed to earn, and the command runs the real matcher
(`chip_keys_for`) over the title and compares. A keyword table change that moves a title
into a different chip — or out of one — fails the seed loudly instead of quietly
producing a catalog whose why-tags do not match what the file says.

**It seeds one city, and one week's worth.** The window is seven days and the page size
is twenty-four, so forty-nine events is deliberately **more than one page**: it proves
the chunk loader, and it gives the `tag:` filter something to narrow. One event is a
cancelled one and one is a postponed one, because those are the must-know stripe — the
surface's one amber card — and a walk-through that has never seen one has not seen the
surface.

**The Free and Pro accounts are the two halves of the save cap.** The Free user spends
the one save a day and is refused the second; the Pro user has no cap at all. A
walk-through that only tested one of them would have tested half the gate.

**A third account has no city, and that is the city-emptiness's subject.** Browse has
two emptinesses, and only one of them is reachable through the API. A user's city can
never be *cleared*: `PUT /onboarding/digest-preference` reads a null city as "leave it
alone", and `set_home_city(None)` — which does clear it — is on no browser path. So the
seed writes the city itself, and the account's Browse shows the quiet empty state with
"Change city". It is a **third** account rather than an emptied one, because clearing
the Free account's city would change what every other test sees.

**A fourth account is a second Free account, and the reason is the save allowance.** The
allowance is one save per user per day, and it lives in a throttle window that outlives
any single test. So two tests that each need to save once cannot share one account — the
first test spends the allowance, and the second finds the wall already up, failing for a
reason that has nothing to do with the code under test. **Separate accounts have
separate allowances**, so each test spends its own.

**The Free account's allowance is put back on every run.** The allowance is a throttle
window in Redis, and it outlives the command — so a second run would find the quota
already spent, the wall would be up before the walk-through had pressed anything, and
the test that exercises the wall would fail for the wrong reason. The seed clears the
window and **leaves the saved rows alone**: the allowance is the counter, not the saves.

**The sign-in allowance is put back too, and for the same reason.** The sign-in limits
are ten an hour per IP and five an hour per account, and the walk-through signs in
several times — from one address, because it runs against one stack on one machine. So
the seed clears the sign-in windows as well, and the reader of a seeded run starts with
a full allowance. **The limits themselves are not touched**: ten sign-ins an hour are
still ten, and the eleventh is still refused.

**`--reset-saves` clears the saved rows too, and it is opt-in.** The default must not
un-save a reader's events — the walk-through is *about* seeing a saved event. But a
**test** run must start from the same state every time: a leftover row puts the Save
button in the `saved` state, so the suite's *first* press takes the unsave branch and
the button correctly goes back to "Save" — a failure that has nothing to do with the
code under test. So the flag says "this is a test run" and the flag is what clears it.

**The order of the writes is load-bearing, and it is not obvious.** The seed writes the
events, then the **Event Fit** rows, and only then the accounts' city — and each of
those depends on the one before it:

- A city's **coverage** is not a list of names; it is "the cities with a published
  event that has an Event Fit". `list_supported_cities` reads the fit rows, so a city
  with no fit row is not a city the catalog serves.
- `set_digest_preference` **checks the city against the catalog's coverage** and
  replaces an uncovered city with the fallback. So if the accounts were written before
  the fits, their city would silently become "New York City" — a real city, full of
  nothing this seed wrote — and Browse would serve an empty surface while the seed
  reported success.
- The fit is computed from the event's **venue city**, so the venues have to exist
  before the events, and the events before the fits.

That chain is why the seed says what it says. It is also why the walk-through's surface
had to be built before this command existed.
"""

import json
import os
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.identity.services import ensure_account, record_subscription_started
from apps.identity.services.throttle import reset_sign_in_throttle
from apps.ingestion.event_fit.writes import backfill_event_fits
from apps.ingestion.services.catalog_read import find_event_by_source_item, list_source_events
from apps.ingestion.services.chip_matching import chip_keys_for
from apps.ingestion.services.event_writes import IncomingEvent, create_event, retire_event
from apps.ingestion.services.source_registry import (
    TosReviewInput,
    find_source_by_url,
    register_source,
)
from apps.ingestion.services.venue_registry import find_venue, register_venue
from apps.personalization.services.onboarding import (
    INTEREST_CHIP_KEYS,
    advance_step,
    set_digest_preference,
    set_interests,
)
from apps.personalization.services.save_cap import reset_save_allowance
from apps.personalization.services.saved_events import list_saved_events, unsave_event
from domain.dedup import title_fingerprint
from domain.errors import OnboardingAlreadyCompleteError
from domain.lifecycle import EventStatus
from ports.billing import ProPlan
from shared.actor import Actor
from shared.constants import (
    EXTRACTION_CONFIDENCE_PUBLISH,
    TZ_INFERENCE_CONFIDENCE_DIGEST,
)
from shared.db import CATALOG
from shared.durations import parse_duration

CONFIG_DIR = Path(__file__).resolve().parents[2]
SEED_FILE = CONFIG_DIR / "browse_seed.json"

#: The actor every write is attributed to. A system actor with a label, never a user's id
#: and never an email (AD-5, AD-13).
SEED_ACTOR = Actor.system("browse_seed")

#: The extraction confidence every seeded event carries. **The publish gate's own value**,
#: so an event seeded at exactly the threshold is exactly as eligible as one that was
#: ingested at it — and `EXTRACTION_CONFIDENCE_PUBLISH` is where it is read from, so a
#: change to the gate moves the seed with it.
SEED_EXTRACTION_CONFIDENCE = EXTRACTION_CONFIDENCE_PUBLISH

#: The timezone-inference confidence. Same reasoning: the digest gate's own value.
SEED_TZ_CONFIDENCE = TZ_INFERENCE_CONFIDENCE_DIGEST

#: The canonical source of the seeded events. Every event comes from one source, so the
#: FR-14 staleness bound has one TTL to reason about, and the Source Badge on every card
#: is the same one.
SEED_SOURCE_EVENT_PREFIX = "browse-seed:"

#: The address the seeded run signs in from, and so the address the sign-in throttle's
#: per-IP counter is keyed on. The frontend proxies to the API over loopback, so the API
#: records the loopback address — the same one the `auth:sign_in:ip:` key names. The
#: environment variable overrides it, for a stack reached on another address.
SEED_CLIENT_IP = "127.0.0.1"

#: The states an event may be seeded in. `superseded` is not among them: a superseded
#: event can only be made by superseding a live one (`make_superseded_pair`), and a seed
#: has no reason to retire its own catalog.
SEEDABLE_STATUSES = ("scheduled", "cancelled", "postponed")

#: Why a row was retired because the file no longer names it. **The two reasons are
#: different facts and are reported differently** — a dropped event is the file changing
#: its mind, and a drifted event is the clock running out — so the command says which one
#: happened rather than reporting both as "retired".
ORPHAN_REASON = "the file no longer names it"

#: Why a row was retired because its time had run out. The file's `day` and `hour` are
#: relative, so every run resolves them to a different instant; a row left where it was
#: keeps the time it had, and a seeded event in the past is one Browse cannot show.
DRIFTED_REASON = "it had run out of time"


def _parse_duration(value: str) -> timedelta:
    """An ISO-8601 duration such as `PT4H`, as a timedelta.

    The shape and the refusals live in `shared.durations`, because the local-stack seed
    command reads the same shape of value and one parser is better than two.
    """
    return parse_duration(value)


def _parse_clock(value: str) -> time:
    """A `HH:MM` wall clock, as `time` — never an instant, never offset-bearing."""
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"{value!r} is not an HH:MM clock")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"{value!r} is not a clock time")
    return time(hour=hour, minute=minute)


def _local_wall_clock(instant: datetime, tz: str) -> str:
    """The normalized `start_time_local` form: no offset, no microseconds (design D8)."""
    return instant.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%dT%H:%M:%S")


def retirement_reason(entry: tuple[str, str]) -> str:
    """Why a row was retired, from the `(key, reason)` pair the command collected.

    **The reason travels with the event, not in a parallel list.** Two reasons exist and
    they are different facts — "the file no longer names it" and "it had run out of
    time" — and a report that printed both as "retired" would hide which one happened. The
    pair carries the fact with the name, so the two can never come apart.
    """
    _key, reason = entry
    return reason


class Command(BaseCommand):
    help = "Seed the Browse surface's local catalog: a city, a week of events, four accounts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default=str(SEED_FILE),
            help="The seed data file. Defaults to config/browse_seed.json.",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="Print what the file says — the city, the counts, the accounts — then exit.",
        )
        parser.add_argument(
            "--reset-saves",
            action="store_true",
            help=(
                "Clear the seeded accounts' saved events, so a test run starts from an "
                "empty Pulse. The save ALLOWANCE is always reset; this flag also clears "
                "the saved rows themselves."
            ),
        )

    def handle(self, *args, **options):
        try:
            data = self._read(options["file"])
        except CommandError:
            raise
        except (OSError, ValueError) as exc:
            raise CommandError(f"Can't read the seed file: {exc}") from None

        if options["list"]:
            self._list(data)
            return

        city = data["city"]
        zone = city["tz"]
        now = datetime.now(UTC)
        local_today = self._base_day(data, zone=zone, now=now)

        try:
            reviewer = self._reviewer(data)
            source = self._source(data, reviewer=reviewer)
            venues = self._venues(data, actor=SEED_ACTOR)
            created_events, kept_events, retired_events = self._events(
                data, source=source, venues=venues, zone=zone, local_today=local_today, now=now
            )
            fitted = self._event_fits(now=now)
            accounts = self._users(data, now=now, reset_saves=options["reset_saves"])
            self._reset_auth_throttle(data)
        except CommandError:
            raise
        except ValueError as exc:
            raise CommandError(str(exc)) from None

        self.stdout.write(
            f"Seeded {len(created_events)} event(s) ({len(kept_events)} already there) "
            f"in {city['name']}."
        )
        self.stdout.write(f"Fitted {fitted} event(s) for the city's coverage.")
        for key, reason in retired_events:
            self.stdout.write(f"  retired {key}: {retirement_reason((key, reason))}")
        for account in accounts:
            self.stdout.write(f"  {account}")

    # --- the file -------------------------------------------------------------------------------

    def _read(self, path: str) -> dict:
        """The seed file, as a dict, with the shape checked."""
        try:
            data = json.loads(Path(path).read_text())
        except OSError as exc:
            raise CommandError(f"Can't read the seed file: {exc}") from None
        except ValueError as exc:
            raise CommandError(f"The seed file is not valid JSON: {exc}") from None

        if not isinstance(data, dict):
            raise CommandError("The seed file must be a JSON object.")
        for key in ("city", "source", "reviewer", "venues", "events", "users"):
            if key not in data:
                raise CommandError(f"The seed file has no {key!r}.")
        return data

    # --- the source and the venues ---------------------------------------------------------------

    def _reviewer(self, data: dict):
        """The person whose ToS review stands behind the seeded source.

        **A review must be recorded by a person, not by the system.** The ingestion
        services refuse a system actor for a terms-of-service review (`_require_person`),
        because a review is a human saying "I have read this source's terms and they
        permit what we are about to do". A seed cannot honestly claim to have read
        anything, so the review is attributed to a **named account in the seed file** —
        the same person a local operator is — rather than to `browse_seed`.

        The account is created through `ensure_account`, so it is idempotent and it is
        not reachable from the network. The review it signs is the review the file
        carries, and the file says plainly that it is a fixture.
        """
        spec = data["reviewer"]
        account = ensure_account(email=spec["email"], password=spec["password"])
        return Actor.user(account.user_id)

    def _source(self, data: dict, *, reviewer: Actor):
        """The one source every seeded event comes from, registered once."""
        spec = data["source"]
        source = find_source_by_url(spec["url"])
        if source is not None:
            return source
        return register_source(
            actor=reviewer,
            name=spec["name"],
            source_type=spec["source_type"],
            url=spec["url"],
            city=data["city"]["name"],
            acquisition_method=spec["acquisition_method"],
            tz_coverage=spec["tz_coverage"],
            ingestion_cadence=_parse_duration(spec["ingestion_cadence"]),
            freshness_ttl_hours=int(spec.get("freshness_ttl_hours", 24)),
            tos_review=TosReviewInput(
                decision=spec["tos"]["decision"],
                evidence_url=spec["tos"]["evidence_url"],
                notes=spec["tos"]["notes"],
            ),
        )

    def _venues(self, data: dict, *, actor: Actor) -> dict[str, object]:
        """The venues, keyed by the file's own key, registered once each."""
        country_code = data["city"]["country_code"]
        tz = data["city"]["tz"]
        venues: dict[str, object] = {}
        for spec in data["venues"]:
            venue = find_venue(name=spec["name"], city=spec["city"], country_code=country_code)
            if venue is None:
                venue = register_venue(
                    actor=actor,
                    name=spec["name"],
                    city=spec["city"],
                    country_code=country_code,
                    tz=tz,
                )
            venues[spec["key"]] = venue
        return venues

    # --- the events -----------------------------------------------------------------------------

    def _base_day(self, data: dict, *, zone: str, now: datetime) -> object:
        """The local date the file's "day 0" is, chosen so that the whole week is ahead.

        **Why the base day is not simply today.** The file's hours are **wall-clock**
        hours — a 07:00 yoga class, an 18:30 meetup — and Browse's window starts at
        *now*. So a day-0 event whose clock time has already passed today is in the
        past, and the read leaves it out. At 19:33 that is nine of the ten day-0
        events: the seed would report forty-nine events and the surface would show
        forty, with no error anywhere. **A walk-through is only worth what it covers**,
        and a surface missing a third of its events is not the surface being walked.

        **So the base day moves, by at most one day.** If the file's **earliest** day-0
        hour is still ahead of now, day 0 is today. If it is not, day 0 is tomorrow.
        One day is enough because the file's day-0 hours all fall inside one local
        day, and tomorrow's day-0 hours are all in tomorrow's future.

        **The earliest hour is the one that decides.** The later day-0 hours would be
        fine on their own — a 20:00 concert is still ahead at 19:33 — but the 07:00
        yoga class is not, and one event behind the clock is one event the surface
        cannot show. So the base day moves for the sake of the **earliest** event, and
        every later one comes along with it.

        **A one-day shift still fits the window.** Browse's window reaches the end of
        the seventh local day from now, so a week starting tomorrow ends on the seventh
        day from today — inside it. The window has room for exactly this one-day slide
        and no more, which is why the shift is one day and not "as many as it takes".

        **The times keep their meaning.** Nothing about the file changes: a 07:00 class
        is at 07:00, and the descriptions that say "doors at seven" stay true. What
        changes is *which* day the file's "day 0" means, and that is the one thing the
        file could not say for itself — it is relative to the moment the command runs.
        """
        zoneinfo = ZoneInfo(zone)
        local_now = now.astimezone(zoneinfo)
        today = local_now.date()

        earliest_day0 = min(
            (int(event["hour"]) * 60 + int(event.get("minute", 0)))
            for event in data["events"]
            if int(event["day"]) == 0
        )
        first_minute_of_day0 = datetime.combine(
            today,
            datetime.min.time(),
            tzinfo=zoneinfo,
        ) + timedelta(minutes=earliest_day0)

        if first_minute_of_day0 > local_now:
            return today
        return today + timedelta(days=1)

    def _events(
        self,
        data: dict,
        *,
        source,
        venues: dict[str, object],
        zone: str,
        local_today,
        now: datetime,
    ) -> tuple[list[str], list[str], list[tuple[str, str]]]:
        """The events, created once each, and the ones the file no longer names retired.

        **An event that is already there is left alone — at the time the file says.**
        The key is `(source, source_event_id)` and the id is the file's own `key`, so a
        second run finds the first run's rows. A row whose time still matches what the
        file resolves to is left exactly as it is: an event that has been saved, shared or
        superseded in the meantime must not silently change under its readers.

        **A row at the wrong time is retired and written again.** The file's `day` and
        `hour` are relative, so they resolve to a different instant every time the
        command runs on a different day — and a row left where it was would keep the
        time it had, not the time the file says. A seeded event whose clock has run out
        is **in the past**, and Browse's window starts at now, so the surface would show
        forty-eight of the file's forty-nine events and the seed would report success.
        The row is retired and the event is created again at the time the file resolves
        to.

        **An event the file has dropped is retired.** The file is the source of truth for
        what the catalog should hold, so leaving the dropped rows behind would make
        "edit the file, re-run" accumulate rather than converge. `_retire_orphans` does
        that half.
        """
        created: list[str] = []
        kept: list[str] = []
        retired: list[tuple[str, str]] = []

        for spec in data["events"]:
            key = spec["key"]
            source_event_id = SEED_SOURCE_EVENT_PREFIX + key

            venue = venues.get(spec["venue"])
            if venue is None:
                raise CommandError(f"The event {key!r} names a venue that is not in the file.")

            start_local = datetime.combine(
                local_today + timedelta(days=int(spec["day"])),
                time(hour=int(spec["hour"]), minute=int(spec["minute"])),
                tzinfo=ZoneInfo(zone),
            )
            start_utc = start_local.astimezone(UTC)

            status = spec["status"]
            if status not in SEEDABLE_STATUSES:
                raise CommandError(f"The event {key!r} has a status that cannot be seeded.")

            # **A row that exists but is at the wrong time does not count as existing.**
            # The file's `day` and `hour` are relative, so they resolve to a different
            # instant every time the command runs on a different day — and a row left
            # where it was would keep the time it had, not the time the file says. A
            # seeded event whose clock has run out is **in the past**, and Browse's
            # window starts at now, so the surface would show forty-eight of the
            # file's forty-nine events and the seed would report success. The row is
            # retired and the event is created again at the time the file resolves to.
            existing = self._existing(source, source_event_id)
            if existing is not None:
                if existing.start_time_utc == start_utc:
                    kept.append(key)
                    continue
                with transaction.atomic(using=CATALOG):
                    retire_event(event_id=existing.id, actor=SEED_ACTOR, now=now)
                retired.append((key, DRIFTED_REASON))

            self._check_chip(spec)

            incoming = IncomingEvent(
                title=spec["title"],
                description=spec.get("description", ""),
                canonical_url=f"https://browse-seed.example.test/events/{key}",
                venue_id=venue.id,
                venue_fingerprint=venue.venue_fingerprint,
                title_fingerprint=title_fingerprint(spec["title"]),
                start_utc=start_utc,
                end_utc=None,
                start_time_local=_local_wall_clock(start_utc, zone),
                start_time_tz=zone,
                status=EventStatus(status),
                is_sold_out=bool(spec.get("is_sold_out", False)),
                series_id=None,
                tz_inference_confidence=SEED_TZ_CONFIDENCE,
                extraction_confidence=SEED_EXTRACTION_CONFIDENCE,
                publication_status="published",
                tz_review_pending=False,
            )
            create_event(
                source=source,
                source_event_id=source_event_id,
                incoming=incoming,
                now=now,
            )
            created.append(key)

        retired.extend(self._retire_orphans(data, source=source, now=now))

        return created, kept, retired

    def _retire_orphans(self, data: dict, *, source, now: datetime) -> list[tuple[str, str]]:
        """Retire the events the file no longer names.

        **The file is the source of truth.** It says what the catalog should contain, so an
        event it has dropped has to leave the catalog — otherwise "edit the file, re-run the
        command" leaves the old rows behind and the walk-through sees events nobody asked
        for. A command that could not do this would not be repeatable; it would be a
        command that worked once.

        **Retiring is not cancelling.** A cancelled event is a *must-know card* — the
        surface's amber stripe — so cancelling a dropped event would make the surface
        announce a cancellation that never happened. `retire_event` supersedes the row
        instead: it leaves every live read, keeps the row and its history (FR-13), and
        says nothing to anybody.

        **Only this source's own rows are touched.** The seed owns its source outright —
        it registered the URL and it wrote every event under it — so the rows it may
        retire are the ones it wrote, identified by the prefix it writes them with.
        """
        wanted = {SEED_SOURCE_EVENT_PREFIX + spec["key"] for spec in data["events"]}
        orphans = [
            ref
            for ref in list_source_events(source_id=source.id)
            if ref.source_event_id.startswith(SEED_SOURCE_EVENT_PREFIX)
            and ref.source_event_id not in wanted
        ]
        for orphan in orphans:
            with transaction.atomic(using=CATALOG):
                retire_event(event_id=orphan.id, actor=SEED_ACTOR, now=now)
        return [
            (ref.source_event_id.removeprefix(SEED_SOURCE_EVENT_PREFIX), ORPHAN_REASON)
            for ref in orphans
        ]

    def _existing(self, source, source_event_id: str):
        """The live event this source already has under this id, or `None`.

        **The lookup goes through the published read**, not the model: AD-2's
        `models-ingestion` contract says only `apps.ingestion` may import
        `apps.ingestion.models`, and this command lives in `config`.

        **"Live" is the word that matters.** A superseded event shares the source item
        with its replacement, so a lookup that counted the retired row would say "already
        there" and the seed would skip the successor — leaving the catalog without the
        event.

        **The start time comes back too**, because "the row is there" is not the whole
        question — see `_events`, where a row at the wrong time is retired and the event
        is written again at the time the file resolves to.
        """
        return find_event_by_source_item(
            source_id=source.id,
            source_event_id=source_event_id,
        )

    def _event_fits(self, *, now: datetime) -> int:
        """Persist the Event Fit for the published events, and report how many were written.

        **Why the seed has to do this at all.** A city's coverage is not a list of names:
        `list_supported_cities` reads the **Event Fit** rows, and a city with no fit row
        is a city the catalog does not serve. `set_digest_preference` checks the city it
        is given against that coverage and replaces an uncovered city with the fallback
        ("New York City") — so without this step the seeded accounts would end up in a
        real city full of nothing this seed wrote, and Browse would serve an empty
        surface while the seed reported success. That is exactly what happened the first
        time this command was written, and the test now pins it.

        **The backfill is the published write, and it is idempotent.** The write is an
        upsert on `(event, city)`, so a second run replaces each row's score and tags
        with the same values rather than adding rows. The command therefore reaches for
        `backfill_event_fits` rather than reaching for the model — AD-2 says only
        `apps.ingestion` may import `apps.ingestion.models`, and this command lives in
        `config`.

        **It covers the whole published catalog, not only the seeded events.** The
        backfill walks every published event with a venue, and that is the right scope
        for a command whose job is "the catalog is consistent now": the seeded events
        are the ones this command is responsible for, and the rest are already there.
        """
        written, _seen = backfill_event_fits(now=now, actor=SEED_ACTOR)
        return written

    def _check_chip(self, spec: dict) -> None:
        """The event's title must still earn the chip the file says it does.

        **This is the check that keeps the file honest.** The chip matcher is a
        whole-word match over `shared.constants.INTEREST_CHIP_KEYWORDS`, so a keyword
        table change can move a title into a different chip or out of one entirely. The
        file's `chip` is what the walk-through was done against, so a title that no
        longer matches it fails the seed rather than producing a catalog whose why-tags
        disagree with its own data file.
        """
        expected = spec.get("chip")
        if expected is not None and expected not in INTEREST_CHIP_KEYS:
            raise CommandError(
                f"The event {spec['key']!r} names the chip {expected!r}, which is not a "
                f"chip the server knows."
            )
        matched = chip_keys_for(title=spec["title"], description=spec.get("description", ""))
        if expected is None:
            if matched:
                raise CommandError(
                    f"The event {spec['key']!r} is expected to earn no chip, but its title "
                    f"matches {', '.join(matched)}."
                )
            return
        if expected not in matched:
            raise CommandError(
                f"The event {spec['key']!r} is expected to earn the chip {expected!r}, but "
                f"its title matches {', '.join(matched) or 'nothing'}."
            )

    # --- the accounts ---------------------------------------------------------------------------

    def _users(self, data: dict, *, now: datetime, reset_saves: bool = False) -> list[str]:
        """The accounts, each with a completed onboarding and a saved city.

        **The `no-city` account has no city, and that is what it is for.** Browse has two
        emptinesses, and only one of them is reachable through the API: a user's city can
        never be *cleared*, because `PUT /onboarding/digest-preference` reads a null city
        as "leave it alone" and `set_home_city(None)` is not on any browser path. So the
        seed writes the city directly — `city: null` in the file means "no city at all",
        and the account's Browse shows the quiet empty state with "Change city".

        **It is a third account, not an emptied one.** Clearing the free account's city
        would change what every other test sees — the free account's cards *are* the
        other tests' subject.
        """
        city = data["city"]["name"]
        lines: list[str] = []

        for spec in data["users"]:
            account = ensure_account(email=spec["email"], password=spec["password"])
            user_id = account.user_id
            user_actor = Actor.user(user_id)

            if spec.get("plan") == "pro":
                record_subscription_started(
                    actor=user_actor,
                    user_id=user_id,
                    plan=ProPlan(spec.get("subscription_plan", ProPlan.MONTHLY.value)),
                    customer_ref=f"seed_{spec['key']}",
                    subscription_ref=f"seed_sub_{spec['key']}",
                    current_period_end=now + timedelta(days=30),
                    event_at=now,
                )

            # The interests, the digest preference and the city. `set_digest_preference`
            # writes the zone, the delivery time and the city in one transaction, and the
            # city is checked against the catalog's own coverage — so the venues above
            # have to exist first, which is why the events are seeded before the users.
            set_interests(
                user_id=user_id,
                chip_keys=list(spec.get("chips", [])),
                actor=user_actor,
                now=now,
            )
            set_digest_preference(
                user_id=user_id,
                delivery_time=_parse_clock(spec.get("delivery_time", "09:00")),
                timezone_name=spec.get("timezone", data["city"]["tz"]),
                actor=user_actor,
                now=now,
                city=spec.get("city", city),
            )

            state = self._complete_onboarding(user_id=user_id, actor=user_actor, now=now)

            # **The save allowance goes back to full.** The Free account's allowance is
            # one save a day, and it lives in a throttle window that outlives the seed. So
            # a second run of this command would find the quota already spent — the wall
            # would be up before the walk-through had pressed anything — and the test that
            # exercises the wall would fail for the wrong reason. **A seed that could only
            # be run once would not be a seed.**
            #
            # **The saved rows are untouched by default.** The allowance is the throttle's
            # counter, not the `SavedEvent` rows: clearing the counter gives the account
            # its one save back while leaving what it has saved where it is. That is right
            # for the walk-through — a seed that un-saved the account's events would
            # change what the surface shows, and the walk-through is *about* seeing a
            # saved event.
            reset_save_allowance(user_id=user_id)

            # **A test run starts from an empty Pulse.** `--reset-saves` is the flag that
            # says so, and it is **opt-in** precisely because the default must not un-save
            # a reader's events. The end-to-end suite needs it: the Free test's *first*
            # press has to be a save and not the unsave of a row a previous run left
            # behind — a leftover row puts the button in the `saved` state, so the press
            # takes the delete branch and the button correctly goes back to "Save". The
            # test would then fail for a reason that has nothing to do with the code it
            # is testing.
            #
            # **The saves are removed through the published service, not through the
            # model.** AD-2's `models-personalization` contract says only
            # `apps.personalization` may import `apps.personalization.models`, and this
            # command lives in `config` — so a direct `SavedEvent.objects...delete()`
            # would break that contract. Going through `unsave_event` is also *more*
            # correct, not merely allowed: the service closes the conflict pairs the save
            # took part in and removes the reminder plans and their pending sends with
            # it. A row deleted behind the service's back would leave a held send
            # pointing at an event that is gone.
            if reset_saves:
                cleared = self._clear_saved_events(user_id=user_id, now=now)
                lines.append(f"  {spec['key']}: cleared {cleared} saved event(s)")

            verb = "created" if account.created else "already had"
            lines.append(
                f"{spec['key']}: {account.email} ({verb}; {spec.get('plan', 'free')}; "
                f"onboarding {state})"
            )
        return lines

    def _clear_saved_events(self, *, user_id, now: datetime) -> int:
        """Remove every saved event this account has, and say how many.

        **Through the service, because the service is the rule.** `unsave_event` closes
        the conflict pairs the save took part in and removes the reminder plans and their
        pending sends with it. A row deleted behind the service's back would leave a held
        send addressed to an event that is gone, and the delivery report would then trip
        on a send nothing can release.

        **The saves are listed through the service too**, for the same reason: the list is
        the account's own, and it is the list the surface reads.
        """
        saved = list_saved_events(user_id=user_id)
        for snapshot in saved:
            unsave_event(
                user_id=user_id,
                event_id=snapshot.event_id,
                actor=SEED_ACTOR,
                now=now,
            )
        return len(saved)

    def _reset_auth_throttle(self, data: dict) -> None:
        """Give the sign-in allowance back, so a seeded run can sign in.

        **The sign-in limits are ten an hour per IP and five an hour per account, and the
        end-to-end suite signs in six times — from one IP, because the whole suite runs
        against one stack on one machine.** So the suite spends the very allowance a
        reader would spend, and a second run inside the hour finds the window already up:
        the sign-in is refused with a 429 and the test fails for a reason that has nothing
        to do with the code under test.

        **This clears the counters, not the rules.** The limits are still ten and five, and
        a reader who signs in ten times in an hour is still refused the eleventh. What
        changes is that a *seeded* run starts from a full allowance instead of from
        whatever the previous run left behind.

        **The address cleared is the loopback the suite signs in from.** The API records
        the caller's `REMOTE_ADDR`, and the frontend proxies to the API over loopback, so
        the address the counter is keyed on is `127.0.0.1` — the same one the
        `throttle:auth:sign_in:ip:127.0.0.1` key names. It is read from the environment
        rather than hard-coded, so a stack reached on another address clears that one.
        """
        reset_sign_in_throttle(
            ip_address=os.environ.get("E2E_CLIENT_IP", SEED_CLIENT_IP),
            emails=[spec["email"] for spec in data["users"]],
        )

    def _complete_onboarding(self, *, user_id, actor: Actor, now: datetime) -> str:
        """Finish the onboarding flow, so `/browse` is not a redirect to `/onboarding`.

        **The flow is advanced, not bypassed.** `/browse` redirects to `/onboarding`
        unless `OnboardingProgress.completed_at` is set, and that row is the command
        layer's to write — a direct write would skip the audit trail and the step
        machine. So the command calls the same `advance_step` the API does, three times.

        The steps are `calendar`, `interests`, `digest`. Advancing past the third one
        completes the flow, and the interests and the digest preference have already been
        written by the two services above — so the walk-through gets a user who is
        *through* onboarding with the interests it wanted, not a user who skipped it.

        **A completed flow is not an error here.** The onboarding is terminal, so the
        second run of the seed advances nothing and says "complete" — which is the state
        it wanted, not a failure to report.
        """
        for _ in range(3):
            try:
                state = advance_step(user_id=user_id, actor=actor, now=now)
            except OnboardingAlreadyCompleteError:
                return "complete"
        return "complete" if state.completed else f"step {state.current_step}"

    # --- listing --------------------------------------------------------------------------------

    def _list(self, data: dict) -> None:
        """What the file says, without touching the database."""
        city = data["city"]
        self.stdout.write(f"City: {city['name']} ({city['tz']}, {city['country_code']})")
        self.stdout.write(f"Venues: {len(data['venues'])}")
        self.stdout.write(f"Events: {len(data['events'])}")
        chips: dict[str, int] = {}
        for spec in data["events"]:
            key = spec.get("chip") or "(none)"
            chips[key] = chips.get(key, 0) + 1
        for chip, count in sorted(chips.items()):
            self.stdout.write(f"  {chip}: {count}")
        self.stdout.write("Accounts:")
        for spec in data["users"]:
            self.stdout.write(
                f"  {spec['key']}: {spec['email']} ({spec.get('plan', 'free')}) — "
                f"{', '.join(spec.get('chips', [])) or 'no interests'}"
            )
        self.stdout.write(f"Reviewer: {data['reviewer']['email']}")
