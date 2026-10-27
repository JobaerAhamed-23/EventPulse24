"""Apps get adapters through ports.registry; settings.ADAPTERS decides which one."""

import pytest
from django.core.exceptions import ImproperlyConfigured

from adapters.billing.fake import FakeBillingAdapter
from adapters.calendar.fake import FakeCalendarAdapter
from adapters.email.memory import InMemoryEmailAdapter
from adapters.email.smtp import SmtpEmailAdapter
from adapters.llm.fake import FakeEmbeddingAdapter, FakeLLMAdapter
from ports.registry import (
    PORT_KEYS,
    get_billing_port,
    get_calendar_port,
    get_email_port,
    get_embedding_port,
    get_llm_port,
)


@pytest.mark.parametrize(
    ("getter", "expected"),
    [
        (get_llm_port, FakeLLMAdapter),
        (get_embedding_port, FakeEmbeddingAdapter),
        (get_email_port, SmtpEmailAdapter),
        (get_billing_port, FakeBillingAdapter),
        (get_calendar_port, FakeCalendarAdapter),
    ],
)
def test_default_fake_mode_returns_local_adapter(getter, expected):
    assert type(getter()) is expected


def test_changing_settings_switches_the_adapter(settings):
    settings.ADAPTERS = {**settings.ADAPTERS, "email": "adapters.email.memory.InMemoryEmailAdapter"}

    assert type(get_email_port()) is InMemoryEmailAdapter


def test_each_call_returns_a_fresh_adapter():
    assert get_llm_port() is not get_llm_port()


def test_missing_key_raises_improperly_configured(settings):
    settings.ADAPTERS = {k: v for k, v in settings.ADAPTERS.items() if k != "billing"}

    with pytest.raises(ImproperlyConfigured, match="'billing'"):
        get_billing_port()


def test_unimportable_path_raises_improperly_configured(settings):
    settings.ADAPTERS = {**settings.ADAPTERS, "llm": "adapters.llm.nope.Missing"}

    with pytest.raises(ImproperlyConfigured, match="cannot be imported"):
        get_llm_port()


@pytest.mark.parametrize(
    "path",
    [
        "adapters.llm.fake.FakeEmbeddingAdapter",  # an adapter for a different port
        "adapters.llm.fake.FAKE_MODEL",  # not a class at all
    ],
)
def test_path_not_implementing_the_port_raises_improperly_configured(settings, path):
    settings.ADAPTERS = {**settings.ADAPTERS, "llm": path}

    with pytest.raises(ImproperlyConfigured, match=r"does not implement ports\.llm\.LLMPort"):
        get_llm_port()


def test_every_port_has_a_settings_key(settings):
    assert set(PORT_KEYS.values()) == set(settings.ADAPTERS)
