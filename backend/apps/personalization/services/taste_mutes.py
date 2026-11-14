"""The category mute (FR-25): how one person asked to see less of one category.

`personalization` owns `CATEGORY_MUTE` (AD-16). The category itself is a **chip key** —
`tech_meetups`, `arts_culture`, … — from `shared.constants.INTEREST_CHIPS`, and it is
held **by value**: the vocabulary lives in `shared`, which holds no tables, so a
relation is not available.

**Why the chip key and not a new `Event.category`.** The codebase already computes each
event's `chip_keys` at read time, deliberately not as a stored column — a stored column
would be wrong the moment the keyword table changed — and FR-22's interest term, the
largest weight in the published formula, already reads it. A second category field would
be a second opinion about what an event is.

**One tap unmutes, and the unmute deletes the row.** There is no `muted` boolean to
flip, because there is no "unmuted" state to record: the absence of a row *is* the
absence of a mute. This is the same shape `SourceMute` takes — "there are two states,
not three; `default` is the absence of a row".

**`expires_at` nullable means indefinite.** The mockup offers four durations — seven
days, thirty, ninety, and "until I change it" — and the fourth is a *state of the same
row* rather than a second code path. A null expiry is indefinite; a set expiry is
finite. So the product never permanently bans a category: the PRD's "serendipity is a
product decision, not a user preference" is a rule about the *default*, and an explicit
indefinite mute is the user saying otherwise.

**The durations are a closed set.** Seven, thirty, ninety, or indefinite. The endpoint
refuses anything else: a mute that outlived the user's patience by a typo is a mute the
user has to find a screen to undo.

**Every write is audited (AD-5), inside the personal transaction.** `write_audit` raises
if it is called outside one.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.db import transaction

from apps.personalization.models import CategoryMute
from apps.personalization.services.audit import write_audit
from shared.actor import Actor
from shared.constants import FR25_MUTE_DURATIONS_DAYS, INTEREST_CHIPS
from shared.db import PERSONAL

#: The chip keys a mute may name.
#:
#: **The vocabulary is closed, and the server owns it.** The category label the user
#: reads comes from `INTEREST_CHIPS`, so an unknown key would have no label — and a mute
#: on a key the server does not recognise would exclude nothing, silently, while the
#: screen showed a row the user could not make sense of.
CHIP_KEYS: frozenset[str] = frozenset(key for key, _label in INTEREST_CHIPS)

#: The chip key → label map.
CHIP_LABELS: dict[str, str] = dict(INTEREST_CHIPS)


@dataclass(frozen=True)
class CategoryMuteResult:
    """The outcome of setting or clearing one category mute.

    `changed` says whether this call did anything. The API needs it: setting a mute that
    is already set is a success, not an error, but a response that claimed a change when
    none happened would make the screen redraw something that did not move.
    """

    category_key: str
    expires_at: datetime | None
    changed: bool


@dataclass(frozen=True)
class ActiveCategoryMute:
    """One active mute, as the settings screen reads it."""

    category_key: str
    label: str
    expires_at: datetime | None

    @property
    def is_indefinite(self) -> bool:
        """Whether this mute has no end date."""
        return self.expires_at is None


class UnknownCategoryError(ValueError):
    """The category key is not one of the server's chip keys.

    A programming error at the boundary, never mapped to HTTP by this service: the API
    layer refuses an unknown key with a 422 before it gets here.
    """


class UnknownDurationError(ValueError):
    """The duration is not one of the three the product offers.

    The same shape as `UnknownCategoryError`: the API layer refuses it with a 422, and
    this service never sees one.
    """


def _validate_category_key(category_key: str) -> str:
    """The key, if it is one of the server's. Raises otherwise."""
    if category_key not in CHIP_KEYS:
        raise UnknownCategoryError(f"unknown category key: {category_key!r}")
    return category_key


def _validate_duration(duration_days: int | None) -> int | None:
    """The duration, if it is one of the three the product offers. Raises otherwise."""
    if duration_days is None:
        return None
    if duration_days not in FR25_MUTE_DURATIONS_DAYS:
        raise UnknownDurationError(f"unknown mute duration: {duration_days!r}")
    return duration_days


