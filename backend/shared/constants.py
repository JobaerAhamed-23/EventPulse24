"""Product constants that must exist exactly once (AD-8, AD-6, AD-16, AD-21, AD-7).

Stdlib only, so `domain` can be allowed to import it (decision for architecture-contracts).
"""

from datetime import time, timedelta
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from uuid import UUID

# AD-8: extraction_confidence gates, numeric(3,2) in [0, 1].
EXTRACTION_CONFIDENCE_REJECT = Decimal("0.50")  # below: auto-reject
EXTRACTION_CONFIDENCE_PUBLISH = Decimal("0.70")  # below: editorial review, never in a digest

# AD-8: structured sources (JSON-LD, RSS, ICS) carry their fields explicitly; nothing is inferred.
EXTRACTION_CONFIDENCE_STRUCTURED = Decimal("1.00")

# AD-6: below this, an Event is not digest-eligible until editorial review completes.
TZ_INFERENCE_CONFIDENCE_DIGEST = Decimal("0.70")
# FR-60: at or above this, a published Event needs no tz review; below it (down to the digest
# gate) it publishes with `tz_review_pending` set.
TZ_INFERENCE_CONFIDENCE_AUTO_PUBLISH = Decimal("0.90")

# FR-60 tz-inference scores and DST caps (domain/timezones.py). Tuning anchors, not truths (AD-8):
# re-baseline against labeled data. tests/shared/test_constants.py pins each one's gate band.
TZ_SCORE_EXPLICIT = Decimal("1.00")  # zone or exact instant agrees with every other claim
TZ_SCORE_VENUE_REGISTRY = Decimal("0.95")  # naive time read in the curated venue tz
TZ_SCORE_FIXED_ZONE = Decimal("0.85")  # exact instant, but only UTC or Etc/GMT±N to show it in
TZ_SCORE_CONFLICT = Decimal("0.60")  # two explicit claims disagree: a human decides
TZ_CAP_DST_FOLD = Decimal("0.80")  # naive time occurs twice; the first is taken
TZ_CAP_DST_GAP = Decimal("0.65")  # naive time doesn't exist in that zone

# AD-4 / FR-15 / FR-58: the ≥80% title token-overlap threshold, exact (no float boundary).
# One threshold, two rules: catalog identity (rule b) and the personal-event duplicate
# prompt both mean "≥80% Jaccard overlap on tokens" (PRD §3, FR-58). A float 0.8 is not
# exactly 4/5, and a boundary test on a float would be a lie.
TITLE_TOKEN_OVERLAP_MIN = Fraction(4, 5)

# AD-4: a move within this distance of the original start keeps the event_id (inclusive).
POSTPONEMENT_WINDOW = timedelta(days=30)

# FR-13 / design D16: the cadence `register_source` applies when none is given, keyed by
# `AcquisitionMethod` value. Crawl is the last resort and is polled politely; email_ics is pushed
# by a mailbox, so its cadence is only a fallback poll.
DEFAULT_INGESTION_CADENCE = {
    "api": timedelta(hours=4),
    "partnership": timedelta(hours=4),
    "jsonld": timedelta(hours=4),
    "rss": timedelta(hours=4),
    "ics": timedelta(hours=4),
    "email_ics": timedelta(hours=24),
    "crawl": timedelta(hours=24),
}
# No source is polled more often than this (respect the feeds).
INGESTION_CADENCE_MIN = timedelta(minutes=15)
# AD-7 scheduling: at most this many sources claimed per tick; a claim older than the TTL is a
# lost job (a worker died) and the source becomes claimable again.
SCHEDULE_BATCH = 100
INGEST_CLAIM_TTL = timedelta(hours=1)
# FR-13: a source with no successful ingestion within this many cadences is flagged stale.
STALE_AFTER_CADENCES = 2

# AD-17: the reconciler re-enqueues state changes unpropagated for longer than this, oldest
# first, at most this many per run.
OUTBOX_RECONCILE_AFTER = timedelta(minutes=5)
OUTBOX_RECONCILE_BATCH = 500
OUTBOX_RECONCILE_EVERY_MINUTES = 5  # the tick enqueues the reconciler when minute % 5 == 0

