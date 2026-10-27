"""Send one test email through the email port (locally it lands in Mailpit)."""

from django.core.management.base import BaseCommand

from ports.email import EmailMessage, Stream
from ports.registry import get_email_port
from shared.constants import SEND_KEY_SEPARATOR
from shared.ids import uuid7

TEST_UNSUBSCRIBE_URL = "http://127.0.0.1:8000/unsubscribe/test"


class Command(BaseCommand):
    help = "Send a test email through the configured email adapter (Mailpit locally)."

    def add_arguments(self, parser):
        parser.add_argument("--to", default="dev@example.test")
        parser.add_argument(
            "--stream", choices=[stream.value for stream in Stream], default=Stream.TRANSACTIONAL
        )

    def handle(self, *args, **options):
        stream = Stream(options["stream"])
        result = get_email_port().send(
            EmailMessage(
                to=options["to"],
                subject=f"EventPulse24 test email ({stream.value})",
                text_body="If you can read this, the email port works.",
                unsubscribe_url=TEST_UNSUBSCRIBE_URL if stream is Stream.BULK else None,
            ),
            stream=stream,
            idempotency_key=f"test-email{SEND_KEY_SEPARATOR}{uuid7()}",
        )
        self.stdout.write(f"Sent on the {stream.value} stream: {result.provider_message_id}")
