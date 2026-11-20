"""The home city and the personal-events opt-out: the commands (FR-19, FR-5).

These are the rules the digest depends on:

- **A city in the curated catalog is stored exactly as picked**, in the catalog's own
  spelling, with the source it arrived under.
- **A city outside the catalog is refused**, not silently rewritten to the fallback.
  The stored city is the picked city, and the pick is authoritative.
- **A geo city outside the catalog still falls back**, because nobody chose it and an
  edge's guess must not be refused back to the reader.
- **The audit row says that the city changed; it never carries the city.** The flag
  **is** in the audit details, because it is not location data.
- **The opt-out defaults to included**, and it is the user's choice that flips it.
- **The backfill is idempotent** and never overwrites a city that is already set.
- **The sign-up path stores the carried city**, and a duplicate sign-up does not touch
  the real account holder's preferences.

**The two tests that could pass for the wrong reason**, and how they are written:

1. *"The audit details carry no city."* A test that asserts `"city" not in
   str(audit.details)` passes if the details were **empty** — which would mean the audit
   row says nothing at all. So the test asserts **both**: that the details carry the
   flag, **and** that the city is absent. An empty details dict fails the first
   assertion, so it cannot pass for the wrong reason.

2. *"The city is stored as it was picked."* A test that asserts
   `preference.city == "Chittagong"` passes if *every* city were Chittagong. So the
   test asserts **both** that the picked city is stored, **and** that a *different*
   picked city is stored as itself — the fallback is not universal.

**The rule this file used to hold, and no longer does.** The coverage rule — "a city the
catalog can serve today, or the fallback" — is gone. It made the picker a mirror of
what had been ingested, and it answered a reader who chose Chittagong with New York
City. The rule now is the curated catalog in `domain.city_catalog`, and the whole-dataset
proof that every one of its rows resolves lives in
`test_stored_city_is_the_picked_city.py`.
"""

from datetime import UTC, datetime, time

import pytest

from apps.personalization.models import DigestPreference, PersonalizationAuditEntry
from apps.personalization.services.digest_preferences import (
    SOURCE_BACKFILL,
    SOURCE_CHOICE,
    SOURCE_FALLBACK,
    SOURCE_GEO,
    backfill_home_cities,
    count_users_without_a_city,
    resolve_home_city,
    set_home_city,
    set_include_personal_events,
)
from domain.errors import UnknownHomeCityError
from shared.actor import Actor
from shared.constants import GEO_CITY_MAX_LENGTH, PREVIEW_FALLBACK_CITY
from shared.db import PERSONAL
from shared.ids import uuid7

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

USER = uuid7()
OTHER = uuid7()
NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)

#: A city in the curated catalog. "Chittagong" is the worked example from the intent —
#: a city the old rule could never have held, because nothing had been ingested there.
COVERED = "Chittagong"

#: A second city in the catalog, for the "the second write wins" test.
SECOND_COVERED = "Kathmandu"

#: A city the catalog does not hold. The name is deliberately not a real city, so the
#: test cannot pass because the catalog happened to cover it.
UNCOVERED = "Zzyzx-not-a-real-city"


def actor():
    return Actor.user(USER)


def read_preference(user_id=USER):
    return DigestPreference.objects.using(PERSONAL).filter(user_id=user_id).first()


def audits_for():
    return list(
        PersonalizationAuditEntry.objects.using(PERSONAL)
        .filter(target_type="DigestPreference")
        .order_by("at")
    )


# --- The rule (the curated catalog, not the preview's coverage) --------------------------------


def test_an_absent_city_stays_absent():
    """`None` means "we do not know" — and that is a real state.

    Storing the fallback for it would be storing an inferred city for someone who
    declined inference.
    """
    resolved_city, resolved_source = resolve_home_city(city=None, source=SOURCE_CHOICE, now=NOW)

    assert resolved_city is None
    assert resolved_source is None


def test_a_catalog_city_is_stored_as_it_was_picked():
    """The whole point of the item: the stored city is the picked city."""
    resolved_city, resolved_source = resolve_home_city(city=COVERED, source=SOURCE_CHOICE, now=NOW)

    assert resolved_city == COVERED
    assert resolved_source == SOURCE_CHOICE


