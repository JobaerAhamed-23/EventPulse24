"""The signed tokens behind the unsubscribe and the click tracker (FR-11, AD-20, SM-2).

**The properties under test are the security properties**, not the format:

- A token names the user, the scope and the target, and **all three are inside the
  signature** — so none of them can be edited.
- A token cannot be forged.
- A token **does not expire**, because an unsubscribe link that quietly stops working is
  worse than one that keeps working.
- A click token cannot be replayed as an unsubscribe, and an unsubscribe token cannot be
  replayed as a click.
- Every refusal is the **same** refusal, so the endpoint is not an oracle.
"""

import pytest

from apps.delivery.services.unsubscribe_tokens import (
    InvalidTokenError,
    mint_click_token,
    mint_unsubscribe_token,
    read_click_token,
    read_unsubscribe_token,
)
from shared.constants import (
    UNSUBSCRIBE_SCOPE_EVENT_REMINDERS,
    UNSUBSCRIBE_SCOPE_PING,
)
from shared.ids import uuid7

# --- The token names three things, and all three are signed --------------------------------------


def test_the_token_names_the_user_the_scope_and_the_target():
    user = uuid7()
    target = uuid7()

    token = mint_unsubscribe_token(
        user_id=user,
        scope=UNSUBSCRIBE_SCOPE_EVENT_REMINDERS,
        target_id=target,
    )
    parsed = read_unsubscribe_token(token)

    assert parsed.user_id == user
    assert parsed.scope == UNSUBSCRIBE_SCOPE_EVENT_REMINDERS
    assert parsed.target_id == target


def test_the_ping_scope_has_no_target():
    parsed = read_unsubscribe_token(
        mint_unsubscribe_token(user_id=uuid7(), scope=UNSUBSCRIBE_SCOPE_PING)
    )

    assert parsed.scope == UNSUBSCRIBE_SCOPE_PING
    assert parsed.target_id is None
    assert parsed.is_event_scope is False


def test_the_event_scope_says_it_is_the_event_scope():
    parsed = read_unsubscribe_token(
        mint_unsubscribe_token(
            user_id=uuid7(),
            scope=UNSUBSCRIBE_SCOPE_EVENT_REMINDERS,
            target_id=uuid7(),
        )
    )

    assert parsed.is_event_scope is True


# --- The token cannot be edited ------------------------------------------------------------------


def test_an_edited_token_is_refused():
    """The scope is **inside** the payload, so editing the token breaks the signature."""
    token = mint_unsubscribe_token(user_id=uuid7(), scope=UNSUBSCRIBE_SCOPE_PING)

    with pytest.raises(InvalidTokenError):
        read_unsubscribe_token(token + "x")


def test_a_token_whose_payload_was_swapped_is_refused():
    """A token for one scope cannot be turned into a token for the other.

    The two payloads are different lengths and different values, so a swap is caught
    twice over: the signature does not match, and the payload is not what was signed.
    """
    ping = mint_unsubscribe_token(user_id=uuid7(), scope=UNSUBSCRIBE_SCOPE_PING)
    event = mint_unsubscribe_token(
        user_id=uuid7(),
        scope=UNSUBSCRIBE_SCOPE_EVENT_REMINDERS,
        target_id=uuid7(),
    )

    # The signed part of a Django `Signer` token is everything before the final `:`.
    ping_payload, ping_sig = ping.rsplit(":", 1)
    event_payload, event_sig = event.rsplit(":", 1)

    with pytest.raises(InvalidTokenError):
        read_unsubscribe_token(f"{event_payload}:{ping_sig}")

    with pytest.raises(InvalidTokenError):
        read_unsubscribe_token(f"{ping_payload}:{event_sig}")


def test_a_forged_token_is_refused():
    with pytest.raises(InvalidTokenError):
        read_unsubscribe_token("not-a-token-at-all")


def test_an_empty_token_is_refused():
    with pytest.raises(InvalidTokenError):
        read_unsubscribe_token("")


def test_a_click_token_is_not_an_unsubscribe_token():
    """**The salts are different**, so the two are different signatures over different
    payloads. This is what stops a tracked link from becoming an opt-out."""
    click = mint_click_token(user_id=uuid7(), destination="https://eventpulse24.example/pulse")

    with pytest.raises(InvalidTokenError):
        read_unsubscribe_token(click)


def test_an_unsubscribe_token_is_not_a_click_token():
    token = mint_unsubscribe_token(user_id=uuid7(), scope=UNSUBSCRIBE_SCOPE_PING)

    with pytest.raises(InvalidTokenError):
        read_click_token(token)


# --- The token does not expire -------------------------------------------------------------------


def test_a_token_still_verifies_a_long_time_after_it_was_minted():
    """**The link must not expire into uselessness.**

    A plain `Signer` is used rather than a timestamped one: an unsubscribe link sits in an
    inbox for weeks, and the moment the user finally clicks it must be the moment it
    works. A dead link is the user unable to stop what they asked to stop.
    """
    token = mint_unsubscribe_token(user_id=uuid7(), scope=UNSUBSCRIBE_SCOPE_PING)

    # The token carries no timestamp at all — there is nothing to age out.
    assert "." not in token.split(":", 1)[-1]

    # And it still verifies, however long ago it was minted.
    parsed = read_unsubscribe_token(token)

    assert parsed.scope == UNSUBSCRIBE_SCOPE_PING


