"""The auth mail (AD-18, AD-20).

Security notices, all of them on the **transactional** stream — a reset link, and the two
messages an email change owes — each carrying an idempotency key (AD-7).

The raw token appears in a message body and in its link, because the user has to follow
the link. It appears nowhere else: not in a log line, not in the audit row, and not in the
stored token row, which holds only a digest.

**An email change owes two messages, not one, and the second one is the security
control.** The confirmation goes to the new address and proves it. The warning goes to the
*old* address, because a credential that moves silently is an account takeover — and the
only person who can stop it is the one reading that warning. **So the warning carries no
token and no link that performs the change**: it tells someone that something is
happening, and it must not also be the means of making it happen.

**Every expiry in this file's copy is rendered from the constant that enforces it.** A
number typed into a template is a number that keeps saying "30 minutes" after the constant
says otherwise, which is a mail that lies to the reader about their own security.
"""

from django.conf import settings
from django.template.loader import render_to_string

from domain.sources import humanise_duration
from ports.email import EmailMessage, Stream
from shared.constants import (
    AUTH_EMAIL_CHANGE_TOKEN_LIFETIME,
    AUTH_RESET_TOKEN_LIFETIME,
    DATA_EXPORT_LINK_LIFETIME,
)


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
    body = render_to_string(
        "identity/password_reset.txt",
        {"reset_link": link, "valid_for": humanise_duration(AUTH_RESET_TOKEN_LIFETIME)},
    ).strip()
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


def confirm_email_change_link(token: str) -> str:
    """The confirmation link: the frontend's own route, with the token.

    The same shape and the same reasoning as `reset_password_link` — the frontend is a
    different origin from this runtime, so the base URL is configuration rather than
    something read off a request.
    """
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/confirm-email?token={token}"


def render_confirm_email_change_email(*, to: str, token: str) -> EmailMessage:
    """The message that proves a new address.

    Args:
        to: **The new address**, which is the one being proven. Sending this to the old
            address would prove nothing at all.
        token: The raw token. It goes into the link and nowhere else.
    """
    body = render_to_string(
        "identity/email_change_confirm.txt",
        {
            "confirm_link": confirm_email_change_link(token),
            "valid_for": humanise_duration(AUTH_EMAIL_CHANGE_TOKEN_LIFETIME),
        },
    ).strip()
    return EmailMessage(
        to=to,
        subject="Confirm your new EventPulse24 email address",
        text_body=body,
    )


def render_email_change_requested_email(*, to: str, new_email: str) -> EmailMessage:
    """The message that warns the **old** address that a change was asked for.

    **This is the control that makes the whole flow safe against a stolen session.** An
    attacker holding a live session can request a change to their own address; nothing in
    the request path can tell them apart from the account holder. This message can, because
    it reaches the person whose account it is.

    **It carries no token and no link that performs the change** (AD-13 for the token, and
    plain sense for the link): a warning that also completed the action would hand the
    means to whoever intercepted the warning.

    **It names the new address.** A warning that will not say what is being changed is hard
    to act on — and the account holder can already see the pending change on their own
    profile screen, so naming it here reveals nothing they could not already read.

    Args:
        to: **The old address** — the one still on the account.
        new_email: The address the change was requested to.
    """
    body = render_to_string(
        "identity/email_change_requested.txt",
        {
            "new_email": new_email,
            "valid_for": humanise_duration(AUTH_EMAIL_CHANGE_TOKEN_LIFETIME),
        },
    ).strip()
    return EmailMessage(
        to=to,
        subject="Someone asked to change your EventPulse24 email address",
        text_body=body,
    )


def email_change_stream() -> Stream:
    """The stream both email-change messages go on. Transactional: they are security
    notices, and one of them is the only warning an account holder gets.

    Named here rather than spelled at the call sites, for the reason
    `reset_password_stream` gives: the stream choice lives in one place, so a second auth
    mail cannot drift onto the wrong one by accident.
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
