"""The published read port for the event embeddings (FR-25, Finding 4).

**This is the wall.** `personalization` may not import `apps.ingestion.models` — the
`models-ingestion` import contract says only `apps.ingestion` may import that module.
So the clustering rule cannot read `Event.embedding` itself. It asks here, and gets
plain tuples back: the same shape `catalog_read` already hands over for a candidate's
facts. A vector crosses the wall as *numbers*, never as a model instance and never as a
relation.

**Only events that have one.** An event with no embedding is simply absent from the
answer: the backfill has not reached it, or its text was empty. Either way it cannot be
clustered on, and **a missing vector is not a zero vector.** A zero vector is a real
point that happens to sit at the origin — the cosine against anything is 0.0, which is
below the threshold, so a zero vector would behave like a "not similar" event and would
silently count toward "how many of the last three are similar". Absent is the honest
answer, and absence is not a number the cluster can miscount.

**One query, bounded.** The clustering reads at most the user's last three dismissals'
events, so this is `WHERE id IN (...)` over three ids — not a scan, and not a query per
event.

**The dimension is checked here, not trusted.** A vector of the wrong width is not a
vector the cosine rule can use: the dot product of two vectors of different lengths is
not defined, and a rule that divided by a length anyway would produce a number that
looked like a cosine and was not one. A vector of the wrong width is dropped, and the
event is absent — the same honest answer as "no vector at all".
"""

from collections.abc import Sequence
from uuid import UUID

from apps.ingestion.models import Event
from shared.constants import FR25_EMBEDDING_DIMENSIONS
from shared.db import CATALOG


def _usable_vector(embedding: object) -> tuple[float, ...] | None:
    """The vector, if it is one the cluster rule can use. `None` otherwise.

    **Two things disqualify a vector.** `None` — the event has not been embedded — and a
    width that is not the dimension the rule compares in. The second cannot happen
    through the ORM: `pgvector` refuses the write, at the column type, so a
    wrong-width vector cannot be stored at all. The check is here anyway, because the
    cost of a wrong-width vector reaching the cosine is a number that looks like a
    cosine and is not one — and because the defence should not depend on a database
    type's behaviour staying exactly as it is.
    """
    if embedding is None:
        return None
    vector = tuple(float(value) for value in embedding)
    if len(vector) != FR25_EMBEDDING_DIMENSIONS:
        return None
    return vector


def read_event_embeddings(*, event_ids: Sequence[UUID]) -> dict[UUID, tuple[float, ...]]:
    """The stored embeddings for these events, by value.

    Returns a mapping from event id to its vector. **An event with no vector, or with a
    vector of the wrong dimension, is absent from the mapping** — and the caller must
    treat an absent id as "not clusterable", not as "a vector of zeros".

    The vectors are returned as plain tuples of floats: they cross the wall as numbers,
    so nothing on the other side holds a model instance or a database connection.
    """
    if not event_ids:
        return {}

    rows = (
        Event.objects.using(CATALOG).filter(pk__in=list(event_ids)).values_list("pk", "embedding")
    )

    found: dict[UUID, tuple[float, ...]] = {}
    for pk, embedding in rows:
        vector = _usable_vector(embedding)
        if vector is None:
            continue
        found[pk] = vector
    return found


__all__ = ["read_event_embeddings"]
