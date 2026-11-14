"""The embed command: read an event's text, embed it, store the vector (FR-25, D13/D14).

**What is embedded is the event's public text and nothing else.** The title and the
description — the same two fields `chip_keys_for` reads, because they are the same
"what is this event" reading. The venue is *where* it happens and is not embedded; the
source is *who said so* and is not embedded. Embedding those would make the vector a
statement about provenance rather than about the event, and the cluster would then find
"events from the same venue" rather than "events the user keeps swiping past".

**The text is untrusted (AD-9).** It came from a scraped page. It is sent to an
embedding provider as *data* and is never rendered raw by this module. The only path
back to a user is the chip key, and the chip key comes from the server's own vocabulary
(`shared.constants.INTEREST_CHIPS`), never from the event's text — so a scraped title
cannot become a string the user is shown.

**The vector is a derived reading, not a fact.** The column is deliberately *not* in
`Event.LIFECYCLE_FIELDS`: recomputing an embedding does not change the event's identity
or its schedule, so it does not bump `event_version` and does not supersede the row. An
embedding can be rewritten any number of times for the same event.

**The cost row is the adapter's (AD-8).** This module calls the embedding port; the
adapter writes the cost row inside the transaction this module opens. The rule is
"the calling command opens `atomic(using=CATALOG)`, and the gateway writes the row
inside it" — so **this module opens the transaction and the adapter does not.** If this
module failed to open one, `write_cost_row` would raise rather than let the row commit
on its own, which is the failure the rule exists to prevent: a cost row describing a
result that later rolled back.
"""

from uuid import UUID

from django.db import transaction

from apps.ingestion.models import Event
from ports.embedding import EmbeddingPort
from shared.constants import FR25_EMBEDDING_DIMENSIONS
from shared.db import CATALOG

#: The longest description that goes into an embedding.
#:
#: **A bound, because the embedding call is billed per token.** An unbounded description
#: is a bill nobody chose, and the description field is a `TextField` — a source can
#: publish a megabyte of text under a 500-character title. The title is always included;
#: the description is truncated, because the title carries the event's identity and the
#: description carries the detail, and the detail is what the tail of a long description
#: is least about.
MAX_DESCRIPTION_CHARS = 2000


def event_embedding_text(*, title: str, description: str = "") -> str:
    """The text that represents an event to the embedding provider.

    **Title first, then description.** The order is the order of the event's own
    salience: a reader meets the title, then the detail. It is also the order the
    provider sees, and a provider's embedding of the earlier text tends to dominate — so
    putting the title first makes the vector "about the title", which is what a
    cluster of "similar events" should mean.

    **The title is not truncated.** It is a `CharField(max_length=500)`, so it is already
    bounded by the schema. The description is a `TextField`, so it is bounded here.
    """
    parts = [title.strip()]
    if description.strip():
        parts.append(description.strip()[:MAX_DESCRIPTION_CHARS])
    return "\n\n".join(parts)


def embed_event(*, event_id: UUID, adapter: EmbeddingPort) -> bool:
    """Embed one event and store its vector. Returns whether a vector was written.

    **A missing event, or an event with no text, writes nothing and says so.**
    Returning `False` is the honest answer for both: there was nothing to embed. A
    backfill counts these as "skipped", not as "failed", because an event with an empty
    title and an empty description is a fact about the catalog, not a fault in the
    command.

    **The vector is stored on the row it belongs to.** The update is a `UPDATE` on the
    event's own primary key — one statement, no load-then-save — so a concurrent writer
    of some other field on the same row is not clobbered. The event's `updated_at` moves
    with it, which is correct: the row did change.
    """
    event = (
        Event.objects.using(CATALOG).filter(pk=event_id).only("pk", "title", "description").first()
    )
    if event is None:
        return False

    text = event_embedding_text(title=event.title, description=event.description)
    if not text.strip():
        return False

    # The transaction is opened *here*, by the calling command, and the cost row is
    # written inside it by the adapter (AD-8).
    with transaction.atomic(using=CATALOG):
        result = adapter.embed([text], dimensions=FR25_EMBEDDING_DIMENSIONS)
        if not result.vectors:
            return False
        vector = result.vectors[0]
        updated = Event.objects.using(CATALOG).filter(pk=event_id).update(embedding=vector)
    return bool(updated)


__all__ = ["MAX_DESCRIPTION_CHARS", "embed_event", "event_embedding_text"]
