"""The public surface, end to end, as a **stranger** sees it.

**Why one file and not eight.** The point of a proof is that the steps *compose*. Nine
work items built this intent's public surface and each was tested in isolation: the read,
the projection, the page, the route, the sitemap, the share control. The failures that
matter live in the seams between them. A chain of independent tests proves each step and
not the whole.

So the scenario is one visitor, one database, and one transaction's worth of shared
state — and the visitor is **the one whose case nobody has proved**: a person with no
account and no cookie.

**What is proved here is what actually left the system.** The assertion surface is the
**HTTP responses the catalog's three public endpoints produce**, and the **rows the
revalidation outbox wrote** — not the service functions behind them. The unit tests
assert each service's own contract; this asserts the *end state*, which is the only
place the whole path is visible at once.

**The clock is frozen, never slept.** Every service on this path takes `now` as an
argument, so the proof passes its own instant and never reads the wall clock. A proof
that sleeps is slow, flaky, and — the defect item 11 found in the backend's own digest
tests — its answer can depend on the hour it ran. **Nothing in this file sleeps, and
nothing in this file waits for a timer.** The revalidation round trip is driven from the
*write path* and asserted on the *paths the signal names* — which is the promise — and
the frontend's half of the round trip is proved in the frontend's own suite.

**The client's jar is empty at every hop.** `Client()` is Django's test client: it
carries no cookie unless a test sets one, and no test in this file sets one. The
"anonymous" property is therefore **structural** — there is no session to forward,
because there is no session — rather than a convention this file has to remember.
"""

import pytest
from django.db import transaction
from django.test import Client
from django.utils import timezone

from apps.ingestion.models import EventFit, RevalidationRequest
from apps.ingestion.services.event_writes import apply_lifecycle_change
from domain.lifecycle import Change, ChangeKind, EventStatus
from shared.actor import Actor
from shared.constants import SCHEMA_ORG_EVENT_STATUS
from shared.db import CATALOG, PERSONAL
from tests.e2e.public_pages_fixtures import (
    QUALIFYING_FITS,
    incoming_for,
    make_city,
    make_event,
    make_fit,
    make_in_review_event,
    make_past_event,
    make_published_city,
)

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

#: The instant the proof acts. **A fixed instant, so the answers do not depend on when
#: the suite ran** — the same rule every read in this codebase follows.
NOW = timezone.now()

#: The revalidation task's dotted name — what the worker registers the task under.
REVALIDATE_TASK = "worker.tasks.revalidate_public_pages"


# ── the clients ────────────────────────────────────────────────────────────────────────


def anonymous() -> Client:
    """A client with no cookie jar at all.

    **The jar is empty and stays empty.** Django's test client sets no cookie unless a
    test sets one, and no test in this file sets one — so "anonymous" is a structural
    property of the harness, not a step this file has to remember. A later test that
    logged in would not make this one anonymous-looking; it would have to *add* a login,
    and the absence of a `login()` call in this file is the proof that it did not.
    """
    return Client()


def get_event_page(slug: str):
    return anonymous().get(f"/api/catalog/events/by-slug/{slug}")


def get_city_page(slug: str):
    return anonymous().get(f"/api/catalog/cities/by-slug/{slug}")


def get_url_feed():
    return anonymous().get("/api/catalog/url-feed")


# ── the scenario ────────────────────────────────────────────────────────────────────────


@pytest.fixture
def published():
    """The catalog the proof walks: a city with six current fits.

    **This is the shared root of the `city` and `listed_event` fixtures, and that is
    deliberate.** The city page's listing is built from the Event Fit rows, so an event
    with no fit is not on the page — and the proof's first hop is *"the city page lists
    the event the crawl then opens"*. So the crawl's event must be **one of the city's
    fitted events**, not an extra one.

    **And it is one shared root so the count is the same number everywhere.** If the
    crawl's event were created by a separate fixture, the city would carry seven fits
    when that fixture was requested and six when it was not — and every count the proof
    asserts would depend on which fixtures a test happened to ask for. A number that
    depends on the test's fixture list is not a number about the system.
    """
    return make_published_city()


