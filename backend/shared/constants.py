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

# FR-57: a user-reported ReviewItem is due this long after its *first* report (review-queue-model
# D8). The other reasons carry no per-item deadline: "reviewed at least daily" is a team cadence.
REVIEW_SLA_USER_REPORTED = timedelta(hours=24)

# FR-52: "A user requesting export receives an email with download links within 24 hours."
# **The same 24 hours as `REVIEW_SLA_USER_REPORTED`, and deliberately a separate constant.**
# They are equal today by coincidence of policy, not by shared cause: one is how fast a
# person's report must reach a reviewer, the other is how fast a person's own data must
# reach them. Collapsing them would mean a change to either silently moved the other.
DATA_EXPORT_SLA = timedelta(hours=24)

# How long a download link lives once the export is built. **Not the same as the SLA** —
# the SLA is how long the user waits, this is how long they have to collect it.
#
# Seven days is chosen against two failure modes: a link short enough to expire before
# somebody back from a week away can use it is a right denied by timing, and a link that
# lived indefinitely would be a copy of the user's whole account sitting behind a URL in
# their mailbox forever. PRD §10.1 keeps an export for 30 days past account deletion, which
# is a different window for a different reason and is deletion's to implement.
DATA_EXPORT_LINK_LIFETIME = timedelta(days=7)

# FR-57: which kind of review item an editor should reach for first.
#
# **`ReviewItem` has no priority column, and this is why.** `review-queue-model` did not add
# one and `review-intake-and-backfill` D1 explicitly declined to: a low-priority item would
# need a migration, and the volume of published-but-flagged events is unknown and potentially
# large — it would dilute the queue-size and oldest-item metrics the admin exists to show.
#
# So priority is *derived from the reason*, which is the one thing every item already carries.
# The order is what an editor's day actually looks like:
#
# 1. `user_reported` — a person says something is wrong, and FR-59's 24h SLA is running.
# 2. `source_reliability` — FR-16's escalation: this source keeps being wrong.
# 3. `in_review` — the confidence gate caught it, and nobody has complained yet.
#
# **Keyed by value, not by the model's enum.** `shared` sits below `apps`, so it cannot import
# `apps.ingestion.models`; this is the same shape as `LIFECYCLE_SEND_BEHAVIOUR` and
# `REPORT_CATEGORIES` above, for the same reason.
REVIEW_PRIORITY = {
    "user_reported": 0,
    "source_reliability": 1,
    "in_review": 2,
}

# FR-59: the four report categories, and the one place they are written down.
#
# **Three enums must agree and none of them can import the others.** `ReviewItem.ReportCategory`
# lives in `catalog`, `EventReport.Category` in `personal`, and `shared` is below `apps` so it
# can hold neither. This is the same shape as `LIFECYCLE_SEND_BEHAVIOUR`, keyed by value for
# the same reason, and `tests/shared/test_constants.py` asserts all three stay in step.
#
# **No free text, ever** (FR-57 and FR-59 both put it in Phase 2). A report is one of four
# values; there is no field for a user to type into, so there is nothing to moderate.
REPORT_CATEGORIES = ("wrong_date_time", "wrong_venue", "does_not_exist", "duplicate")

# FR-59: five reports per user per day, through the throttle port (PRD 11.2), never hand-rolled.
# The sixth answers 429 and the UI renders it calmly; one person cannot pull an event, and a
# troll cannot manufacture a queue.
EVENT_REPORT_DAILY_LIMIT = 5
EVENT_REPORT_WINDOW_SECONDS = 24 * 60 * 60

# How often the reconciler re-offers a report whose ReviewItem was never raised. The same
# cadence as `OUTBOX_RECONCILE_EVERY_MINUTES`, and for the same reason: both are a second
# attempt at one cross-boundary hop, not a retry loop.
EVENT_REPORT_RECONCILE_EVERY_MINUTES = 5

# ── FR-16: the Source Reliability Score (domain/reliability.py) ──────────────────────────────
#
# **The fourth confidence, and never conflated with the other three.** `extraction_confidence`
# is how sure we are we read the page correctly, `tz_inference_confidence` how sure we are of
# the timezone, the Confidence Pulse is what the user is shown. This one is how well a *Source*
# has behaved over time. They are four different questions and they share no constant.
#
# The beta-binomial prior. α = β = 5 means a new Source starts at the prior mean 0.50 and a
# single bad event cannot crater it: one negative gives (5+0)/(10+1) = 0.45, not 0.00.
RELIABILITY_PRIOR_ALPHA = 5
RELIABILITY_PRIOR_BETA = 5

