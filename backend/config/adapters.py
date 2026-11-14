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
    # The revalidation fake records the signals it is given instead of sending them, so a
    # local run never calls the frontend and a test never needs a server.
    "revalidation": "adapters.revalidation.fake.FakeRevalidationAdapter",
}

HTTP_FETCH_ADAPTER = "adapters.crawl.http.HttpFetchAdapter"
FETCH_ADAPTERS = {"fake": FAKE_ADAPTERS["fetch"], "http": HTTP_FETCH_ADAPTER}

#: The throttle's counter store, chosen by `THROTTLE_ADAPTER` rather than by `ADAPTER_MODE`.
#:
#: **The throttle is the one port whose state the whole stack shares**, so it is the one
#: port that cannot be served by a per-process fake in a local run. The API reads and
#: spends the counters, and the seed command clears them — three separate processes that
#: must see one set of numbers. `redis` gives them that, and it is the adapter
#: production already uses; `memory` keeps the counters in the process, which is what a
#: unit test wants (it pins the clock and wants an isolated counter) and what a
#: single-process local run can live with.
THROTTLE_ADAPTERS = {
    "memory": FAKE_ADAPTERS["throttle"],
    "redis": "adapters.throttle.redis.RedisThrottleAdapter",
}

CALENDAR_ADAPTER = "adapters.calendar.ics.IcsCalendarAdapter"

#: The calendar importer, chosen by `CALENDAR_ADAPTER` rather than by `ADAPTER_MODE`.
#:
#: **The fake here is unusually convincing, and that is the problem it solves.** Every other
#: fake announces itself — a canned LLM reply reads as canned, a fake invoice is obviously
#: not Stripe. The calendar fake returns two well-formed events for *any* address, so a
#: developer who connects their own Google calendar sees a healthy connection, a recent
#: `last_polled_at`, no error, and two events that are simply not theirs. Nothing in the UI
#: distinguishes that from a working import.
#:
#: `ADAPTER_MODE=real` cannot be the remedy, because it does not boot yet (`llm` and `email`
#: have no real adapter). So the calendar is overridable on its own, for the same reason the
#: fetch and the throttle are: a local run may need one port's real behaviour without
#: claiming real behaviour for the ports that need credentials.
CALENDAR_ADAPTERS = {"fake": FAKE_ADAPTERS["calendar"], "ics": CALENDAR_ADAPTER}

HEADER_GEO_ADAPTER = "adapters.geo.header.HeaderGeoAdapter"

# Filled in by the intents that build the real gateway and email provider. The Stripe, ICS and
# Voyage adapters have landed; the LLM gateway and the email provider have not.
REAL_ADAPTERS: dict[str, str] = {
    "fetch": HTTP_FETCH_ADAPTER,
    # FR-48: the real Stripe adapter. Note this does **not** make ADAPTER_MODE=real bootable
    # — `llm` and `email` are still missing, and `_mode_paths` still refuses.
    # That is deliberate: this intent ships billing, not go-live.
    "billing": "adapters.billing.stripe.StripeBillingAdapter",
    # FR-25: the real embedding adapter. Same note as the Stripe one above, and for the
    # same reason: `llm` and `email` are still missing, so real mode still refuses to
    # boot. This intent ships embeddings, not go-live.
    "embedding": "adapters.llm.voyage.VoyageEmbeddingAdapter",
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
    # The frontend is always a real deploy, so the revalidation signal has a real adapter
    # from the start. There is no "fake frontend" in production mode — a local run that
    # never signals the frontend is a local run whose pages stay stale, which is honest.
    "revalidation": "adapters.revalidation.http.HttpRevalidationAdapter",
}


def adapter_paths(
    mode: str,
    fetch: str | None = None,
    throttle: str | None = None,
    calendar: str | None = None,
) -> dict[str, str]:
    """The adapter table for `mode`.

    **`fetch` (SOURCE_FETCH), `throttle` (THROTTLE_ADAPTER) and `calendar`
    (CALENDAR_ADAPTER) each override one port.** None of them changes the mode: they name
    the adapter for a single port and leave every other port on the table the mode chose.
    Each is overridable for the same reason — it is a port whose behaviour a local run may
    need to change without changing the mode's meaning for the ports that need credentials.

    **An override left unset follows the mode**, so the default local stack is unchanged:
    `ADAPTER_MODE=fake` with no `CALENDAR_ADAPTER` still imports the fake's two events, and
    nothing a developer has today starts behaving differently.
    """
    paths = _mode_paths(mode)
    if fetch is not None:
        paths["fetch"] = FETCH_ADAPTERS[fetch]
    if throttle is not None:
        paths["throttle"] = THROTTLE_ADAPTERS[throttle]
    if calendar is not None:
        paths["calendar"] = CALENDAR_ADAPTERS[calendar]
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
