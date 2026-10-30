"""Backfill Event Fit for the published events that have none (AD-10, FR-26).

**Idempotent.** Running it twice writes the same rows twice, not twice as many rows: the
write is an upsert on `(event, city)`, so a second run replaces each row's score and
tags with the same values. Running it after a day has passed is also fine — the rows are
recomputed, which is exactly what the staleness refresh does anyway.

**Batched.** The events are read in batches and each batch is written in its own
transaction, so a backfill over a large catalog does not hold one long transaction open
and does not have to be rolled back all at once. The work item asks for the refresh cost
to be bounded; this is the bound.

**Only published events.** An event that is `in_review` is not publicly listed and
cannot appear in the preview, and a superseded event is terminal. Both are skipped —
there is no point writing a fit nobody will ever read.

The command holds no model query of its own: `apps.ingestion.models` is importable only
from `apps.ingestion` (AD-2), so the query lives in the service and the command calls it.
"""

from datetime import UTC, datetime

from django.core.management.base import BaseCommand

from apps.ingestion.event_fit.writes import (
    backfill_event_fits,
    count_published_events_with_a_city,
)
from shared.actor import Actor
from shared.constants import EVENT_FIT_REFRESH_BATCH_SIZE


class Command(BaseCommand):
    help = "Compute and persist Event Fit for the published events. Safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=EVENT_FIT_REFRESH_BATCH_SIZE,
            help=f"Events per transaction (default {EVENT_FIT_REFRESH_BATCH_SIZE}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many events would be fitted, and write nothing.",
        )

    def handle(self, *args, **options):
        batch_size = max(1, options["batch_size"])
        dry_run = options["dry_run"]
        now = datetime.now(UTC)
        actor = Actor.system("event_fit_backfill")

        if dry_run:
            count = count_published_events_with_a_city()
            self.stdout.write(f"Would fit {count} published events. (--dry-run)")
            return

        written, seen = backfill_event_fits(now=now, actor=actor, batch_size=batch_size)
        self.stdout.write(f"Fitted {written} events across {seen} published events.")
        if written != seen:
            self.stdout.write(
                self.style.WARNING(f"{seen - written} events had no venue city and were skipped.")
            )
