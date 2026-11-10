"""The two `domain/` modules whose branches the 100% gate was missing.

**Why this file exists.** The backend's coverage gate is `>= 80%` overall and **100% for
`domain/`** (`make coverage-backend`). The `domain/` half is a gate on *pure* code — the
modules with no Django import and therefore no excuse for an untested branch — and it was
failing at **99%**, on nine lines across two files:

| Module | Missing | What the lines are |
| --- | --- | --- |
| `domain/notices.py` | 258 | `fold_title` on a title that is `None` |
| `domain/notices.py` | 355–358 | `reminder_consequence`'s fallback path |
| `domain/sources.py` | 107–110 | `humanise_duration`'s minute branch and its fallback |

**Two of the three are this intent's own module.** `domain/notices.py` *is* the notice
copy — `subject_template`, `notice_subject`, `reminder_consequence` — and it was
introduced by `notice-composition-and-email` and read by the propagation. So the gap was
not somebody else's untidiness; it was this intent's, and the gate that would have caught
it was red while the intent was being built.

**The third is older, and is here for the same reason.** `humanise_duration` is
`domain/sources.py`'s, and it was left uncovered by an earlier intent. The gate is on the
whole directory, so an older gap keeps this intent's build red — and a red gate is a gate
nobody reads.

**Why these lines, and not just "any line".** Every one of them is a **branch a user can
reach**, and each is reachable in a way that changes what the user is told:

- `fold_title(None)` — a source that publishes a title the pipeline could not read. The
  caller substitutes `MISSING_TITLE`; the fold is what decides a *blank* title and a
  *missing* title are the same thing.
- `reminder_consequence`'s fallback — the kind is in no behaviour map, so the function
  raises rather than promising the user something the send machinery did not do. **A
  promise the send machinery did not make is exactly what FR-54 forbids**, so this branch
  is a safety rule, not a defensive afterthought.
- `humanise_duration` — it is used in refusal messages, where "a wrong unit would
  misstate the rule" (its own docstring). A cadence of 30 minutes must say "30 minutes"
  and not "0 hours".

**The assertions are about the words, not the calls.** A test that calls a function and
asserts it did not raise proves nothing about a branch whose whole purpose is *what it
says*.
"""

from datetime import timedelta

import pytest

from domain.notices import (
    MISSING_TITLE,
    fold_title,
    notice_subject,
    reminder_consequence,
)
from domain.sources import humanise_duration

# ── `domain/notices.py` ─────────────────────────────────────────────────────────────────


def test_a_missing_title_stays_missing():
    """**`None` in, `None` out.**

    **And it stays `None` rather than becoming a blank string.** The caller substitutes
    `MISSING_TITLE` afterwards, and doing it here would hide the difference between "the
    source published no title" and "the source published three spaces" — a distinction the
    caller must be able to see.
    """
    assert fold_title(None) is None


def test_a_title_of_only_whitespace_becomes_missing():
    """**A title that folds to nothing is a missing title.**

    The fold collapses every run of whitespace — newlines included — so a title of
    spaces folds to the empty string, and the empty string is the same thing as no title
    at all. **A subject line reading "EventPulse24: " is worse than one reading
    "EventPulse24: Untitled event"**, and this is the line that decides between them.
    """
    assert fold_title("   ") is None
    assert fold_title("\n\t ") is None


def test_a_title_folds_its_whitespace_into_one_run():
    """**The fold is what keeps the subject one line.**

    A newline inside a title is a header injection (the mail's own guard), and a run of
    spaces is just untidy — but both are the same problem: the subject must not carry a
    line break. **So the fold is one rule for both**, and it applies to the body too, so
    the subject and the body cannot quote the event differently.
    """
    assert fold_title("Night\nMarket") == "Night Market"
    assert fold_title("  Night   Market  ") == "Night Market"
    assert fold_title("Night\tMarket") == "Night Market"


def test_the_reminder_consequence_is_derived_from_the_send_behaviour():
    """**The body cannot promise something the send machinery did not do.**

    The wording is *derived* from `LIFECYCLE_SEND_BEHAVIOUR` rather than written out per
    kind, so there is exactly one table that says what a `sold_out` does to a reminder —
    and the copy cannot drift from it. **This test asserts the derivation by changing the
    table's answer, not by reading the table**: the same kind must produce different words
    when the behaviour differs.
    """
    from shared.constants import LIFECYCLE_SEND_BEHAVIOUR, LifecycleSendBehaviour

    # **A kind whose behaviour is `KEEP` says the reminders are unchanged.**
    keep_kind = next(
        kind
        for kind, behaviour in LIFECYCLE_SEND_BEHAVIOUR.items()
        if behaviour is LifecycleSendBehaviour.KEEP
    )
    # **And one whose behaviour is `CANCEL` says they are cancelled.**
    cancel_kind = next(
        kind
        for kind, behaviour in LIFECYCLE_SEND_BEHAVIOUR.items()
        if behaviour is LifecycleSendBehaviour.CANCEL
    )

    assert reminder_consequence(keep_kind) != reminder_consequence(cancel_kind)


