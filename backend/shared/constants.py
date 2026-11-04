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

# FR-14: an Event older than this many times its source's `freshness_ttl_hours` is not
# surfaced in a fresh Pulse Digest.
#
# This is **not** `STALE_AFTER_CADENCES`, though the number is the same: a cadence is how
# often a source is polled, a TTL is how long its facts are treated as current. Two
# different quantities with two different meanings get two different names — AD-8 says a
# threshold lives in one place, not that two thresholds may share one name.
#
# The bound is measured from `Event.last_seen_at` — when the catalog last saw the event at
# the source — not from `updated_at`, which moves whenever *we* touch the row and would
# keep a stale event alive.
DIGEST_STALE_TTL_MULTIPLIER = 2

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

# **The custom slot's id IS its offset** — `custom:90` means "90 minutes before the event".
#
# The offset used to live nowhere: a custom slot was stored, listed, and **never minted**,
# because there was no column and no encoding carrying the number. The choice was a new
# column or an encoded id, and the encoded id wins for three reasons:
#
# - AD-7's send key already names the custom slot **by its id**, so the id is already a
#   first-class part of the key. A slot whose id *is* its offset cannot disagree with
#   itself; a second column would be a second place for the same fact.
# - No migration. `REMINDER_PLAN.slots` is a JSON array of strings and stays one.
# - The id is self-describing: a stored slot says what it means without a lookup.
#
# The bounds are the UX spec's, exactly: EXPERIENCE.md — *"Min: 15 minutes before; max:
# 30 days before. Out-of-range snaps back."* The minimum keeps a reminder from landing at
# the moment of the event itself; the maximum keeps it inside the window the named tiers
# span, so a custom slot is a finer choice among them and not a way to schedule years
# ahead.
CUSTOM_SLOT_MIN_MINUTES = 15
CUSTOM_SLOT_MAX_MINUTES = 43200  # 30 days

# The custom slot's id format. One place, read by the validator (AD-8): the grammar is
# `custom:<minutes>`, and the minutes are a plain integer — no sign, no decimal point.
CUSTOM_SLOT_FORMAT = "custom:{minutes}"

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

# FR-12 / AD-7: the default Quiet Hours window, as **local wall clocks** paired with the user's
# zone — never instants. The PRD glossary and EXPERIENCE.md both spell it "10pm–8am", and the
# locked microcopy says "10pm–8am. Nothing during this window."
#
# AD-16: one literal. `domain.quiet_hours` computes the shift and `delivery` stores the user's
# window; both read these, and neither declares its own.
#
# **It crosses midnight, and that is the normal case, not an edge case.** Every piece of code
# that compares a time against this window must handle `start > end`, where "inside" is
# `t >= start or t < end` rather than a range.
DEFAULT_QUIET_HOURS_START = time(22, 0)
DEFAULT_QUIET_HOURS_END = time(8, 0)

# ─────────────────────────────────────────────────────────────────────────────
# Email unsubscribe and click tracking (FR-11, FR-10, AD-20, SM-2)
#
# Stdlib only, like the sections below.
# ─────────────────────────────────────────────────────────────────────────────

# FR-11: "A reminder email contains 1-click unsubscribe for that event's reminders (does
# not unsubscribe from Pulse Ping)."
#
# **Two scopes, not one.** A reminder's link stops *that event's* reminders; the digest's
# link stops the Pulse Ping. They are different user decisions about different things, and
# conflating them would mean a user who stops one event's reminders silently loses their
# daily digest — or that stopping the Ping cannot stop the reminders.
#
# AD-16: one literal each. The token builder, the renderers and the unsubscribe command
# all read these, so the scope strings cannot drift apart. The values are also what the
# signed token's payload carries, so a change here is a change to what an already-sent
# link means — which is exactly why they live in one place and are never spelled inline.
UNSUBSCRIBE_SCOPE_EVENT_REMINDERS = "event_reminders"
# The name is `PING`, not `PULSE_PING`: `ScheduledSend.Kind.PULSE_PING` is **reserved** and
# nothing may mint it (the MVP's digest email *is* the Pulse Ping, so there is no separate
# send kind for it). This constant names an *unsubscribe scope*, which is a different
# vocabulary, and it is deliberately spelled differently so the two can never be confused —
# and so a grep for the reserved kind does not land on this file.
UNSUBSCRIBE_SCOPE_PING = "pulse_ping"

