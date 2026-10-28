"""Calendar port (AD-18): read-only ICS/webcal import; every provider credential is a credential."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


class Credential:
    """A secret (e.g. a secret ICS URL). Its value never appears in `repr`, `str` or logs."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Credential('[redacted]')"

    __str__ = __repr__

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Credential) and other._value == self._value

    def __hash__(self) -> int:
        return hash(self._value)


@dataclass(frozen=True)
class CalendarFeed:
    url: Credential


@dataclass(frozen=True)
class CalendarEntry:
    uid: str
    title: str = field(repr=False)  # personal event content (AD-13)
    starts_at: datetime  # aware, UTC (AD-6)
    ends_at: datetime
    tz: str  # IANA name the entry was authored in


class CalendarPort(ABC):
    @abstractmethod
    def fetch_entries(self, feed: CalendarFeed) -> list[CalendarEntry]: ...
