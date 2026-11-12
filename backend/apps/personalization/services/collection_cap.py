"""The Pro gate on collections (FR-49) — and the two operations it actually covers.

**The gate is here, not in the commands.** `saved_collections.py` is deliberately
tier-agnostic: the rows are the user's data, and a command that refused on tier would have
to be re-run after an upgrade to restore what the user already said. The same split
`quiet-hours-pro-api` made, for the same reason — the paywall belongs where the user is.

**Only the two operations that *add* are gated.** Creating a collection and assigning a save
into one are Pro; reading, unassigning, renaming, reordering and deleting are not. The rule
is *a lapsed subscriber keeps using what they have at its current size and cannot grow it*,
and it follows from the brief's own constraint that nothing of theirs is deleted on a
downgrade:

- **Gating rename or reorder** would mean a lapsed user cannot fix a typo in a name they
  wrote. That is punishment for lapsing, not a tier boundary.
- **Gating delete** would trap them with data they want gone — the exact inverse of what a
  "we never delete your data" constraint is for.
- **Not gating assign** would leave the cap limiting how many collections exist and not how
  much they are used, which makes it a counting exercise rather than a tier.

**The refusal is an inline prompt, not a modal.** `CollectionsProRequired` carries
`{"cap", "upgrade_hint"}` and nothing else — no `modal`, no `title`, no `actions`, no
`dismissable` — for the same reason the save cap and the calendar cap do (EXPERIENCE.md §3
and §4). A cap that interrupts is a cap that trains people to dismiss prompts.
"""

from uuid import UUID

from apps.identity.services import is_pro
from domain.errors import CollectionsProRequired
from shared.constants import FREE_TIER_COLLECTIONS

#: The upgrade sentence for an account trying to start or fill a collection. One calm
#: sentence, matching the save cap's and the calendar cap's, and the word "Pro" is what the
#: quiet "Upgrade" link beside it points at.
COLLECTIONS_UPGRADE_HINT = "Group your saves into collections with Pro."


def check_collections_allowed(*, user_id: UUID) -> None:
    """Refuse an operation that would add to this user's collections, unless they are Pro.

    **A Pro user is never refused and nothing is counted.** The check returns before any
    cap arithmetic, so entitlement is read once and the ordinary case costs one query.

    Raises:
        CollectionsProRequired: the account is not Pro.
    """
    if is_pro(user_id=user_id):
        return

    raise CollectionsProRequired(
        details={"cap": FREE_TIER_COLLECTIONS, "upgrade_hint": COLLECTIONS_UPGRADE_HINT}
    )


__all__ = ["COLLECTIONS_UPGRADE_HINT", "check_collections_allowed"]