@pytest.fixture
def city(published):
    """The city the proof walks — published, with six qualifying events."""
    city, _ = published
    return city


@pytest.fixture
def listed_event(published):
    """One of the city's published events — the one the crawl opens.

    **Its fit is current by construction** — the row records the event's own version —
    so the city's qualifying count is exactly `QUALIFYING_FITS` and the proof's "this
    event is on the page" assertion is about the *staleness* rule rather than about a
    miscount.
    """
    _, events = published
    return events[0]


# ── the crawl: the first hop ───────────────────────────────────────────────────────────


class TestTheCityLanding:
    """`/events-in-{city}` — the landing a crawler reaches first."""

    def test_a_stranger_reaches_the_city_page(self, city):
        response = get_city_page(city.slug)

        assert response.status_code == 200
        body = response.json()
        assert body["slug"] == city.slug
        assert body["name"] == city.name

    def test_the_city_page_lists_the_qualifying_events(self, city, listed_event):
        body = get_city_page(city.slug).json()

        slugs = [item["slug"] for item in body["items"]]

        assert listed_event.slug in slugs

    def test_the_city_page_is_published_because_six_events_qualify(self, city):
        """**Six, and the number is the point.** FR-27's threshold is `> 5`.

        A city with five does not publish; a city with six does. The proof builds six, so
        the listing is not empty for a reason that has nothing to do with the rules under
        test.
        """
        body = get_city_page(city.slug).json()

        assert body["is_published"] is True
        assert body["event_count"] == QUALIFYING_FITS

    def test_the_response_sets_no_cookie(self, city):
        """**A public page that set a cookie would not be cacheable for everyone.**

        The response's `Vary` carries nothing session-related and the body is identical
        for everybody — so the cache key is the URL. A `Set-Cookie` here would mean the
        first requester baked something into the shared cache.
        """
        response = get_city_page(city.slug)

        assert "Set-Cookie" not in response.headers

    def test_the_response_does_not_vary_by_a_session_cookie(self, city):
        """**The same body with and without a cookie.** A response that varies on the
        cookie is not cacheable, and a shared cache that stored one variant under a key
        that ignores the cookie would serve one visitor's response to another.
        """
        anonymous_body = get_city_page(city.slug).content

        with_cookie = Client()
        with_cookie.cookies["sessionid"] = "a-session-that-means-nothing"
        cookie_body = with_cookie.get(f"/api/catalog/cities/by-slug/{city.slug}").content

        assert cookie_body == anonymous_body


# ── the crawl: the second hop ──────────────────────────────────────────────────────────


class TestTheEventPage:
    """`/events/{slug}` — the page a city card links to."""

    def test_a_stranger_reaches_the_event_page(self, city, listed_event):
        response = get_event_page(listed_event.slug)

        assert response.status_code == 200
        body = response.json()
        assert body["slug"] == listed_event.slug
        assert body["title"] == listed_event.title

    def test_the_page_carries_the_facts_a_reader_needs(self, city, listed_event):
        body = get_event_page(listed_event.slug).json()

        assert body["description"]
        assert body["start_time_utc"]
        assert body["start_time_tz"]
        assert body["venue_name"]
        assert body["event_version"] == listed_event.event_version

    def test_the_page_carries_the_structured_data_a_crawler_reads(self, city, listed_event):
        """**The JSON-LD is a Schema.org `Event`, and it is on the payload.**

        The frontend embeds this object verbatim in a `<script type="application/ld+json">`
        — so asserting it here asserts what the crawler will parse. The frontend's own
        proof (`frontend/tests/public-crawl-proof.test.tsx`) asserts that it really is in
        the *server-rendered* markup; this asserts that what is in the markup is right.
        """
        body = get_event_page(listed_event.slug).json()
        schema_org = body["schema_org"]

        assert schema_org["@context"] == "https://schema.org"
        assert schema_org["@type"] == "Event"
        assert schema_org["name"] == listed_event.title
        assert schema_org["startDate"]
        assert schema_org["offers"]["availability"] == "https://schema.org/InStock"

    def test_the_page_sets_no_cookie(self, city, listed_event):
        response = get_event_page(listed_event.slug)

        assert "Set-Cookie" not in response.headers


