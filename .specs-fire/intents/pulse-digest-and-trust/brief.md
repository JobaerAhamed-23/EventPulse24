---
id: pulse-digest-and-trust
title: Pulse Digest, Relevance Pulse & the Trust Surfaces
status: in_progress
created: 2026-10-30
---

# Intent: Pulse Digest, Relevance Pulse & the Trust Surfaces

## Goal

Replace the placeholder home with the real thing: a composed, persisted, 3-card **Pulse Digest** at `/`, and the **Detail Screen** at `/events/:id` that explains it.

This is the intent every previous one deferred to. It delivers FR-5 (digest composition), FR-6 (card density), FR-8 (empty state), FR-19 (personal events in the digest), FR-21 (Why-this Tags), FR-22 (Confidence Pulse), FR-23 (Source Badge) and FR-24 (the "Why this?" Detail Screen) — and it builds the **Relevance Pulse**, the per-user half of AD-10 whose absence is the reason `apps/personalization/` has no composition code and `frontend/app/page.tsx` says "Your Pulse is being prepared."

It is the first intent in which a signed-in user is told *why* they are being shown something.

## Users

- **The returning signed-in user** (UJ-1), who opens `/` and gets three cards — one that matters most, one nearby, one they would not have found — and closes the app.
- **The user who doubts a card** (UJ-4), who taps it, reads the why-this breakdown on the Detail Screen, and either accepts it or stops trusting the product. This surface is the trust contract.
- **The user with a quiet week** (FR-8), who is told the truth — "Nothing on the pulse today. The calendar is yours." — instead of being shown filler.
- **The user who just finished onboarding** (UJ-3 step 6), who lands on `/` and sees a real digest rather than a placeholder.

## Problem

Four intents have built everything the digest needs and nothing of the digest itself:

- `frontend/app/page.tsx` is an explicit placeholder: "The Pulse Digest isn't ready yet." Its own docstring names this intent as the one that replaces it.
- `apps/personalization/` owns `PULSE_DIGEST` and `DIGEST_COMPOSITION` in AD-16's table and has neither model, no composition service, and no ranking code. `backend/domain/` has `event_fit.py`, `conflict.py`, `confidence.py` — and **no `ranking.py`**, although AD-2 names ranking as belonging there.
- **Interests are stored and never read.** `onboarding-state-and-interests` built the `Interest` rows and said in as many words that the Pulse Digest intent is the first to read them. Nothing has.
- **The Relevance Pulse does not exist.** AD-10 names two kinds of explanation; `ingestion` built the session-free one (Event Fit), and the per-user one — the one that goes on an authenticated card, the Detail Screen and the email — was deferred here. `tests/architecture/test_event_fit_separation.py` already asserts that `personalization` cannot borrow the Event Fit, so the Relevance Pulse must be built from its own inputs or there is nothing legal to put on a card.
- **FR-19 was deferred wholesale.** The `personal-events-and-saved-catalog` brief refused to build a partial digest projection, on the grounds that it would become a second, divergent implementation of the card. That card is this intent's work.

## Success Criteria

### Composition (FR-5, AD-10, AD-11, AD-16)

- A **`DIGEST_COMPOSITION`** row per `(user, event, composition)` persists the Relevance Pulse score, its bucket, the Why-this Tags and the Source Badge inputs. It is **immutable** and declares a retention category (AD-15).
- **Exactly 3 cards** on a standard day, in A-2's fixed slots, with **no duplicate `event_id`** across them:
  1. **must-know** — an eligible `PERSONAL_EVENT` within 48 hours; otherwise the highest-scoring eligible public event;
  2. **nearby** — the highest-scoring eligible public event in the user's city;
  3. **serendipity** — scored with an **inverted** preference term, so it is structurally the card the user's own signals would not have picked.
- Composition runs **in the worker, never in a request** (AD-11), is **deterministic per `(user, local_date)`**, and re-running it for the same user and local date returns the **same persisted composition** rather than composing again (FR-30).
- The digest read path is **a read of persisted rows**. Nothing is scored, ranked or explained at render time (AD-10). The <500ms p95 budget is a consequence of that, not of a cache.
- Composition assembles `catalog` facts and `personal` signals **in the application layer**. No query joins the two schemas, because AD-3 makes it impossible to write one.
- **Eligibility gates are reused, not restated:** `extraction_confidence` ≥ `EXTRACTION_CONFIDENCE_PUBLISH`, `tz_inference_confidence` ≥ `TZ_INFERENCE_CONFIDENCE_DIGEST`, published and non-superseded, upcoming — the constants that already exist in `shared/constants.py`.

### The ranking, built honestly (FR-5, FR-22, AD-2)

