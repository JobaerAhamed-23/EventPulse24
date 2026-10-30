"""The Event Fit: the catalog's session-free explanation (AD-10, FR-26).

**This package is the wall, and the wall is why the package exists.**

AD-10 says the Event Fit and the Relevance Pulse are never substituted for one
another — "the trust-collapse failure PRD Risk 11 calls company-ending". Enforcing that
as a check on *import names* does not work: a wall made of names is opened by adding a
name. The first version of this contract named two leaves
(`apps.ingestion.services.event_fit` and `apps.ingestion.services.event_fit_read`), and
a third module that re-exported the read — two lines — gave `personalization` the
Event Fit with the contract **green**.

So the Event Fit is a **package**, and the contract names the package:

```
forbidden_modules = ["apps.ingestion.event_fit"]
```

A package is a single name that covers everything inside it. A new Event Fit module
is inside the wall by default, rather than outside it until somebody notices. The
wildcard `apps.ingestion.event_fit.*` is spelled out beside it so that a module
*inside* the package cannot be imported directly and sidestep the package's own
boundary.

Two modules live here:

* `writes` — the only writer of the `EventFit` rows. AD-5's named commands: an
  explicit `Actor` and `now`, and an audit row in the same transaction.
* `reads` — the published read for a city. It serves the **persisted** row and computes
  nothing, and it never touches the `personal` schema.

`domain/event_fit.py` holds the pure function that computes a fit. It is reachable from
here and from nowhere else.
"""

__all__ = [
    "reads",
    "writes",
]