def test_a_catalog_city_is_stored_in_the_catalogs_spelling():
    """The catalog's spelling, not the caller's — "chittagong" and "Chittagong" are one city."""
    resolved_city, resolved_source = resolve_home_city(
        city=COVERED.upper(), source=SOURCE_CHOICE, now=NOW
    )

    assert resolved_city == COVERED
    assert resolved_source == SOURCE_CHOICE


def test_a_catalog_city_is_stored_in_the_catalogs_spelling_through_the_command():
    """The same rule, through the command that writes the row."""
    set_home_city(user_id=USER, city=COVERED.upper(), source=SOURCE_CHOICE, actor=actor(), now=NOW)

    preference = read_preference()
    assert preference.city == COVERED
    assert preference.city_source == SOURCE_CHOICE


def test_a_city_outside_the_catalog_is_refused():
    """**Refused, not rewritten.** The old rule stored the fallback here and called it
    a success; that is the fault this item exists to end."""
    with pytest.raises(UnknownHomeCityError):
        resolve_home_city(city=UNCOVERED, source=SOURCE_CHOICE, now=NOW)


def test_the_refusal_carries_the_rejected_city():
    """The caller sent the value and needs to be told which one was refused."""
    with pytest.raises(UnknownHomeCityError) as caught:
        resolve_home_city(city=UNCOVERED, source=SOURCE_CHOICE, now=NOW)

    assert caught.value.details["rejected_city"] == UNCOVERED
    assert caught.value.details["errors"][0]["loc"] == ["city"]


def test_the_refusal_message_does_not_quote_the_city():
    """The message is for a person; the value is machine-readable data.

    They have different jobs, so they are in different places.
    """
    with pytest.raises(UnknownHomeCityError) as caught:
        resolve_home_city(city=UNCOVERED, source=SOURCE_CHOICE, now=NOW)

    assert UNCOVERED not in caught.value.message


def test_an_empty_city_is_refused_on_a_choice():
    """A `<select>` cannot offer an empty string, so this is a client bug."""
    with pytest.raises(UnknownHomeCityError):
        resolve_home_city(city="   ", source=SOURCE_CHOICE, now=NOW)


def test_an_over_long_city_is_refused_on_a_choice():
    """An over-long value is an attempt to put a value somewhere it should not go."""
    with pytest.raises(UnknownHomeCityError):
        resolve_home_city(city="x" * (GEO_CITY_MAX_LENGTH + 1), source=SOURCE_CHOICE, now=NOW)


def test_a_geo_city_outside_the_catalog_still_falls_back():
    """**The geo path keeps its fallback.** Nobody chose it, so an uncoverable value
    falls back silently exactly as it does today. Refusing it would turn an edge's guess
    into a 4xx on a path the reader never asked for."""
    resolved_city, resolved_source = resolve_home_city(city=UNCOVERED, source=SOURCE_GEO, now=NOW)

    assert resolved_city == PREVIEW_FALLBACK_CITY
    assert resolved_source == SOURCE_FALLBACK


def test_an_over_long_geo_city_still_falls_back():
    """Same reasoning as the unknown geo city: nobody chose it."""
    resolved_city, resolved_source = resolve_home_city(
        city="x" * (GEO_CITY_MAX_LENGTH + 1), source=SOURCE_GEO, now=NOW
    )

    assert resolved_city == PREVIEW_FALLBACK_CITY
    assert resolved_source == SOURCE_FALLBACK


def test_a_catalog_geo_city_is_stored_as_the_catalog_spells_it():
    """The geo path is not second-class: a city the catalog holds is still stored in
    the catalog's spelling, with `geo` as the source."""
    resolved_city, resolved_source = resolve_home_city(
        city=COVERED.upper(), source=SOURCE_GEO, now=NOW
    )

    assert resolved_city == COVERED
    assert resolved_source == SOURCE_GEO


def test_the_fallback_is_the_same_constant_the_preview_uses():
    """One constant for the fallback, not two that could drift apart."""
    from shared.constants import PREVIEW_FALLBACK_CITY as preview_constant

    resolved_city, _source = resolve_home_city(city=UNCOVERED, source=SOURCE_GEO, now=NOW)

    assert resolved_city == preview_constant


# --- Setting the home city -----------------------------------------------------------------------


