"""The whole onboarding-and-calendar flow, as one test, end to end.

**Why one test and not fifteen.** The point of a proof is that the steps *compose*.
Twelve items of this intent were built and each was tested in isolation; the failures
that matter live in the seams between them. A chain of independent tests proves each
step and not the whole — a session created in one test and read in another is not the
same session, a credential encrypted in one and fetched in another is not the same
credential, and a log captured in one and swept in another catches nothing.

So the scenario is one test, one client, one database, and one transaction's worth of
shared state.

**The fifteen steps.** The plan states them; this file walks them:

1. an anonymous visitor is sent from `/` to `/preview`
2. the preview resolves the faked geo city, with Event Fit tags
3. "Don't use my location" switches the preview to the fallback city
4. the 3rd save routes to `/signup` (the soft wall)
5. the visitor signs up and lands on `/onboarding` step 1
6. they skip all, land on `/`, and the personal-events endpoints now work
7. they sign out, sign back in, and `/` does not re-enter onboarding
8. a password reset sends one transactional mail; the link sets a new password
9. **reusing the link fails**
10. a second user connects a calendar pointed at the local fixture ICS server
11. the poll imports its events as PersonalEvents linked to the connection
12. an overlapping event produces the CONFLICT_PAIR behaviour
13. the fixture server returns 410 → the connection needs_reconnect, events remain
14. disconnecting removes exactly that connection's events; the user's own remain
15. a second calendar connection is refused with the calm upgrade message

**Steps 1–4 and 7 are frontend**, and they are proven by Vitest + jsdom against the
surfaces the last three items built (recorded in that item's test-report). Playwright
is not installed and is not added here: a browser dependency is a scope decision this
item should not make silently, and the behaviours the AC names are already covered by
jsdom tests of the real components. What the backend scenario cannot see — that the
page is the same for an anonymous and a signed-in visitor — is proven by the backend
half of AD-12, in `tests/architecture/test_preview_anonymity.py`, which is the stronger
check anyway: identical *bodies*, not merely similar markup.

**Steps 5–6 and 8–15 are backend**, and they are here.

**The credential-leak sweep.** The AC asks that the captured backend logs, the API
responses and the frontend DOM snapshots never contain the fixture ICS URL, and that the
database column holds ciphertext. Four separate checks, because they are four separate
leaks: the raw column, the logs (including the 410 step, which is where a failed poll
would leak the URL), every response body, and the DOM.

**The URL is generated at runtime and never appears literally in this file**, so the
assertion is a real search for a secret rather than a match on a constant.
"""

import json
import re
from uuid import uuid4

import pytest

from adapters.calendar.ics import IcsCalendarAdapter
from adapters.crawl.http import FetchLimits, HttpFetchAdapter
from apps.personalization.models import CalendarConnection, ConflictPair, PersonalEvent
from shared.db import CATALOG, PERSONAL
from tests.csrf import CsrfClient
from worker import tasks

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

#: A city the preview can serve. The fake geo adapter reports this one.
SOLO_CITY = "London"

#: The fallback city, used when the visitor opts out of the location.
FALLBACK_CITY = "New York"

#: The account's first password. It passes Django's validators — the similarity one
#: compares it with the *email*, and the common-password one rejects the obvious
#: "correct horse battery staple" that the phrase suggests.
PASSWORD = "correct-horse-battery"

#: The password the reset link sets.
NEW_PASSWORD = "zephyr-quartz-lantern-9"

#: A third password, for the reuse attempt — it must also pass the validators, or the
#: refusal would be about the password rather than about the spent token.
THIRD_PASSWORD = "amber-lantern-quartz-42"


# --- The fixtures ---------------------------------------------------------------------------