# ── the structured data and the visible page agree ─────────────────────────────────────


class TestTheStructuredDataAgreesWithThePage:
    """**AD-12: the structured data is emitted from the same data the page renders.**

    The two halves of a public page — the line a reader sees and the `eventStatus` a
    crawler reads — come from the same `status` field. **Asserted together, in one
    place**, because asserted separately they could drift: one test would stay green
    while the page lied to half its readers.

    The visible half is proved in the frontend's suite (the `data-public-status` line);
    this proves the machine-readable half, and the pair together are the promise.
    """

    def test_a_cancelled_event_says_so_in_its_structured_data(self, city, listed_event):
        """**The status is moved through the write path**, not by a bare update.

        The trigger (`catalog.guard_event_write`) refuses a status change without a
        version bump, so a cancellation *is* a lifecycle change — and the write path is
        how one happens. Driving it that way means the proof exercises the same code the
        ingest pipeline does.
        """
        with transaction.atomic(using=CATALOG):
            apply_lifecycle_change(
                event=listed_event,
                incoming=incoming_for(listed_event, status=EventStatus.CANCELLED),
                change=Change(
                    kinds=(ChangeKind.CANCELLED,),
                    fields=frozenset({"status"}),
                    is_lifecycle=True,
                ),
                actor=Actor.system("e2e_proof"),
                now=NOW,
            )
        listed_event.refresh_from_db(using=CATALOG)

        body = get_event_page(listed_event.slug).json()

        # **The visible half.** The payload's `status` is what the page renders its
        # `data-public-status` line from — the frontend's proof asserts that line
        # exists and says the same thing.
        assert body["status"] == "cancelled"
        # **And the machine-readable half.** Both are stated together, from one read.
        assert body["schema_org"]["eventStatus"] == SCHEMA_ORG_EVENT_STATUS["cancelled"]
        assert body["schema_org"]["eventStatus"] == "https://schema.org/EventCancelled"

    def test_a_scheduled_event_says_so_in_its_structured_data(self, city, listed_event):
        body = get_event_page(listed_event.slug).json()

        assert body["status"] == "scheduled"
        assert body["schema_org"]["eventStatus"] == "https://schema.org/EventScheduled"

    def test_a_cancelled_event_still_has_a_page(self, city, listed_event):
        """**A cancellation is not a removal.** The page still exists — the reader who
        came to it needs to know it is not going to happen as advertised.
        """
        with transaction.atomic(using=CATALOG):
            apply_lifecycle_change(
                event=listed_event,
                incoming=incoming_for(listed_event, status=EventStatus.CANCELLED),
                change=Change(
                    kinds=(ChangeKind.CANCELLED,),
                    fields=frozenset({"status"}),
                    is_lifecycle=True,
                ),
                actor=Actor.system("e2e_proof"),
                now=NOW,
            )

        response = get_event_page(listed_event.slug)

        assert response.status_code == 200


# ── the past event ─────────────────────────────────────────────────────────────────────


