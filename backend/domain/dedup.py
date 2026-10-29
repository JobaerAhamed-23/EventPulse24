"""Event Identity (FR-15, AD-4): structural, never semantic. Stdlib only.

Three rules decide that a candidate is an existing Event:
  (a) the same source item: decided by the ExtractedRecord binding, passed in as
      `bound_event_id` (design D2), never by an Event's own origin fields;
  (b) the same non-empty venue fingerprint, the same instant, and title Jaccard >= 4/5;
  (c) the same normalized canonical URL and the same instant (plan P1: never across instants,
      so recurring instances that share a page never merge).
(b) and (c) never match an Event that already has an item bound from the candidate's own source:
a venue feed whose items all link one calendar page must not merge its rooms. Instants are
compared in UTC, truncated to whole seconds. Embeddings are not an input anywhere here.

Fingerprints are versioned ("v1:"). Changing how they're computed changes identity: bump the
version, never edit v1 in place (golden tests in tests/domain/test_dedup.py pin it).
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from fractions import Fraction
from hashlib import blake2b, sha256
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from domain.timezones import to_instant
from shared.constants import TITLE_TOKEN_OVERLAP_MIN

FINGERPRINT_VERSION = "v1"
TITLE_FINGERPRINT_MAX = 512  # Event.title_fingerprint is varchar(512)
TOKEN_MAX = 64  # longer "words" are noise; truncated so one can't eat the whole fingerprint
STOP_WORDS = frozenset(
    {"a", "an", "the", "and", "or", "of", "at", "in", "on", "for", "with", "to", "by", "from"}
)

_ACCENT_FOLDED_SCRIPTS = frozenset({"LATIN", "GREEK", "CYRILLIC"})
# Scripts written without spaces: split into overlapping character bigrams.
_UNSPACED_PREFIXES = ("CJK UNIFIED IDEOGRAPH", "HIRAGANA", "KATAKANA", "THAI")
_TRACKING_PARAMS = frozenset({"fbclid", "gclid"})
_PERCENT = re.compile(r"%[0-9a-fA-F]{2}")
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_LOCK_PERSON = b"ep-ident"


class Rule(StrEnum):
    SOURCE_ITEM = "a"
    VENUE_TIME_TITLE = "b"
    CANONICAL_URL = "c"


# --- Fingerprints --------------------------------------------------------------------------


def _script(char: str) -> str:
    return unicodedata.name(char, "").split(" ", 1)[0]


def _fold(text: str) -> str:
    """NFKC, casefold, drop accents from Latin/Greek/Cyrillic letters only, recompose (NFC).

    Combining marks on other scripts carry meaning (ド is not ト) and are kept.
    """
    decomposed = unicodedata.normalize("NFD", unicodedata.normalize("NFKC", text).casefold())
    kept: list[str] = []
    for char in decomposed:
        if unicodedata.combining(char) and kept and _script(kept[-1]) in _ACCENT_FOLDED_SCRIPTS:
            continue
        kept.append(char)
    return unicodedata.normalize("NFC", "".join(kept))


def _is_unspaced(char: str) -> bool:
    return unicodedata.name(char, "").startswith(_UNSPACED_PREFIXES)


def _split_word(word: str) -> list[str]:
    """A spaced-script word stays whole; an unspaced run becomes character bigrams."""
    tokens: list[str] = []
    run, run_unspaced = "", False
    for char in word + "\0":
        unspaced = _is_unspaced(char)
        if run and (char == "\0" or unspaced != run_unspaced):
            if run_unspaced and len(run) > 1:
                tokens += [run[i : i + 2] for i in range(len(run) - 1)]
            else:
                tokens.append(run)
            run = ""
        run_unspaced = unspaced
        run += char
    return [token[:TOKEN_MAX] for token in tokens]


def _words(text: str) -> list[str]:
    """Runs of letters, numbers and combining marks (marks matter: Thai and Indic vowels)."""
    words, word = [], []
    for char in text:
        if unicodedata.category(char)[0] in "LNM":
            word.append(char)
        elif word:
            words.append("".join(word))
            word = []
    if word:
        words.append("".join(word))
    return words


def tokens(text: str | None) -> list[str]:
    """Normalized tokens of `text`, in order (duplicates kept)."""
    return [t for word in _words(_fold(text or "")) for t in _split_word(word)]


def title_fingerprint(title: str | None) -> str:
    """`v1:<content tokens>|<stop-word tokens>`, each sorted and unique, at most 512 chars."""
    all_tokens = set(tokens(title))
    content = sorted(all_tokens - STOP_WORDS)
    stops = sorted(all_tokens & STOP_WORDS)

    def render() -> str:
        return f"{FINGERPRINT_VERSION}:{' '.join(content)}|{' '.join(stops)}"

    while len(render()) > TITLE_FINGERPRINT_MAX:  # keep content over stop words
        (stops or content).pop()
    return render()


def _parse_title_fingerprint(fingerprint: str) -> tuple[str, set[str], set[str]] | None:
    version, sep, body = fingerprint.partition(":")
    content, bar, stops = body.partition("|")
    if not sep or not bar:
        return None
    return version, set(content.split()), set(stops.split())


def jaccard(a: str, b: str) -> Fraction:
    """Title similarity of two fingerprints, exact.

    Compares content tokens; if either side has none (an all-stop-word title), compares all
    tokens on both sides, so the measure stays symmetric. Different versions never match.
    """
    pa, pb = _parse_title_fingerprint(a), _parse_title_fingerprint(b)
    if pa is None or pb is None or pa[0] != pb[0]:
        return Fraction(0)
    left, right = pa[1], pb[1]
    if not left or not right:
        left, right = pa[1] | pa[2], pb[1] | pb[2]
    union = left | right
    return Fraction(len(left & right), len(union)) if union else Fraction(0)


def venue_fingerprint(name: str | None, city: str | None, country_code: str | None) -> str:
    """`v1:` + sha256 of the normalized venue name, city and country; "" with no name.

    Stop words are dropped from the name unless that leaves nothing ("The Fillmore" ==
    "Fillmore"). The country keeps Portland, Oregon apart from Portland, Maine.
    """
    name_tokens = tokens(name)
    content = [t for t in name_tokens if t not in STOP_WORDS] or name_tokens
    if not content:
        return ""
    key = "\x1f".join(
        [" ".join(content), " ".join(tokens(city)), (country_code or "").strip().upper()]
    )
    return f"{FINGERPRINT_VERSION}:{sha256(key.encode()).hexdigest()}"


def canonical_url(url: str | None) -> str:
    """A normalized http(s) URL for rule (c), or "" (which never matches).

    http and https are the same URL, and so are `www.host` and `host`. Userinfo, default ports,
    tracking parameters (`utm_*`, `fbclid`, `gclid`) and non-route fragments are dropped; the
    host is IDNA-encoded (IPv6 literals keep their brackets); escaped unreserved characters are
    decoded and other escapes uppercased; the remaining query is sorted.
    """
    if not isinstance(url, str) or not url.strip():
        return ""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
        hostname = parts.hostname or ""
        if ":" in hostname:  # an IPv6 literal keeps its brackets, or the port would merge in
            host = f"[{hostname}]"
        else:
            host = hostname.encode("idna").decode("ascii").lower().removeprefix("www.")
    except (ValueError, UnicodeError):
        return ""
    if parts.scheme.lower() not in ("http", "https") or not hostname:
        return ""
    if port is not None and port not in (80, 443):
        host = f"{host}:{port}"
    path = _PERCENT.sub(_normalize_escape, parts.path) or "/"
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMS
        )
    )
    fragment = parts.fragment if parts.fragment.startswith(("/", "!")) else ""
    return urlunsplit(("https", host, path, query, fragment))


def _normalize_escape(escape: re.Match) -> str:
    """RFC 3986 §6.2.2: decode an escaped unreserved character; uppercase any other escape."""
    char = chr(int(escape[0][1:], 16))
    return char if char in _UNRESERVED else escape[0].upper()


def ics_item_id(uid: str, recurrence_start_utc: datetime | None = None) -> str:
    """The `source_event_id` for an ICS item: the UID, plus the instance start for a recurring
    instance, so weekly instances that share one UID stay distinct under rule (a).
    """
    uid = (uid or "").strip()
    if not uid:
        raise ValueError("an ICS item needs a UID")
    if recurrence_start_utc is None:
        return uid
    return f"{uid}#{to_instant(recurrence_start_utc).strftime('%Y%m%dT%H%M%SZ')}"


# --- Matching ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    """An incoming source item, after timezone resolution and normalization."""

    source_id: UUID
    source_event_id: str
    venue_fingerprint: str
    start_utc: datetime
    title_fingerprint: str
    canonical_url: str


@dataclass(frozen=True)
class LiveEvent:
    """An existing Event found through the identity indexes, as plain values."""

    event_id: UUID
    venue_fingerprint: str
    start_utc: datetime
    title_fingerprint: str
    canonical_url: str
    bound_source_ids: frozenset[UUID]  # sources with an ExtractedRecord bound to this Event
    superseded: bool = False


@dataclass(frozen=True)
class New:
    """No live Event matches: create one."""


@dataclass(frozen=True)
class Matched:
    event_id: UUID
    rule: Rule
    # Other live Events matching by (b)/(c) while the item is bound by (a): possible duplicates
    # for editorial review, never merged.
    review_signals: frozenset[UUID] = frozenset()


@dataclass(frozen=True)
class Ambiguous:
    """More than one live Event matches: never auto-merged (FR-15); the item stays unbound."""

    event_ids: frozenset[UUID]


Resolution = New | Matched | Ambiguous


def match(candidate: Candidate, event: LiveEvent) -> Rule | None:
    """Rule (b) or (c) between a candidate and one live Event; (b) is reported first."""
    if event.superseded or candidate.source_id in event.bound_source_ids:
        return None
    if to_instant(candidate.start_utc) != to_instant(event.start_utc):
        return None
    if (
        candidate.venue_fingerprint
        and candidate.venue_fingerprint == event.venue_fingerprint
        and jaccard(candidate.title_fingerprint, event.title_fingerprint) >= TITLE_TOKEN_OVERLAP_MIN
    ):
        return Rule.VENUE_TIME_TITLE
    if candidate.canonical_url and candidate.canonical_url == event.canonical_url:
        return Rule.CANONICAL_URL
    return None


def resolve(candidate: Candidate, bound_event_id: UUID | None, live: list[LiveEvent]) -> Resolution:
    """Decide which Event a candidate is. Rule (a) wins: a bound item stays bound."""
    matches = {event.event_id: rule for event in live if (rule := match(candidate, event))}
    if bound_event_id is not None:
        others = frozenset(matches) - {bound_event_id}
        return Matched(bound_event_id, Rule.SOURCE_ITEM, others)
    if not matches:
        return New()
    if len(matches) == 1:
        [(event_id, rule)] = matches.items()
        return Matched(event_id, rule)
    return Ambiguous(frozenset(matches))


# --- Concurrency -----------------------------------------------------------------------------


def _lock_key(*parts: str) -> int:
    digest = blake2b("\x1f".join(parts).encode(), digest_size=8, person=_LOCK_PERSON).digest()
    return int.from_bytes(digest, "big", signed=True)


def identity_lock_keys(candidate: Candidate) -> tuple[int, ...]:
    """Keys for `pg_advisory_xact_lock(bigint)` around match-then-write, one per rule that
    could apply, sorted so every worker locks in the same order.

    Stable across processes (blake2b, never the per-process-salted `hash()`). The pipeline
    commits one transaction per item; batching items in one transaction would require taking
    the union of their keys in sorted order up front.
    """
    instant = to_instant(candidate.start_utc).isoformat()
    keys = set()
    if candidate.source_event_id:
        keys.add(_lock_key("a", str(candidate.source_id), candidate.source_event_id))
    if candidate.venue_fingerprint:
        keys.add(_lock_key("b", candidate.venue_fingerprint, instant))
    if candidate.canonical_url:
        keys.add(_lock_key("c", candidate.canonical_url, instant))
    return tuple(sorted(keys))