# The scopes, as a closed set. A token carrying a scope outside it is refused rather than
# applied, so a forged payload with an invented scope cannot reach the command layer.
UNSUBSCRIBE_SCOPES = (UNSUBSCRIBE_SCOPE_EVENT_REMINDERS, UNSUBSCRIBE_SCOPE_PING)

# AD-20 / RFC 8058: the salt Django's `Signer` uses to derive its signing key. A distinct
# salt per purpose, so a click-tracker token and an unsubscribe token are different
# signatures over different payloads and neither can be replayed as the other.
#
# **These are salts, not secrets.** A salt is a public label that says what a signature is
# *for*; the secret is Django's `SECRET_KEY`, which is configuration and never appears in
# the code. Nothing here is a credential, which is why the names say "salt" and not
# "secret" — a name that read like a secret would be one somebody eventually pasted into
# a public repository.
UNSUBSCRIBE_SIGNING_SALT = "eventpulse24.email.unsubscribe"
CLICK_SIGNING_SALT = "eventpulse24.email.click"

# SM-2: the digest CTA's click is measured, and **open-pixel measurement is rejected as
# unreliable** — a pixel is blocked by mail clients, and a blocked pixel is indistinguishable
# from an unclicked link. So the CTA is a server-side redirect with a signed token.
#
# The redirect is its own path rather than a query on the frontend's route, because the
# click has to be *recorded* server-side before the user is sent onward.
CLICK_REDIRECT_PATH = "/api/email/click"

# The path the RFC 8058 one-click endpoint lives at. RFC 8058 says the endpoint is a
# **POST**, precisely because mail clients and link scanners follow `GET` links
# automatically — a `GET` that unsubscribed would let a scanner unsubscribe every user
# whose mail it touched.
UNSUBSCRIBE_PATH = "/api/email/unsubscribe"

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

#: The keywords that put an **event** into an interest chip.
#:
#: The user's side of the overlap is the chip keys they picked at onboarding (FR-1), and
#: that exists. The **event's** side does not: `Event` has no category field, and the
#: Relevance Pulse's interest term — the largest weight in the formula — needs the
#: event's chips to compute anything at all. Without them the term is pinned to zero,
#: which the ranking domain calls an *inert weight*: "the published formula would stay
#: arithmetically checkable and still produce a different number from the one on the
#: card, which is a worse trust failure than a reduced formula because it looks
#: verifiable."
#:
#: **This table is that missing half.** It is deliberately small and hand-written: four
#: to eight unambiguous keywords per chip, matched as whole words against the event's
#: title and description. It is not a classifier and does not pretend to be one — a
#: keyword broad enough to match the wrong things is worse than no keyword at all,
#: because a false match inflates the interest term and puts a card in a category the
#: user never asked about.
#:
#: **Why whole words, and not substrings.** "art" must not match "start", and "market"
#: must not match "marketing" — a substring match would file part of a city's calendar
#: under "Arts & culture" on the strength of a word that merely contains another.
#:
#: Note that this table lists **both** "sport" and "sports" for `sports_fitness`. Those
#: are two whole words, and "Sports Clinic" matches the second of them — the rule is
#: about *substrings*, not about near-synonyms.
#:
#: **Hyphens and apostrophes are normalised on both sides.** "story-time" and
#: "storytime" are the same word to a reader, so either spelling of a keyword matches
#: either spelling of the text. See `apps.ingestion.services.chip_matching`.
#:
#: **Why the keywords live here, and not in `domain/`.** AD-9: matching text over
#: untrusted source content belongs to the layer that owns the content. `domain/` is
#: stdlib-only and pure, and has no idea a render exists. `shared/constants.py` is
#: stdlib-only too, so both may read it.
#:
#: **Why the table is editable.** The chip *keys* are stable forever — a renamed label
#: must not orphan a user's stored picks. These keywords are the matching policy, and
#: the policy is allowed to change: a new keyword improves the matching for every event
#: at once, with no migration and no backfill.
INTEREST_CHIP_KEYWORDS = {
    "tech_meetups": ("tech", "startup", "developer", "hackathon", "software", "programming"),
    "sports_fitness": (
        "sport",
        "sports",
        "fitness",
        "yoga",
        "gym",
        "basketball",
        "soccer",
        "running",
    ),
    "arts_culture": (
        "concert",
        "gallery",
        "museum",
        "theatre",
        "theater",
        "exhibition",
        "art",
        "music",
        "film",
    ),
    "family_kids": ("family", "kids", "children", "playground", "storytime", "baby"),
    "community_volunteering": (
        "volunteer",
        "volunteering",
        "charity",
        "fundraiser",
        "donate",
        "mutual aid",
    ),
    "outdoors_nature": (
        "hike",
        "hiking",
        "trail",
        "park",
        "garden",
        "outdoor",
        "bird",
        "beach",
    ),
    "classes_workshops": (
        "workshop",
        "class",
        "course",
        "lesson",
        "training",
        "bootcamp",
    ),
    "markets_fairs": ("market", "fair", "farmers", "flea", "bazaar", "craft fair"),
    "talks_lectures": (
        "talk",
        "lecture",
        "panel",
        "conference",
        "symposium",
        "keynote",
        "webinar",
    ),
    "government_civic": (
        "council",
        "town hall",
        "mayor",
        "zoning",
        "public hearing",
        "municipal",
        "civic",
    ),
}

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