The published formulas name four inputs this codebase does not have. **Each is named, not faked** — the same discipline Event Fit used when it refused to invent a "Free" tag:

| Published input | State today | This intent |
| --- | --- | --- |
| `source_reliability` | FR-16 unbuilt; `Source` has no score field | **Omitted from the formula**, not pinned to a prior. Added when FR-16 ships. |
| `normalized_popularity` | No engagement, attendance or save-count signal exists | **Omitted.** Slot 3's anti-popularity bias is expressed as an inverted *preference* term instead. |
| `geographic_distance_factor` | `Venue` has `city` + `country_code`, **no coordinates** — haversine is not computable | **City equality**, as a band, not a distance. |
| category tags / Jaccard < 0.3 | `Event` has no category field | **Interest-chip overlap** from the 10 fixed chips, which is what the user actually told us. |

- Ranking is **one pure module, `backend/domain/ranking.py`**, stdlib-only and importable with Django uninstalled (AD-2), with `now` an explicit parameter and no clock read — matching `domain/event_fit.py`.
- The score is **a documented formula with the omitted terms absent from it**, never a published formula with inert weights. A user reading the code can compute any card's score from the inputs (FR-22's actual promise).
- **Bucketing is FR-22's, verbatim:** ≥0.85 → 5, ≥0.65 → 4, ≥0.45 → 3, ≥0.25 → 2, else 1. **No interpolation**; on an exact boundary the **lower** bucket wins (0.850 → 4 dots).
- **No-flicker rule:** once a bucket is assigned for an event on a user's local calendar day, it holds for that day unless the raw score moves by **≥0.10** within the same day. Hysteresis resets across days; no bucket is persisted between days. *(EXPERIENCE.md's ≥0.10 governs; the deprecated ranking-transparency mockup's "±0.02" is stale.)*
- **No LLM and no embedding call anywhere in this intent.** The ranking is arithmetic.

### The card (FR-6, FR-19, FR-21, FR-23, AD-10)

- Every card shows **event name, user-local time, location, up to 3 Why-this Tags, a 1–5 Confidence Pulse, and a Source Badge** — all six, at every density mode. The locked anti-pattern is explicit: **adaptive density never hides a trust signal.**
- **Why-this Tags** are up to 3 human-readable keywords from the persisted composition (`nearby, tonight, music` — never `loc_score=0.92`), **identical on the card and the Detail Screen**, rendered in `type.scale.microtag` (13px italic). Slot 3's tag reads **`discovery`** or **`new-to-you`**, never a category name.
- **Source Badge**: five variants, each with a **visible inline text label**, always inline in the card's trust-signal row, **never behind a tap**. `official_site` renders in `color.accent.terracotta` — one of the four sanctioned terracotta uses.
- **Personal events (FR-19)** carry the `color.warm.personal` stripe **always paired with the visible text label "Personal"**, and public events with "Public event". Color is never the sole carrier of meaning. A user can **opt out** of personal events appearing in the digest.
- The **conflict indicator** (FR-58, already built) renders on a card whose event is in a `CONFLICT_PAIR`: a **6px** filled `color.warn.amber` circle, top-right, never red, and it never collapses at any density.
- Card headlines are **8 words or fewer**; the card is `color.surface.elevated`, `radius.card` 12px, 24px padding, **no shadow on hover, ever**.

### The Detail Screen (FR-24, AD-10)

- `/events/:id` shows the **12 locked elements in order**, with the **why-this breakdown** reading from the **most recent `DIGEST_COMPOSITION` for that `(user, event)` pair**.
- **It renders no explanation rather than computing one.** An event never composed for this user shows no breakdown — this is AD-10's durability rule and the single most important test in the intent.
- **Neighbor count** honors k-anonymity: ≥5 qualifying users, rendered as **bucketed prose** ("A few / Some / Many / A lot of neighbors saved this"), **silently suppressed below 5** with no "0 neighbors" row, and identical for Free and Pro. *(Exact counts are never exposed — the mockup's "12 neighbors" and §12's own example line both violate this; the Neighbor Count Privacy rule governs.)*
- Reviews and community-corroboration counts **do not ship** (ASSUM-6/7, deferred).

### The empty state (FR-8)

