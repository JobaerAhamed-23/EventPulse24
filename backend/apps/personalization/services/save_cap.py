"""The save gate (FR-49): one free save a day, and the calm prompt after it.

**This is the upgrade trigger.** FR-48 calls the 1-save/day cap "the gate" — the single
thing that turns a Free user into a paying one. Without it the product has no reason to
upgrade anyone, and every other piece of this intent (the pricing page, the upgrade
prompts, the Pro tier itself) is decoration around a gate that is standing open.

**The count is the throttle port's, not a row count.** The gate is declared through
`ThrottlePort.check(key, limit, window_seconds)`, exactly as `EventReport` declares its
own limit — not hand-rolled, and never a count of `SavedEvent` rows. A row count would
make the cap depend on data the user can delete (unsaving an event would hand the
allowance back, and re-saving would spend it again), and it would give the gate a second
source of truth for "how many saves has this user had". The throttle port is the
counter; this module only says what the key is and what a refusal looks like.

**The window is anchored at the first save, so a refusal costs the user no time.** Both
adapters count an attempt *before* deciding whether to allow it — Redis `INCR`s, the
in-memory adapter appends. That is the port's contract, and it is the right one for a
rate limit. But the window itself is fixed: it frees up `window_seconds` after the *first*
attempt in it. A refused save therefore cannot extend the user's wait and cannot shorten
it. Being refused is not what makes them wait; their first save is. That is the sense in
which *"a refused save consumes no throttle"*: the refusal does not cost the user time
they would not have lost anyway, and it writes nothing at all.

**The gate asks who the user is, through the one published read.** `is_pro` is the single
entitlement read this project has (`apps/identity/services/entitlement.py`); it returns a
bool and nothing else, and it lives in the app that owns the data because
`apps.personalization` may not import `apps.identity.models`. A Pro user has no save cap
at all — FR-49's own testable consequence is that a Pro user can save 10+ events in a day
without a soft wall — so the gate is skipped entirely for them, and no throttle slot is
spent on a save that could never have been refused.

**The refusal is an inline prompt, not a modal.** `SaveCapReached` carries
`{"cap", "upgrade_hint"}` and nothing else — no `modal`, no `title`, no `actions`, no
`dismissable` — for the same reason `CalendarProviderCapReached` does (EXPERIENCE.md §3
and §4). A cap that interrupts with a modal is a cap that trains people to dismiss
prompts.
"""

from dataclasses import dataclass
from uuid import UUID

from apps.identity.services import is_pro
from domain.errors import SaveCapReached
from ports.registry import get_throttle_port
from shared.constants import FREE_TIER_SAVE_DAILY_LIMIT, FREE_TIER_SAVE_WINDOW_SECONDS

#: The upgrade sentence. `EXPERIENCE.md` §3, the "Free-tier save-cap prompt" row:
#: *"You saved one event today. Save more with Pro."* — one calm sentence, and the word
#: "Pro" is what the quiet "Upgrade" link beside it points at.
SAVE_CAP_UPGRADE_HINT = "You saved one event today. Save more with Pro."


def save_throttle_key(user_id: UUID) -> str:
    """The throttle key for one user's saves.

    Keyed by **user**, not by IP: the endpoint is session-scoped, so there is always
    exactly one user, and the limit is "1 per user per day" — a per-host limit would let
    one person behind a NAT share an allowance and one person on a VPN lose theirs. A
    user id is already an opaque identifier, so it needs no digest (AD-13 is about
    addresses).

    The prefix keeps the key out of the auth throttle's namespace: both live in the same
    Redis instance, and `save:` and the auth keys must never collide.
    """
    return f"save:{user_id}"