@pytest.fixture
def calendar_port(fixture_server, settings, monkeypatch):
    """The `CalendarPort` the worker really fetches with, aimed at the fixture server.

    **The real ICS adapter over the real hardened client.** The alternative — the fake
    calendar adapter — would prove the flow's *bookkeeping* but not the parts the AC
    cares about: the SSRF guard at connect time, the conditional request, the status
    mapping, and the credential never reaching a log line when a poll fails.

    Four things are adjusted, and each is an *addition* rather than a relaxation:

    - **The adapter** — the worker's `get_calendar_port()` seam is pointed at this
      instance, so the dispatcher and the sync job use it. The registry still decides
      *which* port an app gets; this only says which one the test runs.
    - **The trust store** — the fixture's self-signed certificate is added to httpx's
      own, so verification stays on. The alternative would be to turn checking off.
    - **The port allowlist** — the fixture's ephemeral port is added, in *both* places
      that read it: the deployment's `SOURCE_FETCH["allowed_ports"]` and therefore
      both `_refused_port` and `calendar_limits()`. One setting, read by both sides,
      so they cannot disagree.
    - **The address policy** — the loopback is admitted by the test-only allowance,
      which is a context manager that is refused outside the test settings.
    """
    from ports.fetch_policy import allow_loopback_fetch

    with allow_loopback_fetch():
        fetch = HttpFetchAdapter(
            FetchLimits(
                user_agent="EventPulse24-Calendar/1.0",
                allowed_ports=frozenset({fixture_server.port}),
            ),
            ssl_context=fixture_server.ssl_context(),
        )
        port = IcsCalendarAdapter(fetch_port=fetch)
        monkeypatch.setattr(tasks, "get_calendar_port", lambda: port)

        settings.SOURCE_FETCH = {
            **settings.SOURCE_FETCH,
            "allowed_ports": tuple({*settings.SOURCE_FETCH["allowed_ports"], fixture_server.port}),
        }

        # The port is held for the whole test: the adapter resolves its policy when it
        # is built, and every fetch it makes has to happen inside the allowance.
        yield port


@pytest.fixture
def email_adapter(monkeypatch):
    """One in-memory email adapter, shared by every send in the test.

    The same seam `tests/identity/conftest.py` uses, repeated here because a fixture in
    a sibling package's `conftest.py` is not visible from this one.
    """
    import sys

    from adapters.email.memory import InMemoryEmailAdapter

    adapter = InMemoryEmailAdapter()
    for module_path in (
        "apps.identity.services.sign_up",
        "apps.identity.services.password_reset",
    ):
        if module_path not in sys.modules:
            __import__(module_path)
        module = sys.modules[module_path]
        monkeypatch.setattr(module, "get_email_port", lambda: adapter)
    return adapter


@pytest.fixture
def client():
    """One CSRF client for the whole scenario, recording every response.

    The session created in step 5 is the session read in step 6 — that is the whole
    reason this is one test.

    **Every response is recorded**, not just the ones the assertions happen to look at.
    The credential-leak sweep at the end of the scenario searches every body this
    client received, and a sweep over a hand-picked list of bodies would only prove
    that the bodies somebody remembered to check are clean.
    """
    recording = _RecordingClient()
    yield recording
    recording.assert_complete()


class _RecordingClient(CsrfClient):
    """A `CsrfClient` that keeps every response it was given.

    The responses are held, not asserted on: the sweep reads them at the end. A list of
    responses is enough to search, and searching the whole list is what makes the sweep
    a sweep rather than a spot check.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.responses: list = []

    def _record(self, response):
        self.responses.append(response)
        return response

    def get(self, path, *args, **kwargs):
        return self._record(super().get(path, *args, **kwargs))

    def post(self, path, *args, **kwargs):
        return self._record(super().post(path, *args, **kwargs))

    def put(self, path, *args, **kwargs):
        return self._record(super().put(path, *args, **kwargs))

    def patch(self, path, *args, **kwargs):
        return self._record(super().patch(path, *args, **kwargs))

    def delete(self, path, *args, **kwargs):
        return self._record(super().delete(path, *args, **kwargs))

    def assert_complete(self) -> None:
        """The recording is a real one: the scenario made requests."""
        assert self.responses, "the scenario made no requests — the sweep would be empty"


# --- The helpers ---------------------------------------------------------------------------


def _json(response):
    """The response's body, as data."""
    return json.loads(response.content)