# FR-16's min-N. Below this the score still *moves*, but it cannot fall below the floor below.
#
# **This resolves a contradiction in FR-16, and the resolution is a reading of its own numbers.**
# The PRD says a Source "needs at least 30 observations before its score moves" *and* that one
# under 30 "cannot have its score drop below 0.32". Read literally the first makes the second
# unreachable — a frozen score never approaches any floor. The arithmetic says which was meant:
# the all-negative posterior runs 0.50, 0.45, 0.42, 0.38, 0.36, 0.33 (n=5), 0.31 (n=6), so
# **0.32 is the posterior after five or six straight failures** — not the floor at n=29, which
# is 0.13. So the floor is a deliberate statement: until there are 30 observations, never judge
# a Source worse than about five strikes. The score moves; the clamp holds the bottom.
#
# Escalation requires n >= 30 anyway, so the clamp can never suppress one.
# PRD amendment owed: "before its score moves" -> "before its score moves freely".
RELIABILITY_MIN_OBSERVATIONS = 30
RELIABILITY_NEW_SOURCE_FLOOR = Decimal("0.32")

# FR-16: below this, with at least RELIABILITY_MIN_OBSERVATIONS, a Source is escalated to the
# editorial queue. **Escalation, never removal** — a low score lowers ranking and raises a
# ReviewItem; it never pauses or hides the Source.
RELIABILITY_ESCALATION_SCORE = Decimal("0.30")

# FR-16's spike detection, as a ratio of **week-over-week negative rates** — not of scores.
#
# **A ratio of scores cannot fire, which is why this measures something else.** Under 30
# observations the floor above pins the score between 0.50 and 0.32, a ratio of at most 1.56.
# At or above 30, any score low enough to be a third of its predecessor is already below
# RELIABILITY_ESCALATION_SCORE, so escalation has already fired. And a cumulative posterior is
# sticky: a Source at 0.80 needs ~100 all-negative events in one week to reach even 2.96x.
#
# So `is_spike` compares the *rate of bad events*, each week's rate smoothed with the **same**
# prior above. That costs no further constant and suppresses small samples for free: a week of
# two events with one bad is (5+1)/(10+2) = 0.50 against (5+0)/(10+2) = 0.42, a ratio of 1.2.
# PRD amendment owed: "3x week-over-week drop in reliability score" -> "3x week-over-week rise
# in the smoothed rate of negative observations".
RELIABILITY_SPIKE_MULTIPLIER = Decimal("3")

# FR-16: what each editorial verdict is worth to the score. **The counting rule, written down
# once** (design: reliability-recompute-and-escalation D14).
#
# **Keyed by value, not by the model's enum.** `shared` sits below `apps`, so it cannot import
# `apps.ingestion.models`; this is the same shape as `REVIEW_PRIORITY` and `REPORT_CATEGORIES`
# above, for the same reason. The recorder and the recompute job both read this table, so two
# implementations of the same sign cannot exist.
#
# **`approved` is +1.** FR-16 positive: the listing was right.
#
# **`rejected` is -1.** FR-16 negative: the listing was wrong.
#
# **`edited` is -1** (design D4). **The source was wrong.** A source that gets every event's
# time wrong must not score like one whose times are right. FR-16's own brakes — the floor
# and the min-N — are the protection.
#
# **`dismissed` is 0** — FR-25's **named, unimplemented** input (design D5, D6). A dismissal
# is "I looked at this source and found no fault", not a check of any of its events, so it is
# neither evidence for nor against. The *dismissal rate* is not computed and no term
# anywhere stands in for it.
#
# **Zero is not the same as absent.** A dismissal is recorded as a fact (an editor looked) and
# contributes nothing to the counts. An absent input would not be recorded at all.
OBSERVATION_SIGNS = {
    "approved": 1,
    "rejected": -1,
    "edited": -1,
    "dismissed": 0,
}

