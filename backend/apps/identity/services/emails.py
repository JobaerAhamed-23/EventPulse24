"""The auth mail (AD-18, AD-20).

One message: the password-reset mail. It goes on the **transactional** stream, because it
is a security notice rather than a digest, and it carries an idempotency key (AD-7).

The raw token appears in the message body and in the reset link — the user has to follow
the link, so that is unavoidable. It appears nowhere else: not in a log line, not in the
audit row, and not in the stored token row, which holds only a digest.
"""

from django.conf import settings
from django.template.loader import render_to_string

from ports.email import EmailMessage, Stream


def reset_password_link(token: str) -> str:
    """The reset link: the frontend's own `/reset-password` route, with the token.

    The frontend is a different origin from the API runtime, so the base URL comes from
    configuration rather than from a request.
    """
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password?token={token}"


def render_reset_password_email(*, to: str, token: str) -> EmailMessage:
    """Build the reset message for one token.

    Args:
        to: The account holder's address. It is the recipient, never a log field.
        token: The raw token. It goes into the link and nowhere else.
    """
    link = reset_password_link(token)
    body = render_to_string("identity/password_reset.txt", {"reset_link": link}).strip()
    return EmailMessage(
        to=to,
        subject="Reset your EventPulse24 password",
        text_body=body,
    )


def reset_password_stream() -> Stream:
    """The stream the reset mail goes on. Transactional: it is a security notice.

    The reset mail is a **security notice**, not a digest or a promotion, so it goes on the
    transactional stream (AD-20). It is named here rather than spelled at the call site, so
    the stream choice is in one place and a future second auth mail cannot drift onto the
    wrong one by accident.
    """
    return Stream.TRANSACTIONAL
