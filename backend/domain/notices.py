"""FR-54's notice vocabulary: what a state change is called, and what it says about reminders.

**Stdlib only**, like the rest of `domain`. This is pure copy and pure derivation — a
change kind and its facts in, a subject and a reminder-consequence out — and it lives in
`domain` because the renderer, the notice service and the tests all need the same answers,
and a subject written twice is a subject that drifts.

---

## Why the vocabulary is in `domain` and not in the template

FR-54's subjects are **fixed by the PRD**, verbatim, and a test asserts the literal strings.
That makes them a contract, not a preference. A contract belongs in one place that every
caller reads, and the only place that can be read by both the renderer and the service that
decides *whether* there is a notice at all is `domain`.

**The consequence is that a kind with no subject is a programming error.** If
`domain.lifecycle` gains a kind and this module does not learn it, the renderer raises
rather than falling back to a generic subject. A generic subject is the one thing FR-54
forbids: a notice reading "EventPulse24: your saved event was cancelled" about an event
that was not cancelled is worse than a notice that did not go out, because the user reads it.

---

## The subjects, and whose they are

FR-54 names four subjects verbatim:

| subject | for |
|---|---|
| `EventPulse24: [event name] was cancelled.` | a cancellation |
| `EventPulse24: [event name] was moved to [new date].` | a postponement |
| `EventPulse24: [event name] moved to [new location].` | a venue change |
| `EventPulse24: [event name] is sold out.` | a sell-out |

**The other three kinds are ours**, and the table records which is which. `ChangeKind` has
seven members; the PRD names four.

- **`reinstated`** — the PRD names no subject. It re-mints the reminders, so the user's world
  is "it is back". Ours, in the PRD's register.
- **`superseded`** — the PRD names no subject. The event moved beyond the ±30-day window and
  a *different* event replaced it. Ours, in the PRD's register.
- **`detail_changed`** — **two subjects, or none.** See below.

---

## `detail_changed` is not one thing, and that is the whole subtlety

**FR-54's third subject — "moved to [new location]" — has no kind of its own.**
`domain.lifecycle.classify_change` files a venue change under `DETAIL_CHANGED`, because
`venue_fingerprint` is in `_DETAIL_FACTS`. The same kind also covers a title edit, a
description edit, a canonical-URL edit and a timezone-label edit
(`tests/domain/test_lifecycle.py:105` pins the venue case).

**So silencing `detail_changed` wholesale would silence the PRD's own third subject** — the
one the work item asks for and the PRD fixes verbatim.

**The distinction is available, and it lives in the change's facts rather than its kind.**
`event_writes._kind_facts` records *only what actually changed*, so:

| what changed | the change row carries |
|---|---|
| the venue | `before["venue_fingerprint"]`, `after["venue_fingerprint"]` |
| the title | `before["title"]`, `after["title"]` |
| the description | `before["description"]`, `after["description"]` |

**So the rule is about the change, not the kind:** a `detail_changed` that moved the venue
is notified with the PRD's subject; a `detail_changed` that fixed a typo is not notified at
all.

**Why the rest is silent**, in the PRD's own terms:

1. **FR-53 says not every change deserves a notification.** Its out-of-scope line: *"Real-time
   push notification on every state change (would be engagement-trap; only meaningful changes
   trigger user-facing notification per FR-54)."*
2. **A title or description edit has no reminder consequence.**
   `LIFECYCLE_SEND_BEHAVIOUR` maps `detail_changed` to `KEEP` and
   `LIFECYCLE_PERSONAL_BEHAVIOUR` maps it to `NONE`. **FR-54's body requirement is "what
   changed and what it means for the user's reminders" — and a title edit has no such
   meaning.** A notice with no consequence is exactly the notification FR-54 is trying not
   to send.
3. **It cannot say what changed.** The kind carries no detail, so a notice about a title
   edit could only say "the details changed" — which is not information.
4. **The user can see it for themselves.** A typo fix in a description is on the Detail
   Screen, which is where a description belongs.

**A title change is arguably meaningful** — a venue renaming "Rooftop Cinema" to "Rooftop
Cinema: Late Night" is the kind of thing a user should know about. **The change row does
distinguish it** (`after["title"]` is present), so the argument is not that the distinction
is unavailable; it is that a rename on a page the user can open is not worth an email. **If
a title change should notify, that is a `title_changed` kind** — with its own precedence
position, its own subject and its own ingestion rule. A follow-up, not something this
module smuggles in.

---

## The title is folded, and the fold lives here

**An ingested title is untrusted text, and it lands in a mail header.** A `\n` in the
title would end the `Subject:` header and let the rest of the title become headers of
its own — the SMTP header injection primitive. So the title is folded before it is put
anywhere.

**The fold is one rule: collapse every run of whitespace to a single space and trim.**
`" ".join(title.split())` does all three at once, and it is the same rule the platform's
own header handling applies — so a title that survives the fold is a title the mail
transport can carry.

**Why it lives in `domain` rather than in the renderer.** The subject and the body are
two renderings of the same title, and they are built by two different modules — the
subject by `email_templates`, the body by a Django template. **If each folded its own
way, the mail would say one thing in its subject and another in its body.** The fold is
the same fact as the subject vocabulary, so it belongs beside it: one place, read by both.

**A title that folds to nothing is not a title.** Whitespace-only folds to the empty
string, and the empty string is not a name. So the caller substitutes the fallback
after folding — never before, or `"   "` would survive as a name of three spaces.

---

## The reminder consequence is derived, not written out

**The body's line about the user's reminders must be the same promise the send machinery
kept.** If the body said "your reminders have been cancelled" while the reminders still
fired, that would be exactly the bug class this whole intent exists to prevent — so the
line is *derived* from `LIFECYCLE_SEND_BEHAVIOUR`, the table the sends already follow.

| `LIFECYCLE_SEND_BEHAVIOUR` | the body says |
|---|---|
| `CANCEL` | the reminders were cancelled |
| `REMINT` | the reminders were rescheduled |
| `KEEP` | the reminders are unchanged |

**One kind overrides the derivation: `reinstated`.** It is `REMINT` — the reminders are
re-minted — but "your reminders have been rescheduled to the new time" is a sentence about
a *new time*, and a reinstatement is not a new time: the event is back at the time it was
already at. **So `reinstated` says the reminders are back on**, and the override is written
out explicitly rather than emerging from a branch, so a reader can see which kind says
something other than its behaviour implies.

**`sold_out` is `KEEP`, so it says "unchanged"** — and that is worth saying: a user who
bought a ticket needs to know the reminder is still coming.
"""

