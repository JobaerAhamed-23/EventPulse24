"""Event Fit: the session-free score and tags (AD-10, FR-26). Stdlib only.

AD-10 names **two** kinds of explanation and says both are persisted, neither is ever
recomputed at render:

| Kind | Computed | Persisted on | Serves | Owner |
| --- | --- | --- | --- | --- |
| **Event Fit** | per `(event, city)` | `catalog` | SEO pages, Pulse Preview | `ingestion` |
| Relevance Pulse | at digest composition | `personal` | card, detail, email | `personalization` |

This module is the first kind. The second lives in `personalization`, and the two look
identical on screen — which is why AD-10 says they must never be substituted for one
another. A visitor with no session can be shown an Event Fit and nothing else.

**The score.** Two inputs, both of which already exist on an `Event`: how soon it starts,
and how well its facts were extracted. The score is the **lower** of the two bands.

Taking the lower is the honest rule. A badly-extracted event happening tonight is not a
good fit, however soon it is — and a weighted sum would need weights that nobody can
justify without labelled data. Two bands and a minimum is a rule a person can state out
loud, which is the whole point of an indicator a stranger will read.

**The tags.** Generic, time- and place-based, and **the day boundaries are computed in the
event's own IANA timezone**, never UTC. An event at 23:30 local on Friday is "tonight" on
Friday, not on Saturday. That is the rule that is easiest to get wrong and the one the
tests are built around.

**`now` is an explicit parameter.** There is no clock read in this module and no
randomness anywhere in it: the same inputs always give the same output, and every
boundary is testable at the exact second. Nothing here is computed at render time —
`domain` has no idea a render exists.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from unicodedata import combining, normalize
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.constants import (
    EVENT_FIT_CONFIDENCE_FAIR,
    EVENT_FIT_CONFIDENCE_GOOD,
    EVENT_FIT_CONFIDENCE_HIGH,
    EVENT_FIT_EVENING_HOUR,
    EVENT_FIT_ONE_WEEK,
    EVENT_FIT_SCORE_MAX,
    EVENT_FIT_SCORE_MIN,
    EVENT_FIT_TAG_CITY_PREFIX,
    EVENT_FIT_TAG_ORDER,
    EVENT_FIT_TAG_THIS_WEEKEND,
    EVENT_FIT_TAG_TOMORROW,
    EVENT_FIT_TAG_TONIGHT,
    EVENT_FIT_TODAY,
    EVENT_FIT_TWO_DAYS,
    EVENT_FIT_TWO_WEEKS,
)

UTC_ZONE = "UTC"


@dataclass(frozen=True)
class EventFit:
    """One event's fit for one city: a 1–5 score and an ordered tuple of tag keys.

    Frozen, because a fit that could be mutated after it was computed is a fit whose
    meaning has drifted from the row it was persisted in.
    """

    score: int
    tags: tuple[str, ...]

    def __post_init__(self) -> None:
        if not EVENT_FIT_SCORE_MIN <= self.score <= EVENT_FIT_SCORE_MAX:
            raise ValueError(
                f"the fit score must be in "
                f"[{EVENT_FIT_SCORE_MIN}, {EVENT_FIT_SCORE_MAX}], not {self.score}"
            )


def _zone(name: str) -> ZoneInfo:
    """The event's own zone.

    An unknown zone falls back to UTC rather than raising: a fit is an *indicator*, and
    an event whose zone we cannot read should still get a score. The zone on an `Event`
    is validated at write time by the ingestion commands, so an unknown name here means
    the data is older or hand-edited — not that the event is invalid.
    """
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(UTC_ZONE)


def _proximity_band(until_start: timedelta) -> int:
    """The band for "how soon does this start", 5 being the soonest.

    A negative `until_start` — an event that has already begun — lands in the last band.
    An event in progress is not "tonight" any more, and it is certainly not a good fit
    for a preview that shows what is coming.

    The past check comes **first**, before the "under a day" check. An event that
    started an hour ago is under a day away in one sense, but it is in the past, and
    a negative duration is not "soon" — it is "already".
    """
    if until_start <= timedelta(0):
        return 1
    if until_start < EVENT_FIT_TODAY:
        return 5
    if until_start < EVENT_FIT_TWO_DAYS:
        return 4
    if until_start < EVENT_FIT_ONE_WEEK:
        return 3
    if until_start < EVENT_FIT_TWO_WEEKS:
        return 2
    return 1


def _confidence_band(confidence: Decimal | None) -> int:
    """The band for "how well do we know this event's facts", 5 being the best.

    An event with no extraction confidence scores on proximity alone. It is not a reason
    to refuse an indicator — the score would simply be the proximity band.
    """
    if confidence is None:
        return EVENT_FIT_SCORE_MAX
    if confidence >= EVENT_FIT_CONFIDENCE_HIGH:
        return 5
    if confidence >= EVENT_FIT_CONFIDENCE_GOOD:
        return 4
    if confidence >= EVENT_FIT_CONFIDENCE_FAIR:
        return 3
    return 2


def _city_tag(city: str) -> str | None:
    """`in_<city>`, or None when the city is empty.

    The slug is lowercased and the non-alphanumerics become single underscores, so
    "San Francisco" and "san francisco" produce the same key. An event with no venue city
    gets **no** Event Fit row at all, rather than a guessed one — so an empty city here
    means no place tag.

    Accents are folded to their ASCII base ("São Paulo" → `in_sao_paulo`) because a tag
    key has to survive a JSON round-trip, a URL segment and a CSS selector unchanged.
    A key with a non-ASCII character in it is a key that eventually breaks in one of
    those three places, and the tag is shown to a stranger, so it has to be plain.
    """
    ascii_city = normalize("NFKD", city.strip())
    ascii_city = "".join(character for character in ascii_city if not combining(character))
    cleaned = "".join(character.lower() if character.isalnum() else "_" for character in ascii_city)
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    if not cleaned:
        return None
    return f"{EVENT_FIT_TAG_CITY_PREFIX}{cleaned}"


def _time_tags(*, start_local: datetime, now_local: datetime, is_future: bool) -> list[str]:
    """The time-relative tags, in their fixed order.

    Every comparison here is between two **local** wall clocks in the event's own zone:
    the event's local start and `now` in that same zone. The local day is the event's day,
    not the reader's — which is the whole point of the rule.
    """
    tags: list[str] = []
    day_delta = (start_local.date() - now_local.date()).days

    # "tonight" needs the evening, not just the day. An event at 09:00 today is later
    # today, and calling it "tonight" would be a lie about the next four hours.
    if is_future and day_delta == 0 and start_local.hour >= EVENT_FIT_EVENING_HOUR:
        tags.append(EVENT_FIT_TAG_TONIGHT)
    elif is_future and day_delta == 1:
        tags.append(EVENT_FIT_TAG_TOMORROW)

    # The weekend is the event's local Saturday or Sunday, and it must be **the one
    # weekend in view** — the weekend a reader means when they read "this weekend". A
    # Saturday three weeks out is not it, and a tag that meant "some weekend" would be
    # useless on a preview.
    #
    # There is exactly one weekend in view, and which one it is depends on the day:
    #
    #   * on a **weekday**, the coming weekend — the next Saturday and the Sunday
    #     after it. On a Thursday that is Saturday and Sunday; on a Monday it is the
    #     Saturday five days out.
    #   * on a **Saturday or a Sunday**, the weekend under way — today, or yesterday's
    #     Saturday and today. The weekend *after* it is not "this weekend", and from a
    #     Saturday it is exactly seven days out, which is the case a plain
    #     "within seven days" bound gets wrong.
    #
    # Every weekend is named after its **Saturday** and the comparison is made between
    # **dates**, not between ISO week numbers: the week number wraps at the year
    # boundary (2027-01-01 is ISO week 53 of 2026), and a week-number comparison would
    # lose a New Year weekend entirely.
    if is_future and start_local.weekday() >= 5:
        today = now_local.date()
        if today.weekday() == 5:  # Saturday — the weekend under way is today
            weekend_saturday = today
        elif today.weekday() == 6:  # Sunday — the weekend under way started yesterday
            weekend_saturday = today - timedelta(days=1)
        else:  # a weekday — the coming weekend
            weekend_saturday = today + timedelta(days=(5 - today.weekday()) % 7)

        event_date = start_local.date()
        event_saturday = event_date - timedelta(days=(event_date.weekday() - 5) % 7)
        if event_saturday == weekend_saturday:
            tags.append(EVENT_FIT_TAG_THIS_WEEKEND)

    return tags


def compute_event_fit(
    *,
    start_time_utc: datetime,
    start_time_tz: str,
    now: datetime,
    extraction_confidence: Decimal | None = None,
    end_time_utc: datetime | None = None,
    city: str = "",
) -> EventFit:
    """The event's fit for a city: a 1–5 score and an ordered tuple of tag keys.

    `start_time_utc` is the instant; `start_time_tz` is the event's own IANA zone, and
    **every day boundary is decided in that zone**. `now` is the reference instant, and
    it is compared against the event in the same zone.

    `end_time_utc` is accepted for completeness — a long event still starts when it
    starts, and the fit is about the start. It is not used yet, and saying so is better
    than pretending it is.

    `extraction_confidence` is a `Decimal` in [0, 1], or None for an event whose facts
    were never scored.

    The result is deterministic: the same inputs give the same output, and nothing here
    reads a clock.
    """
    zone = _zone(start_time_tz)
    start_local = start_time_utc.astimezone(zone)
    now_local = now.astimezone(zone)

    until_start = start_time_utc - now
    is_future = until_start > timedelta(0)

    proximity = _proximity_band(until_start)
    confidence = _confidence_band(extraction_confidence)
    score = max(EVENT_FIT_SCORE_MIN, min(proximity, confidence))

    tags: list[str] = []
    for tag in _time_tags(start_local=start_local, now_local=now_local, is_future=is_future):
        if tag not in tags:
            tags.append(tag)
    tags.sort(key=lambda tag: EVENT_FIT_TAG_ORDER.index(tag))

    place = _city_tag(city)
    if place is not None:
        tags.append(place)

    return EventFit(score=score, tags=tuple(tags))


__all__ = [
    "EventFit",
    "compute_event_fit",
]