def set_category_mute(
    *,
    user_id: UUID,
    category_key: str,
    duration_days: int | None,
    actor: Actor,
    now: datetime,
) -> CategoryMuteResult:
    """Mute one category for one user, for the given duration. Idempotent.

    **`duration_days=None` means indefinite.** The mockup's fourth choice — "until I
    change it" — is a null expiry on the same row, not a second code path.

    **The expiry is computed from `now`, not from the row's creation.** A mute set for
    thirty days is muted for thirty days from *now*: re-setting it refreshes the window,
    which is what a user pressing "30 days" again is asking for.

    **The row is locked before it is read.** The expiry is read to decide whether
    anything moved, and then written — and without the lock two concurrent requests
    could both read the old expiry, both conclude they changed it, and both write an
    audit row claiming a change while only the second write survives. `select_for_update`
    takes the row's lock first, so the second request waits, reads the first request's
    expiry, and correctly reports that nothing moved. (The *create* path needs no such
    care: the unique constraint on `(user_id, category_key)` is what `get_or_create`
    leans on.)
    """
    _validate_category_key(category_key)
    _validate_duration(duration_days)
    expires_at = None if duration_days is None else now + timedelta(days=duration_days)

    with transaction.atomic(using=PERSONAL):
        row, created = CategoryMute.objects.using(PERSONAL).get_or_create(
            user_id=user_id,
            category_key=category_key,
            defaults={"expires_at": expires_at},
        )
        changed = created
        if not created:
            # **Re-read under the row's lock.** `get_or_create` fetched the row before
            # the lock was taken, so its `expires_at` may already be stale.
            row = (
                CategoryMute.objects.using(PERSONAL)
                .select_for_update()
                .get(user_id=user_id, category_key=category_key)
            )
            if row.expires_at != expires_at:
                row.expires_at = expires_at
                row.save(using=PERSONAL, update_fields=["expires_at"])
                changed = True
        if changed:
            write_audit(
                actor=actor,
                action="category_mute.set",
                target_type="category",
                target_id=category_id_for(category_key),
                details={
                    "at": now.isoformat(),
                    "category_key": category_key,
                    "expires_at": expires_at.isoformat() if expires_at else None,
                },
            )
    return CategoryMuteResult(category_key=category_key, expires_at=expires_at, changed=changed)


def clear_category_mute(
    *, user_id: UUID, category_key: str, actor: Actor, now: datetime
) -> CategoryMuteResult:
    """Unmute one category. One tap, and the row is gone.

    **The row is deleted, not flipped.** There is no "unmuted" state to record — the
    absence of a row *is* the absence of a mute — so an unmute is a deletion, and
    "Restore all defaults" is the same operation applied to every row.

    **Unmuting does not resurrect the muted events.** The events that were excluded from
    a digest are excluded from the digests they were excluded from; the next digest is
    composed from the current candidate pool. A user who unmutes is asking for the
    category back *from now on*, and the mockup's own framing is "in your next digest".
    """
    _validate_category_key(category_key)

    with transaction.atomic(using=PERSONAL):
        deleted, _ = (
            CategoryMute.objects.using(PERSONAL)
            .filter(user_id=user_id, category_key=category_key)
            .delete()
        )
        if deleted:
            write_audit(
                actor=actor,
                action="category_mute.cleared",
                target_type="category",
                target_id=category_id_for(category_key),
                details={"at": now.isoformat(), "category_key": category_key},
            )
    return CategoryMuteResult(category_key=category_key, expires_at=None, changed=bool(deleted))


