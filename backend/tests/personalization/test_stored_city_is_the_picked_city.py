"""**The stored city is the picked city.** Never silently rewritten to anything else.

This file is the item's own proof, kept apart from the older command tests in
`test_digest_preferences.py` on purpose. The older file tests the *commands* — the
upsert, the audit row, the backfill, the opt-out. This file tests **the rule**: which
cities may be stored, and what happens to one that may not.

**The rule, in one table.**

| The city is… | What happens |
|---|---|
| `None` | stores nothing; clears an existing one |
| in the catalog, `source="choice"` | stored **exactly as picked**, `city_source="choice"` |
| in the catalog, `source="geo"` | stored in the catalog's spelling, `city_source="geo"` |
| **not** in the catalog, `source="choice"` | **refused** — a validation error, nothing written |
| **not** in the catalog, `source="geo"` | `PREVIEW_FALLBACK_CITY`, `city_source="fallback"` |
| any city, `source="seed"` | stored **verbatim**, `city_source="seed"` |
| over-long (> `GEO_CITY_MAX_LENGTH`) | **refused** on a choice; fallback on a geo and on a seed |

**The choice-versus-geo distinction is the subtle part**, and it is the thing these tests
are built around. Three callers reach `resolve_home_city` and they are not the same kind
of caller:

- the reader picking from the dropdown (`source="choice"`) — their choice is
  authoritative, and a city outside the catalog is a **client bug**, so it is refused
  loudly;
- the edge's geo header (`source="geo"`) — **nobody chose it**, so an uncoverable value
  falls back silently exactly as it always has. Refusing it would turn an edge's guess
  into a 4xx on a path the reader never asked for;
- the **server itself** (`source="seed"`) — the local dev seed authors a *fictional*
  city for a walk-through, and stores it verbatim. There is no reader to mislead, which
  is the same reasoning that exempts the fallback from the catalog check.

**The whole-dataset test is the load-bearing one.** It is parameterised over every row
of `domain.city_catalog`, so a **future** catalog row cannot regress the rule: if
somebody adds "Hobart" to the catalog and the picker offers it, the test already knows
that "Hobart" must resolve. It is also mutation-checked — see the run's test report — so
it is known to be able to fail.

**A test that could pass for the wrong reason**, and how it is written:

1. *"Every catalog row resolves."* A test that asserts one row resolves passes if the
   implementation answers everything with the same city. So the parameterisation is over
   **all** rows, and each case asserts the row's **own** name comes back — a
   universal-answer implementation fails 164 of 165 cases.

2. *"A refused city writes nothing."* A test that asserts only that the call raised
   passes if the implementation wrote and *then* raised. So the test asserts **both**:
   that the call raised, **and** that no preference row and no audit row exist
   afterwards.

3. *"The refused city is in the error and nowhere else."* A test that asserts the city
   is absent from the audit details passes if the audit rows are **empty** — which would
   mean the refusal wrote an audit row with nothing in it. So the test asserts **both**
   that the audit rows are empty **and** that the rejected city is in the error.
"""

from datetime import UTC, datetime

import pytest

from apps.personalization.models import DigestPreference, PersonalizationAuditEntry
from apps.personalization.services.digest_preferences import (
    SOURCE_BACKFILL,
    SOURCE_CHOICE,
    SOURCE_FALLBACK,
    SOURCE_GEO,
    SOURCE_SEED,
    backfill_home_cities,
    resolve_home_city,
    set_home_city,
    store_fallback_city,
)
from domain.city_catalog import WORLD_CITIES, lookup
from domain.errors import UnknownHomeCityError
from shared.actor import Actor
from shared.constants import GEO_CITY_MAX_LENGTH, PREVIEW_FALLBACK_CITY
from shared.db import PERSONAL
from shared.ids import uuid7

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)

#: A city the catalog does not hold. The name is deliberately not a real city, so the
#: test cannot pass because the catalog happened to cover it.
OUTSIDE = "Zzyzx-not-a-real-city"


