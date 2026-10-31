"""AD-13: the new paths leak **no** personal information into a sink.

**What AD-13 says.** *"No email address, no city, no event title, no secret of any kind
reaches a log-sink, asserted against the logger adapter's allowlist."*

**Why this file is here now.** AD-13's own test (`tests/adapters/test_logging.py`) proves
the **formatter** redacts — that a field called `title` becomes `[redacted]` and an
email becomes `[email]`. That is the *adapter's* half, and it was already true.

What it does **not** prove is that the **new paths** — the digest composition, the
digest read, the detail read, the detail open, and the saved-events write — do not
hand the formatter something to redact in the first place. A formatter that redacts a
title still means the title was *in the process*, and a title is the user's browsing
history.

So this file runs the **real paths** and looks at what actually reaches the sinks.

**There are two sinks, and the sweep covers both.**

1. **The log sink** — the root logger with the project's `JsonFormatter`. This is
   AD-13's own subject.
2. **The audit sink** — the `PersonalizationAuditEntry` rows the commands write. These
   are the *other* place the new paths put a free-text dict, and they are a sink in
   every sense that matters: `details` is a `JSONField` with no schema and no
   allowlist. A title in an audit row is a title in the database forever.

**The two sinks need different structural checks, and the difference is load-bearing.**
The log sink has an **allowlist** — `ALLOWED_FIELDS` — so the structural check is
"every extra field is allowlisted or `[redacted]`". The audit sink has **no
allowlist**: its `details` dict is whatever the command chose to write. So the audit
sweep's structural check is different — **every key in `details` must be one the
audit sink's own vocabulary allows**, and that vocabulary is stated here rather than
inherited.

**The three sweeps, and why each is a different kind of check.**

1. **No email address.** Recognisable by pattern: an `@` in a captured record is a
   red flag, and the scrubber's own pattern turns one into `[email]`.
2. **No city.** The user's city is personal information, and it is *not* a pattern —
   it is a specific string. So the sweep asserts that the city it put in the database
   does not appear in the sink.
3. **No event title.** The hardest one, because free text is unrecognisable by
   pattern — a title looks like any other sentence. Which is exactly why the
   formatter's rule is *"project loggers never interpolate their args at all"*. So the
   sweep asserts the **title it ingested** does not appear.
"""

import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from adapters.logging.formatter import PROJECT_LOGGER_ROOTS, JsonFormatter
from adapters.logging.redaction import ALLOWED_FIELDS, REDACTED
from apps.personalization.models import (
    Interest,
    PersonalizationAuditEntry,
)
from apps.personalization.services.detail_opens import record_detail_open
from apps.personalization.services.detail_read import read_event_detail
from apps.personalization.services.digest_composition import compose_digest
from apps.personalization.services.digest_read import read_digest
from apps.personalization.services.saved_events import save_event
from shared.actor import Actor
from shared.db import CATALOG, PERSONAL
from tests.ingestion.factories import EventFactory, VenueFactory
from tests.personalization.factories import DigestPreferenceFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

ACTOR = Actor.system("pii_sweep")

NOW = datetime(2026, 11, 4, 16, 0, tzinfo=UTC)

#: The personal information this sweep plants. **Every one of these is a real,
#: recognisable string**, so the sweep's assertions are about *these* values and not
#: about patterns that might not match.
EMAIL = "ada.lovelace@example.test"
CITY = "Reykjavik"
TITLE = "Dinner with Priya at Rosa's"

#: The core fields every log line carries. They are the format's own, and the
#: allowlist is about the **extra** fields — the ones a caller adds.
CORE_KEYS = frozenset({"ts", "level", "logger", "message", "args", "trace_id"})

