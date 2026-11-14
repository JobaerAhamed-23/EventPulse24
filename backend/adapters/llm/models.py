"""The AI cost row (AD-8): one row per call, in the `catalog` schema.

**Why this model lives in an adapter.** The coding standard says the gateway writes "a
per-call cost row in the same transaction as the result", and that under
`apps | adapters` the gateway cannot import an app's models. So the table lives here,
with `adapters.llm` registered as a Django app and routed to `catalog`.

**The table is append-only.** A cost row is a fact about a call that already happened;
rewriting one would change what the AI Cost Dashboard reports about a call that cannot
be re-made. So the three layers apply: the guarded QuerySet, the
`forbid_history_mutation` trigger, and the `REVOKE UPDATE, DELETE` on the runtime role.

**`NOT_USER_DATA`, and no user id stored.** The standard is explicit: the row must be
`NOT_USER_DATA` with **no user id stored**. A cost row is about a *call*, not about a
person — the same embedding of the same event costs the same whoever asked for it, and
storing whose traffic it was would turn a billing fact into a profile. The dashboard
answers "what did we spend"; it does not answer "who spent it", and it reads the costs
through a port query rather than by importing this module.

**`kind` is the model's kind, so the table can hold the LLM's rows later.** Today's only
writer is the embedding adapter. The column is not an enum, because the LLM's kinds are
not known yet and a table that has to be migrated to accept its second kind is a table
that will be migrated.

**`cost_micros` is an integer, never a float.** Micro-dollars are the unit the ports
already use (`ports/llm.py`, `ports/embedding.py`), and a float here would make the
dashboard's sum drift.

**`call_count` is how many texts the call covered, not how many calls there were.** An
embedding call takes a batch, so one call may cover forty events; conflating the two
would make a batched call look forty times more expensive than it was.
"""

from django.db import models
from django.utils import timezone

from shared.models import AppendOnlyModel, UUIDv7Model
from shared.retention import RetentionCategory


class AICostRow(AppendOnlyModel, UUIDv7Model):
    """One row per AI call: what it cost, in micro-dollars.

    **Nothing about a person is stored here.** No user id, no prompt, no text. The row
    is a billing fact: which model, how many tokens, how much, and when.
    """

    class Kind(models.TextChoices):
        """The kind of call this row bills."""

        EMBEDDING = "embedding"
        LLM = "llm"

    # The standard requires `NOT_USER_DATA` with no user id stored: a cost row is about
    # the call, not about the person who caused it.
    retention_category = RetentionCategory.NOT_USER_DATA
    # Nothing about a cost row becomes known after it is written.
    append_only_mutable = frozenset()

    # What kind of call this was. The values are stable slugs; a row written with a raw
    # kind the dashboard does not know is filtered by the dashboard's own query rather
    # than refused here — a cost row is a record of what happened, and what happened
    # cannot be un-happened by a later vocabulary change.
    kind = models.CharField(max_length=16, choices=Kind.choices)
    # The model that produced it — `voyage-4-lite` for an embedding.
    model = models.CharField(max_length=64)
    input_tokens = models.PositiveIntegerField(default=0)
    # 0 for an embedding: an embedding has no output tokens.
    output_tokens = models.PositiveIntegerField(default=0)
    # Integer micro-dollars, never a float — the unit the ports already use.
    cost_micros = models.PositiveIntegerField(default=0)
    # How many texts the call covered.
    call_count = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        # The append-only guards must also apply to related-object paths.
        base_manager_name = "objects"
        indexes = [
            # "What did we spend on embeddings, and when?" — the question the AI Cost
            # Dashboard asks. It aggregates over time and over kind, so the index leads
            # with the kind.
            models.Index(fields=["kind", "-created_at"], name="ai_cost_row_kind_time_idx"),
        ]

    def __str__(self) -> str:
        # The kind, the model and the cost. No user text of any kind (AD-9, AD-13).
        return f"{self.kind} {self.model} {self.cost_micros}us"


__all__ = ["AICostRow"]
