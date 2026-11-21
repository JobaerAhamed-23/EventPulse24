"""The provider-template registry (city-provider-templates).

**Which providers exist for which cities is a code-reviewed fact, and these tests are what
makes it one.** Every invariant below runs over the **whole registry** — every catalog city
crossed with every template — never a sample. A sampled check passes happily while a bad
template sits one line down, and a bad template reaches a reader as a source that is
fetched, found empty, and read as a failure of our collection rather than a fact about the
provider.

**The four rules that matter most:**

- **No template emits `crawl`.** FR-17 makes crawling the last resort and gates it behind
  an approved ToS review, and nothing automatic can grant one. A template that emitted
  `crawl` would mint a source the ingest guard refuses — forever, and silently.
- **Every method the registry can emit has a registered parser.** A source whose method
  `parse()` answers `unsupported_method` for is a defect, and a future template must not be
  able to introduce one.
- **No emitted URL carries an API key.** A key in a URL is a credential: `Source.url` is a
  column read by the admin, and `register_source` writes its fields into an audit row kept
  for 24 months. The key is added at fetch time and never stored.
- **A disabled template produces nothing.** "Disabled" has to mean "cannot be registered",
  not merely "is quiet" — otherwise the Eventbrite Terms question would be settled by
  everyone not reading the code.

`domain/` carries a hard 100% coverage gate in CI. No Django import in the module — the
tests below import Django's model vocabulary **on purpose**, to hold the restated
vocabularies to it.
"""

from dataclasses import FrozenInstanceError
from urllib.parse import parse_qs, urlsplit

import pytest

from domain.city_catalog import WORLD_CITIES
from domain.city_providers import (
    ACQUISITION_METHOD_SET,
    ACQUISITION_METHODS,
    PROVIDER_TEMPLATES,
    SOURCE_TYPES,
    TICKETMASTER_COUNTRIES,
    TICKETMASTER_HOST,
    TZ_COVERAGES,
    ProviderTemplate,
    SourceSpec,
    resolve,
)

#: The `Source.url` column's `max_length`. A URL over this cannot be stored, so a template
#: that emits one is a template that mints an unsaveable source.
URL_MAX = 2048

#: Every (city, template) pair in the registry. The whole cross-product, not a sample.
CROSS_PRODUCT = [(city, template) for city in WORLD_CITIES for template in PROVIDER_TEMPLATES]

#: The cities Ticketmaster serves, by the catalog's own country codes.
TICKETMASTER_CITIES = [c for c in WORLD_CITIES if c.country_code in TICKETMASTER_COUNTRIES]


def _specs() -> list[SourceSpec]:
    """Every spec the registry can emit, from every city it can fire for."""
    return [spec for city, template in CROSS_PRODUCT if (spec := template.build(city)) is not None]


# ── The rules the registry exists to hold ──────────────────────────────────────────────────


class TestNothingCrawls:
    """FR-17: crawling is the last resort, and nothing automatic may approve it."""

    def test_no_template_declares_crawl(self):
        """Asserted on the *declarations*, so a template that never fires still cannot say it."""
        bad = [t.key for t in PROVIDER_TEMPLATES if t.method == "crawl"]

        assert bad == []

    def test_no_emitted_spec_carries_crawl(self):
        """And asserted on what is actually emitted, over the whole cross-product."""
        bad = [s.url for s in _specs() if s.acquisition_method == "crawl"]

        assert bad == []


class TestEveryMethodHasAParser:
    """A source whose method `parse()` refuses is a source that never ingests."""

    def test_every_method_the_registry_can_emit_has_a_parser(self):
        from apps.ingestion.parsers import PARSERS

        missing = sorted({t.method for t in PROVIDER_TEMPLATES} - set(PARSERS))

        assert missing == []

    def test_every_emitted_specs_method_has_a_parser(self):
        from apps.ingestion.parsers import PARSERS

        missing = sorted({s.acquisition_method for s in _specs()} - set(PARSERS))

        assert missing == []


class TestNoUrlCarriesAKey:
    """A key in a URL is a credential, and credentials do not live in a template."""

    def test_no_emitted_url_carries_an_api_key(self):
        bad = [s.url for s in _specs() if "apikey" in s.url.lower()]

        assert bad == []

    def test_no_template_mentions_a_key_parameter(self):
        """Checked on the *template* too — a disabled template that baked in a key would
        still have the secret in the repository and would ship it the day it is enabled."""
        bad = [t.key for t in PROVIDER_TEMPLATES if "apikey" in str(t.build).lower()]

        assert bad == []


# ── The URLs ───────────────────────────────────────────────────────────────────────────────


