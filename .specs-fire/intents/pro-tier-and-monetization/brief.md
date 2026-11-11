---
id: pro-tier-and-monetization
title: Pro Tier & Monetization — Subscription, Entitlement & the Paid Path
status: in_progress
created: 2026-11-11
---

# Intent: Pro Tier & Monetization — Subscription, Entitlement & the Paid Path

## Goal

Make "Pro" mean something in code. Today every user is Free because nothing can be
anything else: there is no `Subscription` entity, so there is no entitlement to read, so
every cap caps everyone and every upgrade prompt points nowhere.

Five MVP requirements sit behind that one missing entity. **FR-48** (the tier and its
checkout), **FR-49** (unlimited saves and named collections), **FR-50**'s Pro cap of three
calendar providers, **FR-51** (per-day-of-week quiet hours) and **FR-52** (JSON + ICS
export) are not five features — they are one entitlement mechanism and the four things it
unlocks. Build any of them alone and you get a gate with nothing behind it, or a feature no
one can reach.

This is the last MVP gap of its kind. **FR-49 is the only MVP functional requirement with
no work item anywhere on disk** — every other MVP FR (FR-1–FR-33, FR-48, FR-50–FR-60) has
at least one. And unlike FR-14's LLM path, which needs a real model provider, this intent's
only external dependency is Stripe, which it can build and prove without an account.

The codebase has been deferring this intent **by name**. `shared/constants.py:469` says it
outright: *"Every user is Free in this intent (there is no SUBSCRIPTION entity yet), so the
cap is 1. The Pro cap of 3 is a later intent and belongs here when it lands."*

## Users

- **The capped free user with nowhere to go.** `CalendarProviderCapReached` already fires
  today with approved, deliberately calm copy — `calendar_connections.py:418` carries
  `"upgrade_hint": "Save more with Pro."`, an inline sentence with no modal-shaped field in
  the payload, exactly as EXPERIENCE.md §3 specifies. The prompt ships. The destination does
  not. This is the one user-visible dead end in the product.
- **The user who wants to save more than one event a day.** FR-48 names the 1-save/day cap
  as "the gate" — the single trigger that turns a Free user into a paying one. It is not
  built, so the gate stands open and the product has no upgrade trigger at all.
- **The Pro user who was promised granular control.** FR-51's per-weekday quiet hours and
  FR-52's data export are both listed on the pricing page as what the money buys. Neither
  exists.
- **The operator validating the business.** PRD §4.11: *"Pro tier ships at MVP to validate
  monetization alongside core product."* There is currently no way to take money.

## Problem

Every seam this intent needs was deliberately cut and left open. The work is not greenfield
design; it is landing a planned entity into sockets that already exist.

- **The `Subscription` entity was declared and never written.**
  `apps/identity/__init__.py` reads *"Accounts and billing state. Owns User and
  Subscription."* `identity/models.py` defines `User`, `PasswordResetToken` and
  `IdentityAuditEntry` — and nothing else.
- **Its retention category is already reserved.** `shared/retention.py:33` defines
  `RetentionCategory.BILLING_RECORDS` — *"Billing records (Pro subscribers): 7 years
  (tax/legal)"* — and **no model in the codebase uses it**. The AD-15 registry is waiting
  for exactly one table.
- **The billing port is outbound-only, and this is the hard part.** `ports/billing.py`
  declares exactly two methods, `create_checkout` and `create_portal_session`. Both send the
  user *to* Stripe. **Nothing in the port brings subscription state back**, and
  `grep -rn webhook backend/ --include='*.py'` returns nothing — the codebase has no inbound
  webhook endpoint, for any purpose. "Is this user Pro?" has no answer path today. Supplying
  one is this intent's central design problem, not its Stripe API calls.
- **Only the fake adapter exists.** `adapters/billing/` contains `fake.py` alone.
  `config/adapters.py` omits `billing` from `REAL_ADAPTERS`, so `_mode_paths` raises
  `ImproperlyConfigured` for any non-fake mode; its comment names the pending work:
  *"Filled in by the intents that build the real gateway, email provider, Stripe and ICS
  adapters."* `tests/config/test_adapters.py:30` pins the current truth: *"no real adapter
  for billing, email, embedding, llm."*
- **The free-tier gate is missing while its sibling is built.** `EventReport` throttles
  through the port (`EVENT_REPORT_DAILY_LIMIT`, `EVENT_REPORT_WINDOW_SECONDS`), proving the
  pattern. The 1-save/day cap has no equivalent — no constant, no check, nothing on the save
  path.
- **Collections have never been designed or built.** TRACEABILITY.md:59 marks FR-49
  **MISSING**: *"Nothing designed. 'Named collections' exists only as a marketing bullet on
  the FR-48-tagged pricing pages — no screen shows creating, viewing, or managing a
  collection."* It notes EXPERIENCE.md's coverage table claims `settings-desktop.html`
  covers FR-49, but that mockup contains zero collection content.
