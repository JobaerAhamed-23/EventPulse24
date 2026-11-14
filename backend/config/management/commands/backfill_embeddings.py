"""Embed every event that has no vector yet (FR-25). Safe to run repeatedly.

**Idempotent.** It reads only the events whose `embedding` is null, so a second run finds
nothing to do and writes nothing. It never re-embeds an event that already has a vector:
that would cost money and change a value the dismissal cluster has already read.

**It holds no model query of its own.** `apps.ingestion.models` is importable only from
`apps.ingestion` (AD-2), so the query lives in the service and the command calls it. The
command is the *schedule*; the service is the *rule*.
"""

from django.core.management.base import BaseCommand

from apps.ingestion.services.embedding_backfill import (
    BACKFILL_BATCH_SIZE,
    backfill_embeddings,
    count_events_without_an_embedding,
)
from ports.registry import get_embedding_port


class Command(BaseCommand):
    help = "Embed every event that has no vector yet. Safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=BACKFILL_BATCH_SIZE,
            help=f"Events per transaction (default {BACKFILL_BATCH_SIZE}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many events would be embedded, and write nothing.",
        )

    def handle(self, *args, **options):
        batch_size = max(1, options["batch_size"])
        if options["dry_run"]:
            pending = count_events_without_an_embedding()
            self.stdout.write(f"Would embed {pending} events. (--dry-run)")
            return

        report = backfill_embeddings(adapter=get_embedding_port(), batch_size=batch_size)
        self.stdout.write(
            f"Embedded {report.embedded} events; skipped {report.skipped}; failed {report.failed}."
        )