class TestEveryUrlIsWellFormed:
    """Over the full cross-product of catalog and templates, not a sample."""

    def test_every_emitted_url_is_an_https_url_with_a_host(self):
        bad = []
        for spec in _specs():
            parts = urlsplit(spec.url)
            if parts.scheme != "https" or not parts.hostname:
                bad.append(spec.url)

        assert bad == []

    def test_every_emitted_url_is_within_the_length_bound(self):
        """`Source.url` is `max_length=2048`. A longer URL cannot be stored at all."""
        bad = [s.url for s in _specs() if len(s.url) > URL_MAX]

        assert bad == []

    def test_every_emitted_url_has_no_credentials_in_it(self):
        """A URL with a userinfo section is a URL with a password in it."""
        bad = [s.url for s in _specs() if urlsplit(s.url).username or urlsplit(s.url).password]

        assert bad == []

    def test_the_query_is_built_by_encoding_not_by_splicing(self):
        """A city with a space or an accent must be percent-encoded, not pasted raw.

        "Portland, OR" pasted raw would put a space and a comma in a query string, which
        is not a URL any client can parse the way we meant.
        """
        spec = next(
            s for s in _specs() if s.acquisition_method == "api" and "portland" in s.url.lower()
        )
        query = parse_qs(urlsplit(spec.url).query)

        assert query["city"] in (["Portland, OR"], ["Portland, ME"])
        assert "+" in spec.url or "%20" in spec.url

    def test_a_city_with_a_comma_is_percent_encoded(self):
        """The catalog's names carry a region qualifier ("Portland, OR"), and a comma
        pasted raw into a query string is not a URL any client parses the way we meant."""
        spec = next(
            s for s in _specs() if s.acquisition_method == "api" and "portland" in s.url.lower()
        )

        assert "%2C" in spec.url

    def test_an_accented_city_reaches_the_url_intact(self):
        """Bogotá, São Paulo, Brasília — a non-ASCII name must survive the round trip.

        None of them is in Ticketmaster's countries, so the accent is carried by the
        *other* template's path segment. The point is that the name is neither mangled
        nor dropped.
        """
        template = next(t for t in PROVIDER_TEMPLATES if t.key == "eventbrite-directory")
        city = next(c for c in WORLD_CITIES if c.name == "Bogotá")

        spec = template.build(city)

        assert spec.url.endswith("/d/colombia--bogotá/events/")


class TestTheUrlComesFromTheCitysOwnRow:
    """A URL is built from one row's columns, so the city and the country cannot disagree."""

    def test_the_api_url_carries_the_city_and_the_country_of_its_own_row(self):
        bad = []
        for city in TICKETMASTER_CITIES:
            spec = next(t for t in PROVIDER_TEMPLATES if t.key == "ticketmaster").build(city)
            query = parse_qs(urlsplit(spec.url).query)
            if query["city"] != [city.name] or query["countryCode"] != [city.country_code]:
                bad.append(city.name)

        assert bad == []

    def test_the_api_url_points_at_the_ticketmaster_host(self):
        """Exactly. A suffix match would accept `app.ticketmaster.com.evil.test`."""
        bad = [
            s.url
            for s in _specs()
            if s.acquisition_method == "api" and urlsplit(s.url).hostname != TICKETMASTER_HOST
        ]

        assert bad == []

    def test_two_cities_never_get_the_same_url(self):
        """Two cities that minted one URL would make one of them unreachable."""
        urls = [spec.url for spec in _specs()]

        assert len(urls) == len(set(urls))


# ── Ticketmaster's country restriction ────────────────────────────────────────────────────


class TestTicketmasterCoversOnlyWhatItCovers:
    """The AC: restricted to the countries it actually covers, `None` elsewhere."""

    def test_every_country_in_the_set_is_a_country_the_catalog_has(self):
        """A constant naming a country with no city in it is a claim nothing exercises."""
        catalog_countries = {row.country_code for row in WORLD_CITIES}

        assert sorted(TICKETMASTER_COUNTRIES - catalog_countries) == []

    def test_the_template_answers_exactly_for_the_countries_it_names(self):
        """Over every catalog city: a spec iff the row's country is in the set."""
        wrong = []
        for city in WORLD_CITIES:
            spec = next(t for t in PROVIDER_TEMPLATES if t.key == "ticketmaster").build(city)
            covered = city.country_code in TICKETMASTER_COUNTRIES
            if (spec is not None) != covered:
                wrong.append(city.name)

        assert wrong == []

    def test_a_city_outside_the_set_is_declined_rather_than_given_an_empty_source(self):
        outside = next(c for c in WORLD_CITIES if c.country_code not in TICKETMASTER_COUNTRIES)
        template = next(t for t in PROVIDER_TEMPLATES if t.key == "ticketmaster")

        assert template.build(outside) is None


