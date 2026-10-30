"""The fake geo adapter: reports the city it was configured with (FR-2).

**The fake is the local and CI default** (`ADAPTER_MODE=fake`), and the work item asks
for it to be "configurable to return a chosen city". The chosen city comes from
`GEO_FAKE_CITY`, read through `config.env` — the only module in the codebase allowed to
read the environment.

**The fake ignores the headers entirely.** It reports its configured city, whatever the
request carried. That is what makes it a fake: a test that wants to exercise the *real*
adapter's header handling reaches for the real adapter, and a test that wants a
deterministic city sets the configuration.

**Configuring it to nothing exercises the geo-miss branch.** With `GEO_FAKE_CITY` unset,
the fake reports no location, and the endpoint falls back to the fallback city — which is
the branch a test for the fallback needs.

The value is read through `settings`, not through the environment directly, so the
setting is the single source of truth and a test can override it with
`settings.GEO_FAKE_CITY`.
"""

from collections.abc import Mapping

from django.conf import settings

from ports.geo import GeoPort


class FakeGeoAdapter(GeoPort):
    """Reports the configured city, or no location when none is configured."""

    def resolve_city(self, headers: Mapping[str, str]) -> str | None:
        """The configured city, or `None`.

        `headers` is deliberately unused: the fake does not read the request. It is
        named with a leading underscore-free name only to satisfy the port's signature.
        """
        city = getattr(settings, "GEO_FAKE_CITY", None)
        if not city:
            return None
        return city.strip() or None


__all__ = ["FakeGeoAdapter"]
