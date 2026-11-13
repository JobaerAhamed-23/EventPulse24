"""ISO-8601 durations, as `timedelta`. Stdlib only.

One parser, because two seed commands need to read the same shape of value and a third
copy would be a third chance to be subtly wrong.

**What is read.** Only the time part (`PT`). The date part (`P1D`) is refused rather
than half-understood: a caller that passes `P1D` almost certainly means days, and a
parser that quietly dropped the `D` would give that caller a duration a quarter of the
size it asked for. The `D` unit *is* readable inside the time part (`PT24H` is four
hours, `P1D` is not a thing here).

**What is refused.** Each unit may appear at most once, and there must be at least one
component: `PT` and `PT4H4H` are errors rather than zero and eight hours. A duplicated
unit is refused rather than added, because `PT1H30H` has two readings — ninety minutes
or ninety — and a seed that silently picked one would be picking for the caller.
"""

from datetime import timedelta

#: The unit letters and how many seconds each is worth.
DURATION_UNITS = {"D": 86400.0, "H": 3600.0, "M": 60.0, "S": 1.0}


def parse_duration(value: str) -> timedelta:
    """An ISO-8601 duration such as `PT4H`, as a timedelta.

    Raises `ValueError` for anything that is not exactly the supported shape. The
    message names the offending value, because the caller who has to fix it is looking
    at a seed file and wants to know which entry to open.
    """
    text = value.strip()
    if not text.startswith("PT"):
        raise ValueError(f"{value!r} is not an ISO-8601 duration")
    total = 0.0
    number = ""
    seen_units: set[str] = set()
    for character in text[2:]:
        if character.isdigit() or character == ".":
            number += character
            continue
        if character not in DURATION_UNITS or not number or character in seen_units:
            raise ValueError(f"{value!r} is not an ISO-8601 duration")
        total += float(number) * DURATION_UNITS[character]
        number = ""
        seen_units.add(character)
    if number or not seen_units:
        raise ValueError(f"{value!r} is not an ISO-8601 duration")
    return timedelta(seconds=total)


__all__ = ["DURATION_UNITS", "parse_duration"]