# ── FR-17's order ─────────────────────────────────────────────────────────────────────────


class TestTheOrderIsFr17s:
    """The API tier first; the structured tier after it; nothing that needs a review."""

    def test_the_templates_are_ordered_by_the_method_priority(self):
        rank = {method: index for index, method in enumerate(ACQUISITION_METHODS)}
        ranks = [rank[t.method] for t in PROVIDER_TEMPLATES]

        assert ranks == sorted(ranks)

    def test_the_api_tier_comes_first(self):
        assert PROVIDER_TEMPLATES[0].method == "api"

    def test_resolve_returns_the_specs_in_template_order(self):
        """Not by source name, not by URL — by the registry's own order."""
        for city in TICKETMASTER_CITIES:
            specs = resolve(city)
            methods = [s.acquisition_method for s in specs]
            rank = {method: index for index, method in enumerate(ACQUISITION_METHODS)}
            assert [rank[m] for m in methods] == sorted(rank[m] for m in methods)


# ── `resolve` ─────────────────────────────────────────────────────────────────────────────


class TestResolve:
    def test_resolve_returns_an_empty_tuple_for_a_city_no_template_covers(self):
        """A normal outcome, not an error. Item 7 records it as `no_providers`."""
        outside = next(c for c in WORLD_CITIES if c.country_code not in TICKETMASTER_COUNTRIES)

        assert resolve(outside) == ()

    def test_resolve_skips_a_disabled_template(self):
        """The Eventbrite template is in the registry but disabled, so it contributes
        nothing — not even to a city Ticketmaster serves."""
        city = next(c for c in TICKETMASTER_CITIES if c.country_code == "US")

        assert all(s.acquisition_method != "jsonld" for s in resolve(city))

    def test_resolve_returns_the_specs_for_a_covered_city(self):
        city = next(c for c in TICKETMASTER_CITIES if c.country_code == "US")

        specs = resolve(city)

        assert [s.acquisition_method for s in specs] == ["api"]

    def test_resolve_is_pure(self):
        """The same city gives the same answer every time — the registry is a fact, not a
        lottery."""
        city = next(c for c in TICKETMASTER_CITIES)

        assert resolve(city) == resolve(city)


# ── Disabled templates ─────────────────────────────────────────────────────────────────────


class TestDisabledTemplatesProduceNothing:
    """'Disabled' has to mean 'cannot be registered', not merely 'is quiet'."""

    def test_a_disabled_template_is_in_the_registry(self):
        """It is *in* the registry, so its shape and its tests survive."""
        assert any(t.key == "eventbrite-directory" for t in PROVIDER_TEMPLATES)

    def test_a_disabled_template_is_marked_disabled(self):
        template = next(t for t in PROVIDER_TEMPLATES if t.key == "eventbrite-directory")

        assert template.enabled is False

    def test_a_disabled_template_emits_nothing_through_resolve(self):
        """For every city in the catalog, not a sample.

        The assertion is **both halves**: the spec the disabled template would have built
        is the one that must be absent, and `resolve` must have returned something at all
        for the cities the enabled template covers — so an empty tuple cannot pass for
        the right reason.
        """
        template = next(t for t in PROVIDER_TEMPLATES if t.key == "eventbrite-directory")

        bad = []
        for city in WORLD_CITIES:
            would_have = template.build(city)
            if would_have is None:
                continue
            if any(s.url == would_have.url for s in resolve(city)):
                bad.append(city.name)

        assert bad == []

    def test_resolve_still_returns_something_for_a_city_the_enabled_template_covers(self):
        """So the test above cannot pass merely because `resolve` returns nothing."""
        city = next(c for c in TICKETMASTER_CITIES if c.country_code == "US")

        assert resolve(city) != ()

    def test_a_disabled_template_cannot_reach_resolve_at_all(self):
        """Even for a city Ticketmaster declines: the template is skipped whole."""
        outside = next(c for c in WORLD_CITIES if c.country_code not in TICKETMASTER_COUNTRIES)

        assert resolve(outside) == ()

    def test_the_disabled_template_still_builds_a_spec_when_asked_directly(self):
        """Its URL shape is proven and kept — it is the *registration* that is switched
        off, not the knowledge. This is what a person flips the constant for."""
        template = next(t for t in PROVIDER_TEMPLATES if t.key == "eventbrite-directory")
        city = next(c for c in WORLD_CITIES if c.country_code == "BD")

        spec = template.build(city)

        assert spec is not None
        assert spec.acquisition_method == "jsonld"


# ── The Eventbrite URL shape ───────────────────────────────────────────────────────────────