from domain.lifecycle import ChangeKind
from shared.constants import LIFECYCLE_SEND_BEHAVIOUR, LifecycleSendBehaviour

#: The prefix every subject carries. FR-54's four subjects all begin with it, and a subject
#: that does not is not a subject FR-54 wrote.
SUBJECT_PREFIX = "EventPulse24: "

#: What a notice says when the event has no name to give.
#:
#: **A fallback, not a second subject.** The PRD's subjects name the event, so a subject
#: with no name in it is still the PRD's subject — it just has "your saved event" where
#: the name would be. The alternative, omitting the name and saying "EventPulse24: was
#: cancelled.", is a sentence about nothing, and the user cannot tell which of their
#: events it means.
#:
#: **The same phrase the reminder body already uses**, so a user reading two mails from
#: the same product is not told two different ways that a name is missing.
MISSING_TITLE = "your saved event"

#: The subjects, by change kind.
#:
#: **A `{title}` is the event's name; a `{when}` is the new date; a `{where}` is the new
#: venue's name.** They are placeholders, not format strings — the subject is *built* by
#: `notice_subject`, not by a `str.format` over a dict, because a missing key is a
#: `KeyError` waiting for a change nobody tested.
#:
#: **`detail_changed` has two entries' worth of meaning and one template.** Its template
#: is the PRD's "moved to {where}." — but it is only used for a change that moved the
#: venue. A `detail_changed` that fixed a typo is not notified at all; see the module
#: docstring.
#:
#: **Four of these are the PRD's, verbatim. Three are ours.** `PRD_SUBJECT_KINDS` says
#: which, so a reader can tell at a glance which lines are the PRD's contract and which are
#: this project's.
NOTICE_SUBJECTS: dict[str, str] = {
    # --- The PRD's four, verbatim. ---
    ChangeKind.CANCELLED.value: "{title} was cancelled.",
    ChangeKind.POSTPONED.value: "{title} was moved to {when}.",
    ChangeKind.TIME_MOVED.value: "{title} was moved to {when}.",
    ChangeKind.SOLD_OUT.value: "{title} is sold out.",
    # --- Ours. The PRD names no subject for these. ---
    #
    # A supersede is not a move: the event was replaced by a different one, so the subject
    # says so rather than naming a time that is not the user's any more.
    ChangeKind.SUPERSEDED.value: "{title} was replaced by a new event.",
    # A reinstatement is the event being back, at the time it was already at.
    ChangeKind.REINSTATED.value: "{title} is back on.",
    # The PRD's third subject. Used only for a `detail_changed` that moved the venue.
    ChangeKind.DETAIL_CHANGED.value: "{title} moved to {where}.",
}

