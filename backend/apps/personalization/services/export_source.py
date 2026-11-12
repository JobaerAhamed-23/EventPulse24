"""What `personalization` publishes to the export (FR-52): one preference, and the dates.

**This module exists because of AD-2, not for convenience.** The export is owned by
`identity` — an export is about an account — but the records it describes are
`personalization`'s, and AD-2's contract says *"only `apps.personalization` imports
`apps.personalization.models`; others call its services"*. So `identity` asks here, and the
models stay behind the wall they are supposed to stay behind.

**The registry walk does not come through here, and that is the point of it.** The bulk of
the export reads `retention_registry()` and never names an app. What this module supplies is
the two things a generic walk genuinely cannot know: whether this user wants their own event
locations to leave in full, and which of their records have a date and therefore belong in a
calendar file.
"""

from collections.abc import Iterator
from uuid import UUID

from apps.personalization.models import DigestPreference, PersonalEvent, SavedEvent
from shared.db import PERSONAL

#: What a redacted location reads as. Matches `identity`'s `REDACTED` by value rather than
#: by import, for the same wall reason this module exists.
REDACTED = "[redacted]"


def shares_precise_location(*, user_id: UUID) -> bool:
    """Whether this user's own event locations may leave the product in full (FR-52).

    **A user with no preference row shares.** The column defaults to `True`, and a missing
    row is a user who has never opened settings — not a user who opted out. Treating absence
    as refusal would redact the locations of every account that never touched the toggle,
    which is most of them, and would look like data loss in their own download.
    """
    row = DigestPreference.objects.using(PERSONAL).filter(user_id=user_id).first()
    if row is None:
        return True
    return row.share_precise_location


def dated_records_for(*, user_id: UUID, redact_location: bool) -> Iterator[dict]:
    """This user's records that belong in a calendar file, as plain dicts.

    **Both kinds of event, because both are the user's.** A personal event is theirs by
    authorship; a saved event is theirs by choice, and an export that dropped the saves
    would hand back a calendar missing everything the product was actually for.

    **The saved event's snapshot is what is exported, not a catalog read.** AD-21 says the
    snapshot is what the Timeline and the conflict detector use, so it is also what the user
    is owed — and reading `catalog` from here would cross the AD-3 wall to tell them
    something slightly different from what their own screens show.

    **Redaction applies to personal events only.** A saved public event's location is the
    catalog's published fact about a public event, not a statement about where this user
    goes; the opt-out is about the user's own records, and redacting a public venue would
    withhold information the user could read on the event's own page.
    """
    personal = PersonalEvent.objects.using(PERSONAL).filter(user_id=user_id).order_by("start_utc")
    for event in personal:
        location = event.location or ""
        yield {
            "uid": f"personal-{event.id}@eventpulse24",
            "summary": event.name,
            "start": event.start_utc,
            "end": event.end_utc,
            "location": REDACTED if (redact_location and location) else location,
        }

    saved = SavedEvent.objects.using(PERSONAL).filter(user_id=user_id).order_by("start_utc")
    for save in saved:
        yield {
            "uid": f"saved-{save.id}@eventpulse24",
            # The snapshot holds no title: AD-21 snapshots the *time*, which is what
            # propagation keeps correct. A title read from `catalog` would cross the wall.
            "summary": f"Saved event {save.event_id}",
            "start": save.start_utc,
            "end": save.end_utc,
            "location": "",
        }


__all__ = ["dated_records_for", "shares_precise_location"]
