"""The city picker's choices: `GET /api/public/cities` (FR-2).

**The claim this file exists to defend** is the one the branch's own commit message makes:
the city picker is a map of the world, not a mirror of the catalog. So the load-bearing
test here is not the response shape — it is `test_a_city_with_no_events_is_still_offered`.
Every other assertion protects a property that makes the endpoint safe to cache or safe to
store from.

The endpoint runs **no query**, and that is asserted rather than assumed: the work item's
technical note says not to add a database read "to make it feel symmetrical with the
preview endpoint", and a note is not a test.
"""

import json

import pytest
from django.test import Client
from django.utils import timezone

from apps.ingestion.services.preview_read import list_supported_cities
from domain.city_catalog import WORLD_CITIES, choices, lookup
from shared.constants import PREVIEW_THROTTLE_IP, PREVIEW_VARY
from shared.db import CATALOG, PERSONAL

pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])

URL = "/api/public/cities"


@pytest.fixture
def throttle_adapter(monkeypatch):
    """One in-memory throttle adapter shared by every request in the test.

    `ports.registry.get_adapter` builds a fresh adapter per call, so the fake's counters
    would not survive between requests and the limit would never be reached. Same reason
    and same shape as the preview's fixture.
    """
    from adapters.throttle.memory import InMemoryThrottleAdapter

    clock = {"now": 1_000_000.0}
    adapter = InMemoryThrottleAdapter(now=lambda: clock["now"])
    monkeypatch.setattr("apps.catalog.cities_api.get_throttle_port", lambda: adapter)
    adapter.test_clock = clock  # type: ignore[attr-defined]
    return adapter


def get(client: Client | None = None, **extra):
    return (client or Client()).get(URL, **extra)


class TestTheCatalogIsWhatIsOffered:
    def test_every_catalog_row_is_offered_exactly_once(self):
        body = get().json()

        assert len(body["cities"]) == len(WORLD_CITIES)
        assert len({c["value"] for c in body["cities"]}) == len(WORLD_CITIES)

    def test_value_is_what_gets_stored_and_label_is_what_is_shown(self):
        body = get().json()

        by_value = {c["value"]: c["label"] for c in body["cities"]}
        assert by_value["Portland, OR"] == "Portland, Oregon"
        assert by_value["Portland, ME"] == "Portland, Maine"
        assert by_value["Chittagong"] == "Chittagong, Bangladesh"

    def test_every_value_round_trips_through_the_catalog(self):
        # Whatever the picker sends back must be storable verbatim. If a value here did
        # not resolve, `stored-city-is-the-picked-city` would have nothing to validate.
        body = get().json()

        assert [c["value"] for c in body["cities"] if lookup(c["value"]) is None] == []

    def test_the_order_is_the_catalogs_own_casefold_sort(self):
        body = get().json()

        assert [c["label"] for c in body["cities"]] == [row.label for row in choices()]

    def test_the_order_is_the_casefold_sort(self):
        # The reason AC 3 insists the sort happens in Python: a database ORDER BY on text
        # is a locale collation, so two deployments would order the picker differently.
        #
        # **This cannot distinguish casefold from a byte sort on today's data** — every
        # label happens to begin with an uppercase letter, so the two agree. The claim is
        # worth asserting here anyway as the endpoint's contract, and the mechanism itself
        # is pinned where it can be: `domain.city_catalog.choices` sorts with
        # `key=str.casefold`, asserted in `tests/domain/test_city_catalog.py`.
        labels = [c["label"] for c in get().json()["cities"]]

        assert labels == sorted(labels, key=str.casefold)

    def test_a_city_with_no_events_is_still_offered(self):
        # **The whole point of the item.** The preview can serve nothing at all here, and
        # Chittagong is still pickable. A picker that mirrored the catalog could not do
        # this, and a reader in a city we have not ingested could never choose it.
        supported = list_supported_cities(now=timezone.now())
        offered = {c["value"] for c in get().json()["cities"]}

        assert supported.cities == ()
        assert "Chittagong" in offered
        assert "Dhaka" in offered


