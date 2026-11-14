"""The AI cost row writer (AD-8): one row per call, in the call's own transaction.

**This is the writer the coding standard asks for.** It says the gateway writes "a
per-call cost row in the same transaction as the result", and that under `apps |
adapters` the gateway cannot import an app's models — so the model lives in
`adapters/llm/models.py`, and this is the one place that knows its shape.

**The writer is the adapter, and that is AD-5's one named exception.** The standard says
so explicitly: "an adapter writing rows is AD-5's one named exception, by AD-8's explicit
rule". The alternative — returning the cost to the caller and letting the caller write
the row — would put the write in two places, and a caller that forgot would produce a
call with no cost row and no way to notice.

**The same transaction as the result.** `write_cost_row` does not open a transaction of
its own; it requires one to be open, the same way `write_audit` does. A cost row
committed apart from the result it bills is a row describing a call that may never have
happened — and a cost row that rolled back with its result is a call that happened for
free.

**The guard is a check, not a wrapper.** `write_cost_row` refuses to run outside an
atomic block rather than opening one, because opening one here would commit the cost row
separately from the result — exactly the failure the standard forbids.

**The row is in `catalog`, not `personal`.** A cost row carries no user id: it is a fact
about a call, not about a person. So the transaction it is written in is the `catalog`
one, and the model is routed there (E001).
"""

from django.db import connections

from adapters.llm.models import AICostRow
from shared.db import CATALOG


class CostRowOutsideCatalogTransaction(RuntimeError):
    """`write_cost_row` was called with no `transaction.atomic(using=CATALOG)` block open.

    A programming error, never mapped to HTTP: a cost row committed apart from the result
    it bills would record a call that may never have happened.
    """


def write_cost_row(
    *,
    kind: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_micros: int,
    call_count: int,
) -> AICostRow:
    """Append one cost row. Call it from inside the call's catalog transaction.

    **`call_count` is how many texts the call covered, not how many calls there were.**
    An embedding call takes a batch of texts, so one call may cover forty events; the
    dashboard needs both numbers, and conflating them would make a batched call look
    forty times more expensive than it was.
    """
    if not connections[CATALOG].in_atomic_block:
        raise CostRowOutsideCatalogTransaction(
            "write_cost_row must run inside transaction.atomic(using=CATALOG)."
        )
    return AICostRow.objects.using(CATALOG).create(
        kind=kind,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_micros=cost_micros,
        call_count=call_count,
    )


__all__ = ["CostRowOutsideCatalogTransaction", "write_cost_row"]