# AD-10 / FR-26: how often the Event Fit rows are recomputed. "Tonight" is a statement about
# now, so a persisted tag goes stale as the clock moves — not only when the event changes.
# The refresh is a **writer's** job (the tick enqueues it), so the read path never computes.
#
# The cadence is a trade-off: a tag can be up to one interval out of date. Fifteen minutes
# is short enough that "tonight" is right for all but the last quarter-hour of the
# evening, and long enough that a refresh is a cheap pass over the published events.
EVENT_FIT_REFRESH_EVERY_MINUTES = 15
# Events per transaction in the refresh, so a run never holds one long transaction open.
EVENT_FIT_REFRESH_BATCH_SIZE = 200

# AD-4: namespace for deterministic series ids (`shared.ids.series_id`). Never change it: every
# existing series would silently split.
SERIES_ID_NAMESPACE = UUID("cbd88e48-d511-4f1b-a595-2f31c0067ad4")


class ReminderSlot(StrEnum):
    """Reminder Plan slots (AD-7). Custom slots are identified by their own id."""

    FIVE_DAYS = "5d"
    TWO_DAYS = "2d"
    ONE_DAY = "1d"
    ONE_HOUR = "1hr"


REMINDER_SLOT_OFFSET = {
    ReminderSlot.FIVE_DAYS: timedelta(days=5),
    ReminderSlot.TWO_DAYS: timedelta(days=2),
    ReminderSlot.ONE_DAY: timedelta(days=1),
    ReminderSlot.ONE_HOUR: timedelta(hours=1),
}

# AD-16: FR-9 and FR-20 share this one default; never a second literal.
DEFAULT_REMINDER_PLAN = (ReminderSlot.ONE_DAY, ReminderSlot.ONE_HOUR)

# FR-9 allows "one custom slot" alongside the four named tiers, and AD-7's send key names it
# by its own id. A custom slot is therefore stored as a string id, and the prefix marks it as
# one so it can never be mistaken for a named tier (`5d`, `2d`, `1d`, `1hr`).
CUSTOM_SLOT_PREFIX = "custom:"

# FR-9: at most this many slots in one plan (the four named tiers, or the named tiers plus
# one custom slot).
REMINDER_PLAN_MAX_SLOTS = 4

# AD-21 / FR-33: two UTC intervals conflict when they overlap by strictly more than this.
CONFLICT_MIN_OVERLAP = timedelta(minutes=15)

# FR-58: how far either side of a candidate's start the scan reaches for other events. This is
# NOT the overlap threshold: the window decides which events to *look at*, while
# CONFLICT_MIN_OVERLAP decides when two of them *clash*. The window belongs to the service
# layer (which events to compare); the threshold belongs to `domain.conflict`.
CONFLICT_SCAN_WINDOW = timedelta(minutes=30)

# FR-58: a personal event is a likely duplicate of another when their names overlap by at least
# TITLE_TOKEN_OVERLAP_MIN and their starts are within this distance. Absolute, not one-sided:
# "starts within 24 hours" reads the same either way round.
DUPLICATE_START_WINDOW = timedelta(hours=24)

# AD-7: joins send-key parts. ":" keeps each UUID a 36-char run, so keys survive log scrubbing.
SEND_KEY_SEPARATOR = ":"

# ─────────────────────────────────────────────────────────────────────────────
# Accounts and auth (FR-4, AD-18, PRD §11.2)
#
# Stdlib only: `domain` imports this module, and the `domain-pure` import-linter
# contract forbids `django` in `domain`. Nothing here may import Django.
# ─────────────────────────────────────────────────────────────────────────────

# FR-4: "not prompted to re-authenticate within 7 days". The session's age, and the
# cookie's, are this one constant.
AUTH_SESSION_LIFETIME = timedelta(days=7)

# A password-reset link is a bearer credential for the account. Its life is short on
# purpose: it sits in a mailbox and in proxy logs for as long as it is valid. Django's
# own default is three days, which is too long for a credential that resets a password.
AUTH_RESET_TOKEN_LIFETIME = timedelta(minutes=30)

# PRD §11.2: "Rate limiting on all public endpoints (per-IP and per-user)". The three
# public auth operations are limited per IP *and* per account identifier, in the window
# below. The per-account sign-up limit is the lowest of the three: sign-up is the
# enumeration-prone one, so an attacker walking a list of addresses hits the wall
# sooner.
AUTH_THROTTLE_WINDOW_SECONDS = 3600
AUTH_THROTTLE_SIGN_IN_IP = 10
AUTH_THROTTLE_SIGN_IN_ACCOUNT = 5
AUTH_THROTTLE_SIGN_UP_IP = 5
AUTH_THROTTLE_SIGN_UP_ACCOUNT = 3
AUTH_THROTTLE_RESET_IP = 5
AUTH_THROTTLE_RESET_ACCOUNT = 3