# FR-16: the score is recomputed **at least weekly**, and the spike rule compares this week
# with last week, so the period is a calendar week.
#
# **A weekly cadence is not a minute-modulo rule.** The worker's tick dispatches on
# `minute % 5` and `minute % 15`; there is no `minute % 10080`. So the tick asks the job to
# look on every tick and the job decides who is due — the same shape as `schedule_digests`,
# which also runs on every tick because "due" is a per-source comparison. The period boundary
# is the **ISO Monday 00:00 UTC**, so a week's observations are unambiguous.
#
# `RELIABILITY_PERIOD_DAYS` is the length of the period the score is computed over: a week.
# The service derives the period's boundaries from it rather than hard-coding 7 twice.
RELIABILITY_PERIOD_DAYS = 7

# FR-16: how long the weekly recompute's claim on a source survives.
#
# **A claim has to outlive the transaction that took it.** The claim is written to
# `Source.reliability_claimed_at` rather than held as a row lock, because the recompute runs
# in its own transaction — a `FOR UPDATE SKIP LOCKED` that releases with its transaction
# prevents nothing (design D10).
#
# **A claim older than this is a lost job.** The source is claimed again rather than being
# skipped for the rest of the week, which is the same rule the scheduler's ingest claim uses.
RELIABILITY_CLAIM_TTL = timedelta(hours=1)

# FR-16: how many sources one recompute batch claims at a time.
#
# **The claim holds a lock on every row it takes**, so an unbounded claim would hold every due
# source's lock for the length of the batch. The batch is bounded for the same reason
# `SCHEDULE_BATCH` is: one slow source must not hold up every other tick's work.
RELIABILITY_BATCH_SIZE = 100

# FR-16's score, rendered as the **1–5 trust dots** on `Settings → Sources`.
#
# **These are not FR-22's bucket boundaries.** `RANKING_BUCKET_*` (below) bands the
# *Relevance Pulse* — the Confidence Pulse's bucket — and its boundaries are FR-22's. The
# trust dots answer a different question ("how much do we trust this source's facts?"),
# so they get their own bands. Reusing `score_bucket` would mean the source's trust was
# silently the confidence of an event from it.
#
# **0.50 is band 3 — "ok".** A source the recompute has never reached has no score, and
# reads as the 0.50 prior (`reliability_score(0, 0)`). Banding it at 3 says "we have not
# learned anything bad yet", which is what the prior actually means. It also means the
# dots are meaningful before a source has 30 observations — which is every source in the
# registry on day one.
#
# **Never a week-over-week delta.** `domain/reliability.py` proves a 3× drop is
# impossible, so a delta here would assert something the domain says cannot happen.
SOURCE_TRUST_BAND_5 = Decimal("0.80")
SOURCE_TRUST_BAND_4 = Decimal("0.65")
SOURCE_TRUST_BAND_3 = Decimal("0.50")
SOURCE_TRUST_BAND_2 = Decimal("0.35")

# The trust dots are 1–5, and 5 is the most trusted.
SOURCE_TRUST_MIN = 1
SOURCE_TRUST_MAX = 5

# The penalty a `show_less` source's events take, applied **after** the published score.
#
# **It is not a sixth term in FR-22's formula.** `relevance_score()` is exactly five
# weighted terms summing to 1.00, and `tests/shared/test_constants.py` pins those
# weights against ADR-0025 — so adding a term would change a published formula and need
# a new ADR to authorise it. "Show less" is a *preference over the ordering*, not a
# property of the event, so it is applied to the score the formula produced, before the
# ordering, and the formula itself is untouched.
#
# **It is a penalty, not an exclusion.** "Show less" means fewer, and a source whose
# events vanished would be indistinguishable from a mute on the wire.
#
# **0.10 is deliberately equal to the smallest published weight** (the city term). One
# "show less" should be able to reorder a slot — that is the whole point of the control —
# but it should not on its own invert what a slot is for: the reliability term is 0.25 and
# the interest term 0.35, so neither a city match nor a good source can be undone by one
# user's preference about one source.
SOURCE_SHOW_LESS_PENALTY = Decimal("0.10")

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

