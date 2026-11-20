"""The digest-preference endpoint answers a city it does not have with a **refusal**.

**The claim this file exists to defend:** the endpoint does not silently rewrite a city
the reader chose. It answers 422, stores nothing, and names the rejected value.

The endpoint is `PUT /api/personal/onboarding/digest-preference`. It is exercised through
a real session, with a real CSRF token, because the refusal happens inside the service
and the client is the only way to see the HTTP shape of it.

**What the endpoint's answer looks like.**

- A city **in** the curated catalog → **200**, and the stored city is exactly what was
  sent, with `city_source` set to `choice`.
- A city **outside** it → **422**, with the project's one error shape
  `{code, message, details}`, `code` being `unknown_home_city`, and the rejected value
  named in `details`. **Nothing is stored.**

**Why the rejected value is in the response and not in the audit row.** The reader sent
it and needs to be told which value was refused — echoing a value back to its sender is
not disclosure. The audit row is a different audience, and AD-13 keeps the city out of
it. `test_the_refused_city_is_in_the_response_and_in_no_audit_row` asserts both halves,
because a test that only checked the audit side would pass if the audit rows were empty.

**Why 422 and not 400.** A `ValidationError` maps to 422 in `config/errors.py`, and the
refusal is "input breaks a rule" — the same shape as every other validation failure in
this codebase. The request was well-formed; it offered a city the server does not have.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.personalization.models import DigestPreference, PersonalizationAuditEntry
from shared.db import PERSONAL
from tests.csrf import CsrfClient

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

URL = "/api/personal/onboarding/digest-preference"

User = get_user_model()

#: A city in the curated catalog.
IN_THE_CATALOG = "Chittagong"

#: A city the catalog does not hold. The name is deliberately not a real city, so the
#: test cannot pass because the catalog happened to cover it.
OUTSIDE = "Zzyzx-not-a-real-city"


def signed_in(user=None):
    """A client whose session identifies `user`."""
    client = CsrfClient()
    client.force_login(user or User.objects.create_user(email="sam@example.test", password="pw"))
    return client


def put(client, **body):
    return client.put(
        URL,
        {"delivery_time": "09:30", "timezone": "America/Los_Angeles", **body},
        content_type="application/json",
    )


def preferences():
    return list(DigestPreference.objects.using(PERSONAL).all())


def audits():
    return list(PersonalizationAuditEntry.objects.using(PERSONAL).all())


# --- A city in the catalog ------------------------------------------------------------------------


def test_a_catalog_city_is_stored_exactly_as_it_was_sent():
    client = signed_in()

    response = put(client, city=IN_THE_CATALOG)

    assert response.status_code == 200
    digest = response.json()["digest"]
    assert digest["city"] == IN_THE_CATALOG
    assert digest["city_source"] == "choice"


def test_the_stored_row_holds_the_city_that_was_sent():
    """The response and the row must agree — and the row is the one that matters."""
    client = signed_in()

    put(client, city=IN_THE_CATALOG)

    rows = preferences()
    assert len(rows) == 1
    assert rows[0].city == IN_THE_CATALOG
    assert rows[0].city_source == "choice"


# --- A city outside the catalog -------------------------------------------------------------------


def test_a_city_outside_the_catalog_is_answered_with_422():
    client = signed_in()

    response = put(client, city=OUTSIDE)

    assert response.status_code == 422


def test_the_refusal_uses_the_projects_one_error_shape():
    client = signed_in()

    response = put(client, city=OUTSIDE)

    body = response.json()
    assert body["code"] == "unknown_home_city"
    assert isinstance(body["message"], str)
    assert body["message"]
    assert body["details"]["errors"][0]["loc"] == ["city"]


def test_the_refusal_names_the_rejected_value():
    """The caller sent it and needs to be told which value was refused."""
    client = signed_in()

    response = put(client, city=OUTSIDE)

    assert response.json()["details"]["rejected_city"] == OUTSIDE


def test_the_refusal_message_does_not_quote_the_value():
    """The message is for a person; the value is machine-readable data."""
    client = signed_in()

    response = put(client, city=OUTSIDE)

    assert OUTSIDE not in response.json()["message"]


def test_a_refused_city_stores_nothing():
    """**The refusal writes nothing at all** — not a row, and not an audit row."""
    client = signed_in()

    response = put(client, city=OUTSIDE)

    assert response.status_code == 422
    assert preferences() == []
    assert audits() == []


def test_a_refused_city_leaves_an_earlier_city_alone():
    """A refusal is not a partial write: the city already stored survives it."""
    client = signed_in()
    put(client, city=IN_THE_CATALOG)

    response = put(client, city=OUTSIDE)

    assert response.status_code == 422
    rows = preferences()
    assert len(rows) == 1
    assert rows[0].city == IN_THE_CATALOG
    assert rows[0].city_source == "choice"


def test_the_refused_city_is_in_the_response_and_in_no_audit_row():
    """**Both halves asserted**, so "the audit rows are empty" cannot pass for the
    right reason while the city leaked into a row's details."""
    client = signed_in()

    response = put(client, city=OUTSIDE)

    assert response.json()["details"]["rejected_city"] == OUTSIDE
    for entry in audits():
        assert OUTSIDE not in str(entry.details)


# --- The endpoint's other refusals are untouched --------------------------------------------------


def test_putting_a_non_iana_timezone_is_still_refused():
    """The city rule did not swallow the timezone rule."""
    client = signed_in()

    response = put(client, timezone="Mars/Olympus_Mons")

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_timezone"
    assert preferences() == []


def test_the_endpoint_requires_a_session():
    client = Client()

    response = client.put(
        URL,
        {"delivery_time": "09:00", "timezone": "UTC", "city": IN_THE_CATALOG},
        content_type="application/json",
    )

    assert response.status_code == 401
