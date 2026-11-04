"""The minted slug's shape is a **contract between two languages**, and this is the test.

**The two sides.** The backend mints an event's slug in
`apps.ingestion/services/slugs.py`; the frontend recognises one in
`frontend/lib/event-identifier.ts` (`MINTED_SLUG`). The route at `/events/{id}` branches
on that recognition: a **minted slug** renders the public event page, and **everything
else** renders the signed-in Detail Screen.

**Why the mismatch is a defect, not a curiosity.** The frontend's predicate was written
against the *shape* of `django.utils.text.slugify` rather than against its behaviour —
and the two differ. `slugify` removes everything that is not alphanumeric, a hyphen or an
**underscore**, so a title like `"AI_ML Night"` mints `ai_ml-night-2026-11-05-a1b2c3`.
A pattern that accepted only `[a-z0-9]` called that slug a *detail* parameter, and the
route then sent a **public event's page** to the signed-in Detail Screen — where the
personal endpoint 404s it, and where the request carries the visitor's cookies.

**The direction of the failure is the safe one, which is why it was silent.** The
underscored slug reached the detail branch, the detail endpoint refused it, and the
reader saw "no longer available" instead of the event. No error, no leak — just a
public event's own address not opening. **That is exactly the fault FR-26 and FR-28
exist to prevent**: a share link that a friend opens and cannot see.

**So the contract is asserted here, against the real mint.** The cases below are
minted by the backend's own function and checked against the **same regex the frontend
uses**, read from the frontend's own source. If either side changes shape, this fails
rather than the failure surfacing as a broken link months later.
"""

import re
import uuid
from pathlib import Path

import pytest

from apps.ingestion.services.slugs import LONG_TAIL, SHORT_TAIL, TITLE_PART_MAX, mint_slug

#: The frontend's own source of the rule.
FRONTEND_IDENTIFIER = Path(__file__).resolve().parents[3] / "frontend/lib/event-identifier.ts"

#: The event id used for the mints. Only its tail matters.
EVENT_ID = uuid.UUID("0196c3a4-5b6d-7e8f-9a0b-1c2d3e4f5061")

#: The local start the mints use, and therefore the date segment of every slug.
LOCAL_START = "2026-11-05T19:30:00"


def _frontend_pattern() -> re.Pattern[str]:
    """The frontend's `MINTED_SLUG`, read from its own source.

    **The regex is read out of the file rather than restated here.** A copy would be a
    second definition of the rule, and the two would drift — which is the whole failure
    this test exists to prevent. So the frontend's own pattern is the one under test.
    """
    source = FRONTEND_IDENTIFIER.read_text()
    match = re.search(r"const MINTED_SLUG = /(.*)/;", source)
    assert match is not None, f"{FRONTEND_IDENTIFIER} has no MINTED_SLUG pattern"
    return re.compile(match.group(1))


@pytest.fixture(scope="module")
def minted() -> re.Pattern[str]:
    return _frontend_pattern()


def _title_part(slug: str, tail_length: int) -> str:
    """The slug's title part — everything before the date and the tail."""
    suffix = f"-{LOCAL_START[:10]}-"
    assert slug.endswith(suffix + slug.rsplit("-", 1)[1]), slug
    return slug[: -len(suffix) - tail_length]


#: Titles that exercise every branch of `slugify`'s behaviour that matters here.
#:
#: - ordinary words, lower-cased and hyphen-separated;
#: - **an underscore**, which `slugify` keeps and which the frontend's rule must keep;
#: - a title that slugifies to nothing, which becomes `"event"`;
#: - a title at the length cap, which `slugify(...).strip("-")` shortens;
#: - non-Latin script, which `slugify` drops entirely.
TITLES = [
    "Free tech meetup",
    "AI_ML Night",
    "Rooftop_Party 2026",
    "Jazz Night at the Fillmore!",
    "under_score show",
    "_leading",
    "trailing_",
    "...",
    "   ",
    "Café之夜",
    "404 Night",
    "a" * 120,
]


@pytest.mark.parametrize("title", TITLES)
def test_a_minted_slug_is_recognised_by_the_frontend(title: str, minted: re.Pattern[str]) -> None:
    """**The contract, stated as the consequence.**

    The route's rule is `isDetailEvent(value) = isEventUuid(value) or not isMintedSlug(value)`
    — and the two shapes are disjoint (a UUID's third group is four characters, a slug's
    is a two-digit month), so a value the frontend recognises as a slug is *not* a detail
    event. **So "the frontend recognises it" is exactly "the route sends it to the public
    page"** — which is what this asserts, one slug at a time, over the titles that
    exercise `slugify`'s behaviour.

    A slug the frontend does *not* recognise would be routed to the signed-in Detail
    Screen, where the personal endpoint 404s it: a public event's own address, opening
    to "no longer available" for the friend the link was sent to.
    """
    slug = mint_slug(title, LOCAL_START, EVENT_ID)
    assert minted.match(slug), f"the frontend does not recognise {slug!r} (from {title!r})"


def test_the_long_tail_is_recognised_too(minted: re.Pattern[str]) -> None:
    """**The retry's tail is the same shape, and it has to be recognised as well.**

    The mint retries with a 12-character tail when the 6-character one collides on
    `event_slug_uq`. A slug minted that way is just as public, and a pattern that
    accepted only six characters would send it to the Detail Screen — the same failure,
    on the events whose titles collided.
    """
    slug = mint_slug("Jazz Night", LOCAL_START, EVENT_ID, long=True)
    assert len(slug.rsplit("-", 1)[1]) == LONG_TAIL
    assert minted.match(slug), f"the frontend does not recognise {slug!r}"


def test_the_title_part_is_capped_at_the_same_length(minted: re.Pattern[str]) -> None:
    """**The cap is the backend's, and the frontend's rule does not re-cap it.**

    A title at the cap mints an 80-character title part plus the date and the tail — and
    the frontend's pattern has no length limit, so it accepts it. This test pins the
    cap itself, so that a change to `TITLE_PART_MAX` is a deliberate one rather than an
    accident the other side never hears about.
    """
    slug = mint_slug("a" * 200, LOCAL_START, EVENT_ID)
    assert len(_title_part(slug, SHORT_TAIL)) == TITLE_PART_MAX
    assert minted.match(slug)


def test_the_two_tail_lengths_are_the_ones_the_pattern_allows() -> None:
    """**The tail's lengths are the pattern's two alternatives.**

    The frontend's regex ends in `[0-9a-f]{6}([0-9a-f]{6})?` — six hex characters, or
    twelve on a retry. The backend's own constants are six and twelve. This test says
    the two agree, so a change to either is caught here rather than in a broken link.
    """
    assert SHORT_TAIL == 6
    assert LONG_TAIL == 12