# ── Digest composition scheduling (FR-1, FR-5, AD-7, AD-11) ─────────────────────
#
# AD-7 scheduling: at most this many users' digests are claimed per dispatcher run.
#
# **Its own number, not `SCHEDULE_BATCH` reused by name.** `SCHEDULE_BATCH` paces
# per-*source* ingestion and `CALENDAR_SYNC_BATCH` paces per-*connection* calendar
# fetches. This paces per-*user* digest composition — a different unit of work, with a
# different cost (three candidate pools and a scoring pass, against one source or one
# calendar fetch). Two schedulers pacing different work must not share a number, or a
# change to one silently changes the other.
DIGEST_DISPATCH_BATCH = 100

# AD-7 scheduling: a digest claim older than this is a lost job (a worker died), so the
# user becomes claimable again.
#
# **Not `INGEST_CLAIM_TTL` or `CALENDAR_CLAIM_TTL` reused by name.** An ingestion run can
# take a long time; a calendar fetch is bounded by a 30 s timeout; a digest composition
# reads three candidate pools and scores them — minutes, not hours. 15 minutes is
# comfortably longer than a composition's worst case and comfortably shorter than the
# 24-hour gap between one digest and the next, so a lost claim is recovered well before
# the next day's digest is due.
DIGEST_CLAIM_TTL = timedelta(minutes=15)

# AD-8: the scheduler's own label, for the audit row and the log line.
#
# **It is a job name, not a user's name.** AD-13 forbids PII in logs, and an audit row
# crosses into `catalog` (AD-3), so the actor names the *job* that acted.
DIGEST_SCHEDULER_ACTOR = "digest_scheduler"

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

# ── Relevance Pulse ranking (AD-10, FR-22, FR-5) ─────────────────────────────────
#
# The Relevance Pulse is the **per-user** explanation — the one on an authenticated card,
# the Detail Screen and (later) the email. AD-10 persists it beside the decision it
# explains and never recomputes it at render.
#
# **The published formula, and what is missing from it.** FR-22 publishes
#
#     relevance_score = 0.40 × preference_graph_match
#                     + 0.25 × source_reliability
#                     + 0.20 × recency_fit
#                     + 0.15 × novelty_vs_exploration
#
# and locks those weights. **Two of the four components have no input in this codebase**:
#
#   * `source_reliability` — FR-16 is unbuilt; `Source` has no score field. It is not
#     "not implemented yet": the number does not exist and cannot be computed.
#   * `novelty_vs_exploration` — needs the Preference Graph (FR-25, deferred) *and* an
#     event category, and `Event` has no category field.
#
# A term multiplied by a constant is an **inert weight**: the published formula would stay
# arithmetically checkable and still produce a different number from the one on the card,
# which is a worse trust failure than a reduced formula because it looks verifiable.
# `domain/event_fit.py` set this precedent when it refused to invent a "Free" tag — "they
# are added to Event Fit's rule set then, not faked now."
#
# So the omitted terms are **absent from the expression**, and the surviving weights are
# redistributed so they still sum to 1.0. The docstring of `domain/ranking.py` states the
# reduction, names every omitted input, and names the FR that will supply it.
#
# The weights below are the **reduced** ones. `RANKING_WEIGHT_SUM` is pinned to 1 by a test,
# so the score still occupies [0, 1] and FR-22's bucket boundaries mean what they say.