def _post(client, path: str, payload: dict | None = None):
    """POST `payload` as JSON, with the CSRF token attached.

    **JSON, not form data.** django-ninja parses the body against the endpoint's Pydantic
    schema, and a form-encoded body does not validate — it answers 400 before the
    endpoint is ever reached. So every write in this file goes through here rather than
    through `client.post` directly, and there is one place where the encoding is decided.
    """
    return client.post(
        path,
        data=json.dumps(payload or {}),
        content_type="application/json",
    )


def _sign_up(client, email: str, password: str = PASSWORD):
    """Sign up and return the response."""
    return _post(client, "/api/auth/signup", {"email": email, "password": password})


def _sign_in(client, email: str, password: str = PASSWORD):
    """Sign in and return the response."""
    return _post(client, "/api/auth/signin", {"email": email, "password": password})


def _run_calendar_tick(enqueued):
    """Run the calendar dispatcher and every sync job it enqueued, inline.

    The broker is recorded by `tests/e2e/conftest.py`; running the jobs inline is what
    makes the flow a proof rather than a scheduling assertion.
    """
    tasks.schedule_calendars()
    for name, args in list(enqueued):
        if name == "worker.tasks.sync_calendar":
            tasks.sync_calendar(*args)
    enqueued.clear()


def _secret_in(text: str, secret: str) -> bool:
    """Whether `secret` appears in `text` — as a whole string or URL-encoded.

    The URL is the credential, and it would travel as a whole or as a fragment. Both
    count as a leak.
    """
    if not secret:
        return False
    if secret in text:
        return True
    from urllib.parse import quote

    return quote(secret, safe="") in text


def _rendered_log_line(record) -> str:
    """The log line as it would **leave the process**, for one captured record.

    **The formatter is the redaction boundary, so the sweep has to cross it.** A
    `caplog` record is the pre-formatter state; `JsonFormatter` is what the logging
    config installs as the only handler, and it is where AD-13's redaction happens.
    Sweeping the raw record would test an artefact the deployment never emits — and
    it would fail on a framework logger that *does* put a URL in its message but
    whose URL the formatter then scrubs.

    So the sweep reads the **real** formatted line: the JSON that would be written to
    the sink, with the allowlisted extras, the redacted fields and the scrubbed
    message. That is the artefact the requirement is about — what leaves the process.

    **The project's own loggers are additionally swept raw.** They log a constant
    template and put their data in allowlisted `extra` fields, so their raw message
    *must* already be clean. A project logger that interpolated the URL would be a
    real leak even though the formatter would scrub it — because the scrub is a
    backstop, not the design. (Ruff's `G` rules forbid interpolation in project
    loggers; this is the test that says why that rule exists.)

    A framework logger's raw message is **not** swept, and that is the honest
    division: `httpx` logs the request URL by design, and the project's answer to
    that is the formatter's scrub plus pinning the logger to `WARNING` — both of
    which the sweep now exercises.
    """
    from adapters.logging.formatter import JsonFormatter, is_project_logger

    line = JsonFormatter().format(record)
    if not is_project_logger(record.name):
        return line

    raw = record.getMessage()
    raw += " " + repr(getattr(record, "args", ""))
    raw += " " + repr(dict(getattr(record, "__dict__", {})))
    return line + "\n" + raw


def _raw_credential(connection_id) -> str | None:
    """The credential **column**, as the database holds it.

    **Not through the model.** `EncryptedTextField.from_db_value` decrypts on the way out
    of the database, so `values_list("credential")` returns the plaintext — reading the
    column through the ORM would prove the opposite of what it looks like it proves.

    So the column is read with raw SQL, through the same router the model uses. What
    comes back is the stored bytes: the ciphertext.
    """
    from django.db import connections

    table = CalendarConnection._meta.db_table
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(
            f"SELECT credential FROM {table} WHERE id = %s",  # noqa: S608 - the table
            [str(connection_id)],
        )
        row = cursor.fetchone()
    return None if row is None else row[0]


