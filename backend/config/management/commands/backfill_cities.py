"""Backfill canonical Cities for the venues registered before they existed (FR-27).

**Idempotent.** It reads only the venues whose `city_ref` is null, so a second run finds
nothing to do. A venue with no city text is skipped permanently — there is no city to
resolve, which is an answer rather than a gap.

**Batched**, each batch in its own transaction. The `city_ref` columns are nullable so a
partial run is a valid intermediate state and never needs rolling back as a whole.

**It never writes `Venue.city`.** That string feeds `domain.dedup.venue_fingerprint` and is
the venue's identity; rewriting it would silently re-identify venues and corrupt event
dedup across the catalog. The backfill only adds the relation beside it.

The command holds no model query of its own: `apps.ingestion.models` is importable only from
`apps.ingestion` (AD-2), so the queries live in the service and the command calls it.
"""

from django.core.management.base import BaseCommand

from apps.ingestion.services.cities import backfill_cities, count_venues_without_a_city
from shared.actor import Actor
from shared.constants import EVENT_FIT_REFRESH_BATCH_SIZE


class Command(BaseCommand):
    help = "Resolve a canonical City for every venue that has none. Safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=EVENT_FIT_REFRESH_BATCH_SIZE,
            help=f"Venues per transaction (default {EVENT_FIT_REFRESH_BATCH_SIZE}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many venues would be resolved, and write nothing.",
        )

    def handle(self, *args, **options):
        batch_size = max(1, options["batch_size"])
        if options["dry_run"]:
            self.stdout.write(f"Would resolve {count_venues_without_a_city()} venues. (--dry-run)")
            return

        venues, fits = backfill_cities(actor=Actor.system("city_backfill"), batch_size=batch_size)
        self.stdout.write(f"Resolved {venues} venues; linked {fits} Event Fit rows.")