# The reduced formula's four surviving inputs.
#
#   relevance_score = RANKING_WEIGHT_INTEREST × interest_overlap
#                   + RANKING_WEIGHT_RECENCY  × recency
#                   + RANKING_WEIGHT_CITY     × city_match
#                   + RANKING_WEIGHT_CONFIDENCE × confidence
#
# **Interest overlap is 0.45**, not FR-22's published 0.40 for `preference_graph_match`.
# The chips are the Preference Graph's only surviving trace, so they inherit the
# preference term's *rank* — the largest — while the slack from the two absent terms is
# spread across the survivors.
#
# **Recency is 0.25**, up from FR-22's 0.20 for `recency_fit`: it is the term that
# survives most directly, the event's start time against the user's day.
#
# **City match is 0.20**, and it is **additive**, not a multiplier. FR-5 multiplies by a
# `geographic_distance_factor`, which zeroes out every event outside the user's city — but
# city membership is decided by the *candidate read*, not by the score. Once the read has
# filtered to the user's city, multiplying by a city factor would multiply by a constant,
# which is exactly the inert weight this section exists to avoid.
#
# **Confidence is 0.10**, the smallest share. FR-22 says the Confidence Pulse measures the
# AI's certainty about relevance "not just trust in the source"; extraction confidence is
# the one measure of "how well do we know this event's facts" that exists, and it is the
# same number the eligibility gates use.
RANKING_WEIGHT_INTEREST = Decimal("0.45")
RANKING_WEIGHT_RECENCY = Decimal("0.25")
RANKING_WEIGHT_CITY = Decimal("0.20")
RANKING_WEIGHT_CONFIDENCE = Decimal("0.10")

# The four weights must sum to exactly 1, so the score stays in [0, 1] and the bucket
# boundaries keep their meaning. Pinned by `tests/shared/test_constants.py`.
RANKING_WEIGHT_SUM = (
    RANKING_WEIGHT_INTEREST
    + RANKING_WEIGHT_RECENCY
    + RANKING_WEIGHT_CITY
    + RANKING_WEIGHT_CONFIDENCE
)

# The recency bands, in order: how soon the event starts, relative to `now`.
#
# Each band is an **inclusive** upper bound on the time until the start, and the comparison
# is made in the **event's own IANA zone** (AD-6) — the same rule `domain/event_fit.py` is
# built around. A 23:30 event in `America/New_York` is "tonight" on Friday, not Saturday.
RANKING_RECENCY_WITHIN_DAY = Decimal("1.00")
RANKING_RECENCY_WITHIN_THREE_DAYS = Decimal("0.75")
RANKING_RECENCY_WITHIN_WEEK = Decimal("0.50")
RANKING_RECENCY_WITHIN_FORTNIGHT = Decimal("0.25")
RANKING_RECENCY_LATER = Decimal("0.00")

# The city bands. **`Venue` has no coordinates**, so haversine is not computable and
# "nearby" is a band rather than a distance. The brief records this as a named deviation
# from FR-5's distance curve; when coordinates arrive, this is where they land.
RANKING_CITY_SAME = Decimal("1.00")
RANKING_CITY_SAME_COUNTRY = Decimal("0.50")
RANKING_CITY_OTHER = Decimal("0.00")

# FR-22's bucket boundaries, exact. The score is clamped to [0, 1] before mapping, and the
# rendered bucket is always an integer 1–5. **No interpolation.**
#
# On an exact boundary the **lower** bucket wins: 0.850 → 4 dots, not 5. That rule is why
# the score is a `Decimal` and never a float — `0.85` as a binary float is not
# `Decimal("0.85")`, and it lands the card in the wrong bucket.
RANKING_BUCKET_5 = Decimal("0.85")
RANKING_BUCKET_4 = Decimal("0.65")
RANKING_BUCKET_3 = Decimal("0.45")
RANKING_BUCKET_2 = Decimal("0.25")

# The score's bounds.
RANKING_SCORE_MIN = Decimal("0.00")
RANKING_SCORE_MAX = Decimal("1.00")

# The score is 1..5, and 5 is the best.
RANKING_BUCKET_MIN = 1
RANKING_BUCKET_MAX = 5

