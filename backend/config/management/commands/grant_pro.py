"""Grant or revoke Pro entitlement on a local account (FR-48).

**What this is for.** Entitlement in this product is a `Subscription` row, and the only
thing that writes one is the inbound billing webhook — `POST /api/webhooks/billing`, from
the provider's signed event. That rule is not incidental: `TestTheWebhookIsTheOnlyGrant`
in `tests/e2e/test_pro_tier_proof.py` asserts that a completed checkout grants nothing and
that an unsigned webhook grants nothing, because the alternative — granting on a redirect
the client controls — is the open-redirect bug in a checkout flow.

So this command does not write the row. **It posts the fake webhook**, the same one the
provider would post, with the fake adapter's sentinel signature. The entitlement therefore
arrives by exactly the route a real payment uses, through signature verification, the
event translation, the ordering guard and the audit write. Nothing here is a back door
around any of that.

**Why a command and not just a curl.** The body shape is the fake adapter's own — `kind`,
`event_id`, `occurred_at` as a Unix timestamp, `user_id` as a UUID — and the user id has
to come out of the database, because it is not in the URL or the cookie. That makes the
recipe a copy-paste with a lookup in the middle, and a lookup in the middle is where a
developer goes wrong at 11pm. This command is that recipe, once.

**It talks to the running API over HTTP rather than calling the receiver in-process.**
That is deliberate. In-process would skip the HTTP boundary, and the HTTP boundary is
where the signature header travels and where the 400-on-bad-signature path lives. Posting
over HTTP means the command exercises the same code a provider's delivery exercises, and
that a failure here is a failure a real delivery would also have. It also means the API
must be running: `make up && make api`.

**It will not work against a real adapter.** With `ADAPTER_MODE=real` the billing port is
`StripeBillingAdapter`, whose `parse_event` verifies a real HMAC — the fake sentinel is
not a signature it accepts, and the delivery is refused with a 400. That is correct: the
fake webhook is the fake provider's language, and a real provider does not speak it. The
command says so plainly rather than failing with a bare 400.

**It never deletes.** A revoke moves the row to `CANCELED`, which is what a real
cancellation does and what `BILLING_RECORDS` retention requires. Nothing the user saved,
built or configured is touched: a lapse removes the effect of their Pro features, not the
rows behind them. See `TestCancellationClosesEveryGate`.
"""

import json
import time
import urllib.error
import urllib.request
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from apps.identity.services.accounts import ensure_account
from apps.identity.services.billing_read import read_billing_account, read_live_subscription_refs
from shared.ids import uuid7

#: The signature the fake billing adapter accepts. `adapters.billing.fake.FAKE_SIGNATURE`.
#: Hardcoded rather than imported: `adapters` is an adapter-layer package, and a
#: `config` management command importing it would reach across the adapter boundary for a
#: string. The value is asserted against the adapter in
#: `tests/identity/test_local_pro_grant.py`, so the copy cannot drift unnoticed.
FAKE_SIGNATURE = "fake-signature"

#: The header the webhook receiver reads the signature from (`webhooks_api.SIGNATURE_HEADER`).
SIGNATURE_HEADER = "Stripe-Signature"

#: The endpoint the provider posts to (`config/api.py` mounts it at `/webhooks/billing`).
WEBHOOK_PATH = "/api/webhooks/billing"

#: Where the API listens locally. Overridable because the port moves when it clashes —
#: `.env` carries `API_PORT` for exactly that reason, and `make doctor` checks it.
DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"

#: The customer reference on a locally-granted subscription. Prefixed so it is obviously
#: local in the `personal` schema and in the audit trail, and so it cannot collide with a
#: reference a real provider minted.
LOCAL_CUSTOMER_REF = "cus_local_pro"

#: The subscription reference on a locally-granted subscription.
LOCAL_SUBSCRIPTION_REF = "sub_local_pro"

#: How long to wait for the API to answer.
REQUEST_TIMEOUT_SECONDS = 10


