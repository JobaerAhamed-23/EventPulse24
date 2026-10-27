"""Email port (AD-20): every send names its stream; transactional and bulk never share one."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import final


class Stream(StrEnum):
    """Sending stream, each with its own reputation (AD-20)."""

    TRANSACTIONAL = "transactional"  # reminders, state-change notices, auth
    BULK = "bulk"  # the Pulse Digest


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text_body: str
    html_body: str | None = None
    # RFC 8058 one-click unsubscribe target; required on the bulk stream.
    unsubscribe_url: str | None = None


@dataclass(frozen=True)
class SendResult:
    provider_message_id: str


class EmailPort(ABC):
    """Adapters implement `_deliver`; the AD-20 rules live in `send`, once for all of them."""

    @final  # adapters implement _deliver; overriding send would skip the AD-20 checks
    def send(self, message: EmailMessage, *, stream: Stream, idempotency_key: str) -> SendResult:
        """Send one message on an explicit stream.

        `stream` has no default: a send without one is a type error, not a default (AD-20).
        `idempotency_key` is the send key minted at row creation (AD-7).

        Raises:
            TypeError: `stream` is not a `Stream` (a plain "bulk" string included).
            ValueError: a bulk send has no unsubscribe URL, or the key is empty.
        """
        if not isinstance(stream, Stream):
            raise TypeError("stream must be a ports.email.Stream member")
        if stream is Stream.BULK and not message.unsubscribe_url:
            raise ValueError("bulk sends require an unsubscribe_url (RFC 8058)")
        if not idempotency_key:
            raise ValueError("idempotency_key is required (AD-7)")
        return self._deliver(message, stream=stream, idempotency_key=idempotency_key)

    @abstractmethod
    def _deliver(
        self, message: EmailMessage, *, stream: Stream, idempotency_key: str
    ) -> SendResult: ...