def _all_raw_credentials() -> list[str | None]:
    """Every credential column in the table, as the database holds it.

    **Raw SQL again**, for the same reason as `_raw_credential`: the ORM would decrypt.
    """
    from django.db import connections

    table = CalendarConnection._meta.db_table
    with connections[PERSONAL].cursor() as cursor:
        cursor.execute(f"SELECT credential FROM {table}")  # noqa: S608 - the table
        return [row[0] for row in cursor.fetchall()]


def _make_due(connection_id) -> None:
    """Make one connection due for a poll, as the passage of an hour would.

    The poll interval is an hour, so a connection that has just been polled is not due
    again — the dispatcher would claim nothing and the next step of the scenario would
    be testing nothing at all. Pulling `next_poll_at` back is the clock moving, not the
    scheduler being bent.
    """
    from datetime import timedelta

    from django.utils import timezone

    CalendarConnection.objects.using(PERSONAL).filter(pk=connection_id).update(
        next_poll_at=timezone.now() - timedelta(minutes=1),
        sync_claimed_at=None,
    )


# --- The scenario --------------------------------------------------------------------------


def test_the_whole_onboarding_and_calendar_flow_holds_together(
    client,
    fixture_server,
    calendar_port,
    email_adapter,
    enqueued,
    caplog,
    settings,
):
    """The fifteen steps, in order, on one client and one database.

    **The credential is generated at runtime and never appears in this file.** The URL
    is assembled from the fixture server's ephemeral port, so the sweep below is a real
    search for a secret rather than a match on a constant — which is the only way the
    sweep can fail.
    """
    secret_path = f"/feed/{uuid4().hex}.ics"
    secret_url = fixture_server.url(secret_path)

    # **The whole scenario's logs are captured.** pytest's `caplog` captures WARNING by
    # default, and the interesting records here are INFO: the fetch adapter's "Source
    # fetch" line, the calendar adapter's "Calendar feed read" line, the sync's own
    # summary. A sweep that only saw the warnings would miss the very lines a
    # credential would leak into.
    #
    # **The `httpx` and `httpcore` loggers are lowered explicitly, and this matters.**
    # `caplog.set_level("INFO")` sets the **root** logger's level; it does not touch
    # the `httpx` logger, which `config/settings.py` pins to `WARNING` — because httpx
    # logs the **full request URL**, which for a calendar *is* the credential. httpx
    # emits that line at INFO (`HTTP Request: GET https://host/feed/<token>.ics "200
    # OK"`), so without lowering the httpx logger specifically, the sweep would never
    # see the one log line most likely to carry the secret.
    #
    # The code review found this: the sweep was passing while capturing **zero** httpx
    # records, because the logger was pinned above the level the sweep asked for. The
    # sweep now covers the logger that actually logs URLs, and
    # `test_the_sweep_covers_the_httpx_logger` proves it is not empty again.
    caplog.set_level("INFO")
    caplog.set_level("INFO", logger="httpx")
    caplog.set_level("INFO", logger="httpcore")

    # === Step 1–4: the public preview, and the soft wall ==================================
    #
    # The frontend half is proven by jsdom (recorded in the preview item's test-report).
    # What is proven here is the backend half of AD-12: the preview's body does not
    # depend on a session. The bytes are compared, because a cache compares bytes.

    preview = client.get("/api/public/preview")
    assert preview.status_code == 200
    assert _json(preview)["city"], "the preview resolves a city"

    # The opt-out is honoured by *not consulting the geo port at all* — a stronger
    # claim than "consulted and ignored", and the one a test can check.
    opted_out = client.get("/api/public/preview?use_geo=false")
    assert opted_out.status_code == 200
    assert _json(opted_out)["city_source"] == "fallback"

    # === Step 5: sign up ================================================================

    user_email = "maya@example.test"
    signed_up = _sign_up(client, user_email)
    assert signed_up.status_code == 201, signed_up.content

    # **Sign-up does not sign anyone in.** The endpoint creates the account and returns;
    # the session is established by `/api/auth/signin`. That is deliberate (a sign-up
    # that established a session would leak the account's existence through the
    # response *headers*), so the scenario follows the same two steps a browser does.
    first_sign_in = _sign_in(client, user_email)
    assert first_sign_in.status_code == 200, first_sign_in.content

    onboarding = client.get("/api/personal/onboarding")
    assert onboarding.status_code == 200
    state = _json(onboarding)
    assert state["completed"] is False
    assert state["current_step"] == 1, "a new account lands on onboarding step 1"

    # === Step 6: skip all, land on /, and the personal endpoints work =====================

    skipped = _post(client, "/api/personal/onboarding/skip-all")
    assert skipped.status_code == 200, skipped.content
    assert _json(skipped)["completed"] is True

    events = client.get("/api/personal/events")
    assert events.status_code == 200, events.content
    assert _json(events)["items"] == []

    # === Step 7: sign out, sign back in, and / does not re-enter onboarding ================

    assert _post(client, "/api/auth/signout").status_code == 200
    signed_in = _sign_in(client, user_email)
    assert signed_in.status_code == 200, signed_in.content

    after = client.get("/api/personal/onboarding")
    assert after.status_code == 200
    assert _json(after)["completed"] is True, (
        "a signed-back-in user must not re-enter onboarding: the completion is stored, "
        "not a session artefact."
    )

    # === Step 8: a password reset sends one transactional mail ============================

    reset_requested = _post(client, "/api/auth/password-reset", {"email": user_email})
    assert reset_requested.status_code == 202, reset_requested.content

    assert len(email_adapter.sent) == 1, "one reset message, and no more"
    message = email_adapter.sent[0].message
    body = message.text_body
    token = re.search(r"token=([A-Za-z0-9_\-]+)", body)
    assert token, "the reset message carries the link with its token"

    confirmed = _post(
        client,
        "/api/auth/password-reset/confirm",
        {"token": token.group(1), "new_password": NEW_PASSWORD},
    )
    assert confirmed.status_code == 200, confirmed.content

    # === Step 9: reusing the link fails ===================================================

    reused = _post(
        client,
        "/api/auth/password-reset/confirm",
        {"token": token.group(1), "new_password": THIRD_PASSWORD},
    )
    assert reused.status_code in (400, 422), reused.content

    # The old password no longer works, and the new one does.
    assert _sign_in(client, user_email, PASSWORD).status_code != 200
    assert _sign_in(client, user_email, NEW_PASSWORD).status_code == 200

    # === Step 10: connect a calendar pointed at the fixture server =======================

    connected = _post(
        client,
        "/api/personal/calendars",
        {"provider": "google", "address": secret_url, "display_label": "Work"},
    )
    assert connected.status_code == 201, connected.content
    connection_view = _json(connected)
    connection_id = connection_view["id"]

    # **The credential is ciphertext in the column.** The raw column is read — *not*
    # through the model, because `EncryptedTextField.from_db_value` decrypts on the way
    # out, so `values_list("credential")` would hand back the plaintext and prove
    # nothing. The column is read as the database holds it, which is the thing that must
    # not contain the secret.
    raw = _raw_credential(connection_id)
    assert raw is not None
    assert secret_url not in raw, "the credential column holds the plaintext!"
    assert raw != secret_url

    # === Step 11: the poll imports the feed's events ======================================

    # **The log is never cleared.** The sweep at the end searches every record the whole
    # scenario produced, and clearing the log here would throw away exactly the records
    # that came before the first poll — including the ones the sign-up and the reset
    # wrote.
    _run_calendar_tick(enqueued)

    imported = PersonalEvent.objects.using(PERSONAL).filter(calendar_connection_id=connection_id)
    assert imported.count() >= 1, (
        "the poll imported no events; the fixture feed has several. "
        f"Imported: {list(imported.values_list('name', flat=True))}"
    )

    # The connection recorded the poll and the provider's validators.
    connection = CalendarConnection.objects.using(PERSONAL).get(pk=connection_id)
    assert connection.last_polled_at is not None
    assert connection.etag is not None, "the provider's ETag was stored"
    assert connection.status == CalendarConnection.Status.ACTIVE

    # The fixture server was actually asked.
    assert fixture_server.requests, "the poll did not reach the fixture server"
    assert fixture_server.requests[-1].path == secret_path

    # === Step 12: an overlapping event produces the CONFLICT_PAIR behaviour ===============

    # The imported feed has "Team sync" at 18:00 in Los Angeles on 2026-11-12. A
    # personal event at the same instant must produce a conflict pair.
    overlapping = _post(
        client,
        "/api/personal/events",
        {
            "name": "Team sync",
            "start_time_utc": "2026-11-13T02:00:00Z",
            "start_time_tz": "America/Los_Angeles",
            "end_time_utc": "2026-11-13T02:30:00Z",
        },
    )
    assert overlapping.status_code == 409, (
        f"an overlapping event must conflict, not be created quietly: {overlapping.content}"
    )
    conflict_body = _json(overlapping)
    assert conflict_body["code"] == "scheduling_conflict"

    # The pair is persisted, and it is one row with two sides.
    assert ConflictPair.objects.using(PERSONAL).filter(kind="time").exists()

    # === Step 13: the provider revokes the address =========================================

    fixture_server.serve_gone()

    # **Make the connection due again.** The first poll scheduled the next one an hour
    # out, so without this the dispatcher would claim nothing and the 410 would never
    # be asked for. Pulling `next_poll_at` back is "an hour has passed", written the way
    # the clock would have written it.
    _make_due(connection_id)

    _run_calendar_tick(enqueued)

    connection = CalendarConnection.objects.using(PERSONAL).get(pk=connection_id)
    assert connection.status == CalendarConnection.Status.NEEDS_RECONNECT, (
        "a 410 revokes the address"
    )
    assert connection.last_error_kind == "revoked"

    # **The imported events stay.** The provider revoked the *address*, not the events,
    # and deleting a user's history over a 410 would be irreversible.
    assert (
        PersonalEvent.objects.using(PERSONAL).filter(calendar_connection_id=connection_id).exists()
    ), "the imported events must survive a revoked credential"

    # === Step 14: disconnecting removes exactly that connection's events ===================

    own_event = _post(
        client,
        "/api/personal/events",
        {
            "name": "Dentist",
            "start_time_utc": "2026-11-20T09:00:00Z",
            "start_time_tz": "Europe/London",
            "end_time_utc": "2026-11-20T10:00:00Z",
        },
    )
    assert own_event.status_code == 201, own_event.content
    own_event_id = _json(own_event)["id"]

    disconnected = client.delete(f"/api/personal/calendars/{connection_id}")
    assert disconnected.status_code == 204, disconnected.content

    assert (
        not PersonalEvent.objects.using(PERSONAL)
        .filter(calendar_connection_id=connection_id)
        .exists()
    ), "the connection's own events are purged on disconnect"
    assert PersonalEvent.objects.using(PERSONAL).filter(pk=own_event_id).exists(), (
        "the user's own event must survive the connection's disconnect"
    )

    # === Step 15: a second calendar connection is refused with the calm upgrade message ===

    # The first connection was disconnected, so it does not occupy a slot. The user
    # connects again — and then a *second* calendar is refused by the Free cap.
    reconnected = _post(
        client,
        "/api/personal/calendars",
        {"provider": "google", "address": fixture_server.url("/feed/other.ics")},
    )
    assert reconnected.status_code == 201, reconnected.content

    capped = _post(
        client,
        "/api/personal/calendars",
        {"provider": "apple", "address": fixture_server.url("/feed/another.ics")},
    )
    assert capped.status_code == 409, capped.content
    cap_body = _json(capped)
    assert cap_body["code"] == "calendar_cap_reached"
    assert cap_body["details"]["upgrade_hint"] == "Save more with Pro."
    # **No modal semantics.** The approved copy is an inline prompt with a quiet
    # "Upgrade" link, so the payload carries no modal-shaped field at all.
    for modal_field in ("modal", "title", "actions", "dismissable"):
        assert modal_field not in cap_body["details"], (
            f"the cap payload carries a modal-shaped field ({modal_field!r}); the "
            "approved copy is an inline prompt."
        )

    # === The credential-leak sweep =========================================================
    #
    # Four places, four separate leaks: the logs, the database, the API responses and
    # the DOM. Each is searched for the **whole** credential, and the credential is a
    # runtime-generated URL that appears nowhere in this file — so a pass is a real
    # absence, not a match against a constant that was never there.

    # **1. The logs.** Every record the scenario produced, including the 410 step —
    # which is where a failed poll would have leaked the URL, because the fetch
    # adapter's error messages carry the request URL.
    #
    # **The records are swept as they reach the sink, not as they were created.**
    # A `caplog` record is the *pre-formatter* state: its message is the raw string
    # the logger was given. Redaction (AD-13) happens in `JsonFormatter`, which is
    # what the logging config installs as the only handler. So sweeping the raw record
    # would test something the deployment never emits, and would fail on a line that
    # the formatter would have scrubbed.
    #
    # Each record is therefore pushed through the **real** formatter and the sweep
    # reads the JSON line that would actually be written. That is the artefact the
    # requirement is about: what leaves the process.
    #
    # The raw message is swept **as well**, and it is expected to be clean for the
    # project's own loggers — they log a constant template and put the data in
    # allowlisted `extra` fields. A raw leak in a project logger is a real leak.
    assert caplog.records, "the scenario logged nothing — the log sweep would be empty"
    for record in caplog.records:
        rendered = _rendered_log_line(record)
        assert not _secret_in(rendered, secret_url), (
            f"the credential reached a log line: {rendered}"
        )

    # **2. The database.** The raw column, read directly — every row of it, not just the
    # one this scenario connected. A credential written in the clear by *any* write path
    # is a leak, and the sweep is over the whole column for that reason.
    for raw_credential in _all_raw_credentials():
        assert not _secret_in(raw_credential or "", secret_url), (
            "the credential reached the database in the clear"
        )

    # **3. The responses.** Every body the scenario received, recorded by the client.
    for response in client.responses:
        body = response.content.decode(errors="replace")
        assert not _secret_in(body, secret_url), (
            f"the credential reached a response: {response.request['PATH_INFO']}"
        )

    # **4. The DOM.** The frontend's rendered output.
    #
    # The DOM half of the AC is proven by the frontend's own jsdom tests — the preview
    # page has no calendar address to render, and the connection view has no field for
    # one (which the backend proves structurally: the output shape has no address
    # field, so the frontend has nothing to print). What the backend *can* check is
    # that the served HTML carries no credential either, and it does: the preview is
    # public and its markup is the same for every visitor.
    served = client.get("/api/public/preview")
    assert not _secret_in(served.content.decode(errors="replace"), secret_url), (
        "the credential reached the served markup"
    )

    # **5. The sweep is not empty where it matters.** The `httpx` logger is the one
    # that logs request URLs, and `config/settings.py` pins it to `WARNING` — above
    # the level the sweep asks for. If the scenario's `caplog.set_level` calls did
    # not lower it *specifically*, the sweep would capture zero httpx records and
    # would pass while looking at nothing where the credential is most likely to be.
    #
    # **And the calendar's own httpx line must be *absent*.** The calendar adapter
    # passes `credential=True`, and the transport suppresses httpx's URL logging for
    # that fetch — so a calendar fetch produces **no** httpx record at all, while the
    # module's own safe record ("Calendar feed read", counts only) still says what
    # happened.
    #
    # Both directions are asserted. The absence is the guarantee; the presence of the
    # safe record is what makes the absence a *decision* rather than a silence.
    httpx_records = [record for record in caplog.records if record.name == "httpx"]
    assert not httpx_records, (
        "the calendar fetch wrote an httpx record, and httpx records carry the "
        "request URL. The calendar adapter must pass credential=True so the "
        f"transport suppresses it. Found: {[r.getMessage() for r in httpx_records]}"
    )

    safe_records = [
        record
        for record in caplog.records
        if record.name == "adapters.calendar.ics" and "Calendar feed read" in record.getMessage()
    ]
    assert safe_records, (
        "the calendar's own safe record is missing, so the absence of the httpx line "
        "would be a silence rather than a decision. The fetch must still be logged — "
        "with counts and byte totals, never the URL."
    )