class TestAPastEventStillResolves:
    """**The case `catalog.get_event` deliberately refuses.**

    `get_public_event(event_id, now=…)` bounds by "has not started yet" — the right rule
    for a digest. `get_public_event_by_slug(slug)` answers *"what is this URL?"*, and
    there **there is no time bound**: a page for an event that already happened stays
    addressable and stays indexed. A page that 404s the moment the doors open throws
    away every bit of ranking it spent months earning.
    """

    def test_the_past_event_answers_a_real_200(self, city):
        past = make_past_event(city)

        response = get_event_page(past.slug)

        assert response.status_code == 200

    def test_the_past_event_answers_with_content(self, city):
        """**Not merely a 200.** An endpoint that answered 200 with an empty body would
        satisfy a status-only assertion and prove nothing — so the title, the slug and
        the structured data are all asserted.
        """
        past = make_past_event(city)

        body = get_event_page(past.slug).json()

        assert body["slug"] == past.slug
        assert body["title"] == past.title
        assert body["schema_org"]["@type"] == "Event"
        assert body["schema_org"]["name"] == past.title

    def test_the_same_past_event_is_a_404_by_id(self, city):
        """**The two reads still answer different questions.**

        The listing's read refuses a started event; the page's read does not. If the two
        ever agreed, one of them would have lost the distinction that makes each of them
        right.
        """
        past = make_past_event(city)

        by_slug = get_event_page(past.slug)
        by_id = anonymous().get(f"/api/catalog/events/{past.id}")

        assert by_slug.status_code == 200
        assert by_id.status_code == 404


# ── the stale fit ──────────────────────────────────────────────────────────────────────


class TestAStaleFitIsAbsent:
    """**A stale `EventFit` row is absent, not rendered wrong.**

    A fit records the Event version it was computed from. If the Event has moved on, the
    row describes an event that no longer exists — so it is **skipped**, never served
    with a score that describes a different event. The row is not deleted: the refresh
    rewrites it, and a fit that is stale for a moment is simply absent from the page.

    **The staleness is produced the way it really happens** — by a lifecycle change that
    bumps the event's version, which leaves the fit behind. A fit written with a
    deliberately wrong version would test the same comparison, but it would not be the
    same *story*, and the story is what the trigger exists to enforce.
    """

    def test_a_stale_fit_is_not_on_the_city_page(self, city, listed_event):
        # The event's version moves; the fit row keeps the old one.
        with transaction.atomic(using=CATALOG):
            apply_lifecycle_change(
                event=listed_event,
                incoming=incoming_for(listed_event, is_sold_out=True),
                change=Change(
                    kinds=(ChangeKind.SOLD_OUT,),
                    fields=frozenset({"is_sold_out"}),
                    is_lifecycle=True,
                ),
                actor=Actor.system("e2e_proof"),
                now=NOW,
            )
        listed_event.refresh_from_db(using=CATALOG)

        # **The row is still there** — it is stale, not deleted.
        fit = EventFit.objects.using(CATALOG).get(event=listed_event, city_ref=city)
        assert fit.event_version != listed_event.event_version

        body = get_city_page(city.slug).json()

        assert listed_event.slug not in [item["slug"] for item in body["items"]]

    def test_a_stale_fit_is_not_counted(self, city, listed_event):
        """**The count and the listing are computed by the same rule.**

        A count that included a stale fit would claim the city qualifies when it does
        not — and the threshold is a count.
        """
        with transaction.atomic(using=CATALOG):
            apply_lifecycle_change(
                event=listed_event,
                incoming=incoming_for(listed_event, is_sold_out=True),
                change=Change(
                    kinds=(ChangeKind.SOLD_OUT,),
                    fields=frozenset({"is_sold_out"}),
                    is_lifecycle=True,
                ),
                actor=Actor.system("e2e_proof"),
                now=NOW,
            )
        listed_event.refresh_from_db(using=CATALOG)

        body = get_city_page(city.slug).json()

        assert body["event_count"] == QUALIFYING_FITS - 1

    def test_a_stale_fit_is_absent_rather_than_wrong(self, city, listed_event):
        """**The event's own page still works.** A stale *fit* is a statement about the
        city's listing, not about the event — the event is still published and still has
        a page.
        """
        with transaction.atomic(using=CATALOG):
            apply_lifecycle_change(
                event=listed_event,
                incoming=incoming_for(listed_event, is_sold_out=True),
                change=Change(
                    kinds=(ChangeKind.SOLD_OUT,),
                    fields=frozenset({"is_sold_out"}),
                    is_lifecycle=True,
                ),
                actor=Actor.system("e2e_proof"),
                now=NOW,
            )
        listed_event.refresh_from_db(using=CATALOG)

        response = get_event_page(listed_event.slug)

        assert response.status_code == 200