#: The kinds whose subject the PRD fixes. The rest are this project's.
#:
#: **`detail_changed` is in here, and that is the whole subtlety**: the PRD's third subject
#: is a venue move, and a venue move is filed under `detail_changed`. It is a member here
#: because the PRD *does* fix that subject — not because every `detail_changed` is notified.
PRD_SUBJECT_KINDS = frozenset(
    {
        ChangeKind.CANCELLED.value,
        ChangeKind.POSTPONED.value,
        ChangeKind.TIME_MOVED.value,
        ChangeKind.SOLD_OUT.value,
        ChangeKind.DETAIL_CHANGED.value,
    }
)

#: The kinds that change a user's world but say nothing to them.
#:
#: **Keyed by value, not by `ChangeKind`, because these are not `ChangeKind` members.**
#: `classify_change` derives its kinds from `EventFacts`, and `publication_status` is not
#: one of them — a delisting is *written* by `apps.ingestion.services.editorial_state`, not
#: inferred from a poll. `state_notices._as_kind` already degrades an unrecognised kind to
#: "ordinary, outranks nothing", so the two live here as the strings the outbox carries.
#:
#: **Why silence is the right answer, and not an oversight.** FR-54 fixes four subjects
#: verbatim and has no wording for a listing we pulled. `"was cancelled"` would be **false**
#: for the two commonest reject reasons — a duplicate and a wrong venue say nothing about
#: whether the event happens — and FR-54's own rule is that a notice must say "what changed
#: and what it means for the user's reminders". Inventing "we removed this listing" would be
#: new product copy no requirement ratifies. So the reminders are cancelled (the user is
#: protected from a false reminder) and nothing is claimed about the world.
#:
#: The user still sees it: their saved card falls back to "event no longer available", the
#: same path a superseded or unpublished event takes.
UNNOTIFIED_KINDS: frozenset[str] = frozenset({"delisted", "relisted"})

#: What the body says about the user's reminders, per kind.
#:
#: **Derived from `LIFECYCLE_SEND_BEHAVIOUR`** so the body cannot promise something the send
#: machinery did not do. The derivation is the default; the overrides below are the kinds
#: whose *wording* needs more than the behaviour implies.
REMINDER_CONSEQUENCE: dict[str, str] = {
    ChangeKind.CANCELLED.value: "Your reminders for this event have been cancelled.",
    ChangeKind.SUPERSEDED.value: "Your reminders for this event have been cancelled.",
    ChangeKind.POSTPONED.value: "Your reminders have been rescheduled to the new time.",
    ChangeKind.TIME_MOVED.value: "Your reminders have been rescheduled to the new time.",
    ChangeKind.REINSTATED.value: "Your reminders are back on.",
    ChangeKind.SOLD_OUT.value: "Your reminders are unchanged.",
    # A venue move keeps the reminders — the event still happens, in a different room.
    ChangeKind.DETAIL_CHANGED.value: "Your reminders are unchanged.",
}

#: The consequence the send behaviour implies, when the kind does not say otherwise.
_BEHAVIOUR_CONSEQUENCE = {
    LifecycleSendBehaviour.CANCEL: "Your reminders for this event have been cancelled.",
    LifecycleSendBehaviour.REMINT: "Your reminders have been rescheduled to the new time.",
    LifecycleSendBehaviour.KEEP: "Your reminders are unchanged.",
}


def fold_title(title: str | None) -> str | None:
    """Fold an untrusted title so it can be put in a mail header and a body.

    **One rule: every run of whitespace becomes a single space, and the ends are
    trimmed.** `str.split()` with no argument splits on any run of whitespace and drops
    the empty pieces, so `" ".join(title.split())` is the whole fold.

    **Why the title is untrusted.** It comes from an ingested source record, so it is
    whatever the source said. A `\n` in it would end the `Subject:` header and turn the
    rest of the title into headers of its own — the SMTP header injection primitive. The
    fold removes every newline, because a newline *is* a run of whitespace.

    **`None` stays `None`, and a title that folds to nothing becomes `None` too.** The
    caller substitutes `MISSING_TITLE` afterwards; doing it here would hide the
    difference between "no title" and "a title of three spaces" — which is the
    difference the caller must not paper over.

    **Both renderings fold the same way.** The subject and the body quote the same
    event, and if one of them folded and the other did not, the mail would say one thing
    in its subject line and another in its body. The fold lives here so there is one
    answer for both.
    """
    if title is None:
        return None
    folded = " ".join(title.split())
    return folded or None