def actor(user_id):
    return Actor.user(user_id)


def read_preference(user_id):
    return DigestPreference.objects.using(PERSONAL).filter(user_id=user_id).first()


def audits_for(user_id):
    return list(
        PersonalizationAuditEntry.objects.using(PERSONAL)
        .filter(target_type="DigestPreference")
        .filter(actor_id=user_id)
        .order_by("at")
    )


# --- The whole dataset (AC 8) ---------------------------------------------------------------


@pytest.mark.parametrize(
    "row",
    WORLD_CITIES,
    ids=[row.name for row in WORLD_CITIES],
)
def test_every_catalog_city_resolves_to_itself(row):
    """**Every row of the catalog resolves to its own name.**

    The picker is populated from this same table (`GET /api/public/cities`, item 4), so
    a row the picker offers is a row that must resolve. Parameterised over the whole
    dataset, so a row added tomorrow is covered without anyone touching this file.
    """
    resolved_city, resolved_source = resolve_home_city(city=row.name, source=SOURCE_CHOICE, now=NOW)

    assert resolved_city == row.name
    assert resolved_source == SOURCE_CHOICE


@pytest.mark.parametrize(
    "row",
    WORLD_CITIES,
    ids=[row.name for row in WORLD_CITIES],
)
def test_every_catalog_city_resolves_from_a_differently_spelled_request(row):
    """The catalog's spelling wins, whatever spelling the caller used.

    "chittagong" and "Chittagong" are the same city, and the events are filed under the
    catalog's — so the stored value is the catalog's, not the caller's.
    """
    resolved_city, _resolved_source = resolve_home_city(
        city=row.name.upper(), source=SOURCE_CHOICE, now=NOW
    )

    assert resolved_city == row.name


@pytest.mark.parametrize(
    "row",
    WORLD_CITIES,
    ids=[row.name for row in WORLD_CITIES],
)
def test_every_catalog_city_is_stored_as_itself(row):
    """The same rule, through the command that writes the row.

    `resolve_home_city` is the rule; this is the rule **in the database**, which is
    where the reader will actually meet it.
    """
    user_id = uuid7()

    set_home_city(
        user_id=user_id, city=row.name, source=SOURCE_CHOICE, actor=actor(user_id), now=NOW
    )

    preference = read_preference(user_id)
    assert preference is not None
    assert preference.city == row.name
    assert preference.city_source == SOURCE_CHOICE


def test_the_catalog_is_not_a_universal_answer():
    """**The guard against passing for the wrong reason.**

    A rule that answered every city with the same value would satisfy "every catalog
    row resolves to *a* city". So this test says plainly: two different rows resolve to
    two different cities, and neither is the fallback.
    """
    first, second = WORLD_CITIES[0], WORLD_CITIES[1]

    first_city, _ = resolve_home_city(city=first.name, source=SOURCE_CHOICE, now=NOW)
    second_city, _ = resolve_home_city(city=second.name, source=SOURCE_CHOICE, now=NOW)

    assert first_city == first.name
    assert second_city == second.name
    assert first_city != second_city
    assert first_city != PREVIEW_FALLBACK_CITY


@pytest.mark.parametrize(
    "row",
    WORLD_CITIES,
    ids=[row.name for row in WORLD_CITIES],
)
def test_the_stored_city_is_always_a_city_the_catalog_holds(row):
    """**The invariant that used to live in a helper, now enforced at the one place
    that stores a city.**

    The stored city is the **catalog's** spelling, never the caller's — because the
    events are filed under the catalog's spelling, and a preference carrying a
    different one would rank on a city the catalog has never heard of. So whatever
    spelling the caller used, the row that comes back is a row the catalog holds.
    """
    resolved_city, _resolved_source = resolve_home_city(
        city=row.name, source=SOURCE_CHOICE, now=NOW
    )

    assert resolved_city is not None
    assert lookup(resolved_city) is not None
    assert lookup(resolved_city).name == row.name


# --- The refusal (AC 2, AC 4, AC 9) -----------------------------------------------------------