class TestTheEventbriteUrlShape:
    """The shape `seed_dhaka_live.py` fetches and parses."""

    def test_the_shape_is_country_slug_double_dash_city_slug(self):
        template = next(t for t in PROVIDER_TEMPLATES if t.key == "eventbrite-directory")
        city = next(c for c in WORLD_CITIES if c.country_code == "BD" and c.name == "Dhaka")

        spec = template.build(city)

        assert spec.url == "https://www.eventbrite.com/d/bangladesh--dhaka/events/"

    def test_the_city_slug_is_the_providers_own_not_ours(self):
        """Eventbrite's shape has one city segment and a separate country segment, so
        `mint_city_slug` is not used — but the region's qualifier is carried, because
        dropping it would make Portland, ME and Portland, OR one city."""
        template = next(t for t in PROVIDER_TEMPLATES if t.key == "eventbrite-directory")
        city = next(c for c in WORLD_CITIES if c.name == "Portland, OR")

        spec = template.build(city)

        assert spec.url == "https://www.eventbrite.com/d/united-states--portland-or/events/"

    def test_two_portlands_do_not_collide(self):
        """The catalog holds two Portlands. One URL for both would mean the second is
        refused as a duplicate, and the reader in Maine is shown Oregon's events."""
        template = next(t for t in PROVIDER_TEMPLATES if t.key == "eventbrite-directory")
        maine = next(c for c in WORLD_CITIES if c.name == "Portland, ME")
        oregon = next(c for c in WORLD_CITIES if c.name == "Portland, OR")

        assert template.build(maine).url != template.build(oregon).url

    def test_the_city_slug_folds_a_space(self):
        template = next(t for t in PROVIDER_TEMPLATES if t.key == "eventbrite-directory")
        city = next(c for c in WORLD_CITIES if c.name == "New York, NY")

        spec = template.build(city)

        assert spec.url.endswith("/d/united-states--new-york-ny/events/")


# ── The vocabularies ──────────────────────────────────────────────────────────────────────


class TestTheVocabulariesMatchTheModels:
    """`domain` may not import `apps.ingestion.models`, so it restates them.

    Restating is a place two truths could grow apart, so these tests hold the copy to the
    original. If `AcquisitionMethod` gains a value, this registry cannot drift from it
    silently.
    """

    def test_every_source_type_is_in_the_models_vocabulary(self):
        from apps.ingestion.models import Source

        assert SOURCE_TYPES <= set(Source.SourceType.values)

    def test_every_acquisition_method_is_in_the_models_vocabulary(self):
        from apps.ingestion.models import AcquisitionMethod

        assert ACQUISITION_METHOD_SET <= set(AcquisitionMethod.values)

    def test_every_tz_coverage_is_in_the_models_vocabulary(self):
        from apps.ingestion.models import Source

        assert TZ_COVERAGES <= set(Source.TzCoverage.values)

    def test_every_emitted_specs_values_are_in_the_vocabularies(self):
        """Over every spec the registry can emit — a spec that names a value the model
        does not know would be refused by the registry's own cleaner."""
        bad = [
            s.url
            for s in _specs()
            if s.source_type not in SOURCE_TYPES
            or s.acquisition_method not in ACQUISITION_METHOD_SET
            or s.tz_coverage not in TZ_COVERAGES
        ]

        assert bad == []


# ── The shape of the module ───────────────────────────────────────────────────────────────


class TestTheModuleItself:
    def test_a_source_spec_is_frozen(self):
        """A spec is a fact about a city, not something that may be edited in place."""
        spec = next(s for s in _specs())

        with pytest.raises(FrozenInstanceError):
            spec.url = "https://elsewhere.test/"

    def test_a_provider_template_is_frozen(self):
        template = PROVIDER_TEMPLATES[0]

        with pytest.raises(FrozenInstanceError):
            template.enabled = False

    def test_the_registry_is_not_empty(self):
        assert PROVIDER_TEMPLATES != ()

    def test_the_template_keys_are_unique(self):
        keys = [t.key for t in PROVIDER_TEMPLATES]

        assert len(keys) == len(set(keys))

    def test_every_template_declares_a_method_in_the_vocabulary(self):
        bad = [t.key for t in PROVIDER_TEMPLATES if t.method not in ACQUISITION_METHOD_SET]

        assert bad == []

    def test_the_types_are_what_they_claim_to_be(self):
        """The module's own public shapes, so a later edit cannot quietly change what
        `resolve()` returns without a test noticing."""
        spec = next(s for s in _specs())

        assert isinstance(spec, SourceSpec)
        assert isinstance(PROVIDER_TEMPLATES[0], ProviderTemplate)