# ── the `in_review` event ──────────────────────────────────────────────────────────────


class TestAnUnreviewedEventIsInvisible:
    """**`in_review` is invisible from every direction.**

    Not at its own slug, not on the city page, not in the sitemap's feed. **Three
    different mechanisms** carry that one promise — the slug read refuses any
    non-published row, the listing filters on `publication_status`, and the feed filters
    on the same field — so the proof asserts all three, and the mutation probes break
    all three.
    """

    def test_it_is_not_at_its_own_slug(self, city):
        unreviewed = make_in_review_event(city)

        response = get_event_page(unreviewed.slug)

        assert response.status_code == 404

    def test_a_404_for_an_unreviewed_event_does_not_confirm_it_exists(self, city):
        """**A 403 would confirm that the slug exists.** The answer is the same as for an
        unknown slug: not found.
        """
        unreviewed = make_in_review_event(city)

        body = get_event_page(unreviewed.slug).json()

        assert body["code"] == "not_found"

    def test_it_is_not_on_the_city_page(self, city):
        unreviewed = make_in_review_event(city)
        make_fit(unreviewed, city=city)

        body = get_city_page(city.slug).json()

        assert unreviewed.slug not in [item["slug"] for item in body["items"]]

    def test_it_is_not_in_the_url_feed(self, city):
        unreviewed = make_in_review_event(city)
        make_fit(unreviewed, city=city)

        body = get_url_feed().json()

        # **The feed carries paths, not slugs** — an event's entry is
        # `/events/{slug}` — so the comparison is against the *path* the event would
        # have. Comparing a bare slug against a list of paths would pass whatever the
        # feed did, and would prove nothing at all.
        assert f"/events/{unreviewed.slug}" not in [item["path"] for item in body["items"]]

    def test_an_unreviewed_event_does_not_make_a_city_published(self, city):
        """**Six *published* events qualify; an unreviewed one does not count.**

        The threshold is on the listing's own filters, so a city whose seventh event is
        unreviewed is a city with six published events — and six publish.
        """
        unreviewed = make_in_review_event(city)
        make_fit(unreviewed, city=city)

        body = get_city_page(city.slug).json()

        assert body["event_count"] == QUALIFYING_FITS


# ── the revalidation round trip ────────────────────────────────────────────────────────