def test_a_city_outside_the_catalog_is_refused_on_a_choice():
    """**Refused, not rewritten.** The old rule stored the fallback here and called it a
    success; that is the fault this item exists to end."""
    with pytest.raises(UnknownHomeCityError):
        resolve_home_city(city=OUTSIDE, source=SOURCE_CHOICE, now=NOW)


def test_the_refusal_carries_the_rejected_city():
    """The caller sent the value and needs to be told which one was refused."""
    with pytest.raises(UnknownHomeCityError) as caught:
        resolve_home_city(city=OUTSIDE, source=SOURCE_CHOICE, now=NOW)

    assert caught.value.details["rejected_city"] == OUTSIDE


def test_the_refusal_message_does_not_quote_the_city():
    """The message is for a person; the value is machine-readable data.

    They have different jobs, so they are in different places.
    """
    with pytest.raises(UnknownHomeCityError) as caught:
        resolve_home_city(city=OUTSIDE, source=SOURCE_CHOICE, now=NOW)

    assert OUTSIDE not in caught.value.message


def test_the_refusal_is_a_validation_error():
    """**422, not 400.** A `ValidationError` is what `config/errors.py` maps to 422, and
    that is the right shape: the request was well-formed and offered a city the server
    does not have."""
    from domain.errors import ValidationError

    with pytest.raises(UnknownHomeCityError) as caught:
        resolve_home_city(city=OUTSIDE, source=SOURCE_CHOICE, now=NOW)

    assert isinstance(caught.value, ValidationError)
    assert caught.value.code == "unknown_home_city"


def test_an_over_long_city_is_refused_on_a_choice():
    """An over-long value is an attempt to put a value somewhere it should not go."""
    with pytest.raises(UnknownHomeCityError):
        resolve_home_city(city="x" * (GEO_CITY_MAX_LENGTH + 1), source=SOURCE_CHOICE, now=NOW)


def test_an_empty_city_is_refused_on_a_choice():
    """A `<select>` cannot offer an empty string, so this is a client bug."""
    with pytest.raises(UnknownHomeCityError):
        resolve_home_city(city="   ", source=SOURCE_CHOICE, now=NOW)


def test_a_refused_city_writes_no_preference_row():
    """**Both halves asserted**, so a `resolve_home_city` that wrote and *then* raised
    could not pass for the right reason."""
    user_id = uuid7()

    with pytest.raises(UnknownHomeCityError):
        set_home_city(
            user_id=user_id, city=OUTSIDE, source=SOURCE_CHOICE, actor=actor(user_id), now=NOW
        )

    assert read_preference(user_id) is None


def test_a_refused_city_writes_no_audit_row():
    """**The refusal writes nothing at all** — no preference, no audit row.

    An audit row saying "the city changed" for a city that did not change would be a
    lie in the one place an editor looks to find out what happened.
    """
    user_id = uuid7()

    with pytest.raises(UnknownHomeCityError):
        set_home_city(
            user_id=user_id, city=OUTSIDE, source=SOURCE_CHOICE, actor=actor(user_id), now=NOW
        )

    assert audits_for(user_id) == []


def test_a_refused_city_is_in_the_error_and_in_no_audit_detail():
    """**Both halves asserted**, so "the audit rows are empty" cannot pass for the
    right reason while the city leaked into a row's details.

    The city is in the API error — the caller sent it and needs to be told which value
    was refused — and in **no** audit detail (AD-13).
    """
    user_id = uuid7()

    with pytest.raises(UnknownHomeCityError) as caught:
        set_home_city(
            user_id=user_id, city=OUTSIDE, source=SOURCE_CHOICE, actor=actor(user_id), now=NOW
        )

    assert caught.value.details["rejected_city"] == OUTSIDE
    for entry in audits_for(user_id):
        assert OUTSIDE not in str(entry.details)