def check_save_allowed(*, user_id: UUID) -> None:
    """Refuse this save if the user's tier has spent its allowance. Returns otherwise.

    **This is called only when a save will actually happen.** A repeat save of an
    already-saved event is not a new save — it is the same row, returned again — so it is
    not gated, and no throttle slot is spent on it. `save_event` checks that first.

    **A Pro user is never refused and never spends a slot.** The check is skipped
    entirely rather than being made with a limit of infinity, so a Pro user's saves leave
    no trace in the counter at all.

    Raises:
        SaveCapReached: The user's tier has spent its allowance in this window.
    """
    if is_pro(user_id=user_id):
        return

    decision = get_throttle_port().check(
        save_throttle_key(user_id),
        limit=FREE_TIER_SAVE_DAILY_LIMIT,
        window_seconds=FREE_TIER_SAVE_WINDOW_SECONDS,
    )
    if not decision.allowed:
        raise SaveCapReached(
            details={
                "cap": FREE_TIER_SAVE_DAILY_LIMIT,
                "upgrade_hint": SAVE_CAP_UPGRADE_HINT,
            }
        )


@dataclass(frozen=True)
class SaveQuota:
    """What a user's save allowance stands at, for showing rather than for deciding.

    **`check_save_allowed` is the gate; this is the sign above it.** The two must never be
    swapped: the gate counts an attempt and this one counts nothing, so asking the gate
    what the allowance is would spend it. A surface that displayed the cap by calling the
    gate would charge a user a save for looking at a page.

    **A Pro user has `cap=None`,** not a very large cap. FR-48's own consequence is that a
    Pro user can save without a soft wall at all, and a cap of "infinity" is a number a
    frontend would eventually render.
    """

    used: int
    cap: int | None
    resets_in_seconds: int
    is_pro: bool

    @property
    def exhausted(self) -> bool:
        """Has this user spent the allowance? Always `False` for Pro, which has none."""
        return self.cap is not None and self.used >= self.cap


def read_save_quota(*, user_id: UUID) -> SaveQuota:
    """This user's save allowance as it stands, **without spending any of it**.

    Read-only by construction: it goes through `ThrottlePort.peek`, which counts nothing.
    The gate is still `check_save_allowed`, and it is still what decides an actual save —
    this read only says what to show.

    **The count is the throttle's, never a `SavedEvent` row count**, for the reason the
    module docstring gives: a row count would let a user hand their allowance back by
    unsaving, and the gate would have two sources of truth.

    **A Pro user is not peeked at all.** They have no cap, so there is no window to read,
    and a Pro user's saves spend no throttle slots — there would be nothing there to find.
    """
    if is_pro(user_id=user_id):
        return SaveQuota(used=0, cap=None, resets_in_seconds=0, is_pro=True)

    state = get_throttle_port().peek(
        save_throttle_key(user_id),
        window_seconds=FREE_TIER_SAVE_WINDOW_SECONDS,
    )
    return SaveQuota(
        used=state.used,
        cap=FREE_TIER_SAVE_DAILY_LIMIT,
        resets_in_seconds=state.resets_in_seconds,
        is_pro=False,
    )


def reset_save_allowance(*, user_id: UUID) -> None:
    """Give this user their save allowance back: clear the throttle window.

    **This exists for the repeatable seed, and it is the reason the throttle port has a
    `reset` at all.** The walk-through's Free account has to start each run with a full
    allowance, or the *second* run would find the quota already spent — the wall would be
    up before the test had pressed anything, and the test that exercises the wall would
    fail for the wrong reason. **A seed that could only be run once would not be a seed.**

    **It does not touch the saved rows.** The allowance is the throttle's counter, not
    the `SavedEvent` rows; clearing the counter gives the account its one save back
    while leaving what it has saved where it is. That is deliberate: a seed that
    un-saved the account's events would change what the surface shows, and the
    walk-through is *about* seeing a saved event.

    **A Pro user's allowance is never spent, so there is nothing to clear.** The call is
    a no-op for them rather than an error — the seed does not need to know the plan.
    """
    if is_pro(user_id=user_id):
        return
    get_throttle_port().reset(save_throttle_key(user_id))


__all__ = [
    "SAVE_CAP_UPGRADE_HINT",
    "SaveQuota",
    "check_save_allowed",
    "read_save_quota",
    "reset_save_allowance",
    "save_throttle_key",
]
