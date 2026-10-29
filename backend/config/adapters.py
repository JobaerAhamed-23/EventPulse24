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
    # The throttle fake counts in memory, so its window is controlled by the test's clock.
    "throttle": "adapters.throttle.memory.InMemoryThrottleAdapter",
}

HTTP_FETCH_ADAPTER = "adapters.crawl.http.HttpFetchAdapter"
FETCH_ADAPTERS = {"fake": FAKE_ADAPTERS["fetch"], "http": HTTP_FETCH_ADAPTER}

# Filled in by the intents that build the real gateway, email provider, Stripe and ICS adapters.
REAL_ADAPTERS: dict[str, str] = {
    "fetch": HTTP_FETCH_ADAPTER,
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