def clear_all_category_mutes(*, user_id: UUID, actor: Actor, now: datetime) -> int:
    """Clear every category mute for one user. Idempotent.

    **This is the bulk reset behind "Restore all defaults".** It removes every row for
    the user and returns how many it removed. Nothing else is touched: the chip
    vocabulary is the server's, and another user's preferences are theirs.
    """
    with transaction.atomic(using=PERSONAL):
        deleted, _ = CategoryMute.objects.using(PERSONAL).filter(user_id=user_id).delete()
        if deleted:
            write_audit(
                actor=actor,
                action="category_mute.restore_defaults",
                target_type="user",
                target_id=user_id,
                details={"at": now.isoformat(), "removed": deleted},
            )
    return deleted


def read_active_mutes(*, user_id: UUID, now: datetime) -> tuple[ActiveCategoryMute, ...]:
    """This user's active category mutes, with their labels and expiries.

    **An expired mute is not active.** The row is still there — it is the user's data, and
    it is purged with the rest — but it no longer mutes anything, so the screen does not
    list it and the composition path does not apply it. A mute that expired an hour ago
    and one that expires in an hour are the same thing to the reader of this list.

    **The chip key's label comes from the server's vocabulary.** The screen names the
    category, and the name is the server's own wording — never a scraped string (AD-9).
    """
    rows = (
        CategoryMute.objects.using(PERSONAL)
        .filter(user_id=user_id)
        .order_by("category_key")
        .values_list("category_key", "expires_at")
    )
    active = [
        ActiveCategoryMute(
            category_key=category_key,
            label=CHIP_LABELS.get(category_key, category_key),
            expires_at=expires_at,
        )
        for category_key, expires_at in rows
        if expires_at is None or expires_at > now
    ]
    return tuple(active)


def read_muted_category_keys(*, user_id: UUID, now: datetime) -> frozenset[str]:
    """The chip keys this user has muted, for the composition path to exclude.

    **This is the read the composition path uses.** It is called on every digest
    composition and every Browse page, so it is one query — and it excludes the expired
    rows for the same reason `read_active_mutes` does.

    **The set is of chip keys, not of event ids.** A category mute is about a
    *category*, and the composition path applies it to whatever categories the candidate
    happens to belong to.
    """
    return frozenset(mute.category_key for mute in read_active_mutes(user_id=user_id, now=now))


def is_muted_by_category(*, chip_keys: tuple[str, ...], muted_keys: frozenset[str]) -> bool:
    """Whether this event's chips include a category the user has muted.

    **The mute is a filter, not a score term.** A muted category's events are *absent*
    from the candidate set — they are not scored and then ranked lower. The distinction is
    the same one the source mute draws: `mute` excludes, `show_less` deprioritises.

    **An event with no chips is never muted.** The chip keys are matched from the event's
    own text, so an event whose title and description match no keyword belongs to no
    category — and excluding it would be the product deciding what it is on the user's
    behalf. A user who muted "Arts & culture" is asking for fewer art events, not fewer
    events the matcher has not learned about yet.

    **The intersection is what makes this a category mute.** An event in two categories,
    one muted and one not, *is* in a muted category — the user asked for less of it, and
    the event is part of it.
    """
    if not muted_keys:
        return False
    return bool(set(chip_keys) & muted_keys)


def category_id_for(category_key: str) -> UUID:
    """A stable UUID for a chip key, for the audit row's `target_id`.

    **The audit row's target is a category, and a category has no id.** The chip key is
    the only name it has, and the audit row's `target_id` is a `UUIDField` — so the key
    is hashed into a UUID. The hash is stable, so the same chip always audits to the same
    id, and two chip keys never collide.

    **This is not a relation.** Nothing looks the id up; it exists so the audit row has
    something of the right shape to point at, and so that an audit reader can group the
    rows for one category together.
    """
    import uuid

    return uuid.uuid5(uuid.NAMESPACE_URL, f"eventpulse24:category:{category_key}")


__all__ = [
    "CHIP_KEYS",
    "CHIP_LABELS",
    "ActiveCategoryMute",
    "CategoryMuteResult",
    "UnknownCategoryError",
    "UnknownDurationError",
    "category_id_for",
    "clear_all_category_mutes",
    "clear_category_mute",
    "is_muted_by_category",
    "read_active_mutes",
    "read_muted_category_keys",
    "set_category_mute",
]