- Never blank. One `Card.PulseDigest` variant reading **"Nothing on the pulse today. The calendar is yours."**, with a `Text.Meta` line **"No qualifying events in {city}."** below it.
- **No CTA, no carousel, no upsell** — one low-weight `Text.Meta` "Suggest an event" link and nothing more. *(EXPERIENCE.md §5 is marked canonical and is stricter than both DESIGN.md and the as-built mockup; the mockup's terracotta primary + ghost button pair is a mockup bug.)*
- Triggered when there are **no qualifying public events and no eligible personal events** (FR-5 widens FR-8's trigger).

### Proof — tests that can fail

- The 3-card count, the slot assignment, and no duplicate `event_id`.
- Determinism: composing twice for the same `(user, local_date)` yields the identical persisted row set.
- Every FR-22 bucket boundary **at the exact value**, including 0.850 → 4, and the ≥0.10 hysteresis both crossing and not crossing.
- The Detail Screen rendering **no** breakdown for an event with no composition — not an empty one, not a recomputed one.
- Neighbor count suppressed at 4 users and bucketed at 5, 10, 25 and 100.
- `personalization` still cannot import `apps.ingestion.event_fit` (the existing contract stays green), and the Relevance Pulse is **never** filled from an Event Fit.
- Composition touching both schemas does so in the application layer; no cross-schema query exists.
- The empty state firing on both halves of its trigger.
- Personal-event opt-out actually removing the card.
- CI stays green with the coverage gates, the `import-linter` contracts and the `axe-core` zero-serious-violations gate on the digest and detail surfaces.

## Constraints

- **Builds on four completed intents.** `catalog_read.py` is the only legal path to public events; `Interest`, `DigestPreference`, `PersonalEvent`, `SavedEvent` and `ConflictPair` all exist; the session seam is real; `domain/conflict.py` and `domain/event_fit.py` are the pattern for `domain/ranking.py`.
- **Ownership (AD-16):** `personalization` owns `PULSE_DIGEST` and `DIGEST_COMPOSITION` and is the only writer. `ingestion` keeps Event Fit. Nothing new is written to `catalog`.
- **AD-10 is the spine of this intent.** Both explanations persist; neither is recomputed at render; **they are never substituted for one another**. The existing package-level import wall stays.
- **AD-3:** no FK and no join across the wall; composition is application-layer; no transaction spans both schemas.
- **AD-11 / AD-1:** composition is worker work. The digest latency budget is the stated reason AD-1 separates runtimes at all.
- **`beat_schedule` stays exactly one 60s tick.** Composition is due-time work dispatched from it, like calendar polling and Event Fit refresh already are.
- **AD-19:** the new endpoints reach the frontend through the generated contract, never hand-written.
- **AD-15:** `DIGEST_COMPOSITION` declares a retention category or `manage.py check` fails.
- **AD-9:** Why-this Tags are derived from persisted facts, never raw passthrough of scraped text.
- **The UX is implemented, not redesigned**, and **the spines win over the mockups** (EXPERIENCE.md's own precedence rule). Binding: `pulse-digest-desktop.html`, `pulse-digest-empty-state-desktop.html`, `event-detail-desktop.html`, `conflict-indicator-card-state-desktop.html`, plus `DESIGN.md` and `EXPERIENCE.md`. There is no component library.
- **Known mockup bugs, not to be reproduced:** the verified badge rendered green instead of terracotta; the 10px conflict dot (6px is locked); the violet `#B59CE8` and amber-tinted buttons, which use stripe-reserved colors on interactive surfaces; `radius.card` 14px and 32px padding; the empty state's button pair. The mobile digest mockup is stale throughout (pre-A-8 tab bar, inverted headline) and is not binding.
- **Why-this tag separator is undecided** in the sources — DESIGN.md says middle dots, EXPERIENCE.md §3 says commas, and the two mockups disagree. The screen-reader rule ("announced as comma-separated text") settles the accessible reading; the visual separator is a plan-time decision to be recorded.
- Binding sources: `ARCHITECTURE-SPINE.md` (AD-1, AD-2, AD-3, AD-5, AD-6, AD-7, AD-9, AD-10, AD-11, AD-13, AD-15, AD-16, AD-19, AD-21), `prd.md` §2.3 UJ-1/UJ-3/UJ-4, §4.2, §4.5, §4.6, §4.9, §11.1, `ux-EventPulse24-2026-08-23/`, `.specs-fire/standards/`.

## Notes

**Out of scope:**

- **Digest delivery (FR-7's send, FR-10 Pulse Ping, FR-9/FR-11 reminders, FR-12 quiet hours).** `ScheduledSend`, AD-7's due-index sweep, the `user_id · digest · local_date` send key and AD-20's bulk stream with RFC 8058 unsubscribe are **the next intent**, which is where the whole delivery machine belongs together. `DigestPreference` is already stored and this intent does not act on it as a send time.
- **FR-25 "Less like this" and the `PREFERENCE_GRAPH`.** Dismissal as a negative signal, embedding-cosine ≥0.7 clustering, the 3-dismissal mute prompt, the 60/180-day decay and the rage-dismiss guard are a feedback intent. The embedding adapter is still a deterministic fake, so clustering has no real input yet.
- **FR-16 source reliability, event categories, venue coordinates, popularity.** Named above as omitted ranking terms. Each is added to the formula by the intent that builds it.
- **FR-32 Timeline, FR-33 `/conflicts`, FR-26–FR-28 public pages, `/browse`.** `/browse` additionally has **no FR at all** and reuses the digest card vocabulary without a `DIGEST_COMPOSITION` to explain from — it needs a decision before it can be built legally under AD-10.
- **Adaptive expansion to 5 or 7 cards** (≥10 saves/30d). ASSUM-5 is open; the digest ships at a fixed 3.
- **Settings → Privacy → "Ranking algorithm version"** (FR-22's transparency surface). The formula is locked in code and in this brief; the settings screen that displays it is the settings intent's.
- **Pro tier, `SUBSCRIPTION`, the sidebar Pro upsell card.** Everyone is Free.

**Still open:**

- **ADR-0007 does not exist.** FR-5 gates the switch from cold-start to personalized ranking weights on a signal threshold that is defined nowhere in the planning artifacts. This intent ships **the cold-start path only**, and that is a statement about the sources, not a shortcut.
- **Open Q #13** — personal events in the digest are opt-**out** by assumption, "pending confirmation", owner Product. Built as opt-out; flagged.
- **Open Q #5** — whether the digest should be 3 fixed slots or dynamically ranked is itself still open post-MVP. A-2's slots are built; the question is recorded.
- **No retention window is stated anywhere for `DIGEST_COMPOSITION`**, yet AD-15 requires a category and AD-10's "most recent composition for that `(user, event)` pair" promise depends on compositions outliving today's digest. A category must be chosen in the design doc and the gap named.
- **No user home city is stored.** The anonymous preview reads a geo header; a signed-in user has no persisted city, and the digest needs one. Where it comes from — onboarding, the geo header at composition time, or a new field — is a design-doc decision.
- **ASSUM-5** (adaptive count 5 vs 7), **ASSUM-8** (live-region debounce ms), **ASSUM-9** (Source Badge roster frozen at 5).

**Source conflicts — architecture governs (decision taken at capture, 2026-10-30):**

1. **UJ-3 puts a "Confidence Pulse" on the anonymous preview.** AD-10 and AD-12 forbid it; that surface shows **Event Fit**, labelled as Event Fit. Already implemented that way in `onboarding-and-account`. *(Spine OQ-3 is marked "Closed → PRD amendment"; the amendment was never made.)*
2. **PRD Glossary says the Confidence Pulse is "persisted on the Event record."** AD-3 makes that impossible — it is per-user data and `Event` is in `catalog`. It persists on `DIGEST_COMPOSITION` in `personal`.
3. **AD-20 puts the digest on the bulk stream; PRD §10.1 and FR-11 call it transactional.** AD-20 governs. Not exercised in this intent, but recorded for the delivery intent.
4. **UJ-1 tags the slot-3 card `novel`**; FR-25 and the Glossary require `discovery` or `new-to-you`. The Glossary governs.
5. **UJ-4 shows "👥 12 neighbors"**; FR-24 buckets and bans exact counts. FR-24 governs, and the emoji prefix is removed under the emoji-as-CTA ban.
6. **The Capability Map's FR-5–8 row omits AD-7 and AD-20**, though both name FR-5–8 in their own Binds lines. Treated as governed by AD-3, AD-10, AD-11, AD-7 and AD-20.
7. **FR-14 still mandates multi-provider LLM fallback**; AD-8 is multi-model within one provider and says it "requires the FR-14 amendment". Not made. Irrelevant here (no LLM call) but still owed.
8. **§10.3's $0.50/MAU ceiling is stale**; FR-29 and ASSUMPTION-5 supersede it with the $1.25 TCO.

**PRD amendments owed** (OQ-6, now overdue from three intents): `SavedEvent`, `ConflictPair`, `ExtractedRecord`, `CalendarConnection`, `EventFit` — and now **`RelevancePulse`**, **`PulseDigest`** and **`DigestComposition`** — must be added to PRD §3 Glossary. The spine's own rule is that new nouns enter the Glossary first.

**Decisions taken during capture (2026-10-30):**

1. **Honest reduced ranking.** A-2's three-slot shape is kept; the four unavailable inputs are omitted from the formula and named, not pinned to constants that would make a published formula partly inert.
2. **Compose and display only.** The real `/` home and `/events/:id` ship; every send — digest email, Pulse Ping, reminders, quiet hours — is the next intent.
3. **Card trust signals plus the Detail Screen.** FR-21–FR-24 ship; FR-25 and the `PREFERENCE_GRAPH` defer to a feedback intent, because AD-10's durability rule is what the Detail Screen exists to prove.
4. **Conflicts recorded, architecture wins.** Work proceeds with the amendment backlog explicit rather than silent.