def moved_venue(*, before: dict, after: dict) -> bool:
    """Whether a change moved the event's venue.

    **The fingerprint is the test, and the fingerprint is enough.** `venue_fingerprint` is
    what `LIFECYCLE_FACTS` holds — a hash of the venue's identity — so a change whose
    before and after fingerprints differ moved the venue. A change that did not touch the
    venue records no fingerprint at all, and the two reads are equal.

    **The fingerprints are compared, not the venues.** The old venue's *name* is not
    recoverable from a hash — that is the limitation `EventFacts.venue_id`'s own comment
    records — so the subject can name only the **new** place, and the new place's name
    comes from the catalog at render time.

    **A change that records no fingerprint on either side has not moved the venue.** That
    is the ordinary case for a title edit, and it is why the two reads are compared rather
    than the after's presence being tested: a change that *recorded* a fingerprint but did
    not change it is not a move either.
    """
    return before.get("venue_fingerprint") != after.get("venue_fingerprint")


def is_notified(change_kind: str, *, before: dict | None = None, after: dict | None = None) -> bool:
    """Whether a change of this kind — with these facts — raises a notice at all.

    **`detail_changed` notifies only when it moved the venue.** See the module docstring for
    the reasoning, and for why the PRD's "moved to [new location]" subject depends on it.

    **`delisted` and `relisted` never notify** — see `UNNOTIFIED_KINDS` for why silence is
    the only answer that states nothing untrue. Checked first, so an editorial reject can
    never consume the day's notice cap on its way to being refused.

    **Every other kind notifies**, whatever its facts. A cancellation is a cancellation
    whether the change also moved the date; the kinds are not refined the way
    `detail_changed` is.
    """
    if change_kind in UNNOTIFIED_KINDS:
        return False
    if change_kind != ChangeKind.DETAIL_CHANGED.value:
        return True
    return moved_venue(before=before or {}, after=after or {})


def subject_template(change_kind: str) -> str:
    """The subject template for a kind.

    **Raises `KeyError` for a kind with no subject**, and that is deliberate. A kind
    `domain.lifecycle` gained without this module learning it must not produce a generic
    subject — FR-54 fixes the copy, and a wrong subject is worse than no email. The
    renderer turns the error into a cancelled send.
    """
    try:
        return NOTICE_SUBJECTS[change_kind]
    except KeyError:
        raise KeyError(f"no notice subject for change kind {change_kind!r}") from None


def notice_subject(
    change_kind: str,
    *,
    title: str,
    when: str | None = None,
    where: str | None = None,
) -> str:
    """The subject line for one change kind.

    **`{when}` and `{where}` are optional, and their absence degrades the sentence rather
    than breaking it.** The catalog may not hold the venue (the event was dropped, or the
    change carried no venue), and a subject that cannot be built is worse than one that says
    less. So:

    - a `time_moved` with no new date → *"…was moved to a new time."* — ours, and honest.
    - a venue move with no new venue → *"…moved to a new location."* — ours, and honest.

    **The title is the caller's to fold — and the fold is `fold_title`, right here.**
    This function does not sanitise: the caller folds first and passes the folded name
    in, so the subject, the text body and the HTML body cannot disagree about what the
    title is. **The fold lives in this module** so that the subject and the body quote
    the same name — and the caller's job is to call `fold_title`, not to invent a second
    rule.
    """
    template = subject_template(change_kind)
    if "{when}" in template:
        template = template.replace("{when}", when or "a new time")
    if "{where}" in template:
        template = template.replace("{where}", where or "a new location")
    return f"{SUBJECT_PREFIX}{template.format(title=title)}"


def reminder_consequence(change_kind: str) -> str:
    """What the body says about the user's reminders for this kind of change.

    **Derived from `LIFECYCLE_SEND_BEHAVIOUR`** — so the body cannot promise something the
    send machinery did not do — with an explicit override for the kind whose wording needs
    more than its behaviour implies (`reinstated`).
    """
    override = REMINDER_CONSEQUENCE.get(change_kind)
    if override is not None:
        return override
    behaviour = LIFECYCLE_SEND_BEHAVIOUR.get(change_kind)
    if behaviour is None:
        raise KeyError(f"no send behaviour for change kind {change_kind!r}")
    return _BEHAVIOUR_CONSEQUENCE[behaviour]


__all__ = [
    "MISSING_TITLE",
    "NOTICE_SUBJECTS",
    "PRD_SUBJECT_KINDS",
    "REMINDER_CONSEQUENCE",
    "SUBJECT_PREFIX",
    "UNNOTIFIED_KINDS",
    "fold_title",
    "is_notified",
    "moved_venue",
    "notice_subject",
    "reminder_consequence",
    "subject_template",
]
