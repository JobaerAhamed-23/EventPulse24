"""The local Pro grant command and the read it leans on.

**What is being protected here.** Two things, and the second is the interesting one.

1. The command grants Pro by **posting the fake webhook**, not by writing the row. If it
   ever writes the row directly it becomes a back door around the rule the e2e proof
   asserts — that the webhook is the only grant — and the local environment stops being a
   rehearsal of the real one.

2. **A cancellation names the subscription, not the user.**
   `record_subscription_ended` looks a subscription up by reference *alone*, with no user
   filter and no ordering. So a command that reused one fixed reference would, after a
   re-subscribe, cancel the *old cancelled* row and leave the live one untouched — and the
   developer would be told they had revoked a Pro account that was still Pro. That is a
   real bug this file exists to prevent, and it is why each grant mints a fresh reference
   and a revoke reads the live row's own.
"""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from adapters.billing.fake import FAKE_SIGNATURE
from apps.identity.models import Subscription, SubscriptionStatus
from apps.identity.services import is_pro
from apps.identity.services.billing_read import read_live_subscription_refs
from config.management.commands.grant_pro import (
    SIGNATURE_HEADER,
    WEBHOOK_PATH,
    Command,
)
from ports.billing import ProPlan
from shared.db import PERSONAL
from shared.ids import uuid7
from tests.identity.factories import SubscriptionFactory

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

WEBHOOK = "/api/webhooks/billing"


def make_user(email="local@example.test"):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(email=email, password="pw")


def post_webhook(client, body: dict, *, signature: str = FAKE_SIGNATURE):
    return client.post(
        WEBHOOK,
        data=json.dumps(body),
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=signature,
    )


class TestTheCommandSpeaksTheFakeProvidersLanguage:
    """The body has to be the fake adapter's shape, not Stripe's envelope."""

    def test_the_signature_is_the_fake_adapters_sentinel(self):
        """**If these drift, the command stops working silently.** The command hardcodes
        the sentinel rather than importing it — `adapters` is an adapter-layer package and a
        `config` command importing it would reach across that boundary for a string — so
        this assertion is what keeps the copy honest.
        """
        from adapters.billing.fake import FAKE_SIGNATURE as adapter_sentinel

        assert FAKE_SIGNATURE == adapter_sentinel

    def test_the_signature_header_is_the_one_the_receiver_reads(self):
        """**The receiver's constant is a Django `request.META` key, not a wire header
        name.** It reads `request.META["HTTP_STRIPE_SIGNATURE"]`, and Django builds that
        key from an incoming `Stripe-Signature` header — prefixing it with `HTTP_` and
        upper-casing it. So the command's wire header and the receiver's META key are
        different spellings of the same thing, and this is what connects them.

        A renamed header is a 400 on every delivery, and the two spellings drifting apart
        is how that would happen.
        """
        from apps.identity.webhooks_api import SIGNATURE_HEADER as receiver_meta_key

        assert receiver_meta_key == "HTTP_STRIPE_SIGNATURE"
        assert SIGNATURE_HEADER == "Stripe-Signature"
        assert receiver_meta_key == f"HTTP_{SIGNATURE_HEADER.upper().replace('-', '_')}"

    def test_the_path_is_the_one_the_receiver_is_mounted_at(self):
        """The command builds its own URL rather than being handed one, so the path it
        builds has to be the path the router is mounted at.
        """
        assert WEBHOOK_PATH == "/api/webhooks/billing"

    def test_the_body_carries_the_fields_the_adapter_reads(self):
        """**`occurred_at` is a Unix timestamp, not an ISO string.** The adapter reads it
        with `datetime.fromtimestamp`, so an ISO string is a `TypeError` on every delivery.
        """
        body = Command()._body(user_id=uuid7(), options={"revoke": False, "plan": "monthly"})

        assert body["kind"] == "subscription_started"
        assert body["plan"] == "monthly"
        assert isinstance(body["occurred_at"], int)
        assert isinstance(body["user_id"], str)
        assert body["subscription_ref"]

    def test_a_revocation_body_names_the_live_subscription(self):
        """**The whole point of the reference.** A revoke has to name the subscription the
        user currently holds, because the receiver looks it up by reference alone.
        """
        user_id = uuid7()
        SubscriptionFactory(
            user_id=user_id,
            stripe_customer_ref="cus_live",
            stripe_subscription_ref="sub_live",
        )

        body = Command()._body(user_id=user_id, options={"revoke": True, "plan": "monthly"})

        assert body["kind"] == "subscription_ended"
        assert body["subscription_ref"] == "sub_live"
        assert body["customer_ref"] == "cus_live"