# ── FR-53: the detection floors ─────────────────────────────────────────────────────
#
# "The system re-ingests high-priority sources at least every 4 hours. Lower-priority
# sources at least daily." Its consequence is the thing that matters: "A cancelled event is
# detected by the system within 4 hours for high-priority sources and within 24 hours for
# lower-priority sources."
#
# **These are ceilings, not defaults.** A default is a starting point; a ceiling is a
# guarantee. A source polled every 24 hours cannot have a cancellation detected within 4
# hours, so a cadence above its tier's ceiling is refused at the point it is written rather
# than discovered later, when the product has already promised on it.
#
# **A source may poll more often than its tier requires.** The ceilings only forbid what the
# guarantee cannot support. `DEFAULT_INGESTION_CADENCE` gives rss/jsonld/ics a 4-hour
# default — inside the lower tier's 24-hour ceiling, and detecting changes in 4 hours
# rather than 24 — and that stays.
#
# **The tier is derived from `acquisition_method`, not stored.** FR-17's order is the
# codebase's own statement of which sources matter more, and the method is already on the
# row. A second priority field would be a second opinion about a question the codebase has
# already answered, and the two could disagree — and a priority that disagrees with the
# method is a guarantee nobody can check.
#
# The split is FR-17's, at the boundary FR-53's parenthetical names: the PRD's §10.4 calls
# high-priority sources "official sites", and the official sources are the API and
# partnership ones. Crawl stays in the lower tier — it is the last resort, and giving it a
# 4-hour floor would push the whole registry toward frequent crawling, which is exactly
# what FR-17's ToS guard exists to prevent.
HIGH_PRIORITY_METHODS = ("api", "partnership")
HIGH_PRIORITY_CADENCE_MAX = timedelta(hours=4)
LOW_PRIORITY_CADENCE_MAX = timedelta(hours=24)

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

# FR-50: "Free tier: 1 connected provider. Pro tier: up to 3". **The cap is chosen by
# entitlement**, so the two tiers are one rule with two values rather than two rules — and
# the choice is made by the one published read (`is_pro`), never by a second mapping of
# "who is Pro" that could disagree with it.
#
# A Pro user who lapses keeps their existing connections. Nothing here deletes anything on
# downgrade: the cap is enforced at the *connect* step, so a lapse closes the door behind
# the user rather than removing what they already have.
FREE_TIER_CALENDAR_PROVIDER_CAP = 1
PRO_TIER_CALENDAR_PROVIDER_CAP = 3

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
# Saved events (FR-49)
#
# Stdlib only, like the sections above.
# ─────────────────────────────────────────────────────────────────────────────

# FR-49: "Free tier: 1 Pulse Card saved per 24-hour period", and the second save attempt
# in that window shows a calm upgrade prompt. **The gate, not a rate limit** — the remedy is
# to upgrade, not to retry, which is why the refusal is a 409 and not a 429.
#
# The count is the throttle port's, exactly as `EVENT_REPORT_DAILY_LIMIT` is: a fixed-window
# counter that the port owns, so a test can pin the window boundary without sleeping and
# without Redis. It is never a count of rows — a row count would make the cap depend on
# data the user can delete, and would give the gate a second source of truth.
#
# The window is 24 hours, measured from the *first* save in it. A refused save cannot move
# that anchor, so being refused costs the user no time they would not have lost anyway.
#: The one quiet-hours window a Free account gets. Pro gets one per weekday (FR-51).
FREE_TIER_QUIET_HOURS_WINDOWS = 1

#: The upgrade sentence for a Free account trying to set a window per weekday. One calm
#: sentence, matching the save cap's and the calendar cap's: the word "Pro" is what the
#: quiet "Upgrade" link beside it points at.
QUIET_HOURS_PRO_UPGRADE_HINT = "Set a different window for each day with Pro."

#: FR-49: named collections are a Pro feature, so a Free account gets **none**.
#:
#: **Zero is a real cap, not a disabled feature flag.** It is carried in the refusal's
#: `{cap, upgrade_hint}` payload exactly as the save cap's 1 and the calendar cap's 1 are,
#: so the inline prompt renders it with no special case for "the limit is nothing".
FREE_TIER_COLLECTIONS = 0

FREE_TIER_SAVE_DAILY_LIMIT = 1
FREE_TIER_SAVE_WINDOW_SECONDS = 24 * 60 * 60

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
# and locks those weights. **One of the four components has no input in this codebase**:
#
#   * `novelty_vs_exploration` — needs the Preference Graph (FR-25, deferred) *and* an
#     event category, and `Event` has no category field.
#
# `source_reliability` **used to** be missing too. FR-16's score now lives on `Source`
# (`reliability_score`), written by the weekly recompute, and the ranking reads it.
#
# A term multiplied by a constant is an **inert weight**: the published formula would stay
# arithmetically checkable and still produce a different number from the one on the card,
# which is a worse trust failure than a reduced formula because it looks verifiable.
# `domain/event_fit.py` set this precedent when it refused to invent a "Free" tag — "they
# are added to Event Fit's rule set then, not faked now."
#
# So the omitted term is **absent from the expression**, and the surviving weights are
# redistributed so they still sum to 1.0. The docstring of `domain/ranking.py` states the
# reduction, names every omitted input, and names the FR that will supply it.
#
# **FR-22's own words: "The Architecture spec describes the *implementation* of the formula
# but does not redefine the weights."** The weights below are that implementation. They are
# **not** FR-22's published MVP weights — those are 0.40 / 0.25 / 0.20 / 0.15 — and
# changing them is not a change to those. The substitution of each published term for the
# term the product can actually compute is recorded in the ADR named below.