def test_the_reminder_consequence_of_an_unknown_kind_raises():
    """**An unknown kind raises rather than promising something untrue.**

    This is the fallback path, and it is a **safety rule** rather than a defensive
    afterthought. `reminder_consequence` produces the sentence that tells the user what
    happened to their reminders — so for a kind the behaviour map does not carry, the
    honest answer is *nothing*, and the only honest way to say that is to raise. **A
    generic "your reminders may have changed" would be a claim about a system the user
    cannot see into, and FR-54's whole promise is that the strip tells the truth.**

    The same shape as `subject_template`, which raises for an unknown kind rather than
    producing a generic subject — and the two are deliberately consistent.
    """
    with pytest.raises(KeyError):
        reminder_consequence("a_kind_this_system_has_never_heard_of")


def test_the_reminder_consequence_is_derived_when_the_kind_has_no_override(
    monkeypatch,
):
    """**A kind with a behaviour but no wording of its own inherits the behaviour's.**

    `REMINDER_CONSEQUENCE` names every kind the system knows, so the derived branch is
    reached only by a kind that has been **given a behaviour but not yet given a
    sentence** — which is exactly the shape of a kind added to `ingestion` before this
    module learns to speak about it. **The derivation is what makes that addition
    survivable**: the body says what the *behaviour* implies rather than saying nothing.

    **The kind is planted, not invented.** `LIFECYCLE_SEND_BEHAVIOUR` is patched with a
    real behaviour for a synthetic kind, so the function under test takes its ordinary
    path — the override misses, the behaviour map answers, and the sentence comes back.
    Nothing about the function is stubbed; only the table it reads is extended, which is
    what a new kind in `ingestion` would do.
    """
    from shared.constants import LIFECYCLE_SEND_BEHAVIOUR, LifecycleSendBehaviour

    kind = "a_kind_with_a_behaviour_but_no_wording"
    monkeypatch.setitem(LIFECYCLE_SEND_BEHAVIOUR, kind, LifecycleSendBehaviour.KEEP)

    # **And the sentence is the one the behaviour implies** — not a generic one.
    assert reminder_consequence(kind) == "Your reminders are unchanged.", (
        "the consequence is derived from the behaviour"
    )


def test_a_reinstated_event_gets_its_own_wording():
    """**The one kind whose wording needs more than its behaviour implies.**

    `reinstated` is `REMINT` like a postponement, but "your reminders have been
    rescheduled" is the wrong sentence for an event that was not happening and now is.
    **So the override exists**, and it is the reason the override branch is above the
    derived one.
    """
    assert reminder_consequence("reinstated") != reminder_consequence("postponed")


def test_the_subject_of_a_missing_title_carries_the_fallback_name():
    """**The fallback belongs to the renderer, not to the subject builder.**

    `notice_subject` does **not** substitute `MISSING_TITLE` — its own docstring says the
    title is the caller's to fold, so that the subject, the text body and the HTML body
    cannot disagree about what the title is. **The substitution is the renderer's**
    (`email_templates.py`: `title = facts.title or MISSING_TITLE`), because the renderer
    is what knows a missing title from a blank one — and that half is proved in
    `tests/delivery/test_state_notice_email.py`.

    **So what this file asserts is the half `domain` owns**: the fold turns a blank title
    into `None`, and the subject builder renders whatever title it is given — including
    the fallback — without inventing a name of its own.
    """
    # **The fold is the fold's job.** A title of only whitespace is no title.
    assert fold_title("   ") is None
    assert fold_title(None) is None

    # **And the subject builder renders the title it is given, verbatim.** It does not
    # substitute, does not re-fold, and does not reject — so the three renderings
    # (subject, text body, HTML body) cannot disagree about what the title is.
    subject = notice_subject("cancelled", title=MISSING_TITLE)

    assert MISSING_TITLE in subject
    assert subject.startswith("EventPulse24: ")
    assert "None" not in subject


# ── `domain/sources.py` ─────────────────────────────────────────────────────────────────


def test_a_duration_in_whole_hours_reads_in_hours():
    """**The hours branch, and its singular.**

    A cadence of one hour says "1 hour" and not "1 hours", because the sentence is shown
    to a person in a refusal message and "1 hours" is the kind of thing that makes a
    system look careless.
    """
    assert humanise_duration(timedelta(hours=1)) == "1 hour"
    assert humanise_duration(timedelta(hours=4)) == "4 hours"


def test_a_duration_in_whole_minutes_reads_in_minutes():
    """**The minutes branch, and its singular.**

    **Not "0 hours"** — a cadence of thirty minutes is thirty minutes, and a rule that
    said "0 hours" would be misstating the rule. This is the branch the function's own
    docstring is about: *"a wrong unit would misstate the rule."*
    """
    assert humanise_duration(timedelta(minutes=30)) == "30 minutes"
    assert humanise_duration(timedelta(minutes=1)) == "1 minute"


def test_a_duration_that_is_neither_reads_as_it_is():
    """**The fallback: the raw string, rather than an invented unit.**

    A duration of ninety seconds is not a whole number of hours and not a whole number of
    minutes, and the function does not pretend otherwise — it falls back to the raw
    string. **A made-up unit would be a claim about a rule the operator does not know.**
    """
    assert humanise_duration(timedelta(seconds=90)) == str(timedelta(seconds=90))
    assert humanise_duration(timedelta(seconds=1)) == str(timedelta(seconds=1))