class Command(BaseCommand):
    help = (
        "Grant or revoke Pro entitlement on a local account by posting the fake billing "
        "webhook. Needs the API running and ADAPTER_MODE=fake."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "email",
            help="The account's email address. Created if it does not exist yet.",
        )
        parser.add_argument(
            "--password",
            default="localpro123",
            help="The password for the account, if it has to be created. Default: localpro123",
        )
        parser.add_argument(
            "--revoke",
            action="store_true",
            help="Cancel the subscription instead of granting it.",
        )
        parser.add_argument(
            "--plan",
            choices=["monthly", "yearly"],
            default="monthly",
            help="Which plan to grant. Default: monthly",
        )
        parser.add_argument(
            "--api-base-url",
            default=DEFAULT_API_BASE_URL,
            help=f"Where the API is running. Default: {DEFAULT_API_BASE_URL}",
        )

    def handle(self, *args, **options):
        # `--revoke` and `--plan` do not combine: a revoke has no plan to speak of, and
        # silently ignoring one of them would leave the developer unsure what ran.
        if options["revoke"] and options["plan"] != "monthly":
            raise CommandError("--plan and --revoke do not go together.")

        outcome = ensure_account(email=options["email"], password=options["password"])
        if outcome.created:
            self.stdout.write(
                f"Created the account {outcome.email} (password: {options['password']})."
            )
        else:
            self.stdout.write(f"Using the existing account {outcome.email}.")

        body = self._body(user_id=outcome.user_id, options=options)
        status, payload = self._post(url=options["api_base_url"], body=body)

        if status != 200:
            raise CommandError(
                f"The webhook was refused with {status}: {payload}\n"
                "If the API is running with ADAPTER_MODE=real, the fake signature is not "
                "accepted by the real adapter — switch to ADAPTER_MODE=fake for local work."
            )

        self.stdout.write(
            self._report(outcome=outcome, status=payload.get("status"), revoked=options["revoke"])
        )

    def _body(self, *, user_id: UUID, options: dict) -> dict:
        """The event body the fake adapter parses.

        **`occurred_at` is a Unix timestamp**, because `FakeBillingAdapter.parse_event` reads
        it with `datetime.fromtimestamp`. It is stamped *now* on every run, and that is
        load-bearing rather than cosmetic: `Subscription.last_event_at` is the ordering
        guard, and a stale timestamp is declined. A hard-coded date would make a re-grant
        after a revoke a no-op, and the developer would see a command that "did nothing".

        **Each grant mints a fresh subscription reference, and a revoke names the live
        row's own reference.** This is not a detail. A cancellation is applied by
        `record_subscription_ended`, which looks a subscription up by reference *alone* —
        `.filter(stripe_subscription_ref=...).first()`, with no user filter and no ordering.
        So a fixed reference is wrong twice over: it cannot cancel a second subscription,
        and it cancels whichever matching row comes first, which after a re-grant is the
        *old cancelled* one. The user would stay Pro and the command would say it had
        revoked them. A provider mints a new reference per subscription for exactly this
        reason, and so does this.
        """
        event_id = f"evt_local_{uuid7().hex}"
        now = int(time.time())

        if options["revoke"]:
            refs = read_live_subscription_refs(user_id=user_id)
            if refs is None:
                raise CommandError(
                    "That account holds no live subscription, so there is nothing to "
                    "cancel. (If it was cancelled already, that is the same thing.)"
                )
            customer_ref = refs.customer_ref
            subscription_ref = refs.subscription_ref
        else:
            # A fresh reference per subscription, as a provider mints one per checkout.
            # `uuid7()` rather than a timestamp: two grants in the same millisecond would
            # otherwise mint the same reference, and the second subscription would be
            # indistinguishable from the first — which is exactly the ambiguity this
            # reference exists to avoid.
            suffix = uuid7().hex
            customer_ref = f"{LOCAL_CUSTOMER_REF}_{suffix}"
            subscription_ref = f"{LOCAL_SUBSCRIPTION_REF}_{suffix}"

        common = {
            "event_id": event_id,
            "occurred_at": now,
            "customer_ref": customer_ref,
            "subscription_ref": subscription_ref,
            "user_id": str(user_id),
        }
        if options["revoke"]:
            return {"kind": "subscription_ended", **common}
        return {
            "kind": "subscription_started",
            "plan": options["plan"],
            **common,
        }

    def _post(self, *, url: str, body: dict) -> tuple[int, dict]:
        """Post the event to the webhook and return the status and the parsed body."""
        target = f"{url.rstrip('/')}{WEBHOOK_PATH}"
        request = urllib.request.Request(  # noqa: S310 — a fixed localhost URL, from configuration
            target,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                SIGNATURE_HEADER: FAKE_SIGNATURE,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310 — as above
                request, timeout=REQUEST_TIMEOUT_SECONDS
            ) as response:
                return response.status, self._parse(response.read())
        except urllib.error.HTTPError as error:
            # A 400 is the receiver refusing the delivery, which is an answer the command
            # has to report rather than swallow.
            return error.code, self._parse(error.read())
        except urllib.error.URLError as error:
            raise CommandError(
                f"Could not reach the API at {target}: {error.reason}\n"
                "Start it with `make api` (and `make up` for the databases)."
            ) from None

    def _parse(self, raw: bytes) -> dict:
        """The response body as a dict, or an empty one when it is not JSON."""
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw.decode(errors="replace")}
        return parsed if isinstance(parsed, dict) else {"raw": parsed}

    def _report(self, *, outcome, status: str | None, revoked: bool) -> str:
        """What the command says when it is done.

        **The outcome is read back from the database, not assumed from the intent.** The
        receiver answers `ended` for a revoke whether or not it changed anything, because
        `record_subscription_ended` matches on the subscription reference and a cancelled
        row still matches it. So "the receiver answered `ended`" is not the same claim as
        "this account is no longer Pro", and the second revoke of a cancelled account
        would otherwise be reported as though it had just cancelled something.

        So the state is read back through the same published read the account screen uses,
        and the message says what is true: the account is Pro, or it is not.
        """
        account = read_billing_account(user_id=outcome.user_id)
        if revoked:
            if account.is_pro:
                return (
                    f"{outcome.email} is still Pro (the receiver answered: {status}). "
                    "Nothing changed — the subscription may still be live."
                )
            return f"Revoked Pro for {outcome.email}. Open /settings/account to see the plan."
        if account.is_pro:
            return (
                f"Granted Pro for {outcome.email} ({account.plan}). "
                "Open /settings/account to see the plan."
            )
        return (
            f"{outcome.email} is not Pro (the receiver answered: {status}). "
            "Nothing changed — the account may already hold a live subscription."
        )


__all__ = ["Command"]