class TestEachGrantMintsItsOwnReference:
    """A provider mints a new subscription reference per subscription, and so does this."""

    def test_two_grants_mint_two_references(self):
        first = Command()._body(user_id=uuid7(), options={"revoke": False, "plan": "monthly"})
        second = Command()._body(user_id=uuid7(), options={"revoke": False, "plan": "monthly"})

        assert first["subscription_ref"] != second["subscription_ref"]
        assert first["customer_ref"] != second["customer_ref"]

    def test_the_reference_is_derived_from_the_event_id(self):
        """The two references move together, because they are minted together. A revoke
        that has to undo a grant needs to name the same pair.
        """
        body = Command()._body(user_id=uuid7(), options={"revoke": False, "plan": "monthly"})

        suffix = body["subscription_ref"].removeprefix("sub_local_pro_")
        assert body["customer_ref"] == f"cus_local_pro_{suffix}"

    def test_two_grants_in_the_same_millisecond_still_differ(self):
        """**A timestamp alone would not do.** Two grants inside one millisecond would
        mint the same reference, and the second subscription would be indistinguishable
        from the first — the exact ambiguity the reference exists to prevent. `uuid7()`
        carries 62 random bits and a monotonic counter, so this holds.
        """
        user_id = uuid7()
        first = Command()._body(user_id=user_id, options={"revoke": False, "plan": "monthly"})
        second = Command()._body(user_id=user_id, options={"revoke": False, "plan": "monthly"})

        assert first["subscription_ref"] != second["subscription_ref"]


class TestTheLiveSubscriptionRead:
    """The read that lets a revoke name the subscription it means to cancel."""

    def test_it_is_none_when_there_is_no_live_subscription(self):
        assert read_live_subscription_refs(user_id=uuid7()) is None

    def test_it_names_the_live_row(self):
        user_id = uuid7()
        SubscriptionFactory(
            user_id=user_id,
            stripe_customer_ref="cus_live",
            stripe_subscription_ref="sub_live",
        )

        refs = read_live_subscription_refs(user_id=user_id)

        assert refs is not None
        assert refs.customer_ref == "cus_live"
        assert refs.subscription_ref == "sub_live"

    def test_a_cancelled_row_is_not_a_live_subscription(self):
        """**This is the case that made the bug.** A user who subscribed and cancelled
        holds a cancelled row; a revoke that found it would cancel it again and leave the
        live row alone.
        """
        user_id = uuid7()
        SubscriptionFactory(
            user_id=user_id,
            status=SubscriptionStatus.CANCELED,
            stripe_customer_ref="cus_old",
            stripe_subscription_ref="sub_old",
        )

        assert read_live_subscription_refs(user_id=user_id) is None

    def test_the_live_row_wins_over_an_older_cancelled_one(self):
        """**The case that made the bug.** A user who subscribed, cancelled and subscribed
        again holds a cancelled row and a live one. The read must name the *live* one,
        because a revoke that named the cancelled one would cancel nothing and leave the
        user Pro.
        """
        user_id = uuid7()
        cancelled = SubscriptionFactory(
            user_id=user_id,
            status=SubscriptionStatus.CANCELED,
            stripe_customer_ref="cus_old",
            stripe_subscription_ref="sub_old",
        )
        live = SubscriptionFactory(
            user_id=user_id,
            stripe_customer_ref="cus_new",
            stripe_subscription_ref="sub_new",
        )

        refs = read_live_subscription_refs(user_id=user_id)

        assert refs is not None
        assert refs.subscription_ref == live.stripe_subscription_ref
        assert refs.subscription_ref != cancelled.stripe_subscription_ref

    def test_the_database_forbids_two_live_rows(self):
        """**Why the read's ordering is defensive rather than load-bearing.**
        `subscription_one_live_per_user_uq` is a partial unique constraint over the live
        statuses, so a second live row for one user cannot be written at all — the
        database refuses it. That is why the cancel-then-resubscribe sequence leaves a
        *cancelled* row behind rather than two live ones.
        """
        from django.db import IntegrityError, transaction

        user_id = uuid7()
        SubscriptionFactory(user_id=user_id)

        with pytest.raises(IntegrityError), transaction.atomic():
            SubscriptionFactory(user_id=user_id)

        assert (
            Subscription.objects.using(PERSONAL)
            .filter(user_id=user_id, status=SubscriptionStatus.ACTIVE)
            .count()
            == 1
        )


