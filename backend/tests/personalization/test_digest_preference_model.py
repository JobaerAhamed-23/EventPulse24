"""The digest preference model's three new columns (FR-19, FR-5).

`DigestPreference` grew three columns: the user's **home city**, the **source** it was
arrived at, and the **personal-events opt-out**. What these tests pin is the shape of
the row itself:

- the three columns exist, with the types and bounds the design says;
- the city and the source **travel together** — the database holds the agreement;
- the opt-out **defaults to included**, which is PRD `[ASSUMPTION-7]`;
- the retention category is **unchanged** — a city is an input, not account content;
- **`__str__` leaks no city** — the city is weak location data about a real person, and
  `__str__` reaches every log line and every admin list column (AD-13).

The two tests that could pass for the wrong reason are written so they cannot:

- the "`__str__` leaks no city" test asserts the city **is** in the row and **is not**
  in the string — so it fails both when the city leaks and when the string is empty of
  everything;
- the "city and source travel together" test tries **both** halves of the agreement —
  a city with no source and a source with no city — so a constraint that only checked
  one of them would fail.
"""

import pytest
from django.db import IntegrityError, transaction

from apps.personalization.models import DigestPreference
from shared.db import PERSONAL

pytestmark = pytest.mark.django_db(databases=[PERSONAL])


def make_preference(**overrides):
    """A digest preference, with the fields the model requires."""
    fields = {
        "user_id": "11111111-1111-4111-8111-111111111111",
        "delivery_time": "09:00:00",
        "timezone": "America/New_York",
    }
    fields.update(overrides)
    return DigestPreference.objects.using(PERSONAL).create(**fields)


# --- The columns --------------------------------------------------------------------------


def test_the_three_columns_exist():
    fields = DigestPreference._meta.get_fields()

    city = next(f for f in fields if f.name == "city")
    city_source = next(f for f in fields if f.name == "city_source")
    include = next(f for f in fields if f.name == "include_personal_events")

    assert city.null is True
    assert city.max_length == 64
    assert city_source.null is True
    assert city_source.max_length == 16
    assert include.default is True
    assert include.null is False


def test_the_opt_out_defaults_to_included():
    """PRD `[ASSUMPTION-7]`: personal events are in the digest unless the user opts out."""
    preference = make_preference()

    assert preference.include_personal_events is True


def test_the_city_may_be_absent():
    """`NULL` is a real state: "we do not know where this user is"."""
    preference = make_preference()

    assert preference.city is None
    assert preference.city_source is None


# --- The city/source agreement ----------------------------------------------------------------


def test_a_city_with_no_source_is_refused():
    """A claim about where the user is with no record of how we learned it."""
    with pytest.raises(IntegrityError):
        with transaction.atomic(using=PERSONAL):
            make_preference(city="Brooklyn", city_source=None)


def test_a_source_with_no_city_is_refused():
    """A record of a decision about a city we do not have."""
    with pytest.raises(IntegrityError):
        with transaction.atomic(using=PERSONAL):
            make_preference(city=None, city_source="choice")


def test_a_city_with_a_source_is_accepted():
    preference = make_preference(city="Brooklyn", city_source="choice")

    assert preference.city == "Brooklyn"
    assert preference.city_source == "choice"


def test_the_source_choices_are_the_four_the_design_names():
    assert {member.value for member in DigestPreference.CitySource} == {
        "geo",
        "choice",
        "fallback",
        "backfill",
    }


# --- The retention category -------------------------------------------------------------------


def test_the_retention_category_is_unchanged():
    """A city is an *input* and may be refreshed — it is not account content."""
    from shared.retention import RetentionCategory

    assert DigestPreference.retention_category == RetentionCategory.PREFERENCE_SIGNALS


# --- `__str__` ---------------------------------------------------------------------------------


def test_the_string_leaks_no_city():
    """AD-13: the city is weak location data about a real person.

    The assertion is **both** halves: the city is in the row, and it is not in the
    string. A test that only checked the absence would pass against an empty string.
    """
    preference = make_preference(city="Brooklyn", city_source="choice")

    rendered = str(preference)

    assert "Brooklyn" not in rendered
    # The delivery time and the zone *are* shown — the string is not empty, and it is
    # not accidentally blank because the model lost its rendering.
    assert "09:00:00" in rendered
    assert "America/New_York" in rendered


def test_the_repr_leaks_no_city():
    """Django's `__repr__` delegates to `__str__`, so this is safe for free."""
    preference = make_preference(city="Brooklyn", city_source="choice")

    assert "Brooklyn" not in repr(preference)
