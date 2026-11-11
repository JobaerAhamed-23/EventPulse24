"""Keeping the review queue in step with what is actually in review (design: review-intake).

**One invariant, stated once and enforced everywhere ingestion writes an Event:**

> An Event with `publication_status = in_review` has exactly one open `in_review`
> `ReviewItem`. An Event that is not in review has none.

Before this module, `domain/confidence.py` sent a low-confidence Event to `Gate.IN_REVIEW`
and `ingest_item` stored it as `in_review` — and then nothing happened to it, ever. The
docstring promised "stored, never in a digest until editorial review" and no editorial review
existed, so the Event was silently lost. `sync_review_item` is what makes that promise true.

---

## Why this keys off the publication status and not the gate

`sync_review_item` looks at the Event's **resulting** `publication_status`, never at which
gate produced it. That is deliberate and it is the whole reason this module is three
functions rather than a hook per gate:

- Today `Gate.IN_REVIEW` comes from `tz_inference_confidence < 0.70`.
- When FR-14's LLM path ships, it will also come from `extraction_confidence < 0.70`.

**The second needs no change here.** Whatever decides an Event belongs in review, the Event
lands in `in_review`, and the next line of `ingest_item` raises its ticket. A gate-shaped
hook would have had to learn each new gate; a status-shaped one cannot fall behind.

---

## Leaving review

An Event leaves `in_review` by three routes, and only one of them is an editorial verdict:

| Route | Resolution | Who |
| --- | --- | --- |
| A later poll re-gates it to `published` (better confidence) | `withdrawn` | system |
| `supersede_event` replaces it; the old Event is terminal (AD-4) | `withdrawn` | system |
| An editor approves, edits or rejects it | the verdict | **`editorial-review-commands`** |

**`withdrawn` is not a verdict and must not be able to look like one.** `ReviewItem`'s D6
check requires a system resolver for `withdrawn` and a *user* resolver for every other
resolution, so the database itself refuses a job recording an editorial decision. That is why
this module's writes are attributed to `Actor.system(...)` and why rejection is deliberately
**not** routed through `sync_review_item`: a reject is an editor's judgement and is recorded
by the command that makes it, not laundered into a system withdrawal here.

**The editorial routes are `editorial_review`'s, and that split held.**
`editorial_state.reject_event` still records no verdict — called on its own it hides the
Event and cancels reminders and leaves the queue alone. `editorial_review.reject_review_item`
is the caller that records the judgement with the editor's name on it. Two tests in
`tests/ingestion/test_review_intake.py` pin both halves, so the boundary stays a design
rather than a coincidence.
"""

from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.ingestion.models import Event, ReviewItem
from apps.ingestion.services.audit import write_audit
from apps.ingestion.services.review_queue import raise_review_item
from shared.actor import Actor, ActorKind
from shared.db import CATALOG

#: The actor every write in this module is attributed to. A system actor, because a
#: withdrawal is the queue noticing the world moved — never an editorial decision.
SYSTEM_ACTOR = Actor.system("review_intake")


def sync_review_item(*, event: Event, actor: Actor | None = None, now: datetime | None = None):
    """Make the queue agree with this Event's publication status. Idempotent.

    Called by `ingest_item` immediately after each Event write, inside the same
    `atomic(using=CATALOG)` — beside `_write_fit`, for the same reason it is there: an item
    that committed apart from the Event that caused it could describe a state that never
    existed.

    Returns the open `ReviewItem` when the Event is in review, otherwise `None`.
    """
    moment = now or timezone.now()
    if event.publication_status == Event.PublicationStatus.IN_REVIEW:
        return raise_review_item(
            event=event,
            reason=ReviewItem.Reason.IN_REVIEW,
            actor=actor or SYSTEM_ACTOR,
            now=moment,
        ).item
    withdraw_review_item(event=event, now=moment)
    return None


