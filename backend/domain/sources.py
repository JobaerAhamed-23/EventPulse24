"""FR-53's source tiers: which sources matter most, and how long one may go unpolled.

**Stdlib only**, like the rest of `domain`. This is a pure decision — a method value in, a
tier and a ceiling out — and it lives in `domain` because **three** call sites need it and
they are in different places: the registry's cleaner, the scheduler's floor check and the
migration. A pure function that three modules need does not belong to any one of them.

---

## Why the tier is derived and not stored

FR-53 says "high-priority sources (FR-13) at least every 4 hours. Lower-priority sources at
least daily" — and **FR-13 has no priority concept at all.** The cross-reference points at a
registry that never gained the field. The only definitional trace anywhere is the PRD's §10.4
paraphrase: *"high-priority sources (official sites) within 4 hours."*

So the tier is derived from the **acquisition method**, and the reasoning is FR-17's own:
`AcquisitionMethod`'s docstring says *"FR-17 priority order, highest first"* — official APIs >
partnerships > RSS/JSON-LD > email/ICS import > web crawling (last resort). The codebase
already holds a position on which sources matter more, and the method is already on the row.

**A second priority field would be a second opinion about a question the codebase has
already answered** — and the two could disagree. A priority that disagrees with the method is
a guarantee nobody can check: which one does the scheduler honour? Which one does the
database constraint enforce? A derived tier has exactly one answer, so there is no question.

**And it is safe by default.** A method added later — or one outside the choices — falls into
the lower tier and gets the 24-hour ceiling. A new acquisition method cannot opt itself out
of the guarantee by being unclassified.

---

## Ceilings, not defaults

FR-53's consequence is *"a cancelled event is detected by the system within 4 hours for
high-priority sources and within 24 hours for lower-priority sources."* A **default** is a
starting point; a **ceiling** is a guarantee. A source polled every 24 hours cannot have a
cancellation detected within 4 hours, so its cadence may not exceed the ceiling — the value
is refused where it is written, rather than discovered later when the product has already
promised on it.

**A source may poll more often than its tier requires.** The ceiling only forbids what the
guarantee cannot support. `DEFAULT_INGESTION_CADENCE` gives rss/jsonld/ics a 4-hour default
— inside the lower tier's 24-hour ceiling, and detecting changes in 4 hours rather than 24 —
and that is unchanged by this.
"""

from datetime import timedelta

from shared.constants import (
    HIGH_PRIORITY_CADENCE_MAX,
    HIGH_PRIORITY_METHODS,
    LOW_PRIORITY_CADENCE_MAX,
)

#: The two tiers, named. A closed set of two.
#:
#: `high` is FR-53's "high-priority"; `lower` is FR-53's "lower-priority".
HIGH_PRIORITY = "high"
LOWER_PRIORITY = "lower"


def source_priority(method: str) -> str:
    """The tier this source's acquisition method puts it in: `high` or `lower` (FR-53).

    **The high tier is the official sources** — the API and partnership methods. The PRD's
    §10.4 calls FR-53's high-priority sources "official sites", and the official sources are
    exactly these two.

    **Crawl is deliberately in the lower tier.** It is the last resort (FR-17), and a 4-hour
    floor on crawling would push the whole registry toward frequent crawls — which is exactly
    what the ToS guard exists to prevent. The ceiling is a guarantee, not an aspiration.

    **Anything not in the high set is lower.** That is not a whitelist of the known lower
    methods — it is the same rule the database constraint enforces, so the two layers cannot
    disagree about a method that did not exist when they were written.
    """
    return HIGH_PRIORITY if method in HIGH_PRIORITY_METHODS else LOWER_PRIORITY


def cadence_ceiling(method: str) -> timedelta:
    """The longest cadence this source's method may have (FR-53).

    **A ceiling, not a default.** A default is a starting point; this is a guarantee. A
    source polled every 24 hours cannot have a cancellation detected within 4 hours, so a
    cadence above the ceiling is refused where the value is written.

    **A source may poll more often than its tier requires.** The ceiling only forbids what
    the guarantee cannot support.
    """
    if source_priority(method) == HIGH_PRIORITY:
        return HIGH_PRIORITY_CADENCE_MAX
    return LOW_PRIORITY_CADENCE_MAX


def humanise_duration(duration: timedelta) -> str:
    """A duration as an operator reads it: "4 hours", "1 hour", "30 minutes".

    **Not a general formatter.** It handles whole hours and whole minutes — which is what a
    cadence can be — and falls back to the raw string for anything else rather than inventing
    a unit. It is used in refusal messages, where a wrong unit would misstate the rule.
    """
    seconds = int(duration.total_seconds())
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    if seconds % 60 == 0:
        minutes = seconds // 60
        return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"
    return str(duration)


__all__ = [
    "HIGH_PRIORITY",
    "LOWER_PRIORITY",
    "cadence_ceiling",
    "humanise_duration",
    "source_priority",
]
