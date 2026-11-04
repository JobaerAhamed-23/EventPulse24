"""In-memory revalidation adapter: records what would have been sent, and how it answered.

This is the fake the tests and local development use. It is the project's `adapter_mode=fake`
default, so a local run never calls the frontend and a test never needs a server.

**It records the requests rather than sending them**, so a test can assert *what paths were
signalled* — which is the part of this signal that is ours. What the frontend does with them
is the frontend's business, and is tested on the frontend's side.

**It can be told to answer with an outcome**, so the retry policy is testable without a
server that is down: `outcome=RevalidationOutcome.UNAVAILABLE` makes every delivery fail the
way a downed frontend would.
"""

from ports.revalidation import (
    RevalidationOutcome,
    RevalidationPort,
    RevalidationRequest,
    RevalidationResult,
)


class FakeRevalidationAdapter(RevalidationPort):
    """Records the signals it is given and answers with a fixed outcome.

    Args:
        outcome: What every delivery answers with. Defaults to delivered.
        status: The status to report alongside a non-delivered outcome.
    """

    def __init__(
        self,
        outcome: RevalidationOutcome = RevalidationOutcome.DELIVERED,
        status: int | None = None,
    ) -> None:
        #: What every delivery answers with. Settable, so a test can change the answer
        #: between two attempts (a frontend that recovers).
        self.outcome = outcome
        #: The status reported alongside a non-delivered outcome.
        self.status = status
        #: Every request it was given, in order.
        self.requests: list[RevalidationRequest] = []

    def revalidate(self, request: RevalidationRequest) -> RevalidationResult:
        self.requests.append(request)
        if self.outcome is RevalidationOutcome.DELIVERED:
            return RevalidationResult(outcome=self.outcome, status=204)
        return RevalidationResult(outcome=self.outcome, status=self.status)