class TestItIsAnonymousAndCacheable:
    """AD-12. These are one property, not two: a response that depends on who asked
    cannot be cached, and a shared cache that ignored the session would serve one
    visitor's response to another."""

    def test_a_signed_in_and_an_anonymous_request_get_identical_bytes(self, django_user_model):
        user = django_user_model.objects.db_manager(PERSONAL).create_user(
            email="reader@example.test", password="not-used-in-tests"
        )
        signed_in = Client()
        signed_in.force_login(user)

        assert get(signed_in).content == get().content

    def test_no_cookie_is_set(self):
        assert get().cookies == {}

    def test_the_response_is_publicly_cacheable_for_longer_than_the_preview(self):
        response = get()

        cache_control = response["Cache-Control"]
        assert cache_control.startswith("public,")
        assert "max-age=3600" in cache_control
        assert "s-maxage=86400" in cache_control

    def test_vary_carries_nothing_session_related(self):
        vary = get()["Vary"]

        assert vary == PREVIEW_VARY
        assert "cookie" not in vary.lower()
        assert "authorization" not in vary.lower()

    def test_the_endpoint_runs_no_query_at_all(self, django_assert_num_queries):
        # The technical note made this a requirement, so it is a test and not a comment:
        # "the catalog is static... do not add a database read to make it feel symmetrical
        # with the preview endpoint."
        with django_assert_num_queries(0, using=CATALOG):
            with django_assert_num_queries(0, using=PERSONAL):
                get()


class TestItIsThrottled:
    def test_the_per_ip_limit_is_enforced(self, throttle_adapter):
        client = Client()
        for _ in range(PREVIEW_THROTTLE_IP):
            assert client.get(URL).status_code == 200

        refused = client.get(URL)

        assert refused.status_code == 429
        assert refused.json()["code"] == "rate_limited"
        assert refused["Retry-After"]

    def test_a_refused_request_is_never_cached(self, throttle_adapter):
        client = Client()
        for _ in range(PREVIEW_THROTTLE_IP):
            client.get(URL)

        refused = client.get(URL)

        # A cached 429 would lock out everyone behind the same shared cache.
        assert refused["Cache-Control"] == "no-store"

    @pytest.mark.parametrize("other", ["/api/public/preview", "/api/public/preview/cities"])
    def test_it_does_not_spend_the_previews_budget(self, throttle_adapter, monkeypatch, other):
        # Separate scopes: exhausting this route must leave **both** preview routes usable.
        #
        # Both are listed deliberately. The preview's routes use the scopes `preview` and
        # `preview:cities`, so checking only one would pass even if this route collided
        # with the other — which is exactly what a mutation check caught an earlier version
        # of this test doing.
        monkeypatch.setattr("apps.catalog.preview_api.get_throttle_port", lambda: throttle_adapter)
        client = Client()
        for _ in range(PREVIEW_THROTTLE_IP):
            client.get(URL)
        assert client.get(URL).status_code == 429

        assert client.get(other).status_code == 200


class TestItDoesNotDisturbThePreview:
    def test_both_routes_answer_on_the_same_prefix(self):
        # Two routers mounted at `/public`. Neither shadows the other.
        assert get().status_code == 200
        assert Client().get("/api/public/preview/cities").status_code == 200

    def test_the_two_city_lists_answer_different_questions(self):
        # `/preview/cities` is coverage — empty here, because nothing is ingested.
        # `/cities` is the catalog — 165 rows regardless. Conflating them is the bug.
        preview = Client().get("/api/public/preview/cities").json()["cities"]
        picker = get().json()["cities"]

        assert preview == []
        assert len(picker) == len(WORLD_CITIES)


def test_the_response_is_an_object_not_a_bare_array():
    # A top-level array cannot grow a sibling field without breaking every client.
    body = json.loads(get().content)

    assert isinstance(body, dict)
    assert set(body) == {"cities"}
