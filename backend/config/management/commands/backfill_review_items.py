"""Raise a review item for every event already stranded in `in_review` (FR-57).

**Why a command and not a data migration.** `review-queue-model` D9 set the precedent inside
this intent: the idempotent command was chosen over the data migration its own AC asked for.
A command is re-runnable, reports what it did, is testable without a migration harness, and
keeps a service call — with the audit row it writes — out of the migration graph.

**Idempotent.** A second run raises nothing: the query skips events that already have an open
item, and `raise_review_item` independently refuses to stack a second one.

The command holds no model query of its own: `apps.ingestion.models` is importable only from
`apps.ingestion` (AD-2), so the query lives in the service and the command calls it.
"""

from django.core.management.base import BaseCommand

from apps.ingestion.services.review_intake import (
    backfill_in_review_items,
    count_unticketed_in_review,
)


class Command(BaseCommand):
    help = "Raise an in_review ReviewItem for every quarantined event that lacks one."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size", type=int, default=200, help="Events per transaction (default 200)."
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Report how many would be raised, write nothing."
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            pending = count_unticketed_in_review()
            self.stdout.write(f"{pending} in_review event(s) have no open review item.")
            return

        raised = backfill_in_review_items(batch_size=options["batch_size"])
        if raised:
            self.stdout.write(self.style.SUCCESS(f"Raised {raised} review item(s)."))
        else:
            self.stdout.write("Nothing to raise: every in_review event already has an item.")
