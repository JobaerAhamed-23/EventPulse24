"""The ranking-transparency endpoint (FR-22): the formula, the scale, the amendment.

**What these tests hold.**

1. **The endpoint publishes the weights the product computes with** — asserted against
   `shared.constants`, never against literals written here. A test that restated the
   weights would be a third copy of them, free to agree with neither the constants nor
   the PRD.
2. **Every weight crosses the wire as a string.** FR-22's boundaries are exact and
   `domain/ranking.py` refuses floats throughout; a JSON number would be a double in the
   browser, on the page that exists to let a reader check the arithmetic.
3. **The weights sum to 1.00**, which is the check a reader of the surface should be able
   to make.
4. **The scale has all five steps**, including the 1-dot floor — a scale missing its
   bottom step reads as a four-step scale.
5. **The boundary rule is published.** An exact 0.85 is 4 dots, not 5, and a reader
   checking a score at a boundary gets the wrong answer without being told.
6. **Anonymous callers are refused.** The formula is not secret, but the surface is an
   authed settings screen, and an anonymous route to it would be a second, quieter one.
"""

import json
from decimal import Decimal
from uuid import uuid4

import pytest

from apps.identity.models import User
from shared.constants import (
    RANKING_BUCKET_2,
    RANKING_BUCKET_3,
    RANKING_BUCKET_4,
    RANKING_BUCKET_5,
    RANKING_SCORE_MIN,
    RANKING_TERM_LABELS,
    RANKING_WEIGHT_CITY,
    RANKING_WEIGHT_CONFIDENCE,
    RANKING_WEIGHT_INTEREST,
    RANKING_WEIGHT_RECENCY,
    RANKING_WEIGHT_RELIABILITY,
    RANKING_WEIGHT_SUM,
    RANKING_WEIGHTS_AMENDMENT,
    RANKING_WEIGHTS_AMENDMENT_DATE,
    RANKING_WEIGHTS_AMENDMENT_ID,
)
from shared.db import PERSONAL
from tests.csrf import CsrfClient

pytestmark = pytest.mark.django_db(databases=[PERSONAL])

RANKING = "/api/settings/ranking"


def signed_in():
    """A client whose session identifies a user."""
    account = User.objects.create_user(email=f"sam-{uuid4().hex[:8]}@example.test", password="pw")
    client = CsrfClient()
    client.force_login(account)
    return client


def read():
    response = signed_in().get(RANKING)
    assert response.status_code == 200
    return json.loads(response.content)


# ── The formula ───────────────────────────────────────────────────────────────────


def test_the_five_published_terms_are_the_constants_the_product_computes_with():
    """Not literals restated here — the constants themselves.

    A test that wrote `"0.35"` would be a third copy of the weight, free to drift from
    both `shared/constants.py` and the PRD.
    """
    expected = {
        "interest_overlap": RANKING_WEIGHT_INTEREST,
        "source_reliability": RANKING_WEIGHT_RELIABILITY,
        "recency": RANKING_WEIGHT_RECENCY,
        "city_match": RANKING_WEIGHT_CITY,
        "confidence": RANKING_WEIGHT_CONFIDENCE,
    }
    terms = read()["terms"]

    assert [term["key"] for term in terms] == [key for key, _ in RANKING_TERM_LABELS]
    for term in terms:
        assert Decimal(term["weight"]) == expected[term["key"]]


def test_each_label_is_the_servers_own_vocabulary():
    """The client never owns a list of formula terms."""
    labels = {key: label for key, label in RANKING_TERM_LABELS}
    for term in read()["terms"]:
        assert term["label"] == labels[term["key"]]


def test_every_weight_is_a_string_so_the_browser_cannot_make_it_a_float():
    """`Decimal("0.85")` is not the float `0.85`, and this page is about exactness."""
    body = read()
    for term in body["terms"]:
        assert isinstance(term["weight"], str)
    assert isinstance(body["total"], str)
    for bucket in body["buckets"]:
        assert isinstance(bucket["min_score"], str)


def test_the_weights_sum_to_one():
    """The check a reader of the surface should be able to make."""
    body = read()
    assert Decimal(body["total"]) == RANKING_WEIGHT_SUM == Decimal("1.00")
    assert sum(Decimal(term["weight"]) for term in body["terms"]) == Decimal("1.00")


# ── The scale ─────────────────────────────────────────────────────────────────────


def test_the_scale_has_all_five_steps_including_its_floor():
    """A scale missing its bottom step reads as a four-step scale."""
    buckets = read()["buckets"]
    assert [bucket["dots"] for bucket in buckets] == [5, 4, 3, 2, 1]
    assert [Decimal(bucket["min_score"]) for bucket in buckets] == [
        RANKING_BUCKET_5,
        RANKING_BUCKET_4,
        RANKING_BUCKET_3,
        RANKING_BUCKET_2,
        RANKING_SCORE_MIN,
    ]


def test_the_boundary_rule_is_published_because_an_exact_boundary_falls_lower():
    """0.850 is 4 dots, not 5. A reader checking a boundary needs to be told."""
    assert read()["boundary_rule"] == "lower"


# ── The amendment ─────────────────────────────────────────────────────────────────


def test_the_amendment_is_the_prd_one_with_the_adr_beside_it_and_a_date():
    """FR-22: the surface shows the current weights **and the last-amendment date**."""
    amendment = read()["amendment"]
    assert amendment["id"] == RANKING_WEIGHTS_AMENDMENT_ID
    assert amendment["record"] == RANKING_WEIGHTS_AMENDMENT
    assert amendment["date"] == RANKING_WEIGHTS_AMENDMENT_DATE.isoformat()


# ── The auth ──────────────────────────────────────────────────────────────────────


def test_an_anonymous_caller_is_refused():
    """The formula is not secret, but this is an authed settings surface."""
    assert CsrfClient().get(RANKING).status_code == 401
