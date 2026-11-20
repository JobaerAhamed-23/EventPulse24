"""The notice that says the account will be destroyed, and how to stop it.

**This mail is the only channel that reaches a user who has closed the tab.** The page
surface is there for someone looking at the site; this is here for someone who asked to
leave and then got cold feet. **If it did not carry a way to stop the deletion, the
thirty-day grace period would be a formality.**

**The mail and the modal make the same promise in two places, so they must not drift.**
Both say what is deleted, what survives as anonymised aggregates, and that the account
keeps working until the date. **One set of words serves both** — `DELETION_REMOVES` and
`DELETION_SURVIVES` in the deletion service — so the two surfaces cannot disagree.

**The expiry in the copy is rendered from the constant that enforces it.** A number typed
into a template keeps saying "30 days" after the constant says otherwise, which is a mail
that lies to the reader about their own account.
"""

from datetime import UTC, datetime, timedelta

from apps.identity.services.deletion import DELETION_REMOVES, DELETION_SURVIVES
from apps.identity.services.emails import (
    account_deletion_link,
    account_deletion_stream,
    render_account_deletion_email,
)
from ports.email import Stream
from shared.constants import DELETION_GRACE_PERIOD

TOKEN = "a-raw-cancel-token-that-should-not-leak"
TO = "maya@example.test"
SCHEDULED = datetime(2026, 12, 20, 9, 30, tzinfo=UTC)


def render(**overrides):
    kwargs = {
        "to": TO,
        "token": TOKEN,
        "scheduled_for": SCHEDULED,
        "what_is_deleted": DELETION_REMOVES,
        "what_survives": DELETION_SURVIVES,
    }
    kwargs.update(overrides)
    return render_account_deletion_email(**kwargs)


class TestTheRecipient:
    def test_it_goes_to_the_accounts_own_address(self):
        """**The account's own address is the recipient.** A notice sent anywhere else
        reaches nobody who can act on it."""
        message = render()

        assert message.to == TO

    def test_it_carries_the_token_in_the_link(self):
        """**The link is the whole point of the mail**, so the token must be in it."""
        message = render()

        assert TOKEN in message.text_body
        assert account_deletion_link(TOKEN) in message.text_body

    def test_the_link_points_at_the_frontend(self, settings):
        """The frontend is a different origin from this runtime, so the base URL is
        configuration — the same rule `reset_password_link` follows."""
        settings.FRONTEND_BASE_URL = "https://example.test/"

        assert account_deletion_link(TOKEN).startswith(
            "https://example.test/cancel-account-deletion?token="
        )


class TestWhatItSays:
    def test_it_carries_the_date_the_account_will_be_destroyed(self):
        """**The server's date, not a duration measured from now.** The deadline was
        computed once, when the request was made, and it does not move — so the mail
        states the date the row holds."""
        message = render()

        assert "20 December 2026" in message.text_body

    def test_it_says_what_is_deleted(self):
        """**The mail must not say less than the modal.** A person deciding whether to
        cancel needs to know what they are keeping as much as what they are losing."""
        message = render()

        assert "personal events" in message.text_body
        assert "saved events" in message.text_body
        assert "preference graph" in message.text_body

    def test_it_says_what_survives_as_anonymised_aggregates(self):
        """**"Aggregate", not "your account".** The anonymised figures carry no user id
        to begin with, and describing them as something of the account's would imply a
        link that does not exist."""
        message = render()

        assert "Anonymised aggregate" in message.text_body
        assert "not linked to your account" in message.text_body

    def test_it_says_the_account_keeps_working_until_then(self):
        """**The grace period is a promise, and the mail has to keep it.** Nothing is
        destroyed at request time."""
        message = render()

        assert "keeps working" in message.text_body

    def test_it_does_not_promise_a_follow_up_mail(self):
        """**The "your account has been destroyed" mail does not exist.**

        It cannot: when the account is destroyed its row is gone, so there is no address
        left to write to. Promising it here would be the same unkept promise the engine
        item refused to make."""
        message = render()

        lowered = message.text_body.lower()
        assert "will email you again" not in lowered
        assert "we will email you when" not in lowered

    def test_it_does_not_say_the_deletion_cannot_be_undone(self):
        """**The A-16 mockup says "Permanent. Cannot be undone." — and that is false.**

        The engine holds a thirty-day grace period, so the mockup's subtitle predates the
        engine and the copy must not follow it."""
        message = render()

        assert "cannot be undone" not in message.text_body.lower()

    def test_it_uses_the_shared_words_the_modal_uses(self):
        """**One source, two surfaces.** The mail and the modal state the same two facts,
        and they state them from the same strings — so a change to one is a change to
        both, rather than two sets of words about one destruction."""
        message = render()

        assert DELETION_REMOVES in message.text_body
        assert DELETION_SURVIVES in message.text_body


class TestTheExpiry:
    def test_it_states_the_grace_period_from_its_constant(self):
        """**A number typed into the template would keep saying "30 days" after the
        constant said otherwise** — which is a mail that lies about the reader's own
        account."""
        message = render()

        assert f"{DELETION_GRACE_PERIOD.days} days" in message.text_body

    def test_changing_the_constant_changes_the_copy(self, monkeypatch):
        """**The assertion above would also pass against hard-coded text that happened to
        match.** This one would not — it moves the constant and asks the copy to follow.
        """
        from apps.identity.services import emails as module

        monkeypatch.setattr(module, "DELETION_GRACE_PERIOD", timedelta(days=14))

        message = render()

        assert "14 days" in message.text_body
        assert "30 days" not in message.text_body


class TestTheStream:
    def test_the_notice_is_transactional(self):
        """**It is a one-time answer to something the user did**, not a list they
        subscribed to — so it carries no RFC 8058 unsubscribe URL (AD-20)."""
        assert account_deletion_stream() is Stream.TRANSACTIONAL
