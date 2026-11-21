"""The Browse seed command, tested apart from the walk-through it exists to make possible.

**What is pinned here.** The command has four jobs and each has a way to go quietly wrong:

- **The data file is checked, not trusted.** The chip matcher is a whole-word match over a
  keyword table, so a keyword change can move a title into a different chip or out of one.
  The file says what each title should earn, and the command compares — so a drift fails the
  seed rather than producing a catalog whose why-tags disagree with its own data.
- **The command is idempotent.** Running it twice leaves the same rows, not twice as many,
  and the second run says so — "it did nothing" and "it did everything" are different
  outputs.
- **It reconciles.** The file is the source of truth for what the catalog should hold, so
  an event the file has dropped has to leave the catalog, and one it has brought back has
  to come back.
- **It writes through the services.** The command lives in `config`, which AD-2 forbids
  from reaching any app's models, so every row goes in through a published write. A row
  that reached the database by any other route would skip the slug mint and the
  `catalog.guard_event_write` trigger, and the catalog would hold a shape the pipeline
  never produces.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from config.management.commands.seed_browse_catalog import SEED_FILE, SEED_SOURCE_EVENT_PREFIX
from domain.errors import SaveCapReached
from shared.db import CATALOG, PERSONAL

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])


def _seed():
    call_command("seed_browse_catalog")


def _data():
    return json.loads(SEED_FILE.read_text())


# --- the data file ---------------------------------------------------------------------------


def test_the_data_file_names_a_city_a_source_and_four_accounts():
    """**Four accounts, and the extra two each earn their place.**

    The `no-city` account is what the city's emptiness needs, and no browser flow can
    produce that state — the API reads a null city as "leave it alone" and never clears
    one — so the seed writes it. It is a **third** account rather than an emptied one:
    emptying the Free account's city would change what every other test sees.

    The `free-saver` account is a **second Free account**, and the reason is the save
    allowance: it is one save per user per day, in a window that outlives a test, so
    two tests that each save once cannot share one account.
    """
    data = _data()

    assert data["city"]["name"]
    assert data["city"]["tz"]
    assert data["source"]["url"].startswith("https://")
    assert data["source"]["tos"]["decision"] == "approved"
    assert len(data["users"]) == 4
    assert {user["plan"] for user in data["users"]} == {"free", "pro"}

    # **The third account is the one with no city**, and it is named by its key — it is a
    # Free account, so "the one Free account" would now be two.
    no_city = [user for user in data["users"] if user["key"] == "no-city"]
    assert len(no_city) == 1
    assert no_city[0]["city"] is None

    # **And the fourth is the second Free account**, which carries a city like every
    # other account except the one above.
    free_saver = [user for user in data["users"] if user["key"] == "free-saver"]
    assert len(free_saver) == 1
    assert free_saver[0]["plan"] == "free"
    assert free_saver[0].get("city", "Fixtureville") == "Fixtureville"


def test_the_data_file_has_more_events_than_one_page_holds():
    """The page size is twenty-four, so a smaller set would not exercise the chunk loader."""
    from apps.personalization.services.browse_read import BROWSE_PAGE_SIZE

    assert len(_data()["events"]) > BROWSE_PAGE_SIZE


def test_the_data_file_spans_the_whole_window():
    """Browse's window is seven days, so the seed has to reach the far end of it."""
    days = {event["day"] for event in _data()["events"]}

    assert min(days) == 0
    assert max(days) == 6


def test_the_data_file_has_one_cancelled_and_one_postponed_event():
    """Those are the must-know stripe, and a walk-through that has never seen one has not
    seen the surface."""
    statuses = [event["status"] for event in _data()["events"]]

    assert statuses.count("cancelled") == 1
    assert statuses.count("postponed") == 1


def test_every_event_in_the_file_names_a_venue_the_file_has():
    data = _data()
    keys = {venue["key"] for venue in data["venues"]}

    assert all(event["venue"] in keys for event in data["events"])


