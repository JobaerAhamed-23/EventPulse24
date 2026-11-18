"""Register and ingest a real Dhaka event source, alongside the Fixtureville fixture.

**This is the live counterpart to `seed_browse_catalog`.** That command seeds an invented
city from a committed JSON file and makes no network call; this one registers a real
source and fetches it, so Browse can be looked at with events that actually exist.

**Venues are registered before the ingest, and that order is the whole point.** The
pipeline never creates a venue (`ingest_item._venue_for`, design D5): it matches a
candidate against the registry by fingerprint and otherwise resolves no venue at all.
That matters more than it sounds here, because this feed's `startDate` values are
date-only — no clock time and no zone. With no zone from the source and no venue to
borrow one from, `resolve_tz` returns `TZ_UNRESOLVABLE` and the event is dropped. So an
ingest run against an empty registry would import nothing, and the reason would look
like a parser bug rather than a missing row. This command therefore parses the feed
first, registers every venue it names, and only then ingests.

**A venue is registered under the city string the feed writes**, not a tidied one. The
match in `_venue_for` fingerprints `candidate.venue_city`, so a venue stored as "Dhaka"
is invisible to a candidate that says "ঢাকা" — and this feed uses both. Normalising on
the way in would therefore cost events, not clean them up.

**The two spellings are reconciled on the read side instead**, by
`domain.cities.CITY_ALIAS_GROUPS`: a reader whose city is "Dhaka" also matches venues
filed under "ঢাকা". That still leaves two `City` rows — FR-27's accepted cost — but it
stops a reader being shown half of their own city.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import UTC, datetime, time

from django.core.management.base import BaseCommand, CommandError

from apps.identity.services import ensure_account
from apps.ingestion.parsers import SourceContext, parse
from apps.ingestion.services.ingest_source import ingest_source
from apps.ingestion.services.source_registry import find_source_by_url, register_source
from apps.ingestion.services.venue_registry import find_venue, register_venue
from apps.personalization.services.onboarding import (
    advance_step,
    set_digest_preference,
    set_interests,
)
from domain.errors import DomainError, OnboardingAlreadyCompleteError
from ports.fetch import FetchError
from ports.registry import get_fetch_port
from shared.actor import Actor

ACTOR = Actor.system("dhaka_live_seed")

# Eventbrite's Dhaka directory page carries one `ItemList` of schema.org `Event` nodes, which
# is the FR-14 structured path — `jsonld`, not `crawl`, so no ToS review gates it. robots.txt
# leaves `/d/` open to `User-agent: *`. Eventbrite's own Terms separately restrict automated
# access and point at their API, so this is a local-development source, not a production one.
DEFAULT_URL = "https://www.eventbrite.com/d/bangladesh--dhaka/events/"
DEFAULT_CITY = "Dhaka"
DEFAULT_TZ = "Asia/Dhaka"
DEFAULT_COUNTRY = "BD"

# The account the live surface is looked at through. It is deliberately *not* one of the
# `browse.example.test` four: those belong to the Fixtureville walk-through and the
# Playwright specs assert on what they see, so moving one of them to Dhaka would break
# six passing tests to save creating one row.
LIVE_EMAIL = "dhaka@live.example.test"
LIVE_PASSWORD = "browse-dhaka-1234"  # noqa: S105 — a local dev seed account, like the Fixtureville four
LIVE_CHIPS = ["talks_lectures", "classes_workshops", "arts_culture"]  # the cap is three


class Command(BaseCommand):
    help = "Register and ingest a real Dhaka source, so Browse has live events to show."

    def add_arguments(self, parser):
        parser.add_argument("--url", default=DEFAULT_URL, help="The feed or page to ingest.")
        parser.add_argument("--city", default=DEFAULT_CITY, help="The source's city.")
        parser.add_argument("--tz", default=DEFAULT_TZ, help="IANA zone for registered venues.")
        parser.add_argument(
            "--country", default=DEFAULT_COUNTRY, help="Fallback ISO country for venues."
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and parse, report what would be registered, write nothing.",
        )
        # **A real address is passed in, never defaulted to in the file.** The default here
        # is a `.example.test` fixture on purpose: a personal address committed to the repo
        # would be published with it, and this command is pushed to a public remote.
        parser.add_argument(
            "--email", default=LIVE_EMAIL, help="The account to read the surface through."
        )
        parser.add_argument(
            "--password",
            default=LIVE_PASSWORD,
            help="Only ever used when the account is created; an existing one keeps its own.",
        )

    # ── the source ──────────────────────────────────────────────────────────────────
    def _source(self, *, url: str, city: str, dry_run: bool):
        existing = find_source_by_url(url)
        if existing is not None:
            self.stdout.write(f"source: reusing {existing.name} ({existing.id})")
            return existing
        if dry_run:
            self.stdout.write(f"source: would register {url}")
            return None
        source = register_source(
            actor=ACTOR,
            name=f"Eventbrite — {city}",
            source_type="ticketing",
            url=url,
            acquisition_method="jsonld",
            # The feed states no zone anywhere, so the source covers none of them and every
            # event leans on its venue for one. Claiming `partial` here would be a claim the
            # feed does not support.
            tz_coverage="none",
            city=city,
        )
        self.stdout.write(f"source: registered {source.name} ({source.id})")
        return source

    # ── the venues the feed names ───────────────────────────────────────────────────
    def _candidate_venues(self, source) -> OrderedDict:
        """Fetch and parse the feed, and return its distinct venues in feed order."""
        try:
            result = get_fetch_port().fetch(source.url, source_id=source.id)
        except FetchError as exc:
            raise CommandError(f"fetch failed: {exc.code}") from None
        parsed = parse(source.acquisition_method, result.body, SourceContext(source.id, source.url))
        if parsed.error:
            raise CommandError(f"parse failed: {parsed.error}")

        venues: OrderedDict = OrderedDict()
        for candidate in parsed.candidates:
            if not candidate.venue_name:
                continue
            key = (
                candidate.venue_name,
                candidate.venue_city or source.city,
                (candidate.venue_country or DEFAULT_COUNTRY).upper(),
            )
            venues.setdefault(key, 0)
            venues[key] += 1
        self.stdout.write(
            f"feed: {len(parsed.candidates)} candidate(s), "
            f"{len(venues)} distinct venue(s), "
            f"{sum(1 for c in parsed.candidates if not c.venue_name)} with no venue"
        )
        return venues

    def _register_venues(self, venues, *, tz: str, dry_run: bool) -> tuple[int, int]:
        made = found = 0
        for name, city, country in venues:
            if find_venue(name=name, city=city, country_code=country) is not None:
                found += 1
                continue
            if dry_run:
                self.stdout.write(f"  would register venue: {name} — {city} ({country})")
                made += 1
                continue
            try:
                register_venue(actor=ACTOR, name=name, city=city, country_code=country, tz=tz)
            except DomainError as exc:
                self.stderr.write(f"  venue refused ({name}): {exc.code}")
                continue
            self.stdout.write(f"  venue: {name} — {city} ({country}) @ {tz}")
            made += 1
        return made, found

    # ── the account the surface is read through ─────────────────────────────────────
    def _account(self, *, city: str, tz: str, email: str, password: str) -> None:
        """An onboarded account whose home city is the one just ingested.

        **The city is set through `set_digest_preference`, not written directly**, and
        that service checks the city against the catalog's own coverage — "the cities
        with a published event that has an Event Fit". So this runs *after* the ingest,
        and if it silently falls back to another city, that is the catalog saying this
        one is not covered, which is worth seeing rather than hiding.

        **Onboarding is advanced, not bypassed**: `/browse` redirects to `/onboarding`
        until `completed_at` is set, and that row belongs to the step machine.
        """
        now = datetime.now(UTC)
        account = ensure_account(email=email, password=password)
        actor = Actor.user(account.user_id)

        set_interests(user_id=account.user_id, chip_keys=LIVE_CHIPS, actor=actor, now=now)
        preference = set_digest_preference(
            user_id=account.user_id,
            delivery_time=time(9, 0),
            timezone_name=tz,
            actor=actor,
            now=now,
            city=city,
        )
        for _ in range(3):
            try:
                advance_step(user_id=account.user_id, actor=actor, now=now)
            except OnboardingAlreadyCompleteError:
                break

        saved = getattr(preference, "city", city)
        self.stdout.write(
            f"account: {email} ({'new' if account.created else 'already existed'}) — city {saved!r}"
        )
        if not account.created:
            # **The trap this line exists to close.** `ensure_account` sets a password only
            # on creation, deliberately — a re-run must not reset a password somebody
            # changed. So `--password` was ignored here, and an operator who assumes
            # otherwise gets a 401 and no idea why. It also means this run just rewrote a
            # real account's city, interests and delivery time.
            self.stderr.write(
                "  note: existing account — its own password still applies, and this run "
                "overwrote its city, interests and digest delivery time."
            )
        if saved != city:
            self.stderr.write(
                f"  note: asked for {city!r} but the catalog's coverage gave {saved!r}."
            )

    # ── the run ─────────────────────────────────────────────────────────────────────
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        source = self._source(url=options["url"], city=options["city"], dry_run=dry_run)
        if source is None:
            self.stdout.write("dry run: no source to parse against yet.")
            return

        venues = self._candidate_venues(source)
        made, found = self._register_venues(venues, tz=options["tz"], dry_run=dry_run)
        self.stdout.write(f"venues: {made} new, {found} already registered")

        if dry_run:
            self.stdout.write("dry run: nothing ingested.")
            return

        try:
            report = ingest_source(source.id, actor=ACTOR)
        except DomainError as exc:
            raise CommandError(f"{exc.code}: {exc.message}") from None
        counts = ", ".join(f"{key}={n}" for key, n in sorted(report.counts.items())) or "no items"
        error = f" [{report.error_code}]" if report.error_code else ""
        self.stdout.write(f"ingest: {report.outcome}{error}: {counts}")

        self._account(
            city=options["city"],
            tz=options["tz"],
            email=options["email"],
            password=options["password"],
        )