# ─────────────────────────────────────────────────────────────────────────────
# Calendar connections (FR-50, AD-18)
#
# Stdlib only, like the section above.
# ─────────────────────────────────────────────────────────────────────────────

# AD-18: "The poll interval is ours to choose, since we are the HTTP client". PROVISIONAL
# (OQ-7): the number is ours, but it is not yet validated against a live Google secret
# address, so it must not be mistaken for a measured value. Change this one line when OQ-7
# closes; nothing else may hold an interval of its own.
CALENDAR_POLL_INTERVAL = timedelta(hours=1)

# FR-50: "Free tier: 1 connected provider. Pro tier: up to 3". Every user is Free in this
# intent (there is no SUBSCRIPTION entity yet), so the cap is 1. The Pro cap of 3 is a
# later intent and belongs here when it lands.
FREE_TIER_CALENDAR_PROVIDER_CAP = 1

# AD-7 scheduling: at most this many calendar connections are claimed per dispatcher run.
# The same shape as SCHEDULE_BATCH, and deliberately a separate constant — the two
# schedulers pace different work, and one number must not silently govern both.
CALENDAR_SYNC_BATCH = 100

# AD-7 scheduling: a calendar claim older than this is a lost job (a worker died), so the
# connection becomes claimable again.
#
# It is NOT `INGEST_CLAIM_TTL` reused by name. A calendar fetch takes at most 30 s
# (TOTAL_TIMEOUT) plus a body download, while an ingestion run can take much longer — so
# the two jobs have different durations and must not share a number. 15 minutes is
# comfortably longer than a fetch's worst case and comfortably shorter than the 1-hour
# poll interval, so a lost claim is recovered well before the next scheduled poll.
CALENDAR_CLAIM_TTL = timedelta(minutes=15)

# ─────────────────────────────────────────────────────────────────────────────
# Onboarding (FR-1)
#
# Stdlib only, like the sections above.
# ─────────────────────────────────────────────────────────────────────────────

# FR-1: the ten interest chips, in the order the step-2 mockup shows them.
#
# **One copy.** The frontend gets this list from the API — the chips endpoint projects
# this constant onto the wire — so the labels live here and nowhere else.
#
# The **key** is the contract: it is what the API accepts, what the database stores and
# what identifies a chip forever. The **label** is display-only. They are separate because
# a renamed label must not orphan a user's stored picks: changing "Tech & meetups" to
# "Technology & meetups" changes the label and leaves every `tech_meetups` row valid.
#
# The keys are slugs rather than the labels themselves for the same reason — a slug is a
# stable identifier, a label is prose.
INTEREST_CHIPS = (
    ("tech_meetups", "Tech & meetups"),
    ("sports_fitness", "Sports & fitness"),
    ("arts_culture", "Arts & culture"),
    ("family_kids", "Family & kids"),
    ("community_volunteering", "Community & volunteering"),
    ("outdoors_nature", "Outdoors & nature"),
    ("classes_workshops", "Classes & workshops"),
    ("markets_fairs", "Markets & fairs"),
    ("talks_lectures", "Talks & lectures"),
    ("government_civic", "Government & civic"),
)

# FR-1: "up to 3 picks". A fourth is refused, not silently dropped.
MAX_INTEREST_PICKS = 3

# FR-1: "A user who leaves mid-step is resumed at the same step on return within 7 days."
#
# The window is **inclusive**: a user exactly 7 days after their last move is still
# resumed at the same step. One second beyond it, the onboarding restarts at step 1.
ONBOARDING_RESUME_WINDOW = timedelta(days=7)

# FR-1: the onboarding flow has at most 3 user-visible steps, and every one can be skipped.
#
# The step's *name* is what the constant holds; its *position* (1, 2, 3) is what the
# progress row stores, because the resume rule is about the position — "resumed at the
# same step" means the same place in the flow.
#
#   1. `calendar`  — the optional calendar connect (owned by `calendar-connect-api`;
#                    this flow only records that the step was passed)
#   2. `interests` — the optional interest chips, up to 3 picks
#   3. `digest`    — the digest delivery time and timezone
ONBOARDING_STEPS = ("calendar", "interests", "digest")