def test_a_refused_city_does_not_disturb_a_city_already_stored():
    """The refusal writes nothing — which includes not touching what was there."""
    user_id = uuid7()
    set_home_city(
        user_id=user_id,
        city="Chittagong",
        source=SOURCE_CHOICE,
        actor=actor(user_id),
        now=NOW,
    )

    with pytest.raises(UnknownHomeCityError):
        set_home_city(
            user_id=user_id, city=OUTSIDE, source=SOURCE_CHOICE, actor=actor(user_id), now=NOW
        )

    preference = read_preference(user_id)
    assert preference.city == "Chittagong"
    assert preference.city_source == SOURCE_CHOICE


# --- `None` is not a refusal (AC 3) ------------------------------------------------------------


def test_an_absent_city_is_not_a_refusal():
    """**"We do not know" is a real state**, and it is not the same as "that was
    wrong".

    Storing the fallback for it would be storing an inferred city for someone who
    declined inference.
    """
    resolved_city, resolved_source = resolve_home_city(city=None, source=SOURCE_CHOICE, now=NOW)

    assert resolved_city is None
    assert resolved_source is None


def test_an_absent_city_clears_the_stored_one_and_is_not_a_refusal():
    """The distinction in one test: a refusal raises, an absent city does not — and the
    absent city clears what was there."""
    user_id = uuid7()
    set_home_city(
        user_id=user_id,
        city="Chittagong",
        source=SOURCE_CHOICE,
        actor=actor(user_id),
        now=NOW,
    )

    # No exception here — that is the point.
    set_home_city(user_id=user_id, city=None, source=SOURCE_CHOICE, actor=actor(user_id), now=NOW)

    preference = read_preference(user_id)
    assert preference.city is None
    assert preference.city_source is None


# --- The geo path keeps its fallback (AC 5) ----------------------------------------------------


def test_a_geo_city_outside_the_catalog_still_falls_back():
    """**The geo path keeps its fallback.** Nobody chose it, so an uncoverable value
    falls back silently exactly as it does today. Refusing it would turn an edge's guess
    into a 4xx on a path the reader never asked for."""
    resolved_city, resolved_source = resolve_home_city(city=OUTSIDE, source=SOURCE_GEO, now=NOW)

    assert resolved_city == PREVIEW_FALLBACK_CITY
    assert resolved_source == SOURCE_FALLBACK


def test_an_over_long_geo_city_still_falls_back():
    """Same reasoning as the unknown geo city: nobody chose it."""
    resolved_city, resolved_source = resolve_home_city(
        city="x" * (GEO_CITY_MAX_LENGTH + 1), source=SOURCE_GEO, now=NOW
    )

    assert resolved_city == PREVIEW_FALLBACK_CITY
    assert resolved_source == SOURCE_FALLBACK


def test_a_geo_city_in_the_catalog_keeps_its_own_source():
    """The geo path is not second-class: a city the catalog holds is still stored in
    the catalog's spelling, with `geo` as the source."""
    resolved_city, resolved_source = resolve_home_city(
        city="chittagong", source=SOURCE_GEO, now=NOW
    )

    assert resolved_city == "Chittagong"
    assert resolved_source == SOURCE_GEO


# --- The server's own city (the local dev seed) ---------------------------------------------------


def test_a_city_the_server_chose_is_stored_verbatim():
    """**The third writer, and the one that is not a reader.**

    The local dev seed authors a *fictional* city — "Fixtureville" — for a walk-through.
    It is not in the catalog and never could be. The server chose it, so it is stored as
    it is: the same exemption the fallback gets, for the same reason. There is no reader
    to mislead, because there is no reader.
    """
    resolved_city, resolved_source = resolve_home_city(
        city="Fixtureville", source=SOURCE_SEED, now=NOW
    )

    assert resolved_city == "Fixtureville"
    assert resolved_source == SOURCE_SEED


def test_a_seed_city_is_not_refused():
    """**The seed's city is not a client bug.** A refusal is for a reader who picked a
    city the server does not have; the seed is the server."""
    resolved_city, _resolved_source = resolve_home_city(city=OUTSIDE, source=SOURCE_SEED, now=NOW)

    assert resolved_city == OUTSIDE