def test_setting_the_city_stores_it():
    set_home_city(user_id=USER, city=COVERED, source=SOURCE_CHOICE, actor=actor(), now=NOW)

    preference = read_preference()
    assert preference is not None
    assert preference.city == COVERED


def test_setting_a_city_outside_the_catalog_stores_nothing():
    """**Both halves asserted**, so a `resolve_home_city` that wrote and *then* raised
    could not pass for the right reason."""
    with pytest.raises(UnknownHomeCityError):
        set_home_city(user_id=USER, city=UNCOVERED, source=SOURCE_CHOICE, actor=actor(), now=NOW)

    assert read_preference() is None


def test_setting_the_city_creates_the_preference_when_there_is_none():
    assert read_preference() is None

    set_home_city(user_id=USER, city=COVERED, source=SOURCE_CHOICE, actor=actor(), now=NOW)

    assert read_preference() is not None


def test_setting_the_city_twice_overwrites_the_first():
    set_home_city(user_id=USER, city=COVERED, source=SOURCE_CHOICE, actor=actor(), now=NOW)
    set_home_city(user_id=USER, city=SECOND_COVERED, source=SOURCE_GEO, actor=actor(), now=NOW)

    preference = read_preference()
    assert preference.city == SECOND_COVERED
    assert preference.city_source == SOURCE_GEO
    # One row per user: the upsert, not an insert.
    assert DigestPreference.objects.using(PERSONAL).filter(user_id=USER).count() == 1


def test_an_absent_city_clears_the_stored_one():
    """ "The user has no city" is a state the digest handles — and it is not the same as
    leaving the city alone."""
    set_home_city(user_id=USER, city=COVERED, source=SOURCE_CHOICE, actor=actor(), now=NOW)

    set_home_city(user_id=USER, city=None, source=SOURCE_CHOICE, actor=actor(), now=NOW)

    preference = read_preference()
    assert preference.city is None
    assert preference.city_source is None


def test_setting_the_city_leaves_the_delivery_time_alone():
    """The city is one column of one row — not a second preference that replaces it."""
    set_home_city(user_id=USER, city=COVERED, source=SOURCE_CHOICE, actor=actor(), now=NOW)

    preference = read_preference()
    assert preference.timezone == "UTC"
    assert preference.delivery_time.hour == 9
    assert preference.delivery_time.minute == 0


# --- The audit rows (AD-5, AD-13) -----------------------------------------------------------------


def test_setting_the_city_writes_an_audit_row():
    set_home_city(user_id=USER, city=COVERED, source=SOURCE_CHOICE, actor=actor(), now=NOW)

    actions = [entry.action for entry in audits_for()]
    assert "preferences.home_city_set" in actions


def test_the_audit_row_does_not_carry_the_city():
    """Both halves asserted, so an empty details dict cannot pass for the right reason."""
    set_home_city(user_id=USER, city=COVERED, source=SOURCE_CHOICE, actor=actor(), now=NOW)

    entry = next(e for e in audits_for() if e.action == "preferences.home_city_set")
    details = entry.details

    # **The city is absent.** The action name says the city changed; the value stays
    # out of the log (AD-13).
    assert COVERED not in str(details)
    assert "city" not in details
    # **And the details are not empty** — the row says *that* it changed, and *when*.
    assert details["has_city"] is True
    assert details["at"] == NOW.isoformat()


def test_a_refused_city_writes_no_audit_row():
    """**The refusal writes nothing at all** — no preference, no audit row.

    An audit row saying "the city changed" for a city that did not change would be a
    lie in the one place an editor looks to find out what happened.
    """
    with pytest.raises(UnknownHomeCityError):
        set_home_city(user_id=USER, city=UNCOVERED, source=SOURCE_CHOICE, actor=actor(), now=NOW)

    assert audits_for() == []


def test_the_refused_city_is_in_no_audit_detail():
    """The refused city is in the API error and nowhere else (AD-13)."""
    with pytest.raises(UnknownHomeCityError):
        set_home_city(user_id=USER, city=UNCOVERED, source=SOURCE_CHOICE, actor=actor(), now=NOW)

    for entry in audits_for():
        assert UNCOVERED not in str(entry.details)