# The formula the product computes.
#
#   relevance_score = RANKING_WEIGHT_INTEREST × interest_overlap
#                   + RANKING_WEIGHT_RECENCY  × recency
#                   + RANKING_WEIGHT_CITY     × city_match
#                   + RANKING_WEIGHT_CONFIDENCE × confidence
#                   + RANKING_WEIGHT_RELIABILITY × source_reliability
#
# **Interest overlap is 0.35.** FR-22 publishes 0.40 for `preference_graph_match`; the
# chips are the Preference Graph's only surviving trace, so they stand in for it. The 0.05
# shortfall is the slack from `novelty_vs_exploration` (0.15), which has no input at all.
#
# **Source reliability is 0.25 — FR-22's published weight for `source_reliability`, exact.**
# This is the term FR-16 built, and it enters at the weight the PRD always gave it.
#
# **Recency is 0.20**, FR-22's published weight for `recency_fit`, exact. It stood at 0.25
# while it was carrying two absent terms' slack; now that it stands for one thing again it
# is back at the PRD's number.
#
# **City match is 0.10**, and it is **additive**, not a multiplier. FR-5 multiplies by a
# `geographic_distance_factor`, which zeroes out every event outside the user's city — but
# city membership is decided by the *candidate read*, not by the score. Once the read has
# filtered to the user's city, multiplying by a city factor would multiply by a constant,
# which is exactly the inert weight this section exists to avoid.
#
# **Confidence is 0.10.** FR-22 says the Confidence Pulse measures the AI's certainty about
# relevance "not just trust in the source"; extraction confidence is the one measure of "how
# well do we know this event's facts" that exists, and it is the same number the
# eligibility gates use.
RANKING_WEIGHT_INTEREST = Decimal("0.35")
RANKING_WEIGHT_RECENCY = Decimal("0.20")
RANKING_WEIGHT_CITY = Decimal("0.10")
RANKING_WEIGHT_CONFIDENCE = Decimal("0.10")
RANKING_WEIGHT_RELIABILITY = Decimal("0.25")

# The five weights must sum to exactly 1, so the score stays in [0, 1] and the bucket
# boundaries keep their meaning. Pinned by `tests/shared/test_constants.py`.
RANKING_WEIGHT_SUM = (
    RANKING_WEIGHT_INTEREST
    + RANKING_WEIGHT_RECENCY
    + RANKING_WEIGHT_CITY
    + RANKING_WEIGHT_CONFIDENCE
    + RANKING_WEIGHT_RELIABILITY
)

# **The amendment that authorises the weights above** (FR-22's amendment policy: "Any
# change to the weights is a PRD amendment requiring explicit product leadership sign-off",
# and "Amendments are tracked in `docs/adr/`").
#
# **A string in a constant is not an amendment.** A test reads the ADR this names and
# checks that it lists the weights it claims to authorise — so moving a weight and
# updating this string in the same commit still fails, because the ADR's own table has to
# move too, and the ADR is a document a human reads.
RANKING_WEIGHTS_AMENDMENT = "ADR-0025"

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

# AD-17: how long a send may sit held for propagation before it is reported as stuck.
#
# **The hold itself is correct and has no timeout** — a held row is one the catalog has moved
# past, and sending it would be the bug this guard exists to prevent. What needs a bound is
# nobody *releasing* it: propagation is what clears `held_at`, and if propagation is broken
# the user's reminders stop with no error anywhere. That failure is quieter than the one being
# fixed, so it gets an alarm rather than a timeout. Nothing is ever sent because this elapsed.
#
# **Comfortably longer than the outbox's own recovery.** `OUTBOX_RECONCILE_AFTER` re-offers an
# unpropagated change after 5 minutes, so a hold outliving 30 minutes means the consumer is
# failing rather than merely slow — the thing worth waking someone for.
HELD_SEND_ALARM_AFTER = timedelta(minutes=30)