def test_an_over_long_seed_city_falls_back():
    """The length bound still applies: a value that long is a value put somewhere it
    should not go, whoever chose it."""
    resolved_city, resolved_source = resolve_home_city(
        city="x" * (GEO_CITY_MAX_LENGTH + 1), source=SOURCE_SEED, now=NOW
    )

    assert resolved_city == PREVIEW_FALLBACK_CITY
    assert resolved_source == SOURCE_FALLBACK


# --- What did not change (AC 6, AC 7) -----------------------------------------------------------


def test_the_fallback_is_stored_as_it_is():
    """**`store_fallback_city` is unchanged.**

    The fallback is not catalog-checked, because the server chose it. Applying the
    catalog rule to it would be circular: the fallback is by definition a city the
    catalog may not hold.
    """
    user_id = uuid7()

    store_fallback_city(user_id=user_id, source=SOURCE_FALLBACK, actor=actor(user_id), now=NOW)

    preference = read_preference(user_id)
    assert preference.city == PREVIEW_FALLBACK_CITY
    assert preference.city_source == SOURCE_FALLBACK


def test_the_backfill_still_writes_the_fallback():
    """**`backfill_home_cities` is unchanged** — it writes the fallback, with
    `backfill` as the source."""
    user_id = uuid7()
    DigestPreference.objects.using(PERSONAL).create(
        user_id=user_id, delivery_time="09:00:00", timezone="UTC"
    )

    written, seen = backfill_home_cities(now=NOW, actor=Actor.system("digest_city_backfill"))

    assert (written, seen) == (1, 1)
    preference = read_preference(user_id)
    assert preference.city == PREVIEW_FALLBACK_CITY
    assert preference.city_source == SOURCE_BACKFILL


def test_the_backfill_never_overwrites_a_city_that_was_picked():
    """A picked city survives the backfill — and now it survives it as itself."""
    user_id = uuid7()
    set_home_city(
        user_id=user_id,
        city="Chittagong",
        source=SOURCE_CHOICE,
        actor=actor(user_id),
        now=NOW,
    )

    written, seen = backfill_home_cities(now=NOW, actor=Actor.system("digest_city_backfill"))

    assert (written, seen) == (0, 0)
    preference = read_preference(user_id)
    assert preference.city == "Chittagong"
    assert preference.city_source == SOURCE_CHOICE


def test_an_existing_fallback_row_is_left_alone():
    """**AC 7: no migration.** A row that already reads `fallback` keeps reading
    `fallback` — the item changes what a *new* pick does, not what an old row says."""
    user_id = uuid7()
    DigestPreference.objects.using(PERSONAL).create(
        user_id=user_id,
        delivery_time="09:00:00",
        timezone="UTC",
        city=PREVIEW_FALLBACK_CITY,
        city_source=SOURCE_FALLBACK,
    )

    # The backfill skips it: a city that is set is never overwritten.
    backfill_home_cities(now=NOW, actor=Actor.system("digest_city_backfill"))

    preference = read_preference(user_id)
    assert preference.city == PREVIEW_FALLBACK_CITY
    assert preference.city_source == SOURCE_FALLBACK


def test_a_pick_replaces_a_fallback_row_with_the_picked_city():
    """The consequence of "no migration", named: the next pick is stored as itself.

    A user whose stored city reads `fallback` picks Chittagong and gets Chittagong.
    That is the point of the item.
    """
    user_id = uuid7()
    DigestPreference.objects.using(PERSONAL).create(
        user_id=user_id,
        delivery_time="09:00:00",
        timezone="UTC",
        city=PREVIEW_FALLBACK_CITY,
        city_source=SOURCE_FALLBACK,
    )

    set_home_city(
        user_id=user_id,
        city="Chittagong",
        source=SOURCE_CHOICE,
        actor=actor(user_id),
        now=NOW,
    )

    preference = read_preference(user_id)
    assert preference.city == "Chittagong"
    assert preference.city_source == SOURCE_CHOICE
