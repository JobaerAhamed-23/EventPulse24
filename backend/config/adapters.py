"""Which adapter implements each port, per ADAPTER_MODE. Resolved by `ports.registry`."""

from django.core.exceptions import ImproperlyConfigured

# fake: local stand-ins, no API keys. Email still really sends, to Mailpit (SMTP_HOST/SMTP_PORT).
FAKE_ADAPTERS = {
    "llm": "adapters.llm.fake.FakeLLMAdapter",
    "embedding": "adapters.llm.fake.FakeEmbeddingAdapter",
    "email": "adapters.email.smtp.SmtpEmailAdapter",
    "billing": "adapters.billing.fake.FakeBillingAdapter",
    "calendar": "adapters.calendar.fake.FakeCalendarAdapter",
}

# Filled in by the intents that build the real gateway, email provider, Stripe and ICS adapters.
REAL_ADAPTERS: dict[str, str] = {}


def adapter_paths(mode: str) -> dict[str, str]:
    if mode == "fake":
        return dict(FAKE_ADAPTERS)
    missing = sorted(FAKE_ADAPTERS.keys() - REAL_ADAPTERS.keys())
    if missing:
        # Fail at startup rather than run stand-ins where real services are expected.
        raise ImproperlyConfigured(
            f"ADAPTER_MODE={mode} is not available yet: no real adapter for {', '.join(missing)}."
        )
    return dict(REAL_ADAPTERS)