# AD-17: one page of the users affected by one event's state change.
#
# **A page, not a limit.** Propagation must reach *every* saver of a popular event, so the
# read is paged to exhaustion — this number bounds one round trip, not the work. A cap that
# silently dropped the tail would make a state change reach some users and not others, which
# is the exact failure AD-17's per-user idempotency exists to rule out.
#
# **Keyset, not offset**, which is why the page can be this large without a long transaction:
# each page is an index range scan on `saved_event_event_idx`, and no page holds a lock across
# the next one. Propagation runs while people save and unsave, and an offset page would skip a
# row whenever an earlier one was deleted between pages.
SAVERS_PAGE = 500

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


# FR-54: how many open state-change notices the digest strip shows.
#
# **A few, not a history.** FR-54's promise is "one calm correction", and the strip is where
# that promise is kept or broken: a strip that grows without bound is a wall of corrections,
# which is the spam FR-54 exists to prevent. There is no inbox to page through, so this is a
# **fixed bound, not a page size** — the client cannot ask for more, and there is no "load
# more" to build.
#
# **Five, not three.** Three is the number of Pulse Card slots, and the strip is not cards:
# a notice is a correction the user may not act on at all, and a notice can exist for an
# event the user has since un-saved — so it need not correspond to a card they saw. Five
# leaves room for a busy day without becoming a list.
#
# **A bound, not a page.** `SAVERS_PAGE` is a page because propagation must reach *every*
# saver of a popular event. This is the opposite case: the strip is a summary, and the
# notices beyond the bound are reachable from the Detail screen. So unlike `SAVERS_PAGE`,
# dropping the tail here loses nothing — the user who needs the sixth notice opens the
# sixth event.
NOTICE_STRIP_LIMIT = 5


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
    # An editor rejected the listing (FR-57). The event may well still be happening — a
    # duplicate or a wrong-venue reject says nothing about the real world — but *we* are no
    # longer willing to stand behind it, and a reminder is us standing behind it. So the
    # pending rows are cancelled and nothing is minted.
    #
    # **This is the entire reason the reject writes a state change at all.**
    # `publication_status` is not a lifecycle field, so hiding the Event bumps no version
    # and reaches nobody; without this row the saver keeps getting "your event is in 3
    # hours" for an event editorial deleted. The outbox is also the *only* fan-out across
    # the schema wall — `cancel_sends_for_targets` is per-user and cannot address savers.
    "delisted": LifecycleSendBehaviour.CANCEL,
    # The reversal re-mints: they saved it, it is back, and their ReminderPlan was never
    # deleted. `mint_for_plan` already declines a slot whose instant has passed, so a
    # long-rejected event reinstated after its start mints nothing.
    "relisted": LifecycleSendBehaviour.REMINT,
}


class LifecyclePersonalBehaviour(StrEnum):
    """What an event state change does to a user's **saved event** (AD-17, AD-21)."""

    #: Re-stamp the snapshot's time and version, and re-judge its conflict pairs.
    RESTAMP = "restamp"
    #: The event is not happening: bump the version and close the pairs.
    CANCEL = "cancel"
    #: Live again: bump the version. The pairs a cancellation closed stay closed (AD-21 D24).
    REINSTATE = "reinstate"
    #: Nothing the snapshot stores changed.
    NONE = "none"


