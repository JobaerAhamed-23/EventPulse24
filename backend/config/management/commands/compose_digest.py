"""Compose a user's digest on demand, or every due user's (FR-1, FR-19).

**Idempotent.** Running it twice writes one digest, not two: the composition service
returns the existing digest with `created=False` and writes nothing the second time.
That is the same guard the scheduler relies on, and the same unique constraint backs it
— so this command is safe to run repeatedly, and safe to run *alongside* the scheduler.

**It composes; it does not send.** A digest is composed so that it exists when the user
arrives. The **send** is the delivery intent's job, and this command has no opinion
about it (D2).

**The `--all` mode composes only what is *due*.** The command asks the scheduler's own
selection rule — `claim_due_digests` — so "everyone who is due right now" means exactly
what the dispatcher means by it, in the user's own local wall clock. The command does not
have a second, looser idea of "due".

**It holds no model query of its own.** `apps.personalization.models` is importable only
from `apps.personalization` (AD-2), so the reads live in the services and the command
calls them. The command is the *schedule*; the services are the *rule*.
"""

from datetime import UTC, datetime
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from apps.personalization.services import digest_scheduling
from apps.personalization.services.digest_composition import compose_digest
from shared.actor import Actor


class Command(BaseCommand):
    help = "Compose a user's digest now, or every due user's. Safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user-id",
            type=str,
            required=False,
            help="The user's id (a UUID). Composes that one user's digest.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Compose every user's digest whose delivery time has arrived.",
        )

    def handle(self, *args, **options):
        user = options.get("user_id")
        compose_all = options.get("all")

        if bool(user) == bool(compose_all):
            raise CommandError("Give exactly one of --user-id or --all.")

        now = datetime.now(UTC)
        actor = Actor.system("digest_command")

        if user:
            self._compose_one(user_id=self._parse(user), actor=actor, now=now)
            return

        self._compose_all(actor=actor, now=now)

    def _parse(self, raw: str) -> UUID:
        try:
            return UUID(raw)
        except ValueError:
            raise CommandError(f"--user-id must be a UUID, not {raw!r}.") from None

    def _compose_one(self, *, user_id: UUID, actor: Actor, now: datetime) -> None:
        """Compose one user's digest, whether or not it is due.

        A single user asked for by name is composed on demand — the point of the command
        is to answer *this* user's request, not to test the schedule.
        """
        result = compose_digest(user_id=user_id, actor=actor, now=now)
        verb = "Composed" if result.created else "Already had"
        self.stdout.write(f"{verb} the digest for {user_id} ({result.local_date}).")

    def _compose_all(self, *, actor: Actor, now: datetime) -> None:
        """Compose every digest that is due right now.

        **The claim is taken, so a dispatcher running at the same time cannot take the
        same user.** The composition releases the claim when it finishes, and the
        composition itself is idempotent — so a race between this command and the
        scheduler produces one digest, not two.
        """
        claimed = digest_scheduling.claim_due_digests(now=now)
        composed = 0
        existing = 0
        for user_id in claimed:
            try:
                result = compose_digest(user_id=user_id, actor=actor, now=now)
                if result.created:
                    composed += 1
                else:
                    existing += 1
            finally:
                digest_scheduling.release_claim(user_id)

        self.stdout.write(
            f"Composed {composed} digests; {existing} already existed; {len(claimed)} claimed."
        )