def withdraw_review_item(
    *,
    event: Event,
    reason: ReviewItem.Reason | str = ReviewItem.Reason.IN_REVIEW,
    now: datetime | None = None,
) -> int:
    """Close this Event's open item for `reason` as `withdrawn`. Returns how many closed.

    **A system close, for a target that left review by a route no editor took.** The
    resolution exists for exactly this (`review-queue-model` D5), which is why no migration
    is needed here.

    **The write is a filtered UPDATE on `status='open'`, not a read-then-save.** Two
    concurrent withdrawals would otherwise both read an open row and both try to close it,
    and the second would hit the `guard_review_item` trigger's "a resolved ReviewItem is
    immutable". Filtering on the status makes the loser a no-op that returns 0.
    """
    reason = ReviewItem.Reason(reason)
    moment = now or timezone.now()

    with transaction.atomic(using=CATALOG):
        open_items = ReviewItem.objects.using(CATALOG).filter(
            event_id=event.pk, reason=reason, status=ReviewItem.Status.OPEN
        )
        # Read the ids before the update: afterwards the filter matches nothing, and the
        # audit row names the item it closed rather than merely a count.
        item_ids = list(open_items.values_list("id", flat=True))
        if not item_ids:
            return 0

        closed = (
            ReviewItem.objects.using(CATALOG)
            .filter(id__in=item_ids, status=ReviewItem.Status.OPEN)
            .update(
                status=ReviewItem.Status.RESOLVED,
                resolution=ReviewItem.Resolution.WITHDRAWN,
                resolved_at=moment,
                resolved_by_kind=ActorKind.SYSTEM,
                resolved_by_id=None,
                resolved_by_label=SYSTEM_ACTOR.label,
                updated_at=moment,
            )
        )
        for item_id in item_ids[:closed]:
            write_audit(
                actor=SYSTEM_ACTOR,
                action="review_item_withdrawn",
                target_type="review_item",
                target_id=item_id,
                details={"reason": reason.value, "event_id": str(event.pk)},
            )
        return closed


def count_unticketed_in_review() -> int:
    """How many `in_review` Events have no open item. The backfill's dry run reads this."""
    return _unticketed_in_review().count()


def backfill_in_review_items(*, now: datetime | None = None, batch_size: int = 200) -> int:
    """Raise an `in_review` item for every quarantined Event that lacks one. Returns the count.

    **The rescue.** Before this intent, `domain/confidence.py` could send an Event to
    `Gate.IN_REVIEW` and nothing downstream ever looked at it again. Every Event already in
    that state is stranded, and no amount of future ingestion frees it: a re-poll only
    re-gates an Event whose facts changed. This command is the only thing that reaches them.

    **Idempotent, and not by checking first.** The query excludes Events that already have an
    open item, and `raise_review_item` independently refuses to stack a second open item per
    (target, reason). A second run therefore raises nothing even if the two disagree — the
    filter is the optimisation, the one-open-item rule is the guarantee.

    **Batched**, like `backfill_event_fits`: each batch is its own transaction, so a backfill
    over a large catalog never holds one long transaction open.

    The query lives here rather than in the command because `apps.ingestion.models` is
    importable only from `apps.ingestion` (AD-2).
    """
    moment = now or timezone.now()
    raised = 0
    while True:
        batch = list(_unticketed_in_review()[:batch_size])
        if not batch:
            return raised
        with transaction.atomic(using=CATALOG):
            for event in batch:
                raise_review_item(
                    event=event,
                    reason=ReviewItem.Reason.IN_REVIEW,
                    actor=SYSTEM_ACTOR,
                    now=moment,
                )
                raised += 1
        if len(batch) < batch_size:
            return raised


def _unticketed_in_review():
    """The `in_review` Events with no open `in_review` item, oldest first.

    **Superseded Events are excluded.** One is terminal (AD-4) and no editor can act on it,
    so a ticket would be work nobody can do. `sync_review_item` withdraws their items for the
    same reason.
    """
    ticketed = ReviewItem.objects.using(CATALOG).filter(
        reason=ReviewItem.Reason.IN_REVIEW,
        status=ReviewItem.Status.OPEN,
        event_id__isnull=False,
    )
    return (
        Event.objects.using(CATALOG)
        .filter(publication_status=Event.PublicationStatus.IN_REVIEW)
        .exclude(status=Event.Status.SUPERSEDED)
        .exclude(pk__in=ticketed.values("event_id"))
        .order_by("created_at")
    )


__all__ = [
    "SYSTEM_ACTOR",
    "backfill_in_review_items",
    "count_unticketed_in_review",
    "sync_review_item",
    "withdraw_review_item",
]