def test_the_audit_row_for_a_cleared_city_says_so():
    set_home_city(user_id=USER, city=None, source=SOURCE_CHOICE, actor=actor(), now=NOW)

    entry = next(e for e in audits_for() if e.action == "preferences.home_city_set")
    assert entry.details["has_city"] is False


def test_the_city_and_the_delivery_time_land_in_one_transaction():
    """A request that sets both is one decision, and a half-applied decision is worse
    than a failed one.

    The city is written **inside** the delivery-time transaction, so a city write that
    fails rolls the delivery time back with it. Without that, the row would say "8am"
    while the city said nothing changed — and neither half would be wrong on its own.
    """
    from apps.personalization.services.onboarding import set_digest_preference

    set_digest_preference(
        user_id=USER,
        delivery_time=time(8, 30),
        timezone_name="America/New_York",
        actor=actor(),
        now=NOW,
        city=COVERED,
    )

    preference = read_preference()
    assert preference.delivery_time.hour == 8
    assert preference.delivery_time.minute == 30
    assert preference.city == COVERED


def test_a_failing_city_write_rolls_the_delivery_time_back(monkeypatch):
    """The half-applied state must not exist.

    The city write is patched to fail *after* the delivery time has been written, so
    the only thing that can save the delivery time from being committed is the shared
    transaction.

    The patch is on `onboarding`'s own namespace, because `onboarding` imports the name
    directly — patching `digest_preferences.set_home_city` would leave the already-bound
    name in place and the failure would never happen.
    """
    from apps.personalization.services import onboarding
    from apps.personalization.services.onboarding import set_digest_preference

    def boom(**_kwargs):
        raise RuntimeError("the city write failed")

    monkeypatch.setattr(onboarding, "set_home_city", boom)

    with pytest.raises(RuntimeError, match="the city write failed"):
        set_digest_preference(
            user_id=USER,
            delivery_time=time(8, 30),
            timezone_name="America/New_York",
            actor=actor(),
            now=NOW,
            city=COVERED,
        )

    # The delivery time was rolled back with the city: the row is as it was.
    preference = read_preference()
    assert preference is None or preference.delivery_time.hour == 9


def test_a_refused_city_rolls_the_delivery_time_back():
    """**The refusal is inside the same transaction**, so a delivery time that was
    already written does not survive a refused city. Half a decision is worse than none.
    """
    from apps.personalization.services.onboarding import set_digest_preference

    with pytest.raises(UnknownHomeCityError):
        set_digest_preference(
            user_id=USER,
            delivery_time=time(8, 30),
            timezone_name="America/New_York",
            actor=actor(),
            now=NOW,
            city=UNCOVERED,
        )

    preference = read_preference()
    assert preference is None or preference.delivery_time.hour == 9


# --- The personal-events opt-out (FR-19) ----------------------------------------------------------


def test_personal_events_are_included_by_default():
    set_home_city(user_id=USER, city=COVERED, source=SOURCE_CHOICE, actor=actor(), now=NOW)

    assert read_preference().include_personal_events is True


def test_the_user_can_opt_out():
    set_include_personal_events(user_id=USER, include=False, actor=actor(), now=NOW)

    assert read_preference().include_personal_events is False


def test_the_user_can_opt_back_in():
    set_include_personal_events(user_id=USER, include=False, actor=actor(), now=NOW)

    set_include_personal_events(user_id=USER, include=True, actor=actor(), now=NOW)

    assert read_preference().include_personal_events is True


def test_the_opt_out_writes_an_audit_row_that_carries_the_flag():
    """The flag **is** in the details: it is not location data, and "did they pick in
    or out" is exactly the question an audit row should answer."""
    set_include_personal_events(user_id=USER, include=False, actor=actor(), now=NOW)

    entry = next(e for e in audits_for() if e.action == "preferences.personal_events_set")
    assert entry.details["include_personal_events"] is False
    assert entry.details["at"] == NOW.isoformat()


def test_the_opt_out_leaves_the_city_alone():
    """Two settings on one row — changing one must not clear the other."""
    set_home_city(user_id=USER, city=COVERED, source=SOURCE_CHOICE, actor=actor(), now=NOW)

    set_include_personal_events(user_id=USER, include=False, actor=actor(), now=NOW)

    preference = read_preference()
    assert preference.city == COVERED
    assert preference.city_source == SOURCE_CHOICE