# The hysteresis threshold: within one local day, a bucket holds unless the raw score
# moves by **at least** this much.
#
# **≥0.10, not ±0.02.** The deprecated `ranking-algorithm-transparency-desktop.html` mockup
# says ±0.02; EXPERIENCE.md §4 says ≥0.10 and is the canonical source, and the spines-win
# rule governs. The deviation is recorded in the design doc.
RANKING_HYSTERESIS_DELTA = Decimal("0.10")

# "Tonight" starts at this local hour, in the **event's** zone.
#
# The same hour Event Fit uses, and the same rule: an event at 09:00 is later today, not
# tonight, and calling it "tonight" would be a lie about the next eight hours.
RANKING_EVENING_HOUR = 17

# FR-5's Slot 1: an eligible **personal** event within this window is the must-know card.
RANKING_PERSONAL_EVENT_WINDOW = timedelta(hours=48)

# The boost a personal event gets in Slot 1.
#
# A personal event inside 48 hours is the one card that is certainly the user's and
# certainly soon. The boost is a named constant rather than a fudge inside the formula, so
# a reader can see exactly how much the slot-1 personal preference is worth.
RANKING_PERSONAL_EVENT_BOOST = Decimal("0.20")

# The Why-this Tag keys. Stable slugs — the server states facts, the client speaks the
# user's language, so the label is the frontend's business.
#
# `discovery` is **not** a generic tag: FR-25 and the PRD §3 Glossary require it on Slot 3,
# where it replaces a category name. UJ-1's `novel` is stale and does not govern.
RANKING_TAG_NEARBY = "nearby"
RANKING_TAG_TONIGHT = "tonight"
RANKING_TAG_TOMORROW = "tomorrow"
RANKING_TAG_WEEKEND = "weekend"
RANKING_TAG_SAVED = "saved"
RANKING_TAG_DISCOVERY = "discovery"

# The prefix for a chip-match tag: `matches_music`, `matches_tech_meetups`.
RANKING_TAG_CHIP_PREFIX = "matches_"

# At most three Why-this Tags on a card (FR-6).
RANKING_MAX_TAGS = 3

# The tag order. Fixed, so two cards carrying the same tags always list them the same way
# — an unordered set would make the rendered card depend on the database's mood.
#
# The order is also the **priority**: when more than three tags apply, the first three in
# this order win. So a card that is nearby, tonight and matches a chip shows
# `nearby, tonight, matches_music` — never three chip tags.
RANKING_TAG_ORDER = (
    RANKING_TAG_DISCOVERY,
    RANKING_TAG_NEARBY,
    RANKING_TAG_TONIGHT,
    RANKING_TAG_TOMORROW,
    RANKING_TAG_WEEKEND,
    RANKING_TAG_SAVED,
)

# ── Pulse Preview (FR-2, AD-12, PRD §11.2) ────────────────────────────────────────
#
# The Pulse Preview is the **first value a visitor gets**, before they have an account:
# three Pulse Cards for their city. It is a *public* surface — no session, no `personal`,
# no cookie — so it is cacheable, and every constant here serves that.

# FR-2: "falls back to the most-popular city (NYC at MVP)".
#
# **One copy.** The backend resolves the fallback and the frontend shows it; if the two
# spelled it differently, the consent banner would name a city the preview does not
# serve. So the spelling lives here and nowhere else.
#
# It is the fallback for two situations only: geo resolved to **nothing**, and geo
# resolved to a city the catalog does not cover. It is *not* the answer to an explicit
# unsupported city — that one returns an empty preview carrying the requested city's
# name, because showing the fallback's events under the requested name is a heading that
# lies.
PREVIEW_FALLBACK_CITY = "New York City"

# The edge's geo header. Vercel sets `x-vercel-ip-city`; the value is URL-encoded
# (e.g. `Brooklyn%2CNY`).
#
# **The header name is a constant**, not a literal spread through the code: the edge owns
# the name, and changing edges changes one line. The *port* does not know it — the port's
# input is a bag of headers, and the adapter is what knows which one to read.
GEO_HEADER_NAME = "x-vercel-ip-city"

# A city name longer than this is not a city, it is an attempt to put a value somewhere it
# should not go. The header is attacker-controlled, and it is read from a request.
GEO_CITY_MAX_LENGTH = 64