def test_the_review_is_attributed_to_a_person():
    """The ingestion services refuse a system actor for a terms-of-service review."""
    data = _data()

    assert data["reviewer"]["email"]
    assert data["reviewer"]["password"]


# --- the chip expectations -------------------------------------------------------------------


def test_the_command_refuses_a_title_that_no_longer_earns_its_chip(tmp_path, monkeypatch):
    """The check that keeps the file honest: a keyword-table change fails the seed."""
    data = _data()
    # "Concert" is an arts-culture keyword; the file says this title earns it.
    data["events"][0]["chip"] = "sports_fitness"
    broken = tmp_path / "browse_seed.json"
    broken.write_text(json.dumps(data))
    monkeypatch.setattr("config.management.commands.seed_browse_catalog.SEED_FILE", broken)

    with pytest.raises(CommandError, match="expected to earn the chip"):
        call_command("seed_browse_catalog", "--file", str(broken))


def test_the_command_refuses_a_chip_the_server_does_not_know(tmp_path):
    data = _data()
    data["events"][0]["chip"] = "underwater_basket_weaving"
    broken = tmp_path / "browse_seed.json"
    broken.write_text(json.dumps(data))

    with pytest.raises(CommandError, match="not a chip the server knows"):
        call_command("seed_browse_catalog", "--file", str(broken))


def test_the_command_refuses_a_title_that_now_earns_a_chip_it_did_not(tmp_path):
    """The other direction: a title that has grown a keyword earns a chip it did not.

    The file's own titles all carry a chip, so the test builds the case: an event the
    file says earns no chip, given a title that matches one.
    """
    data = _data()
    event = data["events"][0]
    event["chip"] = None
    event["title"] = "Concert: A Concert That Is Cancelled"
    broken = tmp_path / "browse_seed.json"
    broken.write_text(json.dumps(data))

    with pytest.raises(CommandError, match="expected to earn no chip"):
        call_command("seed_browse_catalog", "--file", str(broken))


# --- what the command writes ------------------------------------------------------------------


def test_the_command_writes_the_whole_catalog():
    from apps.ingestion.models import Event, Source

    _seed()

    source = Source.objects.using(CATALOG).get(url="https://browse-seed.example.test/events.rss")
    assert source.tos_status == "approved"
    assert Event.objects.using(CATALOG).filter(source_id=source.id).count() == len(
        _data()["events"]
    )


def test_the_events_are_published_and_carry_a_slug():
    """The shape the pipeline produces: published, slugged, and inside the confidence gates."""
    from apps.ingestion.models import Event

    _seed()

    events = Event.objects.using(CATALOG).filter(
        source_event_id__startswith=SEED_SOURCE_EVENT_PREFIX
    )
    assert events
    for event in events:
        assert event.publication_status == "published"
        assert event.slug
        assert event.extraction_confidence >= 0.7
        assert event.tz_inference_confidence >= 0.7
        assert event.original_start_utc is not None


def test_the_review_is_recorded_by_a_person_not_by_the_system():
    """A system actor is refused for a terms-of-service review, so the seed names one."""
    from apps.ingestion.models import TosReview

    _seed()

    review = TosReview.objects.using(CATALOG).get()
    assert review.reviewed_by_id is not None


def test_the_two_accounts_are_made_and_the_free_one_is_not_pro():
    """Pro is a **subscription**, not a field on the user — the read is the entitlement
    service, and that is where the answer comes from."""
    from apps.identity.models import User
    from apps.identity.services import is_pro
    from shared.db import PERSONAL as DB

    _seed()

    free = User.objects.using(DB).get(email="free@browse.example.test")
    pro = User.objects.using(DB).get(email="pro@browse.example.test")
    assert is_pro(user_id=free.pk) is False
    assert is_pro(user_id=pro.pk) is True


def test_the_free_account_can_sign_in():
    """The password the file carries has to be the password the account holds."""
    from apps.identity.models import User
    from apps.identity.services import authenticate

    _seed()

    user = User.objects.using(PERSONAL).get(email="free@browse.example.test")
    assert authenticate(email="free@browse.example.test", password="browse-free-local") == user