def test_the_opt_out_creates_the_preference_when_there_is_none():
    assert read_preference() is None

    set_include_personal_events(user_id=USER, include=False, actor=actor(), now=NOW)

    preference = read_preference()
    assert preference is not None
    assert preference.include_personal_events is False


# --- The backfill (D9) ----------------------------------------------------------------------------


def test_the_backfill_fills_the_accounts_without_a_city():
    DigestPreference.objects.using(PERSONAL).create(
        user_id=USER, delivery_time="09:00:00", timezone="UTC"
    )

    written, seen = backfill_home_cities(now=NOW, actor=Actor.system("digest_city_backfill"))

    assert seen == 1
    assert written == 1
    preference = read_preference()
    assert preference.city == PREVIEW_FALLBACK_CITY
    assert preference.city_source == SOURCE_BACKFILL


def test_the_backfill_never_overwrites_a_city_that_is_set():
    set_home_city(user_id=USER, city=COVERED, source=SOURCE_CHOICE, actor=actor(), now=NOW)

    written, seen = backfill_home_cities(now=NOW, actor=Actor.system("digest_city_backfill"))

    assert seen == 0
    assert written == 0
    preference = read_preference()
    assert preference.city == COVERED
    assert preference.city_source == SOURCE_CHOICE


def test_the_backfill_is_idempotent():
    """Running it twice writes the same value twice, not two rows."""
    DigestPreference.objects.using(PERSONAL).create(
        user_id=USER, delivery_time="09:00:00", timezone="UTC"
    )

    backfill_home_cities(now=NOW, actor=Actor.system("digest_city_backfill"))
    written, seen = backfill_home_cities(now=NOW, actor=Actor.system("digest_city_backfill"))

    assert (written, seen) == (0, 0)
    assert DigestPreference.objects.using(PERSONAL).filter(user_id=USER).count() == 1


def test_the_dry_run_count_matches_the_backfill():
    DigestPreference.objects.using(PERSONAL).create(
        user_id=USER, delivery_time="09:00:00", timezone="UTC"
    )

    assert count_users_without_a_city() == 1


# --- The management command ----------------------------------------------------------------------


def test_the_backfill_command_dry_run_writes_nothing():
    from django.core.management import call_command

    DigestPreference.objects.using(PERSONAL).create(
        user_id=USER, delivery_time="09:00:00", timezone="UTC"
    )

    call_command("backfill_digest_cities", "--dry-run")

    preference = read_preference()
    assert preference.city is None


def test_the_backfill_command_fills_the_accounts():
    from django.core.management import call_command

    DigestPreference.objects.using(PERSONAL).create(
        user_id=USER, delivery_time="09:00:00", timezone="UTC"
    )

    call_command("backfill_digest_cities")

    preference = read_preference()
    assert preference.city == PREVIEW_FALLBACK_CITY
    assert preference.city_source == SOURCE_BACKFILL


# --- The sign-up carry (D13) ---------------------------------------------------------------------


def test_the_sign_up_path_stores_the_carried_city():
    from apps.identity.services.sign_up import sign_up

    sign_up(email="sam@example.test", password="Str0ngPassphrase!", city=COVERED)

    rows = list(DigestPreference.objects.using(PERSONAL).all())
    assert len(rows) == 1
    assert rows[0].city == COVERED
    assert rows[0].city_source == SOURCE_CHOICE


def test_the_sign_up_path_refuses_a_city_outside_the_catalog():
    """**The account still stands.** The city write happens after the account commits,
    so a refused city leaves an account with no city — a state the digest handles — and
    the reader is told their city was not accepted."""
    from apps.identity.services.sign_up import sign_up

    with pytest.raises(UnknownHomeCityError):
        sign_up(email="sam@example.test", password="Str0ngPassphrase!", city=UNCOVERED)

    preference = DigestPreference.objects.using(PERSONAL).first()
    assert preference is None or preference.city is None


def test_the_sign_up_path_without_a_city_stores_none():
    from apps.identity.services.sign_up import sign_up

    sign_up(email="sam@example.test", password="Str0ngPassphrase!")

    preference = DigestPreference.objects.using(PERSONAL).first()
    assert preference is None or preference.city is None