# AD-17's "what each change does", mapped for `personalization`. Keyed by
# `EventStateChange.Kind` values, by value, for the same reason its `delivery` sibling is:
# `shared` is below `apps` and cannot import the enum.
#
# **It is deliberately not the same shape as `LIFECYCLE_SEND_BEHAVIOUR`.** `SAVED_EVENT`
# stores a start, an end and a version; `SCHEDULED_SEND` stores a due time computed from
# them. So `sold_out` and `detail_changed` — which `delivery` must still act on, because a
# held send needs its version re-stamped to be released — change *nothing* the snapshot
# holds. `event_writes._kind_facts` does not even record a time for those kinds.
#
# Calling the snapshot updater for them would bump the version and then re-run
# `reconcile_pairs_for_side` and `detect_conflicts` for an overlap that cannot have moved.
# Letting the snapshot's version lag behind the catalog's is safe because every gate in
# this tree is `>` and not `==`: a snapshot at v1 that skipped a `sold_out` at v2 still
# accepts a `time_moved` at v3.
#
# **Every kind is mapped explicitly and there is no default**, so a new kind added in
# `ingestion` fails a test rather than silently doing nothing to anyone's calendar.
LIFECYCLE_PERSONAL_BEHAVIOUR = {
    "time_moved": LifecyclePersonalBehaviour.RESTAMP,
    "postponed": LifecyclePersonalBehaviour.RESTAMP,
    "reinstated": LifecyclePersonalBehaviour.REINSTATE,
    "cancelled": LifecyclePersonalBehaviour.CANCEL,
    "superseded": LifecyclePersonalBehaviour.CANCEL,
    "sold_out": LifecyclePersonalBehaviour.NONE,
    "detail_changed": LifecyclePersonalBehaviour.NONE,
    # **Deliberately NONE, and this is the one entry whose reason is not about the snapshot.**
    #
    # `cancel_saved_event` would be the obvious choice — it is what `cancelled` and
    # `superseded` use — and it would close the user's conflict pairs as
    # `cleared_by_state_change`. The problem is that AD-21 D24 makes a closed pair
    # **immutable** (`guard_conflict_pair`) and `conflict_pair_pair_uq` forbids a
    # replacement row. A reject is reversible by an editor; a closed pair is not. So an
    # editor who rejected an event and then reinstated it would restore a real clash that
    # `/conflicts` could never mention again — the open AD-17/AD-21 defect, walked into
    # deliberately. Leaving the pair open costs nothing: a side whose catalog event is not
    # published already renders `available: false` ("event no longer available"), the same
    # path superseded and unpublished events take.
    #
    # **The sends still cancel.** `worker.propagation._apply_sends` takes the version from
    # the *change* (`replace(target, version=change.event_version)`), never from the
    # snapshot, so a NONE personal behaviour does not weaken the CANCEL above.
    "delisted": LifecyclePersonalBehaviour.NONE,
    "relisted": LifecyclePersonalBehaviour.NONE,
}

# AD-17: how long a state change may sit unpropagated before it is reported as stuck.
#
# **An alarm, not a timeout.** `EventStateChange` is append-only — `propagated_at` is its one
# mutable column — so there is no attempts counter to retire a poisoned change with, and
# marking it propagated to stop the churn would claim a propagation that never happened and
# leave that user on the old state forever. What is bounded here is how long the failure can
# stay quiet.
#
# Comfortably longer than `OUTBOX_RECONCILE_AFTER`, which re-offers an unpropagated change
# after 5 minutes: a change outliving 30 minutes is failing rather than merely waiting.
PROPAGATION_ALARM_AFTER = timedelta(minutes=30)


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


# ── FR-25: "Less like this" — the dismissal cluster (AD-8) ──────────────────────────
#
# FR-25 is the feedback loop: the user swipes past a card, and after enough *similar*
# swipes the product asks whether they would like less of that category.
#
# **Every number the loop uses is here.** AD-8: a threshold lives in one place, so that
# there is one answer to "what does 0.7 mean?" and one place to change it. None of these
# may be written as a literal in the service that reads them — the cosine rule lives in
# `apps/personalization/services/dismissals.py`, and a literal there would be a second
# answer to the same question.
#
# **The category is the chip key.** There is no `Event.category` column and this section
# does not invent one: `apps/ingestion/services/chip_matching.py` already computes each
# event's `chip_keys` at read time, deliberately not as a stored column (a stored column
# would be wrong the moment the keyword table changed), and the interest term of FR-22 —
# the largest weight in the published formula — already reads it. So the mute is keyed on
# the chip key, and the prompt names the chip's own label from `INTEREST_CHIPS`.

#: The cosine similarity two events' embeddings must reach for the dismissals to count
#: as the same cluster.
#:
#: **0.70 is a threshold on a unit vector's cosine**, which is a number in `[-1, 1]`
#: where `1.0` means "the same direction" and `0.0` means "orthogonal". 0.70 is
#: "clearly the same thing, but not a duplicate" — two events about the same thing in
#: the same vein, not the same event listed twice.
#:
#: It is `Decimal` rather than `float` because it is compared against a cosine computed
#: in `Decimal` (the embedding vectors are read as exact decimals), and a float
#: comparison at the boundary would make "exactly 0.70" a coin flip.
FR25_CLUSTER_COSINE_THRESHOLD = Decimal("0.70")

