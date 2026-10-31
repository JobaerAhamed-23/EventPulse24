"""The event's own interest-chip keys: which chips an event belongs to (FR-1, FR-22).

**Why this module exists.** The Relevance Pulse's interest term is the **largest**
weight in the formula — `0.45 × interest_overlap` — and `interest_overlap` needs two
tuples: the chips the *user* picked, and the chips the *event* belongs to. The user's
side exists (`Interest.chip_key`, set at onboarding). The event's side did not:
`Event` has no category field, and no read produced one.

So the interest term was pinned to `0.0` for every candidate, and a pinned term is
what `domain/ranking.py` calls an *inert weight*: "the published formula would stay
arithmetically checkable and still produce a different number from the one on the card,
which is a worse trust failure than a reduced formula because it looks verifiable." With
the term inert the score could never exceed `0.55`, so no card could ever reach bucket
4 or 5; and `score_slot_3`'s inverted term — `1 − 0.0` — was identical to the plain
score, so the serendipity slot did not invert anything.

**Why it lives in `ingestion`, and not in `domain/`.** AD-9: matching text over
untrusted source content is not a render concern, and it belongs to the layer that
owns the content. `domain/` is stdlib-only and pure, and has "no idea a render
exists"; giving it a keyword table over event titles would make the pure domain depend
on a content policy. `domain/event_fit.py` set the precedent — it refused to invent a
"Free" tag rather than guess a category.

**Why it is a pure function and not a stored column.** A `chip_keys` column on `Event`
would need a migration, a write-time computation and a backfill for every existing
event — and it would be *wrong* the moment the keyword table changed. The matching is a
function of the event's text and a small, stable table, so computing it at read time is
both simpler and more correct. A new keyword improves the matching for every event at
once, with no migration.

**The matching is whole-word, and it is deliberately conservative.** A keyword that
matches too broadly is worse than no keyword: it inflates the interest term and files a
card under a category the user never asked about. So the rule is a whole-word match on
a small, hand-written keyword set (`shared.constants.INTEREST_CHIP_KEYWORDS`), and the
table says so.

**The venue is not matched.** "Brooklyn Brewery" would match a food chip on the word
"Brooklyn" if the keywords were loose, and a venue named "The Tech Bar" would make
every event there a tech event. The venue is *where* the event happens; the title and
description are *what* it is.
"""

import re
from functools import cache

from shared.constants import INTEREST_CHIP_KEYWORDS

#: A word is a run of letters, digits, apostrophes and hyphens.
#:
#: Hyphens matter: "story-time" and "storytime" are the same word to a reader, and a
#: keyword set that matched one but not the other would be a rule nobody could predict.
#: Apostrophes matter for the same reason: "storytime" and "story-time" are both
#: plausible spellings of the same thing.
_WORD = re.compile(r"[a-z0-9]+(?:['\-][a-z0-9]+)*")

#: The *parts* of a word: the word itself, and its pieces once the joining hyphens and
#: apostrophes are removed.
#:
#: This is what makes the hyphen rule real. "story-time" tokenises as one word, so a
#: keyword of "storytime" would not match it — and the module's own docstring promises
#: that it does. Splitting the word into its parts means a token contributes both
#: "story-time" and "storytime", so either spelling of the keyword matches either
#: spelling of the text.
#:
#: **The parts are added to the word, not substituted for it.** "story-time" still
#: matches a keyword of "story-time", and "story" still matches a keyword of "story" —
#: a hyphenated compound is not automatically two words, but a keyword that is one of
#: its parts is a legitimate match.
_SPLIT = re.compile(r"['\-]")


#: The keyword → chip mapping, compiled once.
#:
#: The compiled pattern is built per keyword and cached: the table is fixed at import
#: time, so there are at most a few dozen patterns, and rebuilding them per event would
#: cost a regex compile per chip per event on a read that runs for every user every day.
@cache
def _pattern_for(keyword: str) -> re.Pattern[str]:
    """The whole-word pattern for one keyword.

    The keyword is matched case-insensitively and **as a whole word**: `\\b` on both
    sides, so "art" does not match "start" and "sports" does not match "sport".

    A keyword that itself contains a space ("craft fair") is matched as a **phrase** —
    the pattern is built from the keyword's own words, joined by `\\s+`, so any run of
    whitespace between them matches.
    """
    words = _WORD.findall(keyword.casefold())
    if not words:
        return re.compile(r"(?!x)x")  # matches nothing
    body = r"\s+".join(re.escape(word) for word in words)
    return re.compile(rf"\b{body}\b")


@cache
def _keyword_tokens(keyword: str) -> frozenset[str]:
    """The keyword's own token set, normalised the same way the text's is.

    **The same hyphen rule on both sides.** A keyword of "story-time" and a text of
    "storytime" have to agree, and so do a keyword of "storytime" and a text of
    "story-time". Normalising both sides through the same rule is what makes that
    true; normalising only the text would make the first pair work and the second not.
    """
    return frozenset(_words_in(keyword))


def _words_in(text: str) -> set[str]:
    """The whole words of `text`, lowercased, plus their hyphen- and apostrophe-free
    parts.

    Splitting on a word boundary rather than searching for keywords directly is what
    makes the whole-word rule cheap: the text is tokenised **once**, and each keyword
    is then tested against the token set.

    The parts are what make "story-time" match a keyword of "storytime" — see `_SPLIT`.
    """
    words: set[str] = set()
    for word in _WORD.findall(text.casefold()):
        words.add(word)
        parts = [part for part in _SPLIT.split(word) if part]
        if len(parts) > 1:
            words.update(parts)
            # The joined form too: "story-time" → "storytime".
            words.add("".join(parts))
    return words


def chip_keys_for(*, title: str, description: str = "") -> tuple[str, ...]:
    """The interest-chip keys this event belongs to, in the table's own order.

    **The order is the table's order, not the order the keywords were found.** The
    table is a fixed dict, so its order is stable for a given build; the result is
    therefore deterministic, which is what the ranking's determinism requirement needs.
    The order is also the `INTEREST_CHIPS` order, so the keys come back in the same
    order the chips are offered to the user.

    **A chip with more than one matching keyword is listed once.** The interest
    overlap is counted over *distinct* event chips (`domain/ranking.py`), so a chip
    that matched three of its keywords must still be one chip — and the caller must not
    have to de-duplicate.

    **The event's own text only.** The title and the description are the event's
    words; the venue is where it happens.
    """
    if not title and not description:
        return ()

    words = _words_in(title) | _words_in(description)
    if not words:
        return ()

    matched: list[str] = []
    for chip_key, keywords in INTEREST_CHIP_KEYWORDS.items():
        for keyword in keywords:
            pattern = _pattern_for(keyword)
            # A multi-word keyword is a phrase, so it is tested against the text
            # rather than the token set.
            if " " in keyword:
                haystack = f" {title.casefold()} {description.casefold()} "
                if pattern.search(haystack):
                    matched.append(chip_key)
                    break
                continue
            if _keyword_tokens(keyword) & words:
                matched.append(chip_key)
                break

    return tuple(matched)


__all__ = ["chip_keys_for"]
