"""The fake adapters are deterministic, free and safe to run anywhere."""

import math
import uuid
from datetime import UTC

import pytest

from adapters.billing.fake import FAKE_BILLING_URL, FakeBillingAdapter
from adapters.calendar.fake import FakeCalendarAdapter
from adapters.llm.fake import FAKE_MODEL, FakeEmbeddingAdapter, FakeLLMAdapter
from ports.billing import BillingCustomer, ProPlan
from ports.calendar import CalendarFeed, Credential
from ports.llm import LLMRequest

REQUEST = LLMRequest(
    task="extract_event", instructions="Extract the event", untrusted_content="Jazz night at 8pm"
)


def test_fake_llm_is_deterministic_and_free():
    first = FakeLLMAdapter().complete(REQUEST)
    second = FakeLLMAdapter().complete(REQUEST)

    assert first == second
    assert first.model == FAKE_MODEL
    assert first.input_tokens == 7
    assert first.cost_micros == 0


def test_fake_llm_result_changes_with_the_content():
    other = LLMRequest(REQUEST.task, REQUEST.instructions, "Book fair on Sunday")

    assert FakeLLMAdapter().complete(other).text != FakeLLMAdapter().complete(REQUEST).text


@pytest.mark.parametrize("dimensions", [1, 256, 512])
def test_fake_embeddings_are_unit_vectors_of_the_requested_size(dimensions):
    result = FakeEmbeddingAdapter().embed(["jazz night", "book fair"], dimensions=dimensions)

    assert len(result.vectors) == 2
    for vector in result.vectors:
        assert len(vector) == dimensions
        assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0)
    assert result.input_tokens == 4
    assert result.cost_micros == 0


def test_fake_embeddings_same_text_same_vector_different_text_different_vector():
    adapter = FakeEmbeddingAdapter()
    [a, b, a_again] = adapter.embed(["jazz", "books", "jazz"], dimensions=8).vectors

    assert a == a_again
    assert a != b


def test_fake_embeddings_reject_non_positive_dimensions():
    with pytest.raises(ValueError, match="dimensions"):
        FakeEmbeddingAdapter().embed(["jazz"], dimensions=0)


def test_fake_billing_returns_local_urls():
    adapter = FakeBillingAdapter()
    customer = BillingCustomer(user_id=uuid.uuid4(), email="dev@example.test")

    checkout = adapter.create_checkout(
        customer, ProPlan.YEARLY, success_url="http://x.test/ok", cancel_url="http://x.test/no"
    )
    portal = adapter.create_portal_session("cus_fake", return_url="http://x.test/account")

    assert checkout.url.startswith(f"{FAKE_BILLING_URL}/checkout?")
    assert f"session={checkout.session_id}" in checkout.url
    assert "plan=yearly" in checkout.url
    assert portal.url.startswith(f"{FAKE_BILLING_URL}/portal?")


def test_fake_calendar_entries_are_aware_utc_and_ordered():
    result = FakeCalendarAdapter().fetch_entries(
        CalendarFeed(url=Credential("webcal://example.test/private-abc123/basic.ics"))
    )

    assert result.entries
    for entry in result.entries:
        assert entry.starts_at.tzinfo is UTC
        assert entry.starts_at < entry.ends_at


def test_credential_never_shows_its_value():
    secret = "webcal://example.test/private-abc123/basic.ics"
    feed = CalendarFeed(url=Credential(secret))

    assert secret not in repr(feed)
    assert secret not in str(feed.url)
    assert secret not in f"{feed.url}"
    assert feed.url.reveal() == secret
    assert feed.url == Credential(secret)


def test_calendar_entry_repr_hides_the_title():
    result = FakeCalendarAdapter().fetch_entries(CalendarFeed(url=Credential("x")))
    [entry, *_] = result.entries

    assert entry.title not in repr(entry)


def test_fake_billing_parses_an_event_from_its_own_body_shape():
    """The fake's `parse_event` is what lets the webhook receiver be tested with no SDK.

    Its body shape is its own, not Stripe's: a test writes what it means rather than
    reconstructing a provider envelope the adapter would only throw away.
    """
    import json

    from adapters.billing.fake import FAKE_SIGNATURE
    from ports.billing import BillingEventKind

    payload = json.dumps(
        {
            "kind": "subscription_ended",
            "event_id": "evt_fake_1",
            "occurred_at": 1_762_000_000,
            "subscription_ref": "sub_1",
        }
    ).encode()

    event = FakeBillingAdapter().parse_event(payload, signature=FAKE_SIGNATURE)

    assert event.kind is BillingEventKind.SUBSCRIPTION_ENDED
    assert event.subscription_ref == "sub_1"
    assert event.occurred_at.timestamp() == 1_762_000_000


def test_fake_billing_refuses_a_wrong_signature():
    """So a test can exercise the receiver's 400 path without a signing secret."""
    import json

    from ports.billing import InvalidWebhookSignature

    with pytest.raises(InvalidWebhookSignature):
        FakeBillingAdapter().parse_event(json.dumps({}).encode(), signature="nope")


def test_fake_billing_defaults_an_unnamed_kind_to_ignored():
    import json

    from adapters.billing.fake import FAKE_SIGNATURE
    from ports.billing import BillingEventKind

    event = FakeBillingAdapter().parse_event(
        json.dumps({"event_id": "e"}).encode(), signature=FAKE_SIGNATURE
    )
    assert event.kind is BillingEventKind.IGNORED