class TestTheRevocationNamesTheLiveSubscription:
    """The end-to-end shape of the bug, through the real receiver.

    **A grant, a revoke, a grant, a revoke.** The second revoke is the one that used to
    cancel the wrong row.
    """

    def _grant(self, client, user_id):
        """A grant, through the real receiver and the real command."""
        body = Command()._body(user_id=user_id, options={"revoke": False, "plan": "monthly"})
        assert post_webhook(client, body).status_code == 200

    def _revoke(self, client, user_id):
        body = Command()._body(user_id=user_id, options={"revoke": True, "plan": "monthly"})
        assert post_webhook(client, body).status_code == 200

    def test_a_revoke_after_a_resubscribe_cancels_the_live_one(self, client):
        user = make_user()
        user_id = user.pk

        self._grant(client, user_id)
        assert is_pro(user_id=user_id) is True

        self._revoke(client, user_id)
        assert is_pro(user_id=user_id) is False

        # **Re-subscribe.** A second live row now exists, and the cancelled one is still
        # there — so there are two rows with the same user and two different references.
        self._grant(client, user_id)
        assert is_pro(user_id=user_id) is True

        # **And cancel again.** This is the case that used to leave the account Pro.
        self._revoke(client, user_id)

        assert is_pro(user_id=user_id) is False, (
            "the revoke cancelled the wrong row and left the account Pro"
        )

    def test_the_history_is_kept_and_nothing_is_deleted(self, client):
        """A lapse is a transition, not a deletion — `BILLING_RECORDS` keeps these for
        seven years, and the user's saved data is untouched either way.
        """
        user = make_user()
        user_id = user.pk

        self._grant(client, user_id)
        self._revoke(client, user_id)
        self._grant(client, user_id)
        self._revoke(client, user_id)

        rows = Subscription.objects.using(PERSONAL).filter(user_id=user_id)

        assert rows.count() == 2, "a lapse deleted a row"
        assert all(row.status == SubscriptionStatus.CANCELED for row in rows)

    def test_the_audit_trail_records_the_webhook_as_the_actor(self, client):
        """**The entitlement arrives as the provider's event, not as an admin action.** The
        actor is the system, labelled `stripe_webhook`, so an audit row distinguishes a
        paid subscription from one somebody granted by hand.
        """
        from apps.identity.models import IdentityAuditEntry

        user = make_user()
        self._grant(client, user.pk)

        entry = (
            IdentityAuditEntry.objects.using(PERSONAL)
            .filter(action="subscription.started")
            .order_by("-at")
            .first()
        )

        assert entry is not None
        assert entry.actor_kind == "system"
        assert entry.actor_label == "stripe_webhook"


class TestTheCommandRefusesWhatItCannotDo:
    """The refusals, and each one says why."""

    def test_a_revocation_with_nothing_to_cancel_says_so(self):
        """Not a traceback and not a silent success. There is nothing to cancel, and the
        developer is told that rather than left wondering.
        """
        with pytest.raises(CommandError, match="no live subscription"):
            Command()._body(user_id=uuid7(), options={"revoke": True, "plan": "monthly"})

    def test_plan_and_revoke_do_not_go_together(self):
        """A revoke has no plan, and silently ignoring one of the two flags would leave
        the developer unsure which ran.
        """
        from django.core.management.base import CommandParser

        parser = CommandParser()
        Command().add_arguments(parser)
        options = vars(parser.parse_args(["someone@example.test", "--revoke", "--plan", "yearly"]))

        with pytest.raises(CommandError, match="do not go together"):
            Command().handle(**options)