# PRD §11.2: "Rate limiting on all public endpoints (per-IP and per-user)".
#
# The preview is limited **per IP only**. It has no per-user limit because it has no
# user — that is the point of AD-12, and a per-user limit on an anonymous endpoint would
# mean reading the session, which would mean the endpoint is not anonymous.
#
# The limit is generous because the endpoint is cheap, cacheable, and a visitor
# legitimately reloads a preview while deciding. Sixty a minute is far above what a
# person does and far below what a scraper does.
PREVIEW_THROTTLE_WINDOW_SECONDS = 60
PREVIEW_THROTTLE_IP = 60

# The preview's cache headers. The browser holds it for a minute, a shared cache for five,
# and a shared cache may serve a slightly stale copy while it refreshes in the background.
#
# `stale-while-revalidate` is the point of the third number: a visitor is never made to
# wait on the origin for a card they could have had a moment ago.
#
# The preview's content moves when the Event Fit refresh runs (every 15 minutes) and when
# events start, so these TTLs are longer than one refresh and shorter than a day.
PREVIEW_CACHE_CONTROL = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"

# The preview's `Vary` header. **Nothing session-related may appear here.**
#
# A response that varies on the cookie is not cacheable, and — worse — a shared cache
# that stores one variant under a key that ignores the cookie would serve one visitor's
# response to another. The preview sets no cookie and reads no session, so the response
# is identical for everyone and the cache key is the URL.
PREVIEW_VARY = "Accept-Encoding"

# The public event page's cache headers (FR-26). The browser holds it for an hour, a
# shared cache for an hour too, and a shared cache may serve a slightly stale copy while
# it refreshes in the background.
#
# **The TTL is longer than the preview's, because this page is indexed.** A crawler that
# has spent months earning a ranking on `/events/{slug}` must not be told to come back in
# sixty seconds. The revalidation work item is what makes the page *current*; the cache
# TTL is only how long a page may sit without being revalidated, and the two are separate
# facts.
#
# `stale-while-revalidate` is the point of the third number: a crawler is never made to
# wait on the origin for a page it could have had a moment ago.
PUBLIC_PAGE_CACHE_CONTROL = "public, max-age=3600, s-maxage=3600, stale-while-revalidate=86400"

# The public event page's `Vary` header. **Nothing session-related may appear here.**
#
# A response that varies on the cookie is not cacheable, and — worse — a shared cache
# that stores one variant under a key that ignores the cookie would serve one visitor's
# response to another. The public page sets no cookie and reads no session (AD-12), so
# the response is identical for everyone and the cache key is the URL.
PUBLIC_PAGE_VARY = "Accept-Encoding"

# The revalidation signal's retry bound and cadence (FR-26, FR-27).
#
# **A revalidation that cannot be delivered is retried, and the retry is bounded.** The
# signal is delivered by the worker to the frontend's revalidation route handler; if the
# frontend is down, the request row stays open and a reconciler re-delivers it on the next
# cadence, exactly as AD-17's outbox does for personal propagation.
#
# The bound is what makes "stale-but-correct, never wrong" a promise rather than a hope: a
# request that has failed this many times is **exhausted** — it is kept and surfaced, not
# retried forever, because a page that is stale and a queue that retries forever are both
# facts an operator needs to see.
#
# **The cadence matches `OUTBOX_RECONCILE_EVERY_MINUTES` on purpose.** The two reconcilers
# are the same shape — find the rows nobody finished, offer them again — and running them on
# one cadence means one mental model for "a job that did not happen".
REVALIDATION_MAX_ATTEMPTS = 5
REVALIDATION_RECONCILE_AFTER = timedelta(minutes=5)
REVALIDATION_RECONCILE_BATCH = 500
REVALIDATION_RECONCILE_EVERY_MINUTES = 5  # the tick enqueues the reconciler when minute % 5 == 0

# How long the backend waits for the frontend's revalidation route handler to answer.
#
# **Bounded, and short.** The delivery is on the worker, not on a user's request, so a slow
# frontend delays a background job rather than a request. Five seconds is long enough for a
# warm serverless function to cold-start and short enough that a hung frontend does not
# hold the worker slot.
REVALIDATION_TIMEOUT_SECONDS = 5.0