# FR-1 caps the flow at 3 steps: "exceeds 3 steps ... violates FR-1". The count is derived
# from the tuple so the two cannot drift, and a test pins both the count and the
# membership — a bare count would pass on the wrong three steps.
ONBOARDING_STEP_COUNT = len(ONBOARDING_STEPS)

# The digest preference a user gets when they skip step 3.
#
# **9:00 in UTC** is deliberately boring and documented rather than clever. A default that
# guessed the user's local zone would need the guess, and the guess would be wrong for most
# of the world. The user changes it in one tap.
#
# The default is *written* when step 3 is skipped, not merely assumed at read time, so the
# preference is always a real row with a real value and `delivery` — which will consume the
# delivery time — reads one row rather than branching on "was it set?".
DEFAULT_DIGEST_DELIVERY_TIME = time(9, 0)
DEFAULT_DIGEST_TIMEZONE = "UTC"

# ── Event Fit (AD-10, FR-26) ───────────────────────────────────────────────────────
#
# Event Fit is the **session-free** explanation: a non-personalized 1–5 score and generic
# Why-this Tags per `(event, city)`. It is the only indicator a visitor without an account
# is allowed to see, because there is no user for a personal explanation to be *about*
# (AD-10). The Relevance Pulse is the other kind, and the two must never be substituted
# for one another.
#
# The score has **two** inputs, both of which already exist on an Event: how soon it
# starts, and how well we know its facts. There is no price field and FR-16 source
# reliability is not built, so there is no "free" tag and no source weighting — the work
# item says so explicitly, and those wait until the fields they need exist.

# The proximity bands, in order: how soon the event starts, relative to now.
#
# Each band is an **inclusive** upper bound on the time until the start. The bands are
# written as windows rather than as a single threshold so the boundaries are readable:
# "today", "within two days", "within a week", "within a fortnight", "later".
EVENT_FIT_TODAY = timedelta(days=1)
EVENT_FIT_TWO_DAYS = timedelta(days=2)
EVENT_FIT_ONE_WEEK = timedelta(days=7)
EVENT_FIT_TWO_WEEKS = timedelta(days=14)

# The confidence bands, in the same order. Each is an **inclusive** lower bound.
#
# These deliberately echo `EXTRACTION_CONFIDENCE_PUBLISH` (0.70) and the reject edge
# (0.50) rather than inventing new numbers: the same extraction confidence that decides
# whether an event publishes at all decides how much the fit trusts it.
EVENT_FIT_CONFIDENCE_HIGH = Decimal("0.90")
EVENT_FIT_CONFIDENCE_GOOD = Decimal("0.70")
EVENT_FIT_CONFIDENCE_FAIR = Decimal("0.50")

# The score is 1..5, and 5 is the best. A preview shows three cards, so the top of the
# range has to be reachable by something ordinary.
EVENT_FIT_SCORE_MIN = 1
EVENT_FIT_SCORE_MAX = 5

# "Tonight" starts at this local hour.
#
# A tag called "tonight" on an event at 09:00 is wrong, so the hour is a constant rather
# than an implicit "the rest of today". 17:00 is the hour a listing starts to mean
# "this evening". It is a **local** hour: the boundary is read in the event's own zone.
EVENT_FIT_EVENING_HOUR = 17

# The tag keys. Stable slugs — the server states facts, the client speaks the user's
# language, so the label is the frontend's business.
#
# The place tag is a prefix, not a key: `in_brooklyn`, `in_san_francisco`. The prefix is
# a constant so a reader can tell a place tag from a time tag without a lookup table.
EVENT_FIT_TAG_TONIGHT = "tonight"
EVENT_FIT_TAG_TOMORROW = "tomorrow"
EVENT_FIT_TAG_THIS_WEEKEND = "this_weekend"
EVENT_FIT_TAG_CITY_PREFIX = "in_"

# The tag order. Fixed, so two events carrying the same tags always list them the same
# way — an unordered set would make the rendered card depend on the database's mood.
EVENT_FIT_TAG_ORDER = (
    EVENT_FIT_TAG_TONIGHT,
    EVENT_FIT_TAG_TOMORROW,
    EVENT_FIT_TAG_THIS_WEEKEND,
)