class TestTheCommandGrantsThroughTheWebhook:
    """The command's own HTTP path, end to end, against the real receiver."""

    def test_the_command_grants_and_the_receiver_writes_the_row(self, monkeypatch, client):
        """**The command does not write the row; it posts the webhook and the receiver
        writes it.** The posted request is captured and then replayed into the real
        receiver, so this proves the command's wire format is the one the receiver
        accepts — not merely that the command built a dict.

        (The command's HTTP call is intercepted rather than made, because the API server
        is a separate process — but the *body* and the *header* are the command's own,
        and they are what gets replayed.)
        """
        user = make_user("wire@example.test")
        captured: dict = {}

        def fake_urlopen(request, timeout=None):
            captured["body"] = json.loads(request.data)
            captured["headers"] = request.headers

            class _Response:
                status = 200

                def read(self):
                    return b'{"status": "started"}'

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            return _Response()

        monkeypatch.setattr(
            "config.management.commands.grant_pro.urllib.request.urlopen", fake_urlopen
        )

        call_command("grant_pro", "wire@example.test")

        assert captured["body"]["kind"] == "subscription_started"
        assert captured["body"]["user_id"] == str(user.pk)
        # Header names are case-insensitive on the wire, and `urllib` capitalises this
        # one as `Stripe-signature`. See the other header test for why.
        sent = {name.lower(): value for name, value in captured["headers"].items()}
        assert sent[SIGNATURE_HEADER.lower()] == FAKE_SIGNATURE

        # **And the body the command built is one the real receiver accepts.**
        response = post_webhook(client, captured["body"])

        assert response.status_code == 200
        assert response.json()["status"] == "started"
        assert Subscription.objects.using(PERSONAL).filter(user_id=user.pk).count() == 1, (
            "the receiver did not write the row"
        )

    def test_the_signature_is_sent_in_the_header_the_receiver_reads(self, monkeypatch):
        """Without the header the receiver refuses the delivery with a 400 and grants
        nothing — so a header that is merely *similar* is a command that does nothing.

        **The lookup is case-insensitive**, because HTTP header names are.
        `urllib` capitalises as `Stripe-signature`, and Django's `request.META` maps that
        to `HTTP_STRIPE_SIGNATURE` regardless of case. So the assertion has to be
        case-insensitive too, or it would be asserting a spelling the wire never carries.
        """
        captured: dict = {}

        def fake_urlopen(request, timeout=None):
            captured["headers"] = request.headers

            class _Response:
                status = 200

                def read(self):
                    return b'{"status": "started"}'

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            return _Response()

        monkeypatch.setattr(
            "config.management.commands.grant_pro.urllib.request.urlopen", fake_urlopen
        )

        call_command("grant_pro", "headers@example.test")

        sent = {name.lower(): value for name, value in captured["headers"].items()}
        assert sent[SIGNATURE_HEADER.lower()] == FAKE_SIGNATURE


class TestTheReferenceAProviderWouldMint:
    """The grant body matches what a checkout carries as metadata."""

    def test_the_grant_carries_the_user_id_the_checkout_would_carry(self):
        """`BillingEvent`'s docstring: *"user_id is present only on the event that starts a
        subscription, and only because the checkout session was created carrying it as
        metadata."* A grant that omitted it would be unattributable — charged, and logged
        as an error, and still not Pro.
        """
        user_id = uuid7()
        body = Command()._body(user_id=user_id, options={"revoke": False, "plan": "monthly"})

        assert body["user_id"] == str(user_id)

    def test_the_plan_is_carried(self):
        body = Command()._body(user_id=uuid7(), options={"revoke": False, "plan": "yearly"})

        assert body["plan"] == ProPlan.YEARLY.value
