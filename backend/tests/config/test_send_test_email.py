"""`manage.py send_test_email`: the manual Mailpit check, through the email port."""

import pytest
from django.core import mail
from django.core.management import call_command

from adapters.email.smtp import STREAM_HEADER


@pytest.mark.parametrize("stream", ["transactional", "bulk"])
def test_send_test_email_sends_one_message_on_the_chosen_stream(stream):
    call_command("send_test_email", "--to", "reader@example.test", "--stream", stream)

    [sent] = mail.outbox
    assert sent.to == ["reader@example.test"]
    assert sent.extra_headers[STREAM_HEADER] == stream
    assert ("List-Unsubscribe" in sent.extra_headers) is (stream == "bulk")


def test_send_test_email_defaults_to_transactional_for_dev_address():
    call_command("send_test_email")

    [sent] = mail.outbox
    assert sent.to == ["dev@example.test"]
    assert sent.extra_headers[STREAM_HEADER] == "transactional"