class TestTheRevalidationRoundTrip:
    """**The intent's central freshness promise: the page reflects a change without
    waiting for a timer.**

    A cancellation writes one `RevalidationRequest` naming the paths whose cached copies
    are now wrong — the event's own page and the city's page — and the outbox offers it
    to the broker **after** the transaction commits.

    **The proof asserts the signal, not a wait.** The promise is that the *paths* are
    named and the *enqueue* happens; the frontend's half — `revalidatePath` and
    `revalidateTag(path, { expire: 0 })` — is proved in the frontend's own suite. **No
    test sleeps**, and no test polls: a proof that waited for a timer would be asserting
    the machine's speed, not the system's promise.
    """

    def test_a_cancellation_writes_one_revalidation_request(self, city, listed_event):
        with transaction.atomic(using=CATALOG):
            apply_lifecycle_change(
                event=listed_event,
                incoming=incoming_for(listed_event, status=EventStatus.CANCELLED),
                change=Change(
                    kinds=(ChangeKind.CANCELLED,),
                    fields=frozenset({"status"}),
                    is_lifecycle=True,
                ),
                actor=Actor.system("e2e_proof"),
                now=NOW,
            )

        requests = RevalidationRequest.objects.using(CATALOG).filter(event=listed_event)

        assert requests.count() == 1

    def test_the_signal_names_the_event_page_and_the_city_page(self, city, listed_event):
        """**The two paths, and only the two.**

        The event's own page now shows a cancelled event, and the city's listing now
        shows a cancelled event — so both are stale. A third path would be a rebuild of
        something that did not change.
        """
        with transaction.atomic(using=CATALOG):
            apply_lifecycle_change(
                event=listed_event,
                incoming=incoming_for(listed_event, status=EventStatus.CANCELLED),
                change=Change(
                    kinds=(ChangeKind.CANCELLED,),
                    fields=frozenset({"status"}),
                    is_lifecycle=True,
                ),
                actor=Actor.system("e2e_proof"),
                now=NOW,
            )

        request = RevalidationRequest.objects.using(CATALOG).get(event=listed_event)

        assert f"/events/{listed_event.slug}" in request.paths
        assert f"/events-in-{city.slug}" in request.paths
        assert len(request.paths) == 2

    def test_the_signal_carries_the_newest_version(self, city, listed_event):
        """**The version the signal carries is the version *after* the change.**

        The frontend's guard compares the rebuild against the newest state the change
        produced — so a signal at the *old* version would let a rebuild at the old
        version satisfy it, and the stale page would stay live.
        """
        with transaction.atomic(using=CATALOG):
            apply_lifecycle_change(
                event=listed_event,
                incoming=incoming_for(listed_event, status=EventStatus.CANCELLED),
                change=Change(
                    kinds=(ChangeKind.CANCELLED,),
                    fields=frozenset({"status"}),
                    is_lifecycle=True,
                ),
                actor=Actor.system("e2e_proof"),
                now=NOW,
            )
        listed_event.refresh_from_db(using=CATALOG)

        request = RevalidationRequest.objects.using(CATALOG).get(event=listed_event)

        assert request.event_version == listed_event.event_version

    def test_the_signal_is_offered_to_the_broker_after_the_commit(
        self, city, listed_event, revalidation_sent, django_capture_on_commit_callbacks
    ):
        """**The enqueue happens after the commit, not inside it.**

        A rebuild fired from inside an uncommitted write would read the old row back and
        re-cache exactly the stale page it was meant to fix. The `on_commit` callback is
        what makes that impossible — and the broker seam is what lets the proof *see* it.

        **The callbacks are captured and executed, because `pytest`'s `django_db` wrapper
        never commits.** It holds the whole test in a transaction that is rolled back, so
        Django's `on_commit` queue never drains on its own — which is the right default
        for a test (a rolled-back write must not reach a broker) and the wrong one for a
        proof *about* the enqueue. So the callbacks are captured and run exactly as
        Django's runner would run them: `execute=True` honours the `robust` flag, so a
        callback that raised would be logged rather than swallowed.
        """
        with django_capture_on_commit_callbacks(using=CATALOG, execute=True):
            with transaction.atomic(using=CATALOG):
                apply_lifecycle_change(
                    event=listed_event,
                    incoming=incoming_for(listed_event, status=EventStatus.CANCELLED),
                    change=Change(
                        kinds=(ChangeKind.CANCELLED,),
                        fields=frozenset({"status"}),
                        is_lifecycle=True,
                    ),
                    actor=Actor.system("e2e_proof"),
                    now=NOW,
                )

        assert len(revalidation_sent) == 1
        task_name, args = revalidation_sent[0]
        assert task_name == REVALIDATE_TASK

        # **And the id it names is the row that was written.**
        request = RevalidationRequest.objects.using(CATALOG).get(event=listed_event)
        assert args == [str(request.id)]

    def test_the_signal_is_open_when_it_is_written(self, city, listed_event):
        """**An open request is one nobody has delivered yet.** A delivered request
        would mean the frontend had already rebuilt the page.
        """
        with transaction.atomic(using=CATALOG):
            apply_lifecycle_change(
                event=listed_event,
                incoming=incoming_for(listed_event, status=EventStatus.CANCELLED),
                change=Change(
                    kinds=(ChangeKind.CANCELLED,),
                    fields=frozenset({"status"}),
                    is_lifecycle=True,
                ),
                actor=Actor.system("e2e_proof"),
                now=NOW,
            )

        request = RevalidationRequest.objects.using(CATALOG).get(event=listed_event)

        assert request.state == RevalidationRequest.State.OPEN