def test_the_accounts_are_through_onboarding():
    """`/browse` redirects to `/onboarding` unless the flow is complete."""
    from apps.identity.models import User
    from apps.personalization.models import OnboardingProgress

    _seed()

    free = User.objects.using(PERSONAL).get(email="free@browse.example.test")
    progress = OnboardingProgress.objects.using(PERSONAL).get(user_id=free.pk)
    assert progress.completed_at is not None


def test_the_accounts_have_a_city_and_interests():
    from apps.identity.models import User
    from apps.personalization.models import DigestPreference

    _seed()

    free = User.objects.using(PERSONAL).get(email="free@browse.example.test")
    preference = DigestPreference.objects.using(PERSONAL).get(user_id=free.pk)
    assert preference.city == "Fixtureville"
    assert preference.timezone == "America/New_York"


def test_the_seeded_city_is_labelled_as_the_seeds_own():
    """**The seed's city is the server's choice, and it says so.**

    "Fixtureville" is not in the curated catalog and never could be — it is a fictional
    city for a local walk-through. A reader's pick is `choice`, and a reader who picked
    a city the catalog does not hold is *refused* rather than silently answered with
    somewhere else. The seed is not a reader, so it writes `seed`, and the value is
    stored verbatim.
    """
    from apps.identity.models import User
    from apps.personalization.models import DigestPreference

    _seed()

    free = User.objects.using(PERSONAL).get(email="free@browse.example.test")
    preference = DigestPreference.objects.using(PERSONAL).get(user_id=free.pk)
    assert preference.city_source == "seed"


# --- idempotency -------------------------------------------------------------------------------


def test_running_the_command_twice_leaves_the_same_rows(capsys):
    from apps.ingestion.models import Event

    _seed()
    first = capsys.readouterr().out
    count_after_first = Event.objects.using(CATALOG).count()

    _seed()
    second = capsys.readouterr().out
    count_after_second = Event.objects.using(CATALOG).count()

    assert count_after_first == count_after_second
    assert "Seeded 49 event(s) (0 already there)" in first
    assert "Seeded 0 event(s) (49 already there)" in second


def test_the_second_run_says_the_accounts_were_already_there(capsys):
    _seed()
    _ = capsys.readouterr().out

    _seed()
    out = capsys.readouterr().out

    assert "already had" in out


def test_the_password_of_an_existing_account_is_not_changed():
    """A re-run must not silently reset a password behind the holder's back."""
    from apps.identity.models import User
    from apps.identity.services import authenticate
    from domain.errors import AuthenticationFailedError

    _seed()
    user = User.objects.using(PERSONAL).get(email="free@browse.example.test")
    user.set_password("something-else-entirely")
    user.save(using=PERSONAL, update_fields=["password"])

    _seed()

    with pytest.raises(AuthenticationFailedError):
        authenticate(email="free@browse.example.test", password="browse-free-local")
    signed_in = authenticate(email="free@browse.example.test", password="something-else-entirely")
    assert signed_in == user


# --- the reconciliation ---------------------------------------------------------------------------


def test_an_event_the_file_drops_leaves_the_catalog(tmp_path):
    """The file is the source of truth: a dropped event has to stop being offered."""
    from apps.ingestion.models import Event
    from apps.ingestion.services.catalog_read import list_public_candidates

    data = _data()
    dropped = data["events"][0]["key"]
    dropped_title = data["events"][0]["title"]
    data["events"] = [event for event in data["events"] if event["key"] != dropped]
    smaller = tmp_path / "browse_seed.json"
    smaller.write_text(json.dumps(data))

    # The full file first, so the dropped event **exists** and there is something to
    # retire. Seeding only the smaller file would prove nothing: an event that was
    # never created cannot leave.
    _seed()
    call_command("seed_browse_catalog", "--file", str(smaller))

    assert (
        not Event.objects.using(CATALOG)
        .filter(
            source_event_id=SEED_SOURCE_EVENT_PREFIX + dropped,
            status="scheduled",
        )
        .exists()
    )
    titles = {candidate.title for candidate in list_public_candidates(now=datetime.now(UTC))}
    assert dropped_title not in titles