# AD-7: how long a sweep's claim on a `SCHEDULED_SEND` row stays valid.
#
# The sweep claims with `FOR UPDATE SKIP LOCKED` but releases the lock before calling the
# email provider, so an in-flight row is marked by `claimed_at` rather than held. A claim
# older than this is a worker that died mid-send, and the row becomes claimable again.
#
# **Shorter than `DIGEST_CLAIM_TTL` (15 minutes) on purpose.** A digest has a 24-hour gap
# before the next one is due, so a lost claim has all day to be recovered. A reminder has
# the ±5-minute delivery budget of AD-7, so a dead worker's row has to come back quickly or
# the reminder is late. Re-sending is safe: the send key is the provider's idempotency key.
SEND_CLAIM_TTL = timedelta(minutes=5)

# AD-7 scheduling: at most this many due sends are claimed per sweep run.
#
# **Its own number, not `SCHEDULE_BATCH` / `CALENDAR_SYNC_BATCH` / `DIGEST_DISPATCH_BATCH`
# reused by name.** Those pace per-source ingestion, per-connection calendar fetches and
# per-user digest compositions. This paces per-*send* deliveries — a different unit of work,
# with a different cost (one provider call each, against one fetch or one scoring pass). Two
# schedulers pacing different work must not share a number, or a change to one silently
# changes the other.
SEND_SWEEP_BATCH = 100

# AD-7: how many times a provider failure is retried before the row is recorded as failed.
#
# **A bound, not a hope.** A permanently-refused address — a full mailbox, a bounced domain —
# would otherwise be retried on every 60-second tick, forever. `ScheduledSend.Status.FAILED`
# is the terminal answer: the row is *recorded*, never retried past the bound and never
# silently dropped.
#
# Three attempts is two retries after the first. It is deliberately modest: the sweep runs
# every 60 seconds, so three attempts are exhausted inside two minutes, and the user is not
# left waiting on a retry ladder that takes hours to climb. The send key is the provider's
# idempotency key (AD-7), so a retry cannot produce a second email.
SEND_MAX_ATTEMPTS = 3


class LifecycleSendBehaviour(StrEnum):
    """What an event state change does to a user's scheduled sends (AD-17)."""

    #: Cancel the stale pending rows and mint fresh ones against the new version.
    REMINT = "remint"
    #: Cancel the stale pending rows and mint nothing — the event is not happening.
    CANCEL = "cancel"
    #: Keep the sends; only re-stamp the working version. The event still happens.
    KEEP = "keep"


# AD-17's "what each change does" table, mapped for `delivery`. Keyed by
# `apps.ingestion.models.EventStateChange.Kind` values — by value, because `shared` is below
# `apps` in the layer order and cannot import the enum.
#
# **Every kind is mapped explicitly and there is no default.** A new kind added in `ingestion`
# fails `test_every_lifecycle_kind_is_mapped` rather than silently falling through and doing
# nothing to anyone's reminders — which is how a new lifecycle kind would otherwise ship
# looking like it worked.
#
# `sold_out` is the one that reads wrong at a glance: a sold-out event **still happens**, and a
# user who saved it still wants their reminder. AD-17 says "keep sends, queue a notice".
LIFECYCLE_SEND_BEHAVIOUR = {
    "time_moved": LifecycleSendBehaviour.REMINT,
    "postponed": LifecycleSendBehaviour.REMINT,
    "reinstated": LifecycleSendBehaviour.REMINT,
    "cancelled": LifecycleSendBehaviour.CANCEL,
    "superseded": LifecycleSendBehaviour.CANCEL,
    "sold_out": LifecycleSendBehaviour.KEEP,
    "detail_changed": LifecycleSendBehaviour.KEEP,
}


# Schema.org's vocabulary for the public event page's structured data (FR-26, AD-12).
#
# These strings are Schema.org's, not ours, and they live here so they exist exactly once
# (`shared` is stdlib-only, so `domain` may import them — the `domain-pure` contract).
#
# **Every value is a full IRI**, not a bare term. `https://schema.org/EventScheduled` is what
# a crawler resolves; `EventScheduled` is a local convenience that would not validate.
SCHEMA_ORG_CONTEXT = "https://schema.org"
SCHEMA_ORG_EVENT_TYPE = "Event"
SCHEMA_ORG_PLACE_TYPE = "Place"
SCHEMA_ORG_POSTAL_ADDRESS_TYPE = "PostalAddress"
SCHEMA_ORG_OFFER_TYPE = "Offer"