#: **The audit sink's vocabulary.**
#:
#: The log sink has an allowlist (`ALLOWED_FIELDS`) and the formatter enforces it.
#: The audit sink has **no such mechanism**: `details` is a `JSONField` and whatever a
#: command writes in it is stored verbatim. So the vocabulary has to be stated here,
#: and the check is against it.
#:
#: Every entry is a **key**, not a value. The values are checked separately, by the
#: three sweeps above — because a key can be innocuous and its value free text.
AUDIT_DETAIL_KEYS = frozenset(
    {
        # The composition's own facts: a date, a flag, a count, a timestamp.
        "local_date",
        "is_empty",
        "composition_count",
        "at",
        # The save's own facts: which event, which version, what happened.
        "event_id",
        "event_version",
        "created",
        "conflicts",
        # The detail open's own facts.
        "opened_at",
    }
)


class CapturedSink(logging.Handler):
    """A log sink that keeps the formatted lines.

    **It formats with the project's own formatter**, so the sweep sees the bytes that
    would reach production — not a stub's return value, and not the raw `LogRecord`.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())
        self.lines: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(json.loads(self.formatter.format(record)))

    @property
    def project_lines(self) -> list[dict]:
        """The captured lines from **the project's own loggers**.

        **The filter is on the logger's name, not on the message.** Third-party
        loggers — `factory`, `django`, `celery` — are not the project's code and their
        verbosity is not AD-13's business. The project's loggers are the ones AD-13 is
        about: "no email address, no city, no event title … reaches a log-sink" is a
        statement about *our* code's output.
        """
        return [
            line
            for line in self.lines
            if any(line.get("logger", "").startswith(root) for root in PROJECT_LOGGER_ROOTS)
        ]

    @property
    def raw(self) -> str:
        """Every captured line, as text — for the substring sweeps."""
        return "\n".join(json.dumps(line) for line in self.lines)


@pytest.fixture
def sink() -> CapturedSink:
    """A sink attached to the **root** logger, and **proved to work**.

    **The root, because that is where the project's own handler lives.** AD-13 says
    "one redacting JSON log handler on the root" — so a record that reaches the root
    is a record that reached production. Attaching to a specific logger would let a
    path that logs to a *different* logger escape the sweep.

    **The self-check is the point.** The paths under test log *nothing* — which is
    the correct behaviour, and also the behaviour that would make every sweep here
    pass vacuously. A sweep that cannot fail is exactly what the acceptance criterion
    forbids.

    So the sink proves **it** works before the sweep begins: it emits a record with
    the project's own logger name, carrying a title and an email, and asserts that
    the captured line shows them **redacted**. If the formatter were broken, or the
    sink were miswired, this would fail — and it fails *before* the sweep's silence
    can be mistaken for a pass.

    The calibration line is **cleared** afterwards, so the sweep only sees what the
    paths under test wrote.
    """
    handler = CapturedSink()
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        # The calibration: prove the sink captures and the formatter redacts.
        logger = logging.getLogger("apps.pii_sweep")
        logger.info("calibration", extra={"title": TITLE, "email": EMAIL})
        assert handler.lines, "the sink captured nothing, so the sweep would be vacuous"
        calibration = handler.lines[-1]
        assert calibration.get("title") == REDACTED, (
            f"the formatter did not redact a title: {calibration.get('title')!r}. The "
            "sink is not measuring what it claims to measure."
        )
        assert calibration.get("email") == REDACTED, (
            f"the formatter did not redact an email: {calibration.get('email')!r}. The "
            "sink is not measuring what it claims to measure."
        )
        # Clear the calibration, so the sweep sees only the paths' own output.
        handler.lines.clear()

        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)


@pytest.fixture
def user_with_personal_data():
    """A user whose city, email and saved event carry the personal strings."""
    user_id = uuid4()
    DigestPreferenceFactory(
        user_id=user_id,
        timezone="Atlantic/Reykjavik",
        city=CITY,
        city_source="choice",
    )
    Interest.objects.using(PERSONAL).create(user_id=user_id, chip_key="tech")

    venue = VenueFactory(city=CITY, country_code="IS")
    event = EventFactory(
        title=TITLE,
        venue=venue,
        last_seen_at=NOW,
    )
    return user_id, event


def _exercise_every_new_path(user_id, event) -> None:
    """Run the five new paths, in the order a user would hit them."""
    # 1. The saved-events write.
    save_event(user_id=user_id, event_id=event.id, actor=ACTOR, now=NOW)

    # 2. The digest composition.
    compose_digest(user_id=user_id, actor=ACTOR, now=NOW)

    # 3. The digest read.
    read_digest(user_id=user_id, now=NOW)

    # 4. The detail read.
    read_event_detail(event_id=event.id, user_id=user_id, now=NOW)

    # 5. The detail open.
    record_detail_open(user_id=user_id, event_id=event.id, actor=ACTOR, now=NOW)


def _audit_rows() -> list[PersonalizationAuditEntry]:
    """Every audit row the exercise wrote."""
    return list(PersonalizationAuditEntry.objects.using(PERSONAL).order_by("id"))


# ── The three sweeps ──────────────────────────────────────────────────────────────────


def test_no_email_address_reaches_the_sink(sink, user_with_personal_data):
    """**AD-13's first named case.** An email address is a secret of a kind.

    The check is on the **email pattern** rather than on this test's particular
    address, because the formatter's own scrubber recognises addresses by shape — so
    the sweep is looking for a shape that got through, not for one string that did.
    """
    user_id, event = user_with_personal_data

    _exercise_every_new_path(user_id, event)

    # **No assertion that the paths logged something.** The paths log *nothing*, and
    # that is the correct behaviour — the formatter's rule is "project loggers never
    # interpolate their args", and these paths have nothing to say. The sweep's
    # meaningfulness comes from the sink's own calibration (see the fixture), not
    # from the paths being noisy.

    for line in sink.project_lines:
        for key, value in line.items():
            if key in CORE_KEYS:
                continue
            if isinstance(value, str):
                assert "@" not in value or value == REDACTED or "[email]" in value, (
                    f"the log field {key!r} carries an email address: {value!r}"
                )


def test_the_city_does_not_reach_the_sink(sink, user_with_personal_data):
    """**AD-13's second named case.** The user's city is personal information.

    **The check is on this test's particular city**, because a city is not
    recognisable by shape — "Reykjavik" looks like any other proper noun. So the
    sweep plants a city and then asserts that exact string never appears.
    """
    user_id, event = user_with_personal_data

    _exercise_every_new_path(user_id, event)

    # **No assertion that the paths logged something.** The paths log *nothing*, and
    # that is the correct behaviour — the formatter's rule is "project loggers never
    # interpolate their args", and these paths have nothing to say. The sweep's
    # meaningfulness comes from the sink's own calibration (see the fixture), not
    # from the paths being noisy.
    assert CITY not in sink.raw, (
        f"the user's city {CITY!r} reached the log sink. AD-13: no city reaches a "
        "log-sink."
    )

    # And the audit sink, which is the other place a city could go.
    for row in _audit_rows():
        assert CITY not in json.dumps(row.details), (
            f"the audit row {row.action!r} carries the user's city {CITY!r}. AD-13: no "
            "city reaches a sink."
        )


def test_the_event_title_does_not_reach_the_sink(sink, user_with_personal_data):
    """**AD-13's third named case, and the hardest one.**

    A title is free text. It is unrecognisable by pattern, so no pattern-based sweep
    could ever prove its absence — which is exactly why the formatter's rule is
    *"project loggers never interpolate their args at all"*.

    So the sweep plants a title and asserts that exact string never appears. It is
    the only kind of check that can speak about free text at all.
    """
    user_id, event = user_with_personal_data

    _exercise_every_new_path(user_id, event)

    # **No assertion that the paths logged something.** The paths log *nothing*, and
    # that is the correct behaviour — the formatter's rule is "project loggers never
    # interpolate their args", and these paths have nothing to say. The sweep's
    # meaningfulness comes from the sink's own calibration (see the fixture), not
    # from the paths being noisy.
    assert TITLE not in sink.raw, (
        f"the event title {TITLE!r} reached the log sink. AD-13: no event title reaches "
        "a log-sink."
    )

    # And the audit sink. A title in an audit row is a title in the database forever.
    for row in _audit_rows():
        assert TITLE not in json.dumps(row.details), (
            f"the audit row {row.action!r} carries the event title {TITLE!r}. AD-13: no "
            "event title reaches a sink."
        )


# ── The structural checks ─────────────────────────────────────────────────────────────


def test_every_extra_log_field_is_allowlisted_or_redacted(sink, user_with_personal_data):
    """**"Asserted against the logger adapter's allowlist" — the structural form.**

    This is the check that does not depend on knowing which particular PII to look
    for. Every field on a captured line is either:

    - one of the format's **core** fields (`ts`, `level`, `logger`, `message`, `args`,
      `trace_id`), which the format itself puts there;
    - in **`ALLOWED_FIELDS`** — ids, counts, durations and slugs, never free text; or
    - the literal **`[redacted]`**.

    A field that is none of those is free text that reached the sink, whatever it
    happens to be.
    """
    user_id, event = user_with_personal_data

    _exercise_every_new_path(user_id, event)

    # **No assertion that the paths logged something.** The paths log *nothing*, and
    # that is the correct behaviour — the formatter's rule is "project loggers never
    # interpolate their args", and these paths have nothing to say. The sweep's
    # meaningfulness comes from the sink's own calibration (see the fixture), not
    # from the paths being noisy.

    offenders: list[str] = []
    for line in sink.project_lines:
        for key, value in line.items():
            if key in CORE_KEYS:
                continue
            if key in ALLOWED_FIELDS:
                continue
            if value == REDACTED:
                continue
            offenders.append(f"{key}={value!r}")

    assert not offenders, (
        "these log fields are neither core, nor allowlisted, nor redacted: "
        + ", ".join(offenders)
        + ". AD-13: every field is asserted against the logger adapter's allowlist."
    )


def test_every_audit_detail_key_is_in_the_audits_vocabulary(user_with_personal_data):
    """**The audit sink's structural check.**

    The log sink's structural check is the allowlist. The audit sink has no
    allowlist, so **this file states the vocabulary** and the check is against it.

    **Why the key is what matters.** A key can be innocuous and its value free text,
    so the key check alone is not the whole story — the three sweeps above cover the
    values. But the key check is what stops the vocabulary from growing by accident:
    a new key is a new thing that can be written into a permanent row, and it should
    be a decision rather than a side effect.
    """
    user_id, event = user_with_personal_data

    _exercise_every_new_path(user_id, event)

    rows = _audit_rows()
    assert rows, "the paths under test wrote no audit rows, so the sweep proved nothing"

    offenders: list[str] = []
    for row in rows:
        for key in row.details:
            if key not in AUDIT_DETAIL_KEYS:
                offenders.append(f"{row.action}: {key}")

    assert not offenders, (
        "these audit detail keys are not in the audit sink's vocabulary: "
        + ", ".join(offenders)
        + ". The log sink has an allowlist; the audit sink has none, so its vocabulary "
        "is stated here. Add the key here first."
    )


def test_the_allowlist_itself_holds_no_free_text():
    """**The allowlist's own shape.** It is ids, counts, durations and slugs.

    This is a check on the *allowlist*, not on a log line — and it is here because
    the allowlist is the thing every other check leans on. A free-text entry would
    make every allowlist check above vacuous: the field would be "allowlisted", so
    the sweep would pass, and the free text would be in the sink.

    **How "free text" is judged.** The entries are all identifiers, counts and
    slugs. A slug is lowercase words joined by underscores. So the check is that
    every entry is a lowercase snake_case name — no spaces, no capitals, and no
    sentence.
    """
    for field in sorted(ALLOWED_FIELDS):
        assert "_" in field or field.isalpha(), (
            f"the allowlist entry {field!r} is not an identifier, a count or a slug. "
            "AD-13: the allowlist holds ids, counts, durations and slugs — never free text."
        )
        assert field == field.lower(), (
            f"the allowlist entry {field!r} is not lowercase. A capitalised entry is "
            "where a person's name would go."
        )
        assert " " not in field, (
            f"the allowlist entry {field!r} contains a space. Free text has spaces."
        )
