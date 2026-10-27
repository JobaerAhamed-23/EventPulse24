"""AD-20: every send names its stream, enforced once in EmailPort.send for every adapter."""

import inspect

import pytest

from adapters.email.memory import InMemoryEmailAdapter
from ports.email import EmailMessage, EmailPort, Stream

MESSAGE = EmailMessage(to="dev@example.test", subject="Reminder", text_body="Starts in 1 hour")
BULK_MESSAGE = EmailMessage(
    to="dev@example.test",
    subject="Your Pulse Digest",
    text_body="Three events",
    unsubscribe_url="https://eventpulse24.test/unsubscribe/abc",
)


def test_send_signature_stream_is_keyword_only_without_default():
    parameter = inspect.signature(EmailPort.send).parameters["stream"]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty
    assert parameter.annotation is Stream


def test_send_without_stream_raises_type_error():
    adapter = InMemoryEmailAdapter()

    with pytest.raises(TypeError, match="stream"):
        adapter.send(MESSAGE, idempotency_key="k1")  # type: ignore[call-arg]

    assert adapter.sent == []


@pytest.mark.parametrize("stream", ["bulk", "transactional", None])
def test_send_with_plain_value_instead_of_stream_raises_type_error(stream):
    adapter = InMemoryEmailAdapter()

    with pytest.raises(TypeError, match="Stream"):
        adapter.send(MESSAGE, stream=stream, idempotency_key="k1")  # type: ignore[arg-type]

    assert adapter.sent == []


def test_bulk_send_without_unsubscribe_url_raises_value_error():
    adapter = InMemoryEmailAdapter()

    with pytest.raises(ValueError, match="unsubscribe_url"):
        adapter.send(MESSAGE, stream=Stream.BULK, idempotency_key="k1")

    assert adapter.sent == []


def test_send_with_empty_idempotency_key_raises_value_error():
    adapter = InMemoryEmailAdapter()

    with pytest.raises(ValueError, match="idempotency_key"):
        adapter.send(MESSAGE, stream=Stream.TRANSACTIONAL, idempotency_key="")


@pytest.mark.parametrize(
    ("message", "stream"),
    [(MESSAGE, Stream.TRANSACTIONAL), (BULK_MESSAGE, Stream.BULK)],
)
def test_valid_send_reaches_adapter_with_stream_and_key(message, stream):
    adapter = InMemoryEmailAdapter()

    result = adapter.send(message, stream=stream, idempotency_key="send:1")

    assert [(s.message, s.stream, s.idempotency_key) for s in adapter.sent] == [
        (message, stream, "send:1")
    ]
    assert result.provider_message_id == "memory-1"


def test_adapter_missing_deliver_cannot_be_instantiated():
    class Incomplete(EmailPort):
        pass

    with pytest.raises(TypeError, match="_deliver"):
        Incomplete()  # type: ignore[abstract]
