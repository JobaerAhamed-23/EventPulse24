"""Give every account without a home city the fallback city (FR-19, FR-5).

**Idempotent.** Running it twice writes the same value twice, not two rows: the write is
an upsert on the one row per user, and it **never overwrites a city that is already
set** — a user who chose their city keeps it, and a second run changes nothing.

**It writes the fallback, because it has no better information.** There is no geo header
in a management command, and the accounts it fills were created before the city existed.
The source is recorded as `backfill`, so the digest can tell a backfilled city from one
the user chose.

**It holds no model query of its own.** `apps.personalization.models` is importable only
from `apps.personalization` (AD-2), so the query lives in the service and the command
calls it. The command is the *schedule*; the service is the *rule*.
"""

from datetime import UTC, datetime

from django.core.management.base import BaseCommand

from apps.personalization.services.digest_preferences import (
    backfill_home_cities,
    count_users_without_a_city,
)
from shared.actor import Actor


class Command(BaseCommand):
    help = "Give every account without a home city the fallback city. Safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many accounts would be filled, and write nothing.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        now = datetime.now(UTC)
        actor = Actor.system("digest_city_backfill")

        if dry_run:
            count = count_users_without_a_city()
            self.stdout.write(f"Would fill {count} accounts. (--dry-run)")
            return

        written, seen = backfill_home_cities(now=now, actor=actor)
        self.stdout.write(f"Filled {written} accounts across {seen} without a city.")
