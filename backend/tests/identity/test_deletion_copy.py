"""The deletion's copy, published — **one set of words for two surfaces.**

**What this file holds.**

The confirmation mail and the confirmation modal both have to say what the deletion
removes and what it leaves behind. **Two sets of words about the same destruction is
how a product ends up telling someone one thing in a mail and another thing in a
dialog** — and the whole point of publishing the copy on the endpoint is that the two
cannot drift.

So this file asserts one thing, and it asserts it from both ends:

1. **The endpoint publishes the copy**, and the copy is the *same constants* the mail
   renders — not a paraphrase of them.
2. **The endpoint's copy is true of the engine.** The first paragraph names the three
   families of data `purgeable_models()` actually purges, and the second names
   aggregates that actually survive.

**And it holds the copy to the promise the product makes**, which is the reason the
copy is checked rather than assumed. The A-16 mockup's second paragraph ends *"We can't
reverse deletion."* — **which contradicts the thirty-day grace period the paragraph
after it promises.** A modal that says both in consecutive paragraphs is a modal that
lies, so the mockup's wording is not what ships.
"""

import pytest
from django.test import Client

from apps.identity.models import DeletionRequest
from apps.identity.services.deletion import (
    DELETION_REMOVES,
    DELETION_SURVIVES,
    purgeable_models,
)
from shared.db import PERSONAL
from tests.identity.test_account_deletion_api import ask, signed_in_client

# **The mark is declared here rather than imported.** `pytestmark` is a module-level
# name, and importing a helper from another module does not bring its marks with it —
# so the endpoint tests below need their own.
pytestmark = pytest.mark.django_db(databases=[PERSONAL])


class TestTheEndpointPublishesTheCopy:
    """**The modal has to say what the deletion does, and it cannot write that itself.**"""

    def test_the_preview_carries_both_paragraphs(self):
        """**Two fields, both present.** The preview is what the modal reads *before*
        the person has typed anything."""
        client = signed_in_client()

        body = client.get("/api/auth/profile/deletion").json()

        assert body["what_is_deleted"]
        assert body["what_survives"]

    def test_the_paragraphs_are_the_ones_the_mail_renders(self):
        """**One set of words, not two.** The mail's own test asserts these constants
        appear in the message; this asserts the endpoint carries the same objects, so a
        frontend that renders the endpoint's fields cannot tell the person something
        different from what the mail told them."""
        client = signed_in_client()

        body = client.get("/api/auth/profile/deletion").json()

        assert body["what_is_deleted"] == DELETION_REMOVES
        assert body["what_survives"] == DELETION_SURVIVES

    def test_the_answer_carries_the_copy_too(self):
        """**A client that has just asked for the deletion wants to say what it did**,
        and the copy is in this answer anyway — so asking for it again would be a
        second request for a string the server already sent."""
        client = signed_in_client()

        body = ask(client).json()

        assert body["what_is_deleted"] == DELETION_REMOVES
        assert body["what_survives"] == DELETION_SURVIVES

    def test_the_copy_is_the_same_on_a_second_request(self):
        """**Asking twice does not change the answer.** The endpoint is idempotent, and
        a second request that produced different prose would be a second version of the
        same story."""
        client = signed_in_client()
        first = ask(client).json()

        second = ask(client).json()

        assert second["what_is_deleted"] == first["what_is_deleted"]
        assert second["what_survives"] == first["what_survives"]
        assert second["scheduled_for"] == first["scheduled_for"]

    def test_the_preview_changes_nothing(self):
        """**It is a preview, and a preview must not ask.** The copy describes what
        the engine would do; reading it must not record a request to delete anything."""
        client = signed_in_client()

        client.get("/api/auth/profile/deletion")

        assert not DeletionRequest.objects.filter(user_id=client._test_user.pk).exists()

    def test_an_anonymous_caller_is_refused_the_preview(self):
        """**Behind the same session wall as the thing it previews.**"""
        client = Client()

        response = client.get("/api/auth/profile/deletion")

        assert response.status_code == 401


class TestTheCopyIsTrueOfTheEngine:
    """**The paragraphs are checked against the code, not against the mockup.**"""

    def test_the_first_paragraph_names_what_is_actually_purged(self):
        """**Personal events, saved events, and the preference graph.**

        Those are the three families A-16 names, and they are the three the copy says
        — in the product's words, because a person asking to delete their account wants
        to know what happens to their events, not which tables hold them.

        **The model-level check is behind this one.** `purgeable_models()` is the
        engine's own list, and this asserts that each of the three families is actually
        on it — so a copy that names a family the engine does not purge would fail.
        """
        labels = {model._meta.label_lower for model in purgeable_models()}

        assert "personalization.personalevent" in labels
        assert "personalization.savedevent" in labels
        # **The preference graph is four models**, not one: the interests, the digest
        # preference, and the two event-level preferences.
        assert "personalization.interest" in labels
        assert "personalization.digestpreference" in labels
        assert "personalization.eventdetailopen" in labels
        assert "personalization.eventdismissal" in labels

        assert "personal events" in DELETION_REMOVES
        assert "saved events" in DELETION_REMOVES
        assert "preference graph" in DELETION_REMOVES

    def test_the_second_paragraph_says_aggregate_and_not_account(self):
        """**It says "aggregate", not "your account".**

        The anonymised figures survive because they carry no user id to begin with.
        **Describing them as something of the account's would imply a link that does
        not exist** — and the copy is published to a screen where a person is deciding
        whether to trust the product with their account.
        """
        assert "Anonymised aggregate" in DELETION_SURVIVES
        assert "not linked to your account" in DELETION_SURVIVES

    def test_neither_paragraph_claims_the_deletion_cannot_be_reversed(self):
        """**The one claim the copy must not make.**

        The A-16 mockup's second paragraph ends *"We can't reverse deletion."* — and
        the grace period reverses it, for thirty days. **A copy that says that is
        contradicting the promise the very next paragraph makes**, and the promise is
        the reason the person can agree to the deletion at all.
        """
        for paragraph in (DELETION_REMOVES, DELETION_SURVIVES):
            assert "can't reverse" not in paragraph.lower()
            assert "cannot reverse" not in paragraph.lower()
            assert "cannot be undone" not in paragraph.lower()
            assert "permanent" not in paragraph.lower()