#: How many distinct events must be dismissed before the cluster can fire.
#:
#: **Three is the minimum, and it is not two.** FR-25's own wording is "3 distinct
#: events dismissed" — the mockup's specs panel says the same. Two dismissals is what a
#: user does when a card renders wrong; three is what a user does when they do not want
#: a category. The number also bounds the work: the rule reads at most three vectors.
FR25_CLUSTER_MIN_EVENTS = 3

#: How far apart the dismissals may be and still be one cluster.
#:
#: **24 hours is the window on the *span*, not on each dismissal.** The first and the
#: third must be within a day of each other; a dismissal this morning and one this
#: evening are adjacent, while one this morning and one tomorrow morning are not.
#:
#: The window is what stops the rule from muting a category from three swipes spread
#: over a year — a year of drifting preferences is not one verdict.
FR25_CLUSTER_WINDOW_HOURS = 24

#: The rage-dismiss guard: three dismissals inside this many seconds is a flick, not a
#: preference.
#:
#: **Five seconds.** A user who swipes three cards in five seconds has not formed an
#: opinion about a category; they have cleared a screen. Without the guard, the fastest
#: way to get a category muted is to be annoyed for four seconds — which would make the
#: mute a button for *being irritated*, and the mute is not reversible to the user's
#: taste, only to their patience.
#:
#: The guard is **not** a veto on recording: the dismissal is still recorded (the user
#: really did dismiss it), it just does not advance the cluster counter.
FR25_RAGE_GUARD_SECONDS = 5

#: How many dismissals inside the rage window trigger the guard.
#:
#: Three, and it is a separate constant because it is a different kind of number: this
#: one counts dismissals, and the window above measures time. Writing "3" inline at the
#: call site would be the kind of bare literal this section exists to prevent.
FR25_RAGE_GUARD_COUNT = 3

#: After this many days a dismissal counts for **half**.
#:
#: The decay is a half-life, not a cliff: a dismissal from two months ago is weaker
#: evidence than one from yesterday, but it is not nothing. A cliff at 60 days would
#: throw away the evidence of a slow, deliberate dislike — the user who swipes past the
#: same kind of event for two months *before* the cluster fires is precisely the user
#: the loop should catch.
FR25_DECAY_HALF_DAYS = 60

#: After this many days a dismissal is **expired** — ignored entirely.
#:
#: This is the cliff, and it exists because the half-life alone never reaches zero: a
#: decade-old swipe would still count for a sliver, and a sliver that never dies is a
#: preference the user cannot escape. 180 days is the window in which the product is
#: willing to speak for the user.
FR25_DECAY_EXPIRE_DAYS = 180

#: The durations a category mute may last, in days.
#:
#: **The mockup's four choices, and the fourth is not a number.** Seven days, thirty
#: days, ninety days, and "until I change it" — the indefinite one is represented by a
#: `null` expiry on the row, so it is a *state* of the same row rather than a second
#: code path. The constant is the three finite durations, and `None` is the indefinite
#: case.
#:
#: **These are the only accepted durations.** The endpoint refuses anything else with a
#: 422: a mute that outlived the user's patience by a typo (3650 days) is a mute the
#: user has to find a screen to undo, and there is one tap to undo it but no reason to
#: make it hard.
FR25_MUTE_DURATIONS_DAYS = (7, 30, 90)

#: The embedding dimensions the product stores.
#:
#: **`voyage-4-lite` is a Matryoshka model**, so it can be truncated to a smaller
#: dimension at essentially no loss in similarity — and the cluster rule compares
#: vectors by cosine, so the dimension is a storage and comparison cost, not a
#: capability.
#:
#: **256 rather than 512.** Half the storage, half the bytes on the wire, and the
#: cosine at the same threshold. The spine pins 256 or 512; this is the 256 choice, and
#: it is written down here rather than left to whichever adapter was configured.
FR25_EMBEDDING_DIMENSIONS = 256

#: The model that produces the embeddings.
#:
#: **The name is a constant because the cost row carries it.** A cost row that records
#: "some model" cannot answer "what did we spend on embeddings", and the AI Cost
#: Dashboard reads exactly that. The string here and the string in the adapter's cost
#: row must be the same one.
FR25_EMBEDDING_MODEL = "voyage-4-lite"