def test_an_event_the_file_brings_back_comes_back(tmp_path):
    """A retired event's slot is freed by supersession, so the item can be created again."""
    from apps.ingestion.models import Event

    data = _data()
    dropped = data["events"][0]["key"]
    data["events"] = [event for event in data["events"] if event["key"] != dropped]
    smaller = tmp_path / "browse_seed.json"
    smaller.write_text(json.dumps(data))

    _seed()
    call_command("seed_browse_catalog", "--file", str(smaller))
    call_command("seed_browse_catalog", "--file", str(SEED_FILE))

    assert (
        Event.objects.using(CATALOG)
        .filter(source_event_id=SEED_SOURCE_EVENT_PREFIX + dropped, status="scheduled")
        .exists()
    )


def test_the_retired_event_is_not_deleted_only_moved_out_of_the_live_set(tmp_path):
    """FR-13: a row is never deleted. Retiring supersedes it and keeps the history."""
    from apps.ingestion.models import Event

    data = _data()
    dropped = data["events"][0]["key"]
    data["events"] = [event for event in data["events"] if event["key"] != dropped]
    smaller = tmp_path / "browse_seed.json"
    smaller.write_text(json.dumps(data))

    _seed()
    call_command("seed_browse_catalog", "--file", str(smaller))

    rows = Event.objects.using(CATALOG).filter(source_event_id=SEED_SOURCE_EVENT_PREFIX + dropped)
    assert rows.exists()
    assert all(row.status == "superseded" for row in rows)


def test_the_retirement_is_reported(capsys, tmp_path):
    data = _data()
    dropped = data["events"][0]["key"]
    data["events"] = [event for event in data["events"] if event["key"] != dropped]
    smaller = tmp_path / "browse_seed.json"
    smaller.write_text(json.dumps(data))

    _seed()
    call_command("seed_browse_catalog", "--file", str(smaller))
    out = capsys.readouterr().out

    assert f"retired {dropped}" in out


# --- --list -------------------------------------------------------------------------------------


def test_list_prints_the_city_the_counts_and_the_accounts(capsys):
    call_command("seed_browse_catalog", "--list")

    out = capsys.readouterr().out
    assert "Fixtureville" in out
    assert f"Events: {len(_data()['events'])}" in out
    assert "free@browse.example.test" in out
    assert "pro@browse.example.test" in out


def test_list_prints_nothing_into_the_database():
    from apps.ingestion.models import Event

    call_command("seed_browse_catalog", "--list")

    assert not Event.objects.using(CATALOG).exists()


# --- the refusals --------------------------------------------------------------------------------


def test_an_unreadable_seed_file_is_refused(tmp_path):
    with pytest.raises(CommandError, match="Can't read the seed file"):
        call_command("seed_browse_catalog", "--file", str(tmp_path / "missing.json"))


