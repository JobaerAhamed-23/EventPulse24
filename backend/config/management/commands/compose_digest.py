"""Compose a user's digest on demand, or every due user's (FR-1, FR-19).

**Idempotent.** Running it twice writes one digest, not two: the composition service
returns the existing digest with `created=False` and writes nothing the second time.
That is the same guard the scheduler relies on, and the same unique constraint backs it
— so this command is safe to run repeatedly, and safe to run *alongside* the scheduler.

**It composes *and* mints the Ping.** The digest email **is** the Pulse Ping (FR-10),
so a digest with no send row is a user who gets nothing. The command does what the
worker task does, in the same order: compose, then decide whether to send, then mint.
The decision and the minting live in `delivery`, and the command only passes the
composition's own counts — there is no second definition of "qualifying" here either.

**It used to compose only, and that was correct then.** When there was no send to
mint, "compose, and stop" was the whole job. Now it would leave a user with a
composed digest and no email, and — worse — **no counted suppression either**, so the
day's silence would be invisible to SM-C1. A product that cannot say *why* it stayed
quiet cannot tell its own intelligence apart from a broken pipe.

**The `--all` mode composes only what is *due*.** The command asks the scheduler's own
selection rule — `claim_due_digests` — so "everyone who is due right now" means exactly
what the dispatcher means by it, in the user's own local wall clock. The command does not
have a second, looser idea of "due". Taking the scheduler's claim is also why it must
mint: it is standing in for the dispatcher, and a dispatcher that composed without
minting would leave the same gap.

**It holds no model query of its own.** `apps.personalization.models` is importable only
from `apps.personalization` (AD-2), so the reads live in the services and the command
calls them. The command is the *schedule*; the services are the *rule*.
"""

from datetime import UTC, datetime
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from apps.delivery.services.pulse_ping import mint_ping_send
from apps.personalization.services import digest_scheduling
from apps.personalization.services.digest_composition import compose_digest
from shared.actor import Actor


def _now() -> datetime:
    """The current instant, behind a seam.

    **The seam exists so the clock can be frozen in a test.** The due rule is a
    comparison against the user's own local wall clock, so a test that composes "now"
    has to know what "now" is — and a test that reads the wall clock is a test whose
    answer depends on the hour it ran. This is the same seam `worker.tasks._now` has.
    """
    return datetime.now(UTC)


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

        now = _now()
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
        outcome = self._mint_ping(result, actor=actor, now=now)
        verb = "Composed" if result.created else "Already had"
        self.stdout.write(f"{verb} the digest for {user_id} ({result.local_date}).")
        self.stdout.write(f"  {self._ping_verb(outcome)}")

    def _compose_all(self, *, actor: Actor, now: datetime) -> None:
        """Compose every digest that is due right now.

        **The claim is taken, so a dispatcher running at the same time cannot take the
        same user.** The composition releases the claim when it finishes, and the
        composition itself is idempotent — so a race between this command and the
        scheduler produces one digest, not two. The **Ping is minted the same way**,
        and `mint_digest` is idempotent on its own key — so the race produces one send,
        not two.
        """
        claimed = digest_scheduling.claim_due_digests(now=now)
        composed = 0
        existing = 0
        minted = 0
        suppressed = 0
        for user_id in claimed:
            try:
                result = compose_digest(user_id=user_id, actor=actor, now=now)
                if result.created:
                    composed += 1
                else:
                    existing += 1
                outcome = self._mint_ping(result, actor=actor, now=now)
                if outcome.minted:
                    minted += 1
                elif outcome.suppressed:
                    suppressed += 1
            finally:
                digest_scheduling.release_claim(user_id)

        self.stdout.write(
            f"Composed {composed} digests; {existing} already existed; {len(claimed)} claimed."
        )
        self.stdout.write(f"Minted {minted} Pulse Pings; {suppressed} suppressed.")

    def _mint_ping(self, result, *, actor: Actor, now: datetime):
        """Mint the Pulse Ping for a composed digest, or record why it was suppressed.

        **The decision is `delivery`'s, not this command's.** The command passes the
        composition's own counts and asks; it does not re-derive the rule, and it does
        not write a send row itself.
        """
        return mint_ping_send(
            user_id=result.user_id,
            local_date=result.local_date,
            public_qualifying_count=result.public_qualifying_count,
            personal_qualifying_count=result.personal_qualifying_count,
            has_qualifying_events=result.has_qualifying_events,
            actor=actor,
            now=now,
        )

    def _ping_verb(self, outcome) -> str:
        """What happened to the Ping, in one line.

        **The suppressed case says why**, because "no Ping" and "no Ping because the
        user turned it off" are different facts and only one of them is the product's
        doing.
        """
        if outcome.minted:
            return "Minted the Pulse Ping."
        if outcome.suppressed:
            return f"Suppressed the Pulse Ping ({outcome.reason})."
        return f"No Pulse Ping ({outcome.reason})."