- **Quiet hours are structurally single-window.** `domain/quiet_hours.QuietHours` is a frozen
  pair of `start`/`end` wall clocks. `NotificationPreference` stores one column pair guarded
  by `notification_preference_quiet_hours_pair_ck`, which asserts both are null or both are
  set. FR-51's seven windows change the shape of both the domain value and the table.

## Success Criteria

**FR-48: the tier, and a way to pay for it**
- `Subscription` lives in `identity` (AD-3), carries
  `retention_category = RetentionCategory.BILLING_RECORDS`, and records plan
  (`ProPlan.MONTHLY` / `YEARLY`), status, current period end, and the Stripe customer and
  subscription references.
- A single entitlement read answers "is this user Pro?" for every caller. It is the only
  way any caller asks.
- The pricing page is one screen, built from `pricing-page-desktop.html`, at $4.99/month or
  $49/year, with no upsell copy beyond *"fewer interruptions, more control."*
- The inline upgrade CTA from `pro-upgrade-cta-desktop.html` appears where a cap is hit. It
  is never a modal, matching the shipped `CalendarProviderCapReached` payload.
- Checkout is web-only. Every subscription transition is a named command with an audit
  entry (AD-5), and a lapse is a **state transition, never a delete**.

**FR-49: unlimited saves and named collections**
- A Free user's second save inside a 24-hour window is refused with a calm inline upgrade
  prompt — declared through `ThrottlePort.check(key, limit, window_seconds)`, as
  `EventReport` already does, not hand-rolled. The limit lives in `shared/constants.py`.
- A Pro user saves 10+ events in a day with no soft wall.
- A Pro user can create, rename, delete and reorder named collections over `SavedEvent`.
  Reorder is explicit and persisted, not derived from creation order.
- Collections respect AD-3: they live in `personal` and reference catalog events by value,
  never by foreign key, exactly as `SavedEvent.event_id` does.
- A test proves a Free user hitting the cap sees the prompt, and that the same user, once
  Pro, does not.

**FR-50: the cap reads entitlement**
- `FREE_TIER_CALENDAR_PROVIDER_CAP = 1` becomes a cap chosen by entitlement: 1 for Free, 3
  for Pro. The comment at `shared/constants.py:469` that names this intent is resolved and
  removed.
- A test proves a Pro user connects a second and third provider, and that a Free user still
  cannot.

**FR-51: per-day-of-week quiet hours**
- A Pro user sets seven distinct windows, one per weekday, from
  `settings-quiet-hours-pro-desktop.html`. A Free user keeps the single window.
- Windows stay **local wall-clock** values, re-read against the zone on every due-time
  computation, preserving the invariant `domain/quiet_hours.py` documents: *"'10pm' means
  10pm wherever the user is, and survives both travel and DST."*
- `shift_to_sendable` defers a send into the correct day's window, including a window that
  crosses midnight into a different day's window.
- The existing single-window behaviour is preserved for every Free user, with no migration
  that invents windows nobody set.

**FR-52: JSON + ICS export**
- Export is driven off `retention_registry()`, which `shared/retention.py` already names as
  its source: *"The sweep job, account deletion and export (FR-52) all read
  retention_registry()."* No hand-maintained second list of what to export.
- A requesting user receives an email with download links within 24 hours.
- JSON covers all user-created records; personal-event locations are redacted when the user
  opted out of precise location sharing.
- The ICS export imports cleanly into Google, Apple and Outlook calendars.

**Stripe, for real**
- `adapters/billing/stripe.py` implements `BillingPort` against the real API, and `billing`
  joins `REAL_ADAPTERS`.
- An **app-layer webhook receiver** verifies signatures and handles
  `checkout.session.completed`, `customer.subscription.updated`,
  `customer.subscription.deleted` and `invoice.payment_failed`.
- The receiver is **idempotent and order-tolerant**: a replayed event changes nothing, and
  an out-of-order event never lets a stale state overwrite a newer one. `SavedEvent`'s
  `event_version` guard is the precedent to follow.
- Both adapter and receiver are proven against `tests/adapters/scripted_network.py`, the
  harness already used by `test_crawl_http.py`, `test_revalidation_http.py` and
  `test_calendar_ics.py`. **No Stripe account is required to run the suite**, and CI stays
  secret-free.
- Keys are read via pydantic-settings at startup with local-only placeholders in
  `.env.example`; no credential enters source control.

**Proof**
- An end-to-end test walks the paid path: a Free user hits the save cap, sees the prompt,
  checks out, the webhook lands, entitlement flips, the cap lifts, a collection is created,
  a second calendar provider connects, and per-weekday quiet hours defer a send correctly.
  Then the subscription is cancelled and every gate closes again.
- Contract tests cover the new API surface and its regenerated `frontend/lib/api/schema.ts`.

## Constraints

- **AD-3:** `Subscription` belongs to `identity`. `personalization` and `delivery` read
  entitlement **by value across the wall** — no foreign key, no join, matching how
  `SavedEvent.event_id` already crosses.
