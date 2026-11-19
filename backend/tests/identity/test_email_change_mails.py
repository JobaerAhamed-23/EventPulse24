"""The two letters an email change owes, and the one that is a security control.

**The confirmation proves the new address. The warning defends the old one.** They are
tested apart because they fail differently: a confirmation sent to the wrong address
proves nothing, and a warning that carries the token *is* the attack it warns about.

The expiry in both is rendered from the constant that enforces it. A number typed into a
template keeps saying "30 minutes" after the constant says otherwise, which is a mail that
lies to the reader about their own security — so that is asserted rather than eyeballed.
"""

import pytest

from apps.identity.services.emails import (
    confirm_email_change_link,
    email_change_stream,
    render_confirm_email_change_email,
    render_email_change_requested_email,
    render_reset_password_email,
)
from ports.email import Stream
from shared.constants import AUTH_EMAIL_CHANGE_TOKEN_LIFETIME, AUTH_RESET_TOKEN_LIFETIME

TOKEN = "a-raw-token-that-should-not-leak"
OLD = "maya@example.test"
NEW = "maya.new@example.test"


class TestTheConfirmation:
    def test_it_goes_to_the_new_address(self):
        """**Swapping the recipients must fail.** Sent to the old address it proves
        nothing — the point is that the *new* mailbox is reachable."""
        message = render_confirm_email_change_email(to=NEW, token=TOKEN)

        assert message.to == NEW

    def test_it_carries_the_link_with_the_token(self):
        message = render_confirm_email_change_email(to=NEW, token=TOKEN)

        assert confirm_email_change_link(TOKEN) in message.text_body
        assert TOKEN in message.text_body

    def test_the_link_points_at_the_frontend(self, settings):
        """The frontend is a different origin from this runtime, so the base URL is
        configuration — the same rule `reset_password_link` follows."""
        settings.FRONTEND_BASE_URL = "https://example.test/"

        assert confirm_email_change_link(TOKEN).startswith("https://example.test/confirm-email?")

    def test_it_states_the_expiry_from_the_constant(self):
        message = render_confirm_email_change_email(to=NEW, token=TOKEN)

        hours = int(AUTH_EMAIL_CHANGE_TOKEN_LIFETIME.total_seconds() // 3600)
        assert f"{hours} hours" in message.text_body

    def test_it_says_nothing_has_changed_yet(self):
        """A person who did not expect this must be able to tell that reading it is not
        itself consent."""
        message = render_confirm_email_change_email(to=NEW, token=TOKEN)

        assert "nothing changes" in message.text_body.lower()


class TestTheWarning:
    def test_it_goes_to_the_old_address(self):
        message = render_email_change_requested_email(to=OLD, new_email=NEW)

        assert message.to == OLD

    def test_it_carries_no_token(self):
        """**It warns; it must not also be the means.** A warning that carried the token
        would hand the change to whoever intercepted the warning."""
        message = render_email_change_requested_email(to=OLD, new_email=NEW)

        assert TOKEN not in message.text_body
        assert "token=" not in message.text_body

    def test_it_carries_no_confirmation_link(self):
        message = render_email_change_requested_email(to=OLD, new_email=NEW)

        assert "/confirm-email" not in message.text_body

    def test_it_names_the_address_the_change_is_to(self):
        """A warning that will not say what is being changed is hard to act on."""
        message = render_email_change_requested_email(to=OLD, new_email=NEW)

        assert NEW in message.text_body

    def test_it_tells_the_reader_what_actually_stops_this(self):
        """**The remedy has to be real.** `confirm_email_change` checks a token, not a
        session, so the advice is only true because `reset_password` revokes outstanding
        requests — see `test_password_reset_revokes_a_pending_email_change`."""
        message = render_email_change_requested_email(to=OLD, new_email=NEW)

        assert "password" in message.text_body.lower()


class TestTheStream:
    def test_both_messages_are_transactional(self):
        """Security notices, not digests (AD-20). One of them is the only warning an
        account holder gets."""
        assert email_change_stream() is Stream.TRANSACTIONAL


class TestTheResetMailNoLongerRetypesItsExpiry:
    """The finding this item fixed on the way past.

    `password_reset.txt` said *"valid for 30 minutes"* as literal text, so changing
    `AUTH_RESET_TOKEN_LIFETIME` left the mail misstating its own rule.
    """

    def test_the_reset_mail_states_the_expiry_from_its_constant(self):
        message = render_reset_password_email(to=OLD, token=TOKEN)

        minutes = int(AUTH_RESET_TOKEN_LIFETIME.total_seconds() // 60)
        assert f"{minutes} minutes" in message.text_body

    def test_changing_the_constant_changes_the_copy(self, monkeypatch):
        """The assertion above would also pass against hard-coded text that happened to
        match. This one would not."""
        from datetime import timedelta

        from apps.identity.services import emails as module

        monkeypatch.setattr(module, "AUTH_RESET_TOKEN_LIFETIME", timedelta(minutes=45))

        message = render_reset_password_email(to=OLD, token=TOKEN)

        assert "45 minutes" in message.text_body
        assert "30 minutes" not in message.text_body
