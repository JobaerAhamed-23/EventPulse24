"""The ranking-transparency endpoint (FR-22): the screen behind `Settings → Privacy`.

`GET /api/settings/ranking` publishes the Relevance Pulse's formula, its 1-5 dot scale and
the amendment that last moved it.

**FR-22's promise is the *publication* of the formula**, not merely its existence: the
weights are "published in the PRD and immutable post-launch", and the requirement's own
testable consequence is that Settings -> Privacy -> "Ranking algorithm version" shows the
current weights and the last-amendment date. This endpoint is the half of that promise the
product owes; the PRD is the other half, and `tests/shared/test_constants.py` asserts the
two agree.

**Every value is projected from `shared.constants`.** Nothing here is a literal, and the
frontend holds no copy. A weights table typed into TypeScript would be a second source of
truth on the one page whose entire job is that there is exactly one, and it would drift
silently - which is the failure FR-22 was written to prevent.

**The decimals leave as strings.** `Decimal("0.85")` is not the float `0.85`, and
`domain/ranking.py` refuses floats throughout because an exact boundary decides a dot
count. Serialising a weight as a JSON number would hand the browser a double on the page
that exists to let a reader check the arithmetic.

**The auth is on the router**, as every other `settings` router's is: `auth=current_user`.
The response is the same for every caller - the formula is not personal - but the surface
is an authed settings screen (EXPERIENCE.md section 2, row 9), and an endpoint that
answered anonymously would be a second, quieter way to reach a settings surface.

**This is a read.** It opens no transaction, writes no audit row and touches no model. It
runs no query at all: the answer is a projection of module constants.
"""

from ninja import Router

from apps.identity.api_auth import current_user
from apps.personalization.schemas import (
    RankingAmendmentOut,
    RankingBucketOut,
    RankingTermOut,
    RankingTransparencyOut,
)
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

router = Router(tags=["settings"], auth=current_user)

#: Each published term's weight, by the key `RANKING_TERM_LABELS` names it with.
#:
#: **A mapping rather than a list of pairs**, so the labels and the weights cannot fall out
#: of order: the response is built by walking `RANKING_TERM_LABELS` and looking each key up
#: here. A key in one and not the other is caught at **import time** by the check below —
#: not at request time, which would be a 500 on a trust surface, and not silently, which
#: would be a mislabelled weight on one.
_WEIGHTS = {
    "interest_overlap": RANKING_WEIGHT_INTEREST,
    "source_reliability": RANKING_WEIGHT_RELIABILITY,
    "recency": RANKING_WEIGHT_RECENCY,
    "city_match": RANKING_WEIGHT_CITY,
    "confidence": RANKING_WEIGHT_CONFIDENCE,
}

#: The dot count for each boundary, highest first - FR-22's wireframe-locked scale.
#:
#: The 1-dot step has no lower bound to publish (every score below `RANKING_BUCKET_2` is
#: one dot), so it is listed with the floor of the clamped range rather than omitted: a
#: scale missing its bottom step would read as a four-step scale.
_BUCKETS = (
    (5, RANKING_BUCKET_5),
    (4, RANKING_BUCKET_4),
    (3, RANKING_BUCKET_3),
    (2, RANKING_BUCKET_2),
    (1, RANKING_SCORE_MIN),
)

# **The two tables must describe the same five terms, and that is checked here.**
#
# A label without a weight would raise `KeyError` while rendering a response — a 500 on
# the page whose job is to inspire confidence — and a weight without a label would simply
# never be published, which is worse: the formula would silently show four terms summing
# to less than the total printed beside them. Neither is worth discovering from a user.
# This runs once, when the module is imported, so the process does not start if they
# disagree.
_LABELLED = tuple(key for key, _ in RANKING_TERM_LABELS)
if set(_LABELLED) != set(_WEIGHTS):
    raise RuntimeError(
        "RANKING_TERM_LABELS and the published weights describe different terms: "
        f"{sorted(set(_LABELLED) ^ set(_WEIGHTS))}. FR-22 publishes a formula whose parts "
        "sum to the total printed beside them; a term with a label and no weight, or a "
        "weight and no label, breaks that promise."
    )

#: Which way an exact boundary falls. A score of exactly 0.85 shows **4** dots, not 5.
#:
#: Published because a reader checking the arithmetic at a boundary gets the wrong answer
#: without it, and FR-22's promise is that they can check it.
_BOUNDARY_RULE = "lower"


@router.get(
    "/ranking",
    response=RankingTransparencyOut,
    summary="The published Relevance Pulse formula, its scale and its amendment",
)
def read_ranking_transparency(request) -> RankingTransparencyOut:
    """FR-22's published formula, projected from the constants the product computes with."""
    return RankingTransparencyOut(
        terms=[
            RankingTermOut(key=key, label=label, weight=f"{_WEIGHTS[key]:.2f}")
            for key, label in RANKING_TERM_LABELS
        ],
        total=f"{RANKING_WEIGHT_SUM:.2f}",
        buckets=[
            RankingBucketOut(dots=dots, min_score=f"{minimum:.2f}") for dots, minimum in _BUCKETS
        ],
        boundary_rule=_BOUNDARY_RULE,
        amendment=RankingAmendmentOut(
            id=RANKING_WEIGHTS_AMENDMENT_ID,
            record=RANKING_WEIGHTS_AMENDMENT,
            date=RANKING_WEIGHTS_AMENDMENT_DATE,
        ),
    )
