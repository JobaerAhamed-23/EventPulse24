"""The SMTP adapter (Mailpit locally), checked through Django's test outbox (locmem mailer)."""

from django.core import mail

from adapters.email.smtp import IDEMPOTENCY_HEADER, STREAM_HEADER, SmtpEmailAdapter
from ports.email import EmailMessage, Stream


def test_transactional_send_has_stream_and_key_headers_and_no_unsubscribe():
    result = SmtpEmailAdapter().send(
        EmailMessage(to="dev@example.test", subject="Reminder", text_body="Starts in 1 hour"),
        stream=Stream.TRANSACTIONAL,
        idempotency_key="send:abc",
    )

    [sent] = mail.outbox
    assert sent.to == ["dev@example.test"]
    assert sent.subject == "Reminder"
    assert sent.body == "Starts in 1 hour"
    assert sent.extra_headers[STREAM_HEADER] == "transactional"
    assert sent.extra_headers[IDEMPOTENCY_HEADER] == "send:abc"
    assert sent.extra_headers["Message-ID"] == result.provider_message_id
    assert "List-Unsubscribe" not in sent.extra_headers
    assert "List-Unsubscribe-Post" not in sent.extra_headers


def test_bulk_send_carries_rfc_8058_one_click_headers():
    SmtpEmailAdapter().send(
        EmailMessage(
            to="dev@example.test",
            subject="Your Pulse Digest",
            text_body="Three events",
            html_body="<p>Three events</p>",
            unsubscribe_url="https://eventpulse24.test/unsubscribe/abc",
        ),
        stream=Stream.BULK,
        idempotency_key="digest:1",
    )

    [sent] = mail.outbox
    assert sent.extra_headers[STREAM_HEADER] == "bulk"
    assert sent.extra_headers["List-Unsubscribe"] == "<https://eventpulse24.test/unsubscribe/abc>"
    assert sent.extra_headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert sent.alternatives[0].content == "<p>Three events</p>"
    assert sent.alternatives[0].mimetype == "text/html"