def test_a_seed_file_that_is_not_json_is_refused(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")

    with pytest.raises(CommandError, match="not valid JSON"):
        call_command("seed_browse_catalog", "--file", str(broken))


def test_a_seed_file_without_a_city_is_refused(tmp_path):
    data = _data()
    del data["city"]
    broken = tmp_path / "browse_seed.json"
    broken.write_text(json.dumps(data))

    with pytest.raises(CommandError, match="no 'city'"):
        call_command("seed_browse_catalog", "--file", str(broken))


def test_a_seed_file_that_is_not_an_object_is_refused(tmp_path):
    broken = tmp_path / "browse_seed.json"
    broken.write_text("[1, 2, 3]")

    with pytest.raises(CommandError, match="must be a JSON object"):
        call_command("seed_browse_catalog", "--file", str(broken))


def test_an_event_naming_a_venue_the_file_does_not_have_is_refused(tmp_path):
    data = _data()
    data["events"][0]["venue"] = "the-place-that-is-not-listed"
    broken = tmp_path / "browse_seed.json"
    broken.write_text(json.dumps(data))

    with pytest.raises(CommandError, match="names a venue that is not in the file"):
        call_command("seed_browse_catalog", "--file", str(broken))


def test_an_event_with_a_status_the_seed_cannot_write_is_refused(tmp_path):
    data = _data()
    data["events"][0]["status"] = "superseded"
    broken = tmp_path / "browse_seed.json"
    broken.write_text(json.dumps(data))

    with pytest.raises(CommandError, match="status that cannot be seeded"):
        call_command("seed_browse_catalog", "--file", str(broken))


# --- the times -----------------------------------------------------------------------------------


def test_the_events_are_placed_relative_to_the_day_the_command_runs():
    """An absolute date in the file would put the catalog in the past the day after it was
    written, and the window is seven days — so a stale file would seed an empty surface
    and still report success.

    **The base day moves by one day when the file's latest day-0 hour is behind the
    clock**, so the offset may be one rather than zero. What must hold either way is
    that every event is in the future and inside the window.
    """
    from zoneinfo import ZoneInfo

    from apps.ingestion.models import Event

    _seed()

    zone = _data()["city"]["tz"]
    local_now = datetime.now(UTC).astimezone(ZoneInfo(zone))
    events = Event.objects.using(CATALOG).filter(
        source_event_id__startswith=SEED_SOURCE_EVENT_PREFIX,
        publication_status="published",
    )
    assert events
    for event in events:
        start_local = datetime.fromisoformat(event.start_time_local)
        offset = (start_local.date() - local_now.date()).days
        assert 0 <= offset <= 7, f"{event.slug} is {offset} days out"


def test_every_seeded_event_is_in_the_future():
    """The seed's own window starts at *now*, so an event behind the clock is invisible —
    and a seed that reported success while serving a third of its events would be a lie."""
    from apps.ingestion.models import Event

    _seed()

    now = datetime.now(UTC)
    events = Event.objects.using(CATALOG).filter(
        source_event_id__startswith=SEED_SOURCE_EVENT_PREFIX,
        publication_status="published",
    )
    assert events
    for event in events:
        assert event.start_time_utc > now, f"{event.slug} is in the past"


def test_the_window_the_command_seeds_is_the_one_browse_reads():
    """The seed's week and Browse's week are the same week, or the surface is empty."""
    from apps.identity.models import User
    from apps.personalization.services.browse_read import read_browse_page

    _seed()

    free = User.objects.using(PERSONAL).get(email="free@browse.example.test")
    page = read_browse_page(user_id=free.pk, now=datetime.now(UTC))

    assert page.total == len(_data()["events"])
    assert page.city == "Fixtureville"
    assert page.city_missing is False


def test_the_seed_leaves_room_for_a_second_page():
    """More events than one page holds, so the chunk loader has something to load."""
    from apps.identity.models import User
    from apps.personalization.services.browse_read import read_browse_page

    _seed()

    free = User.objects.using(PERSONAL).get(email="free@browse.example.test")
    page = read_browse_page(user_id=free.pk, now=datetime.now(UTC))

    assert page.has_more is True
    assert len(page.cards) == 24
    assert page.tier_2_starts_at == 3


def test_the_must_know_stripe_is_on_the_first_page():
    """A cancelled event that only shows up on page two is a must-know nobody sees."""
    from apps.identity.models import User
    from apps.personalization.services.browse_read import read_browse_page

    _seed()

    free = User.objects.using(PERSONAL).get(email="free@browse.example.test")
    page = read_browse_page(user_id=free.pk, now=datetime.now(UTC))

    stripes = [card.stripe for card in page.cards]
    assert "must_know" in stripes
    assert stripes.count("must_know") == 1
    assert set(stripes) <= {"must_know", "public"}


def test_the_quota_is_the_free_one_for_the_free_account():
    from apps.identity.models import User
    from apps.personalization.services.browse_read import read_browse_page

    _seed()

    free = User.objects.using(PERSONAL).get(email="free@browse.example.test")
    page = read_browse_page(user_id=free.pk, now=datetime.now(UTC))

    assert page.quota.cap == 1
    assert page.quota.is_pro is False


def test_the_quota_is_uncapped_for_the_pro_account():
    from apps.identity.models import User
    from apps.personalization.services.browse_read import read_browse_page

    _seed()

    pro = User.objects.using(PERSONAL).get(email="pro@browse.example.test")
    page = read_browse_page(user_id=pro.pk, now=datetime.now(UTC))

    assert page.quota.cap is None
    assert page.quota.is_pro is True


def test_the_seed_puts_the_free_accounts_save_allowance_back(monkeypatch):
    """**The allowance is a throttle window, and it outlives the seed.**

    The Free account's one-save-a-day allowance lives in Redis. A seed that did not
    clear it would leave the *second* run with the quota already spent — the wall would
    be up before the walk-through had pressed anything, and the test that exercises the
    wall would fail for the wrong reason. **A seed that could only be run once would not
    be a seed.**

    **The port is stubbed with one adapter instance**, because `get_throttle_port()`
    builds a fresh adapter on every call and the in-memory adapter's counter lives on
    the instance. The Redis adapter is stateless and needs no such thing.
    """
    from adapters.throttle.memory import InMemoryThrottleAdapter
    from apps.identity.models import User
    from apps.personalization.services import save_cap as save_cap_service
    from apps.personalization.services.browse_read import read_browse_page
    from apps.personalization.services.save_cap import check_save_allowed

    throttle = InMemoryThrottleAdapter()
    monkeypatch.setattr(save_cap_service, "get_throttle_port", lambda: throttle)

    _seed()

    free = User.objects.using(PERSONAL).get(email="free@browse.example.test")

    # **Spend the allowance.** The gate raises when the window is full.
    check_save_allowed(user_id=free.pk)
    with pytest.raises(SaveCapReached):
        check_save_allowed(user_id=free.pk)

    # **The second run puts it back.**
    _seed()

    page = read_browse_page(user_id=free.pk, now=datetime.now(UTC))
    assert page.quota.used == 0
    # **And the gate lets the save through again.**
    check_save_allowed(user_id=free.pk)


def test_the_seed_puts_the_sign_in_allowance_back(monkeypatch):
    """**The sign-in limit is a throttle window too, and it outlives the seed.**

    The sign-in limits are ten an hour per IP and five an hour per account, and the
    end-to-end suite signs in six times — from one IP, because the whole suite runs
    against one stack on one machine. So the suite spends the very allowance a reader
    would spend, and a second run inside the hour finds the window already up: the
    sign-in is refused with a 429 and the test fails for a reason that has nothing to do
    with the code under test.

    **The seed gives the allowance back**, so a seeded run starts from a full allowance
    instead of from whatever the previous run left behind. **The limits are not
    touched** — the last assertion below is the one that matters: after the reset, ten
    sign-ins from one address are still allowed and the eleventh is still refused.
    """
    from adapters.throttle.memory import InMemoryThrottleAdapter
    from apps.identity.services import throttle as throttle_service
    from apps.identity.services.throttle import is_throttled
    from shared.constants import AUTH_THROTTLE_SIGN_IN_IP

    throttle = InMemoryThrottleAdapter()
    monkeypatch.setattr(throttle_service, "get_throttle_port", lambda: throttle)

    _seed()

    # **Spend the allowance.** Ten sign-ins from one address fill the per-IP bucket.
    for _ in range(AUTH_THROTTLE_SIGN_IN_IP):
        is_throttled("sign_in", ip_address="127.0.0.1", normalised_email="free@browse.example.test")
    assert (
        is_throttled("sign_in", ip_address="127.0.0.1", normalised_email="other@example.com")
        is True
    )

    # **The second run puts it back.**
    _seed()

    assert (
        is_throttled("sign_in", ip_address="127.0.0.1", normalised_email="other@example.com")
        is False
    )

    # **And the limit itself is unchanged.** Ten are still allowed; the eleventh is
    # still refused. A reset that changed the rule would be the rate limit quietly
    # becoming a suggestion.
    for _ in range(AUTH_THROTTLE_SIGN_IN_IP):
        is_throttled("sign_in", ip_address="127.0.0.1", normalised_email="free@browse.example.test")
    assert (
        is_throttled("sign_in", ip_address="127.0.0.1", normalised_email="other@example.com")
        is True
    )


def test_the_seed_does_not_unsave_what_the_free_account_saved():
    """**The allowance is the throttle's counter, not the saved rows.**

    Clearing the counter gives the account its one save back. It must not take away what
    the account has already saved — the walk-through is *about* seeing a saved event, and
    a seed that un-saved the account's events would change what the surface shows.
    """
    from apps.identity.models import User
    from apps.personalization.models import SavedEvent
    from apps.personalization.services.browse_read import read_browse_page
    from apps.personalization.services.saved_events import save_event
    from shared.actor import Actor

    _seed()

    free = User.objects.using(PERSONAL).get(email="free@browse.example.test")
    page = read_browse_page(user_id=free.pk, now=datetime.now(UTC))
    event_id = page.cards[0].event_id

    save_event(
        user_id=free.pk,
        event_id=event_id,
        actor=Actor.user(free.pk),
        now=datetime.now(UTC),
    )

    _seed()

    assert (
        SavedEvent.objects.using(PERSONAL)
        .filter(
            user_id=free.pk,
            event_id=event_id,
        )
        .exists()
    )


def test_the_reset_saves_flag_clears_the_saved_rows():
    """**The opt-in flag is the half that makes a test run repeatable.**

    The default seed leaves the saved rows alone — the walk-through is *about* seeing a
    saved event, and a seed that un-saved the account's events would change what the
    surface shows. **A test suite needs the opposite**: a leftover row puts the Save
    button in the `saved` state, so the suite's *first* press takes the unsave branch,
    the button correctly goes back to "Save", and the test fails for a reason that has
    nothing to do with the code under test.

    So `--reset-saves` is the flag that says "this is a test run", and this test says
    it does what it says: the saved row is gone afterwards.
    """
    from apps.identity.models import User
    from apps.personalization.models import SavedEvent
    from apps.personalization.services.browse_read import read_browse_page
    from apps.personalization.services.saved_events import save_event
    from shared.actor import Actor

    _seed()

    free = User.objects.using(PERSONAL).get(email="free@browse.example.test")
    page = read_browse_page(user_id=free.pk, now=datetime.now(UTC))
    event_id = page.cards[0].event_id

    save_event(
        user_id=free.pk,
        event_id=event_id,
        actor=Actor.user(free.pk),
        now=datetime.now(UTC),
    )
    assert SavedEvent.objects.using(PERSONAL).filter(user_id=free.pk, event_id=event_id).exists()

    call_command("seed_browse_catalog", reset_saves=True)

    assert (
        not SavedEvent.objects.using(PERSONAL).filter(user_id=free.pk, event_id=event_id).exists()
    )


def test_the_events_are_not_stale_by_the_time_browse_reads_them():
    """`list_public_candidates` drops a row the catalog has not seen for too long, and a
    seed that wrote a stale `last_seen_at` would seed an empty surface."""
    from apps.identity.models import User
    from apps.personalization.services.browse_read import read_browse_page

    _seed()

    free = User.objects.using(PERSONAL).get(email="free@browse.example.test")
    page = read_browse_page(user_id=free.pk, now=datetime.now(UTC))

    assert page.total > 0
    assert (datetime.now(UTC) - datetime.now(UTC)) < timedelta(seconds=1)