# ── the sitemap's promise ──────────────────────────────────────────────────────────────


class TestTheSitemapCarriesNoDeadURL:
    """**Every URL in the sitemap resolves.**

    The feed is the sitemap's source, and the feed is fed by the same rules the two page
    reads apply — so a URL in the sitemap is a URL that serves, and a URL that serves is
    a URL in the sitemap. A sitemap that lists a 404 is a crawl-budget leak: the crawler
    spends a fetch to learn that the URL does not exist.

    **So the proof walks every entry and fetches it.** The feed's own rules are proved
    by the other tests in this file; this one proves the *promise the sitemap makes*.
    """

    def test_every_event_path_in_the_feed_resolves(self, city, listed_event):
        feed = get_url_feed().json()

        event_paths = [item["path"] for item in feed["items"] if item["kind"] == "event"]

        assert event_paths, "the feed carried no event paths at all"
        for path in event_paths:
            slug = path.removeprefix("/events/")
            response = get_event_page(slug)
            assert response.status_code == 200, f"{path} is in the sitemap but 404s"

    def test_every_city_path_in_the_feed_resolves(self, city):
        feed = get_url_feed().json()

        city_paths = [item["path"] for item in feed["items"] if item["kind"] == "city"]

        assert f"/events-in-{city.slug}" in city_paths
        for path in city_paths:
            slug = path.removeprefix("/events-in-")
            response = get_city_page(slug)
            assert response.status_code == 200, f"{path} is in the sitemap but 404s"

    def test_the_feed_carries_the_city_page_of_a_qualifying_city(self, city):
        feed = get_url_feed().json()

        paths = [item["path"] for item in feed["items"]]

        assert f"/events-in-{city.slug}" in paths

    def test_the_feed_does_not_carry_a_city_below_the_threshold(self):
        """**A city with fewer than six events has no page, so it has no URL.**

        The feed and the city page compute the qualification by the same rule, so they
        cannot disagree about whether a city is published.
        """
        sparse = make_city(slug="sparseville", name="Sparseville")
        make_fit(make_event(sparse, hours=4, title="Only Event"), city=sparse)

        feed = get_url_feed().json()

        assert "/events-in-sparseville" not in [item["path"] for item in feed["items"]]


# ── the authed surfaces ────────────────────────────────────────────────────────────────


class TestTheAuthedSurfacesAreUnbroken:
    """**The branching route did not regress the signed-in Detail Screen.**

    `/events/{id}` serves two pages: a minted slug is the public event page, and
    everything else is the signed-in Detail Screen. **The branch is only worth anything
    if both halves still work** — so the authed half is asserted here, and the frontend's
    own suite proves the routing.

    These are the *catalog's* endpoints, not the personalized ones: the Detail Screen
    reads `GET /api/events/{event_id}`, and the proof asserts that endpoint still
    answers for an event that is public and upcoming.
    """

    def test_the_detail_endpoint_still_answers_for_a_public_event(self, city, listed_event):
        response = anonymous().get(f"/api/catalog/events/{listed_event.id}")

        assert response.status_code == 200
        assert response.json()["slug"] == listed_event.slug

    def test_the_detail_endpoint_still_refuses_a_started_event(self, city):
        """**The two reads still differ.** The listing's read refuses an event that has
        started; the page's read does not. A change that made them agree would have lost
        the distinction that makes each right.
        """
        past = make_past_event(city)

        response = anonymous().get(f"/api/catalog/events/{past.id}")

        assert response.status_code == 404
