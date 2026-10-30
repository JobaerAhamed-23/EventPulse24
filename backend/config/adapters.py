"""Which adapter implements each port, per ADAPTER_MODE. Resolved by `ports.registry`."""

from django.core.exceptions import ImproperlyConfigured

# fake: local stand-ins, no API keys. Email still really sends, to Mailpit (SMTP_HOST/SMTP_PORT).
FAKE_ADAPTERS = {
    "llm": "adapters.llm.fake.FakeLLMAdapter",
    "embedding": "adapters.llm.fake.FakeEmbeddingAdapter",
    "email": "adapters.email.smtp.SmtpEmailAdapter",
    "billing": "adapters.billing.fake.FakeBillingAdapter",
    "calendar": "adapters.calendar.fake.FakeCalendarAdapter",
    "fetch": "adapters.crawl.fake.FakeFetchAdapter",
    # FR-2: the fake geo adapter reports the city GEO_FAKE_CITY names. It is the local and
    # CI default, and it is what makes the geo hit, the geo miss and the fallback
    # branches testable without a header.
    "geo": "adapters.geo.fake.FakeGeoAdapter",
    # The throttle fake counts in memory, so its window is controlled by the test's clock.
    "throttle": "adapters.throttle.memory.InMemoryThrottleAdapter",
}

HTTP_FETCH_ADAPTER = "adapters.crawl.http.HttpFetchAdapter"
FETCH_ADAPTERS = {"fake": FAKE_ADAPTERS["fetch"], "http": HTTP_FETCH_ADAPTER}

CALENDAR_ADAPTER = "adapters.calendar.ics.IcsCalendarAdapter"

HEADER_GEO_ADAPTER = "adapters.geo.header.HeaderGeoAdapter"

# Filled in by the intents that build the real gateway, email provider, Stripe and ICS adapters.
REAL_ADAPTERS: dict[str, str] = {
    "fetch": HTTP_FETCH_ADAPTER,
    # The ICS adapter serves Google, Apple and Outlook alike: they all publish
    # iCalendar, so there is one adapter, not three.
    "calendar": CALENDAR_ADAPTER,
    # FR-2: the real geo adapter reads the edge's geo header. There is no vendor to call
    # and no database to consult — the edge already knows where the request came from —
    # so the real adapter needs no credentials and no configuration beyond the header's
    # name. It is therefore available in real mode from the start.
    "geo": HEADER_GEO_ADAPTER,
    # Redis is already in the stack (the Celery broker), so the throttle has a real
    # adapter from the start.
    "throttle": "adapters.throttle.redis.RedisThrottleAdapter",
}


def adapter_paths(mode: str, fetch: str | None = None) -> dict[str, str]:
    """The adapter table for `mode`; `fetch` (SOURCE_FETCH) overrides the fetch port alone."""
    paths = _mode_paths(mode)
    if fetch is not None:
        paths["fetch"] = FETCH_ADAPTERS[fetch]
    return paths


def _mode_paths(mode: str) -> dict[str, str]:
    if mode == "fake":
        return dict(FAKE_ADAPTERS)
    missing = sorted(FAKE_ADAPTERS.keys() - REAL_ADAPTERS.keys())
    if missing:
        # Fail at startup rather than run stand-ins where real services are expected.
        raise ImproperlyConfigured(
            f"ADAPTER_MODE={mode} is not available yet: no real adapter for {', '.join(missing)}."
        )
    return dict(REAL_ADAPTERS)
