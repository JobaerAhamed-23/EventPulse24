"""How apps get an adapter: through its port, chosen by `settings.ADAPTERS`.

Apps never import adapters (the `apps | adapters` contract); settings name the class by dotted
string (`config/adapters.py`), resolved here. The only module in `ports` that touches Django.
"""

from typing import cast

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from ports.billing import BillingPort
from ports.blob import BlobPort
from ports.calendar import CalendarPort
from ports.email import EmailPort
from ports.embedding import EmbeddingPort
from ports.fetch import SourceFetchPort
from ports.geo import GeoPort
from ports.llm import LLMPort
from ports.revalidation import RevalidationPort
from ports.throttle import ThrottlePort

# settings.ADAPTERS key for each port.
PORT_KEYS: dict[type, str] = {
    LLMPort: "llm",
    EmbeddingPort: "embedding",
    EmailPort: "email",
    BillingPort: "billing",
    BlobPort: "blob",
    CalendarPort: "calendar",
    SourceFetchPort: "fetch",
    GeoPort: "geo",
    ThrottlePort: "throttle",
    RevalidationPort: "revalidation",
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


def get_blob_port() -> BlobPort:
    return get_adapter(BlobPort)


def get_calendar_port() -> CalendarPort:
    return get_adapter(CalendarPort)


def get_fetch_port() -> SourceFetchPort:
    return get_adapter(SourceFetchPort)


def get_geo_port() -> GeoPort:
    return get_adapter(GeoPort)


def get_throttle_port() -> ThrottlePort:
    return get_adapter(ThrottlePort)


def get_revalidation_port() -> RevalidationPort:
    return get_adapter(RevalidationPort)
