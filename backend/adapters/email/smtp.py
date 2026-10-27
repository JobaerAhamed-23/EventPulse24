"""SMTP email adapter. Locally it delivers to Mailpit (SMTP_HOST/SMTP_PORT via Django's mail)."""

from django.core.mail import EmailMultiAlternatives
from django.core.mail.message import make_msgid

from ports.email import EmailMessage, EmailPort, SendResult, Stream

FROM_ADDRESS = "EventPulse24 <no-reply@eventpulse24.local>"
STREAM_HEADER = "X-EventPulse-Stream"
IDEMPOTENCY_HEADER = "X-EventPulse-Idempotency-Key"


class SmtpEmailAdapter(EmailPort):
    def _deliver(
        self, message: EmailMessage, *, stream: Stream, idempotency_key: str
    ) -> SendResult:
        message_id = make_msgid(domain="eventpulse24.local")
        headers = {
            "Message-ID": message_id,
            STREAM_HEADER: stream.value,
            IDEMPOTENCY_HEADER: idempotency_key,
        }
        if stream is Stream.BULK:
            # RFC 8058 one-click unsubscribe (AD-20).
            headers["List-Unsubscribe"] = f"<{message.unsubscribe_url}>"
            headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        email = EmailMultiAlternatives(
            subject=message.subject,
            body=message.text_body,
            from_email=FROM_ADDRESS,
            to=[message.to],
            headers=headers,
        )
        if message.html_body:
            email.attach_alternative(message.html_body, "text/html")
        email.send(fail_silently=False)
        return SendResult(provider_message_id=message_id)