#: `Event.status` -> Schema.org's `eventStatus`.
#:
#: **Keyed by value and there is no default**, for the same reason `LIFECYCLE_SEND_BEHAVIOUR`
#: is: a status added to the model must fail a test rather than silently produce an event with
#: no `eventStatus` at all — which is a structured-data warning a crawler would raise.
#:
#: `superseded` is deliberately **absent**. It is terminal, the public read 404s it before it
#: ever builds a payload, and Schema.org's `EventStatus` vocabulary has no term for it. There is
#: no honest mapping, so there is no mapping.
SCHEMA_ORG_EVENT_STATUS = {
    "scheduled": "https://schema.org/EventScheduled",
    "postponed": "https://schema.org/EventPostponed",
    "cancelled": "https://schema.org/EventCancelled",
}

#: `Event.is_sold_out` -> Schema.org's `offers.availability`.
#:
#: The registry knows whether an event is sold out. It does **not** know a price, so no price
#: is ever emitted: an `Offer` carrying only `availability` says exactly what we know, and a
#: fabricated `"price": "0"` says something we do not.
SCHEMA_ORG_AVAILABILITY_SOLD_OUT = "https://schema.org/SoldOut"
SCHEMA_ORG_AVAILABILITY_IN_STOCK = "https://schema.org/InStock"

#: Schema.org's `eventAttendanceMode` vocabulary, for the day the registry learns one.
#:
#: **The registry has no attendance mode today** — no column on `Event`, none on `Venue`. So
#: the projection omits the property entirely rather than defaulting to `Offline` for an
#: event the registry says nothing about. These constants exist so that the vocabulary is
#: written down once, ready for the schema change that would make the value knowable.
SCHEMA_ORG_ATTENDANCE_MODE_OFFLINE = "https://schema.org/OfflineEventAttendanceMode"
SCHEMA_ORG_ATTENDANCE_MODE_ONLINE = "https://schema.org/OnlineEventAttendanceMode"
SCHEMA_ORG_ATTENDANCE_MODE_HYBRID = "https://schema.org/MixedEventAttendanceMode"


# ── The SEO city page (FR-27) ───────────────────────────────────────────────────────
#
# FR-27: *"A city page exists for every city in the Source Registry with >5 events."*
#
# **The threshold is one number, and it is here.** FR-27 says ">5", which means **more
# than five** — so a city with exactly five does not qualify and a city with exactly six
# does. The comparison is `>`, not `>=`, and the boundary is a test rather than a reading
# of the sentence.
CITY_PAGE_EVENT_THRESHOLD = 5

#: How far back a city page's *qualification* looks, when it is not counting only what's
#: happening next.
#:
#: **The listing and the qualification deliberately measure different things.** The
#: listing shows upcoming events, because a page headed "events in Brooklyn" that leads
#: with last week's is a page nobody comes back to. The qualification asks a different
#: question — *has this city ever had enough events to deserve a page?* — and a city that
#: had six events last season still deserves its URL.
#:
#: Without this window, a city's page would **wink out of existence** the moment its last
#: event started: a URL that 404s after ranking is worse than one that never ranked. With
#: it, the page persists and shows "coming soon" between seasons, which is exactly what
#: FR-27 asks for ("a city page degrades gracefully when no events are present").
#:
#: A year is the window. It is long enough to carry a city across a quiet season and short
#: enough that a city that has genuinely stopped having events stops qualifying.
CITY_PAGE_QUALIFICATION_WINDOW = timedelta(days=365)

#: A page of city-page events. The ceiling keeps one request from asking for a city's
#: whole history.
CITY_PAGE_DEFAULT_PAGE_SIZE = 20
CITY_PAGE_MAX_PAGE_SIZE = 50

# ── The public URL feed (the sitemap's source) ─────────────────────────────────────
#
# The feed lists every publicly addressable page, so it **grows with the catalog** — and
# a read that grows with the catalog must never be an unbounded scan. These two numbers
# are the bound on that scan (AD-8: a threshold lives in one place).
#
# **The default is small enough to be cheap and large enough to be useful.** The sitemap
# handler pages the feed; at a thousand URLs a page, a 50,000-URL sitemap child is fifty
# bounded requests, which is measurable rather than one enormous one.
URL_FEED_DEFAULT_PAGE_SIZE = 1000

#: The ceiling on one feed page. A caller asking for more has made a mistake, and the
#: HTTP edge refuses it with a 422 — the same rule the city page's query follows.
URL_FEED_MAX_PAGE_SIZE = 1000