- **AD-5:** every subscription transition is a named command with an audit entry, never a
  bare `obj.save()`.
- **AD-15:** `Subscription` declares `RetentionCategory.BILLING_RECORDS` (7 years). System
  checks `eventpulse.E003/E004` fail on any concrete model without a valid category, so this
  is enforced, not optional.
- **Constitution:** no secrets in code; Stripe keys come from the platform secret store, and
  `.env.example` carries local-only placeholders as `DJANGO_SECRET_KEY` and
  `REVALIDATION_SECRET` already do.
- **Testing standards (`testing-standards.md:94`):** billing stays faked at the **port**
  boundary for every test except the adapter's own. The entitlement spine, the save gate,
  collections, quiet hours and export are all proven against `FakeBillingAdapter`.
- **Never delete.** A lapsed or cancelled subscription is a state, consistent with soft
  reject and with paused-not-deleted sources.
- **Calm, not coercive.** Every cap prompt is one inline sentence with a quiet upgrade link.
  No modal, no interstitial, no countdown. The shipped `CalendarProviderCapReached` payload
  is the reference implementation.
- **Entitlement is read on a hot path.** The save gate runs on every save; the cost of the
  entitlement read is a design constraint, not an afterthought.

**Out of scope:**
- **Shared collections** and **collection-level reminders** — FR-49 puts both in Phase 2.
- **Native mobile paywall** — FR-48 is explicitly web-only.
- **The pricing A/B test** — Open Q #14, post-launch.
- **Real-time data streaming API** — FR-52 Out of Scope; Year 2+ FR-43.
- **Real LLM, embedding and email adapters.** This intent adds `billing` to `REAL_ADAPTERS`
  only. `ADAPTER_MODE=real` still will not boot afterwards, because `llm`, `embedding` and
  `email` remain missing. That is the separate go-live-adapters intent.
- **Dunning emails and payment-recovery campaigns** beyond the entitlement consequence of
  `invoice.payment_failed`.

## Notes

**Decisions taken during capture (2026-11-11):**

1. **Full tier scope, FR-48 through FR-52**, rather than an entitlement spine alone. The
   entitlement mechanism is worthless until something reads it, and three of the four
   features are small once it exists.
2. **Real Stripe adapter plus an app-layer webhook receiver**, proven against the existing
   `scripted_network.py` harness rather than a live account. Rationale: the valuable and
   risky part is state-sync correctness — idempotency, ordering, signature verification —
   and all of it is testable without Stripe. Live keys stay a config flip, consistent with
   how `ADAPTER_MODE` already works. CI has no secrets (`ci.yml` sets only test-local
   values) and could not run live tests anyway.
3. **Webhook-driven, not poll-driven.** A pull-based `fetch_subscription()` on a Celery beat
   was considered and rejected: it is simpler and needs no public URL, but leaves
   entitlement stale between polls, which is wrong on a hot save path.
4. **Prioritised toward the end-to-end paid path** over breadth of Pro features, per PRD
   §4.11's stated purpose of validating monetization at MVP.

**Open, to settle during decomposition and design:**

- **The entitlement read path.** Does `personalization` call an `identity` service on every
  check, or is a denormalized flag carried closer to the caller? AD-3 permits only
  by-value crossing, and the save gate is hot. A cached read needs an invalidation story
  that the webhook drives.
- **The per-day quiet-hours shape.** Widen `NotificationPreference` to seven column pairs,
  or add a child table? The existing `notification_preference_quiet_hours_pair_ck`
  constraint assumes exactly one pair, and `domain.quiet_hours.QuietHours` is a single
  frozen value — both need a decision before either moves.
- **Whether FR-52 export belongs behind the paywall at all.** Its own text concedes the
  tension: *"export is free for GDPR compliance but UX is in Pro settings for non-EU
  users."* Article 20 is a right, not a feature. Gating the only export affordance behind
  $4.99/month is a legal question before it is a product one, and it should be answered
  deliberately rather than inherited from a pricing bullet.
- **Grace on `invoice.payment_failed`.** Does entitlement drop on the first failure, or
  after a dunning window? This decides whether `Subscription.status` needs a `past_due`
  state distinct from `cancelled`.
- **What happens to over-cap data when a subscription lapses.** A Pro user with 400 saves,
  12 collections and 3 connected providers downgrades. Nothing is deleted (see Constraints),
  but which of it stays readable, and which becomes read-only, needs stating.

**Carried forward, unresolved:** `ADAPTER_MODE=real` remains unbootable after this intent
(`llm`, `embedding`, `email`); the LLM ports `get_llm_port` and `get_embedding_port` are
still called by no product code, so FR-14's "hybrid" extraction remains parser-only; there
is still no deploy pipeline beyond `ci.yml` and no observability dependency anywhere in
`backend/`; and the open items inherited from `trust-loop` — OQ-5, the beachhead city, the
FR-13 launch floor, the AD-17/AD-21 reinstated-conflict defect, and the editorially-released
event that still cannot reach a digest.
