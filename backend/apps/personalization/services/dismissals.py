"""The dismissal and the cluster (FR-25): "Less like this", from the swipe to the prompt.

**What this module is.** A user swipes a Pulse Card away. That is a dismissal. Three
dismissals of *similar* events, close together in time, are a *cluster* — a signal that
the user does not want more of whatever those events have in common. When a cluster
fires, the product asks once whether to mute that category, and the answer is the mute.

**The rule, in order.**

1. **Resolve the slot.** A card in the serendipity slot is *not* a clustering candidate.
   The product put that card there deliberately, to show the user something they did not
   ask for; a dismissal of it is a dismissal of that one card, not of the category it
   happens to belong to. Serendipity is protected (the mockup's "Slot 3 immunity").
2. **The rage-dismiss guard.** Three dismissals inside five seconds is a flick, not a
   preference. The dismissal is still *recorded* — the user really did dismiss it — but it
   does not advance the cluster counter. Without the guard, the fastest way to get a
   category muted is to be annoyed for four seconds.
3. **The window.** The cluster's dismissals must fall inside one 24-hour span.
4. **The cosine.** The newest dismissal's vector must be at least 0.70 from *each* of the
   previous two. "Each", not "any pair" — the mockup says "cosine ≥0.7 between them", and
   reading it as "any pair" would make the cluster loose: two events close together and
   a third unrelated one would still fire, and the mute would be for a category the third
   event has nothing to do with.
5. **The decay.** A dismissal older than 180 days is expired. One older than 60 days
   counts for half.
6. **The prompt.** If all of that holds, and the cluster has not already fired, the
   prompt is due. It fires **once** per cluster.

**The cosine lives here, not in `domain/`.** `domain/` is stdlib-only and pure, and
`tests/domain/test_domain_api.py` forbids the symbols `embed`, `cosine`, `vector` and
`similar` there — the rule is about a *product decision* (when to ask the user), not
about arithmetic that could be pure. The arithmetic itself is one small function below.

**The vectors cross the wall by value.** `personalization` may not import
`apps.ingestion.models`, so the vectors come from `ingestion`'s published read port as
plain tuples of numbers.

**The prompt's copy is the server's.** The category label comes from
`shared.constants.INTEREST_CHIPS` — the server's own vocabulary — never from the event's
text. A scraped title cannot become a string the user is shown (AD-9).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from django.db import transaction

from apps.ingestion.services.catalog_read import read_chip_keys_for_events
from apps.ingestion.services.event_embeddings import read_event_embeddings
from apps.personalization.models import DigestComposition, EventDismissal
from apps.personalization.services.audit import write_audit
from apps.personalization.services.digest_composition import read_latest_slot
from shared.actor import Actor
from shared.constants import (
    FR25_CLUSTER_COSINE_THRESHOLD,
    FR25_CLUSTER_MIN_EVENTS,
    FR25_CLUSTER_WINDOW_HOURS,
    FR25_DECAY_EXPIRE_DAYS,
    FR25_DECAY_HALF_DAYS,
    FR25_RAGE_GUARD_COUNT,
    FR25_RAGE_GUARD_SECONDS,
    INTEREST_CHIPS,
)
from shared.db import PERSONAL

#: The chip key → label map, from the server's own vocabulary.
#:
#: **The prompt names a chip the user can recognise.** The mockup's "Less rooftop jazz"
#: is not in the chip vocabulary — the vocabulary is ten broad buckets — so the prompt
#: names the chip the cluster actually shares, and the chip's label is the server's own
#: wording. A label built from the event's title would be a scraped string in the user's
#: face (AD-9).
CHIP_LABELS: dict[str, str] = dict(INTEREST_CHIPS)

#: The prompt's copy when the cluster has one dominant chip.
#:
#: **"in your next digest"**, because the mute applies to the digest's candidate pool —
#: the next one the product composes. It is not "forever" and not "from now on": the
#: mute has an expiry, and the copy says where the effect is felt rather than promising
#: a duration the user did not choose.
PROMPT_TITLE_EXPLICIT = "Less {label} in your next digest?"
PROMPT_TITLE_GENERIC = "Less events like these in your next digest?"
PROMPT_DESCRIPTION = (
    "You've swiped past {count} similar events. Want us to deprioritize this category "
    "for a while? You can undo anytime in Settings → Taste."
)

#: The slot whose dismissals are protected from clustering.
#:
#: **The serendipity slot, by its own name.** The mockup calls it "slot 3" because it
#: numbered the slots on a picture; the codebase's vocabulary calls it `serendipity`, and
#: a rule keyed on a number would need a translation table nobody would remember to
#: update.
SERENDIPITY_SLOT = DigestComposition.Slot.SERENDIPITY


@dataclass(frozen=True)
class ClusterPrompt:
    """The prompt the product shows when a cluster fires."""

    #: The title — "Less arts & culture in your next digest?"
    title: str
    #: The description — the mockup's shape, with the real count in it.
    description: str
    #: The chip key the cluster agreed on, when there was one. `None` for the generic
    #: variant.
    category_key: str | None


@dataclass(frozen=True)
class DismissalResult:
    """What one dismissal did.

    **`cluster_advanced` says whether this dismissal counted**, and `prompt_due` says
    whether the product should now ask. Both are separate facts: a dismissal that
    advanced the counter may still not have completed a cluster (there were not three
    yet), and a dismissal that did not advance can never complete one.
    """

    event_id: UUID
    cluster_advanced: bool
    prompt_due: bool
    prompt: ClusterPrompt | None


def cosine(left: tuple[float, ...], right: tuple[float, ...]) -> Decimal:
    """The cosine similarity of two vectors, in `Decimal`.

    **Both vectors must be the same length.** A dot product of two vectors of different
    lengths is not a cosine, and a rule that divided by whatever length it had would
    produce a number that *looks* like a cosine and is not one. A length mismatch raises.

    **A zero vector has no direction**, so its cosine with anything is undefined — and
    the division would be by zero. The read port never returns a zero vector (a missing
    vector is absent, not zero), but a zero can still arrive from a provider, and a rule
    that crashed on one would take the whole dismissal path down.

    **`Decimal`, not `float`.** The threshold is `Decimal("0.70")`, and comparing a float
    against it would make "exactly 0.70" a coin flip.
    """
    if len(left) != len(right):
        raise ValueError("cosine needs two vectors of the same length")

    dot = sum((Decimal(str(a)) * Decimal(str(b))) for a, b in zip(left, right, strict=True))
    left_norm = sum(Decimal(str(a)) ** 2 for a in left) ** Decimal("0.5")
    right_norm = sum(Decimal(str(b)) ** 2 for b in right) ** Decimal("0.5")
    if left_norm == 0 or right_norm == 0:
        raise ValueError("cosine needs two non-zero vectors")

    # Rounded to 6 places: the vectors came from a float provider, so the exact value is
    # already approximate, and a comparison at the tenth decimal place would be a
    # comparison of two roundings.
    return (dot / (left_norm * right_norm)).quantize(Decimal("0.000001"))


def _resolve_slot(*, user_id: UUID, event_id: UUID) -> str | None:
    """Which slot this event was in, in the user's most recent digest. `None` if unknown.

    **The read is the composition service's, not this module's.** The composition rows
    are `digest_composition`'s business — it writes them — and AD-10's architecture test
    names the *only* two read paths that may query a composition, because a third one
    would be a new place an explanation could be served from. This module needs the
    slot, so it asks the module that owns the rows rather than querying them itself.

    **Why the slot is read at all.** The serendipity slot is protected from clustering:
    the product put that card there deliberately, so dismissing it is not a verdict on
    the category. A dismissal of a card the user was *shown* carries that verdict; a
    dismissal of an event opened directly does not, and has no slot to speak of.
    """
    return read_latest_slot(user_id=user_id, event_id=event_id)


def _is_rage_dismissal(*, user_id: UUID, now: datetime) -> bool:
    """Whether this dismissal is the third of a rapid flick.

    **Three dismissals inside five seconds.** The two previous dismissals must both be
    within the rage window of *this* one, and of each other — three dismissals spread
    over four seconds are a flick, but two dismissals a second apart and a third a
    minute later are not.

    **Only the count of *recent* dismissals matters, not their slots.** A rage flick
    across three different slots is still a flick.
    """
    window_start = now - timedelta(seconds=FR25_RAGE_GUARD_SECONDS)
    recent = (
        EventDismissal.objects.using(PERSONAL)
        .filter(user_id=user_id, dismissed_at__gte=window_start, dismissed_at__lte=now)
        .count()
    )
    return recent >= FR25_RAGE_GUARD_COUNT - 1


def _decayed_weight(*, dismissed_at: datetime, now: datetime) -> Decimal:
    """How much this dismissal counts for, after the decay.

    **A half-life, not a cliff.** A dismissal from two months ago is weaker evidence
    than one from yesterday, but it is not nothing — and the user who swipes past the
    same kind of event for two months *before* the cluster fires is precisely the user
    the loop should catch.

    **Expired means zero.** Past 180 days the dismissal is not counted at all: a
    preference the user cannot escape is not a preference the product should speak for.
    """
    age = now - dismissed_at
    if age > timedelta(days=FR25_DECAY_EXPIRE_DAYS):
        return Decimal(0)
    if age > timedelta(days=FR25_DECAY_HALF_DAYS):
        return Decimal("0.5")
    return Decimal(1)


def _cluster_candidates(*, user_id: UUID, now: datetime) -> list[EventDismissal]:
    """The dismissals that could be part of the cluster, newest first.

    **Only advancing dismissals.** A dismissal that the rage guard stopped does not
    count, and neither does a dismissal of a serendipity card — the guard says the user
    did not mean it, and the immunity says the product did not offer it.

    **Only unexpired ones.** A dismissal past the expiry contributes nothing, so it is
    not a candidate.

    **More than three of them, because the decay weights them.** The rule needs three
    *dismissals' worth* of evidence, and an older dismissal is worth half — so the pool
    has to be able to hold more than three rows for the weighted sum to reach three.
    Reading exactly three would make the half-life unreachable: a half-weight dismissal
    inside a three-row pool leaves the sum at 2.5, and the rule could never fire.
    """
    cutoff = now - timedelta(days=FR25_DECAY_EXPIRE_DAYS)
    return list(
        EventDismissal.objects.using(PERSONAL)
        .filter(
            user_id=user_id,
            cluster_advanced=True,
            dismissed_at__gte=cutoff,
            dismissed_at__lte=now,
        )
        .exclude(slot=SERENDIPITY_SLOT)
        .order_by("-dismissed_at")[: FR25_CLUSTER_MIN_EVENTS * 2]
    )


def _cluster_forms(*, candidates: list[EventDismissal], now: datetime) -> bool:
    """Whether these dismissals are one cluster.

    **The window is on the span.** The oldest and the newest must be within
    `FR25_CLUSTER_WINDOW_HOURS` of each other. A dismissal this morning and one this
    evening are adjacent; one this morning and one tomorrow morning are not.

    **The cosine is against *each* of the others.** The newest is compared with every
    other candidate, and every comparison must clear the threshold. "Each", not "any
    pair": a loose cluster would mute a category on the strength of two events and one
    coincidence.

    **The decay weights the count, and that is where it bites.** A dismissal older than
    the half-life counts for **half a dismissal**, not for a whole one — so two fresh
    dismissals and one half-decayed one are 2.5 dismissals, which is not the three the
    rule asks for, and the cluster does not form. A dismissal past the expiry counts for
    nothing at all.

    **Why the count and not the cosine.** The decay is about how much the *evidence* is
    worth, and the evidence is "the user dismissed something like this, and did so
    recently". A cosine between two vectors says how similar the events are; it says
    nothing about how recently the user said so. Adjusting the cosine by the age would
    mean a stale-but-similar pair passes and a fresh-but-dissimilar pair fails — which
    inverts the rule's sense. Weighting the count keeps the cosine honest and lets the
    age speak about the evidence, which is what it is about.

    **So the two rules are not redundant.** The window bounds the *span* — how close in
    time the dismissals are — and the decay bounds the *strength* — how much each one
    counts. A cluster of three inside 24 hours is three dismissals; the same three
    spread over two months is three dismissals that no longer add up to three.
    """
    if len(candidates) < FR25_CLUSTER_MIN_EVENTS:
        return False

    newest = candidates[0]
    others = candidates[1:]

    # **The window, measured on the fresh dismissals only.** A half-weight dismissal
    # may still join the cluster, but it does not stretch the window: the window is
    # about "these are the same moment", and a dismissal from two months ago was not
    # part of that moment.
    fresh = [
        row for row in candidates if _decayed_weight(dismissed_at=row.dismissed_at, now=now) == 1
    ]
    if fresh:
        span = newest.dismissed_at - fresh[-1].dismissed_at
        if span > timedelta(hours=FR25_CLUSTER_WINDOW_HOURS):
            return False

    vectors = read_event_embeddings(event_ids=[row.event_id for row in candidates])
    newest_vector = vectors.get(newest.event_id)
    if newest_vector is None:
        # **No vector is not a zero vector.** The event has not been embedded, so it
        # cannot be compared, and a cluster that cannot be compared has not formed.
        return False

    # **The count, weighted by the decay.** The newest dismissal is fresh by
    # construction — it was just recorded — so it counts for one.
    evidence = Decimal(1)
    for other in others:
        other_vector = vectors.get(other.event_id)
        if other_vector is None:
            return False
        try:
            similarity = cosine(newest_vector, other_vector)
        except ValueError:
            # A zero vector or a length mismatch: not comparable, so not a cluster.
            return False
        if similarity < FR25_CLUSTER_COSINE_THRESHOLD:
            return False
        evidence += _decayed_weight(dismissed_at=other.dismissed_at, now=now)

    return evidence >= Decimal(FR25_CLUSTER_MIN_EVENTS)


def _cluster_category_key(*, candidates: list[EventDismissal], now: datetime) -> str | None:
    """The chip key the cluster agrees on, when one dominates. `None` otherwise.

    **The chip keys come from the catalog, read through `ingestion`.** The dismissal
    rows hold no chip key — the chip is a property of the event's text, and the catalog
    computes it. So the cluster asks the catalog which chips its events belong to.

    **A key has to be on a majority to win.** One event in the cluster being a jazz
    event does not make the cluster jazz: the cluster is three events, and the mute is
    for the thing they have in common. A tie is not a majority, and a tie produces the
    generic prompt.
    """
    event_ids = [row.event_id for row in candidates]
    chips_by_event = read_chip_keys_for_events(event_ids=event_ids)

    tally: dict[str, int] = {}
    for event_id in event_ids:
        for chip_key in chips_by_event.get(event_id, ()):
            tally[chip_key] = tally.get(chip_key, 0) + 1

    if not tally:
        return None
    majority = len(event_ids) / 2
    winners = [key for key, count in tally.items() if count > majority]
    if len(winners) != 1:
        # No majority, or a tie: the generic prompt is the honest one.
        return None
    return winners[0]


def record_dismissal(
    *,
    user_id: UUID,
    event_id: UUID,
    actor: Actor,
    now: datetime,
) -> DismissalResult:
    """Record one dismissal, and say whether the prompt is due.

    **The dismissal is always recorded.** The user really did dismiss the event, and
    the product does not get to decide the gesture did not count and decline to remember
    it. What varies is `cluster_advanced` — whether it moved the counter.

    **The same event dismissed twice is one dismissal.** The unique constraint on
    `(user_id, event_id)` makes the second swipe update the existing row rather than
    adding a second one: the product asks "does the user want less of this?", and the
    answer does not get stronger by swiping the same card twice.

    **The prompt fires once per cluster.** The counter resets when it fires, so the same
    three events do not produce a second prompt. And the prompt is not a nag: the
    cluster's counter is the three dismissals, and once it has fired the cluster is done.
    """
    slot = _resolve_slot(user_id=user_id, event_id=event_id)
    advanced = not _is_rage_dismissal(user_id=user_id, now=now)

    with transaction.atomic(using=PERSONAL):
        _record_row(
            user_id=user_id,
            event_id=event_id,
            slot=slot,
            cluster_advanced=advanced,
            now=now,
        )
        candidates = _cluster_candidates(user_id=user_id, now=now)
        formed = _cluster_forms(candidates=candidates, now=now)

        prompt: ClusterPrompt | None = None
        if formed:
            category_key = _cluster_category_key(candidates=candidates, now=now)
            prompt = _build_prompt(candidates=candidates, category_key=category_key)
            # **The counter resets when the prompt fires.** Without this the same three
            # dismissals would raise the prompt on every subsequent dismissal — a nag,
            # and the mockup's "no dark-pattern nag" is explicit about it.
            EventDismissal.objects.using(PERSONAL).filter(
                user_id=user_id, event_id__in=[row.event_id for row in candidates]
            ).update(cluster_advanced=False)

        write_audit(
            actor=actor,
            action="event.dismissed",
            target_type="event",
            target_id=event_id,
            details={
                "at": now.isoformat(),
                "advanced": advanced,
                "slot": slot,
                "prompt": prompt.title if prompt else None,
            },
        )

    return DismissalResult(
        event_id=event_id,
        cluster_advanced=advanced,
        prompt_due=prompt is not None,
        prompt=prompt,
    )


def _record_row(
    *,
    user_id: UUID,
    event_id: UUID,
    slot: str | None,
    cluster_advanced: bool,
    now: datetime,
) -> None:
    """Write the dismissal row, or refresh the one that is already there.

    **The second dismissal of the same event updates the row.** It does not add a
    second one — the pair is unique — and it does not move the row's timestamp: the
    dismissal happened when it first happened, and moving it would let a user keep a
    cluster alive by re-swiping the same card.
    """
    existing = (
        EventDismissal.objects.using(PERSONAL).filter(user_id=user_id, event_id=event_id).first()
    )
    if existing is not None:
        existing.slot = slot if slot is not None else existing.slot
        existing.cluster_advanced = cluster_advanced
        existing.save(using=PERSONAL, update_fields=["slot", "cluster_advanced"])
        return

    EventDismissal.objects.using(PERSONAL).create(
        user_id=user_id,
        event_id=event_id,
        dismissed_at=now,
        cluster_advanced=cluster_advanced,
        slot=slot,
    )


def _build_prompt(*, candidates: list[EventDismissal], category_key: str | None) -> ClusterPrompt:
    """The prompt's copy, built from the cluster.

    **The explicit variant names the chip's own label.** "Less arts & culture in your
    next digest?" — the label is the server's, from `INTEREST_CHIPS`, so a scraped
    title can never reach the user's screen.

    **The generic variant is used when no chip dominates.** "Less events like these in
    your next digest?" — and the mute it creates is on nothing, because there is no
    category to mute; the user is asked a question whose answer would have no effect.
    The generic variant is therefore only a prompt, never a mute's subject.
    """
    count = len(candidates)
    description = PROMPT_DESCRIPTION.format(count=count)
    if category_key is None:
        return ClusterPrompt(
            title=PROMPT_TITLE_GENERIC.format(), description=description, category_key=None
        )
    label = CHIP_LABELS.get(category_key, category_key)
    return ClusterPrompt(
        title=PROMPT_TITLE_EXPLICIT.format(label=label),
        description=description,
        category_key=category_key,
    )


__all__ = [
    "CHIP_LABELS",
    "ClusterPrompt",
    "DismissalResult",
    "PROMPT_DESCRIPTION",
    "PROMPT_TITLE_EXPLICIT",
    "PROMPT_TITLE_GENERIC",
    "SERENDIPITY_SLOT",
    "cosine",
    "record_dismissal",
]