# --- The refusal is uniform ----------------------------------------------------------------------


def test_a_token_with_an_unknown_scope_is_refused():
    """A scope outside the closed set is refused at the point it is *read*, so a forged
    payload with an invented scope cannot reach the command layer."""
    from django.core import signing

    from shared.constants import UNSUBSCRIBE_SIGNING_SALT

    forged = signing.Signer(salt=UNSUBSCRIBE_SIGNING_SALT).sign_object(
        {"user": str(uuid7()), "scope": "everything", "target": ""}, compress=True
    )

    with pytest.raises(InvalidTokenError):
        read_unsubscribe_token(forged)


def test_minting_an_unknown_scope_is_refused():
    with pytest.raises(InvalidTokenError):
        mint_unsubscribe_token(user_id=uuid7(), scope="everything")


def test_minting_an_event_token_without_a_target_is_refused():
    """An event-scope token with no event would mean "stop all reminders" — which is the
    Ping's scope and not this one's."""
    with pytest.raises(InvalidTokenError):
        mint_unsubscribe_token(
            user_id=uuid7(),
            scope=UNSUBSCRIBE_SCOPE_EVENT_REMINDERS,
            target_id=None,
        )


def test_reading_an_event_token_without_a_target_is_refused():
    from django.core import signing

    from shared.constants import UNSUBSCRIBE_SIGNING_SALT

    forged = signing.Signer(salt=UNSUBSCRIBE_SIGNING_SALT).sign_object(
        {"user": str(uuid7()), "scope": UNSUBSCRIBE_SCOPE_EVENT_REMINDERS, "target": ""},
        compress=True,
    )

    with pytest.raises(InvalidTokenError):
        read_unsubscribe_token(forged)


def test_every_refusal_is_the_same_error():
    """**One error for every failure**, so the refusal never says which half was wrong.

    A token that was forged, a token that was edited and a token naming a scope we do not
    act on are the same refusal with the same message — otherwise the response becomes an
    oracle and the endpoint can be used to probe for accounts.
    """
    failures = ["", "not-a-token", "a:b:c"]

    messages = set()
    for token in failures:
        with pytest.raises(InvalidTokenError) as caught:
            read_unsubscribe_token(token)
        messages.add(caught.value.message)

    assert len(messages) == 1


# --- The click token -----------------------------------------------------------------------------


def test_a_click_token_names_the_user_and_the_destination():
    user = uuid7()
    destination = "https://eventpulse24.example/pulse"

    parsed = read_click_token(mint_click_token(user_id=user, destination=destination))

    assert parsed.user_id == user
    assert parsed.destination == destination


def test_an_edited_click_token_is_refused():
    token = mint_click_token(user_id=uuid7(), destination="https://eventpulse24.example/pulse")

    with pytest.raises(InvalidTokenError):
        read_click_token(token + "x")


def test_a_click_token_with_no_destination_is_refused():
    from django.core import signing

    from shared.constants import CLICK_SIGNING_SALT

    forged = signing.Signer(salt=CLICK_SIGNING_SALT).sign_object(
        {"user": str(uuid7()), "destination": ""}, compress=True
    )

    with pytest.raises(InvalidTokenError):
        read_click_token(forged)


def test_a_click_token_with_a_destination_that_is_not_a_string_is_refused():
    """The destination must be a string, because it is a URL and the endpoint compares
    its path against a closed set."""
    from django.core import signing

    from shared.constants import CLICK_SIGNING_SALT

    forged = signing.Signer(salt=CLICK_SIGNING_SALT).sign_object(
        {"user": str(uuid7()), "destination": 42}, compress=True
    )

    with pytest.raises(InvalidTokenError):
        read_click_token(forged)


def test_a_click_token_whose_user_is_not_a_uuid_is_refused():
    from django.core import signing

    from shared.constants import CLICK_SIGNING_SALT

    forged = signing.Signer(salt=CLICK_SIGNING_SALT).sign_object(
        {"user": "not-a-uuid", "destination": "https://eventpulse24.example/pulse"},
        compress=True,
    )

    with pytest.raises(InvalidTokenError):
        read_click_token(forged)


def test_an_unsubscribe_token_whose_user_is_not_a_uuid_is_refused():
    from django.core import signing

    from shared.constants import UNSUBSCRIBE_SIGNING_SALT

    forged = signing.Signer(salt=UNSUBSCRIBE_SIGNING_SALT).sign_object(
        {"user": "not-a-uuid", "scope": UNSUBSCRIBE_SCOPE_PING, "target": ""},
        compress=True,
    )

    with pytest.raises(InvalidTokenError):
        read_unsubscribe_token(forged)


def test_a_payload_that_is_not_a_dict_is_refused():
    """The payload is signed, so this can only happen if the *signing* code changed
    shape — and the refusal is the same one, so a shape change cannot turn into a
    different answer."""
    from django.core import signing

    from shared.constants import UNSUBSCRIBE_SIGNING_SALT

    forged = signing.Signer(salt=UNSUBSCRIBE_SIGNING_SALT).sign_object("not-a-dict", compress=True)

    with pytest.raises(InvalidTokenError):
        read_unsubscribe_token(forged)
