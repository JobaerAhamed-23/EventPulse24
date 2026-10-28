"""How apps get an adapter: through its port, chosen by `settings.ADAPTERS`.

Apps never import adapters (the `apps | adapters` contract); settings name the class by dotted
string (`config/adapters.py`), resolved here. The only module in `ports` that touches Django.
"""

from typing import cast

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from ports.billing import BillingPort
from ports.calendar import CalendarPort
from ports.email import EmailPort
from ports.embedding import EmbeddingPort
from ports.llm import LLMPort

# settings.ADAPTERS key for each port.
PORT_KEYS: dict[type, str] = {
    LLMPort: "llm",
    EmbeddingPort: "embedding",
    EmailPort: "email",
    BillingPort: "billing",
    CalendarPort: "calendar",
}


def get_adapter[P](port: type[P]) -> P:
    key = PORT_KEYS[port]
    path = settings.ADAPTERS.get(key)
    if not path:
        raise ImproperlyConfigured(f"settings.ADAPTERS has no '{key}' adapter.")
    try:
        adapter = import_string(path)
    except ImportError as exc:
        raise ImproperlyConfigured(f"ADAPTERS['{key}'] = '{path}' cannot be imported.") from exc
    if not (isinstance(adapter, type) and issubclass(adapter, port)):
        raise ImproperlyConfigured(
            f"ADAPTERS['{key}'] = '{path}' does not implement {port.__module__}.{port.__name__}."
        )
    return cast(P, adapter())


def get_llm_port() -> LLMPort:
    return get_adapter(LLMPort)


def get_embedding_port() -> EmbeddingPort:
    return get_adapter(EmbeddingPort)


def get_email_port() -> EmailPort:
    return get_adapter(EmailPort)


def get_billing_port() -> BillingPort:
    return get_adapter(BillingPort)


def get_calendar_port() -> CalendarPort:
    return get_adapter(CalendarPort)
