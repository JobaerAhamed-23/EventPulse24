"""The coverage request's wire shapes (AD-19).

**The surface owns the contract, so the shapes live here and not in the service that fills
them.** The data comes from `apps.ingestion.services.coverage_requests`, which owns the
command and hands over plain data.

**The request body carries a city and nothing else.** In particular it carries no user id:
the reader comes from the session, and an endpoint that accepted a user id in a payload
would be an endpoint whose scoping could be talked out of by the client. The same rule
`apps.identity.api_auth` states — *"the user id comes from the session, never from the
request body"* — and the reason every endpoint in this project refuses one.
"""

from ninja import Field, Schema


class CoverageRequestIn(Schema):
    """The request: the city to cover.

    **A city *name*, and only a city name.** The catalog is keyed by name at the wire and
    by id in the row, and the service resolves one to the other. The reader has the name —
    it is the city they picked — and the catalog has the id.

    **Bounded, and the bound is a refusal.** An empty city names no city, and one longer
    than the catalog's own name column cannot name one either, so both are a 422 rather
    than a lookup that would match nothing.
    """

    city: str = Field(..., min_length=1, max_length=100)


class CoverageRequestOut(Schema):
    """What one request produced.

    **`recorded` is the answer the control reads.** It is always true on a success — the
    endpoint has no other successful answer — and it is here so the control has something
    explicit to branch on rather than inferring from a status code it did not write.

    **`request_count` is the number editorial reads, and it is not the reader's business.**
    It is on the wire because the editorial surface reads it, and the reader's control
    does not show it: a reader who is told "you are the 47th person to ask" is being told
    something about a crowd, and the product's voice is calm.
    """

    city: str
    recorded: bool
    request_count: int
    #: Whether this call is the one that created the row. False for a repeat — the row
    #: was already there, and the count went up.
    created: bool


__all__ = ["CoverageRequestIn", "CoverageRequestOut"]