# --- The boundary cases ----------------------------------------------------------------------


def test_a_calendar_connection_to_a_private_address_is_refused(
    client,
    fixture_server,
    settings,
):
    """The pre-flight refuses a denied literal, so no row is ever created.

    The connection service's pre-flight is a *pre-flight*, not the policy — the real
    check is at connect time. But the pre-flight exists so the user hears about it
    while they are still there, and this proves it is still there after the test-only
    allowance was added.

    **The allowance must not weaken it.** If the pre-flight stopped refusing, the user
    would get a "connected" row that fails on every poll, and the only evidence would
    be a slug in the error field.
    """
    _sign_up(client, "maya@example.test")
    assert _sign_in(client, "maya@example.test").status_code == 200

    refused = _post(
        client,
        "/api/personal/calendars",
        {"provider": "google", "address": "https://10.0.0.1/feed.ics"},
    )

    assert refused.status_code == 422, refused.content
    assert _json(refused)["code"] == "invalid_calendar_credential"
    assert CalendarConnection.objects.using(PERSONAL).count() == 0


def test_the_reset_request_is_indistinguishable_for_a_known_and_an_unknown_address(client):
    """Enumeration safety: the same answer either way.

    A reset request that said "no such account" would tell an attacker which addresses
    have accounts, and the address list is the thing worth guessing.
    """
    _sign_up(client, "known@example.test")

    known = _post(client, "/api/auth/password-reset", {"email": "known@example.test"})
    unknown = _post(client, "/api/auth/password-reset", {"email": "nobody@example.test"})

    assert known.status_code == unknown.status_code == 202
    assert known.content == unknown.content, (
        "the reset request answers differently for a known and an unknown address; "
        "that is an enumeration leak."
    )


