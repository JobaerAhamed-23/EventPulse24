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
from shared.constants import DATA_EXPORT_LINK_LIFETIME


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


def data_export_link(*, export_id, token: str, fmt: str) -> str:
    """A download link for one export in one format.

    **It is the site's own origin plus `/api/...`, which is how every browser request in
    this product reaches Django** — the frontend proxies `/api` through. There is no
    separate public API origin to point at, and inventing a setting for one would create a
    second base URL that could disagree with the one every other link already uses.

    It is a direct link to the file rather than to a page that fetches it: a page in the
    middle is a second place for the token to live and a second thing to get wrong.
    """
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    return f"{base}/api/exports/{export_id}/{fmt}?token={token}"


def render_data_export_email(
    *, to: str, json_link: str, ics_link: str, locations_redacted: bool
) -> EmailMessage:
    """Build the "your data is ready" message (FR-52).

    **Transactional, like the reset mail.** It is a one-time answer to something the user
    asked for, not a list they subscribed to — so it carries no RFC 8058 unsubscribe URL,
    and `EmailPort.send`'s refusal of an unsubscribe-less *bulk* message does not apply.

    **The redaction is stated in the mail, not left to be discovered.** A user who opened a
    download and found "[redacted]" where their addresses should be would reasonably think
    the export was broken. Saying it here, where they are already reading, is the
    difference between a setting working and a file looking wrong.

    The links carry signed tokens. They appear in the body and nowhere else — not in a log
    line and not in an audit row (AD-13).
    """
    body = render_to_string(
        "identity/data_export_ready.txt",
        {
            "json_link": json_link,
            "ics_link": ics_link,
            "link_days": DATA_EXPORT_LINK_LIFETIME.days,
            "locations_redacted": locations_redacted,
        },
    ).strip()
    return EmailMessage(
        to=to,
        subject="Your EventPulse24 data is ready",
        text_body=body,
    )


def data_export_stream() -> Stream:
    """The stream the export mail goes on. Transactional: the user asked for it."""
    return Stream.TRANSACTIONAL
