"""In-memory email adapter for tests: records each send instead of delivering it."""

from dataclasses import dataclass

from ports.email import EmailMessage, EmailPort, SendResult, Stream


@dataclass(frozen=True)
class SentEmail:
    message: EmailMessage
    stream: Stream
    idempotency_key: str


class InMemoryEmailAdapter(EmailPort):
    def __init__(self) -> None:
        self.sent: list[SentEmail] = []

    def _deliver(
        self, message: EmailMessage, *, stream: Stream, idempotency_key: str
    ) -> SendResult:
        self.sent.append(SentEmail(message, stream, idempotency_key))
        return SendResult(provider_message_id=f"memory-{len(self.sent)}")