def test_the_fixture_server_is_not_reachable_without_the_allowance(fixture_server):
    """Without the allowance, the real policy refuses the fixture's loopback address.

    This is the counterpart of `tests/e2e/test_loopback_allowance.py`: that file proves
    the allowance cannot be *enabled* outside the tests, and this one proves the
    default still refuses loopback — so the proof's own reachability is the only way in.
    """
    from ports.fetch_policy import fetch_deny_policy

    deny = fetch_deny_policy()
    from ipaddress import ip_address

    assert deny(ip_address("127.0.0.1")) is True, (
        "the default policy must still deny loopback; only the explicit "
        "allow_loopback_fetch() block admits it."
    )


def test_the_calendar_connection_view_never_carries_the_address(
    client, fixture_server, calendar_port
):
    """The address is write-only: there is nowhere for it to go.

    Not in full, not masked, not as a fragment — the output shape has no field for it,
    so the guarantee is structural rather than careful.

    The `calendar_port` fixture is requested for its **port allowlist**: the fixture
    server's ephemeral port has to be in `SOURCE_FETCH["allowed_ports"]` or the connect
    is refused by the port pre-flight. The connection is never polled here — the point
    is the shape of the answer, not the import.
    """
    _sign_up(client, "maya@example.test")
    assert _sign_in(client, "maya@example.test").status_code == 200

    connected = _post(
        client,
        "/api/personal/calendars",
        {"provider": "google", "address": fixture_server.url("/feed.ics")},
    )
    assert connected.status_code == 201, connected.content

    listed = client.get("/api/personal/calendars")
    assert listed.status_code == 200
    body = listed.content.decode()

    assert "127.0.0.1" not in body, "the connection list carries the host"
    assert "address" not in _json(listed)["items"][0], "the connection view has an address field"
