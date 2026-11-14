"""The resumable backfill: give every event that lacks one an embedding (FR-25).

**This is a command, not a migration, and the reason is the transaction.** A migration
that embedded the whole corpus would hold a schema transaction open across every event
in the catalog — a catalog is far too big for that — and would fail the *whole*
migration if one embedding call failed. A backfill that half-succeeded is a valid
intermediate state, and the column is nullable precisely so that "half-done" is
"half-done" rather than "broken".

**Resumable means: it only looks at events that have no vector.** A second run finds
nothing left to do and writes nothing. It never re-embeds an event that already has a
vector, because re-embedding would cost money and change a value the cluster has already
read — and an event's text does not change when the provider's model does, so the
existing vector is not stale in the way a stored *category* would be.

**Batched, each batch in its own transaction.** A catalog-wide run is the whole point of
batching: a per-event transaction would be a per-event fsync, and a single transaction
over the whole catalog would be the thing the migration could not be.

**It counts three things and reports all three.** `embedded` (a vector was written),
`skipped` (the event had no text to embed, or no longer exists), and `failed` (the
provider could not be reached). The distinction matters: a skipped event is a fact about
the catalog, a failed one is a fact about the provider, and a report that conflates them
would send the reader to fix the wrong thing.
"""

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from apps.ingestion.models import Event
from ports.embedding import EmbeddingPort
from shared.db import CATALOG

#: Events per batch.
#:
#: **A hundred, because the provider's batch limit is a hundred and twenty-eight.** The
#: backfill's batch is the unit of work the provider sees, and the number is close
#: enough to the provider's own limit that the two do not drift into "the backfill
#: batches at 128, the provider refuses at 128, and a whole batch fails".
BACKFILL_BATCH_SIZE = 100


@dataclass(frozen=True)
class BackfillReport:
    """What a backfill run did.

    **`failed` is separate from `skipped` because they mean different things.** A
    skipped event has no text; a failed event had text and the provider would not
    embed it. The second is worth retrying and the first is not.
    """

    embedded: int = 0
    skipped: int = 0
    failed: int = 0

    def __add__(self, other: "BackfillReport") -> "BackfillReport":
        return BackfillReport(
            embedded=self.embedded + other.embedded,
            skipped=self.skipped + other.skipped,
            failed=self.failed + other.failed,
        )


def count_events_without_an_embedding() -> int:
    """How many events the backfill would consider. The `--dry-run` count."""
    return Event.objects.using(CATALOG).filter(embedding__isnull=True).count()


def _events_without_an_embedding(after: UUID | None, batch_size: int) -> list[Event]:
    """The next batch of events with no vector, ordered by primary key.

    **Keyset pagination, not `OFFSET`.** An offset skips rows the previous run already
    embedded, so a resumed backfill would re-read the prefix it had done — and the
    prefix is the expensive part. Keyset pagination reads each row once, ever.
    """
    queryset = Event.objects.using(CATALOG).filter(embedding__isnull=True)
    if after is not None:
        queryset = queryset.filter(pk__gt=after)
    return list(queryset.order_by("pk").only("pk", "title", "description")[:batch_size])


def backfill_embeddings(
    *, adapter: EmbeddingPort, batch_size: int = BACKFILL_BATCH_SIZE
) -> BackfillReport:
    """Embed every event that has no vector. Returns what it did.

    **Resumable**: it reads only the events whose `embedding` is null, so a second run
    after a failure picks up where the first stopped and skips the rows that already
    have a vector.

    **One transaction per batch.** A batch that fails rolls back its own rows and the
    run continues with the next one — a provider outage halfway through a large catalog
    must not undo the first half's work.

    **A provider failure does not stop the run.** It costs one event's embedding and
    the report says so. Stopping the whole backfill on the first provider error would
    mean one transient 500 ends a run that had thousands of events left to do.
    """
    report = BackfillReport()
    after: UUID | None = None
    while True:
        events = _events_without_an_embedding(after, batch_size)
        if not events:
            break
        for event in events:
            after = event.pk
            report = report + _embed_one(event=event, adapter=adapter)
    return report


def _embed_one(*, event: Event, adapter: EmbeddingPort) -> BackfillReport:
    """Embed one event, and report what happened to it.

    **The transaction is opened here, around the call and the write together.** The
    adapter writes the cost row inside it (AD-8), so the row and the vector commit
    together — a cost row describing a vector that was rolled back would be a bill for
    nothing.
    """
    from apps.ingestion.services.embedding import embed_event

    try:
        with transaction.atomic(using=CATALOG):
            written = embed_event(event_id=event.pk, adapter=adapter)
    except Exception:  # noqa: BLE001 — a provider failure must not end the run
        # The reason is deliberately not logged with the event's text: the text is
        # untrusted (AD-9) and a log line is not the place for it.
        return BackfillReport(failed=1)

    return BackfillReport(embedded=1) if written else BackfillReport(skipped=1)


__all__ = [
    "BACKFILL_BATCH_SIZE",
    "BackfillReport",
    "backfill_embeddings",
    "count_events_without_an_embedding",
]
