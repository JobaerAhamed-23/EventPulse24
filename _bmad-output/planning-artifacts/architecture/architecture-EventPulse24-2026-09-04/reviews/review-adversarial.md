---
name: 'review-adversarial'
type: architecture-review
reviews: architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md
method: 'adversarial pair construction — two units, both AD-compliant, incompatible together'
created: '2026-09-04'
---

# Adversarial Review — ARCHITECTURE-SPINE.md

**Method:** for each hole below, two concrete units one level down (a feature's command/query, a module's owned entity) are named. Each is checked against every AD it binds to and shown compliant *to the letter*. Then the pair is run together and the incompatibility is shown. A new or tightened AD is proposed to close it.

**Verdict up front:** the spine's biggest structural gap is asymmetry, not vagueness — AD-4 gives `catalog` a named sole writer and a named merge discipline; nothing in `personal` schema gets the same treatment, even though `personal` holds nine of the thirteen ERD entities and the two most failure-prone lifecycles in the product (`SCHEDULED_SEND`, and anything downstream of a postponement). Every top-severity hole below traces back to that asymmetry.

---

## HOLE 1 (CRITICAL) — SCHEDULED_SEND has no reschedule owner, and the sweep can race a postponement

**Units:**
- **Unit A** — `delivery`'s due-index sweep worker (`worker/sweep-due-sends.ts`), dispatching reminders and digests per AD-7.
- **Unit B** — `ingestion`'s state-sync path that detects a source postponement (FR-53) and must trigger the FR-54 consequence: *"Reminders are re-scheduled to the new time."*

**Unit A compliance:** Sweeps `(due_at, status)` at ≤60s intervals, uses the idempotency key `user_id + event_id + slot + scheduled_for`, dispatch is at-least-once with dedupe at the send boundary. Textbook AD-7.

**Unit B compliance:** `ingestion` is the sole writer of `catalog` (AD-4), detects the postponement, writes the new `start_time_utc` to `EVENT_RECORD`/`EVENT_CLUSTER` and appends to `state_history` — exactly what FR-15 and FR-53 require. It never writes outside `catalog` (AD-9's "a source can never cause a write outside `catalog`").

**The incompatibility:** FR-54 requires that reminders for the postponed event move to the new time. But AD-4 forbids `ingestion` from writing `SCHEDULED_SEND` (that's `personal` schema), and no AD names who *is* allowed to write it, or how the postponement signal reaches them. Two equally "compliant" builders diverge:

- Builder 1 has `ingestion`'s postpone command call directly into `delivery`'s app interface synchronously (permitted by AD-2 — cross-module calls go through the target's `app` interface). This creates a hard, in-process coupling between a catalog write and a personal-schema write with no defined ordering guarantee against the sweep that might, in the same instant, have already run `UPDATE scheduled_send SET status='claimed' WHERE ... RETURNING *` on the *old* `due_at` for that exact row.
- Builder 2 has `delivery` poll `catalog.state_history` independently on its own cadence and reschedule reactively. This adds unbounded propagation lag between "ingestion knows" and "delivery acts," during which the sweep can and will dispatch a stale-time reminder — the AD-7 idempotency key is keyed by `scheduled_for`, so once `scheduled_for` changes, the *old* key's dedupe record does nothing to stop the *old-time* send that already left the claim boundary.

Neither builder is wrong per the ADs as written. The spine specifies dispatch (AD-7) and specifies the sole catalog writer (AD-4) but never specifies **how a catalog-side fact becomes a personal-side mutation**, and never specifies what happens to a `SCHEDULED_SEND` row that is mid-flight (claimed, not yet sent) when a reschedule arrives. FR-54's own consequence — "Reminders are re-scheduled to the new time" — has no implementation path that both modules would independently arrive at.

**Proposed AD-14 — Postponement propagates by outbox, and "claimed" is a terminal lock the reschedule path must respect.**
- `ingestion`'s postponement command writes a durable outbox row (`event_state_change{event_cluster_id, new_start_utc, kind, version}`) in the **same transaction** as its `catalog` write (same Postgres transaction, different schema — permitted; AD-3 bans cross-schema *joins*, not cross-schema transactions).
- `delivery` owns exactly one consumer, `apply-event-reschedule.ts`, the **only** legitimate writer of `SCHEDULED_SEND.due_at`/`.status` for rows still `status='pending'`.
- A `SCHEDULED_SEND` row the sweep has already moved to `status='claimed'` is never touched by the reschedule path — the in-flight send is allowed to complete (and, per FR-54, the user gets the one-time state-change notification separately), and a **new** `SCHEDULED_SEND` row is created for the corrected time instead of mutating the claimed one.
- This closes the race with a CAS discipline (`WHERE status='pending'`) instead of leaving two builders to invent two different propagation mechanisms.

---

## HOLE 2 (HIGH) — REMINDER_SLOT has no assigned sole writer; AD-4's discipline never crossed the schema wall

**Units:**
- **Unit A** — `personalization`'s `create-personal-event.ts` (FR-18/FR-20): on creating a Personal Event, must also create the default Reminder Plan (1d + 1hr).
- **Unit B** — `delivery`'s `save-reminder-plan.ts` (FR-9): the canonical picker command — "up to 4 slots... the user can edit a saved Reminder Plan."

**Unit A compliance:** FR-18–20 is capability-mapped to `personalization`. FR-20's default-reminder consequence is part of personal-event creation, which `personalization` owns end to end. Writing `REMINDER_SLOT` inline, in the same command, is the obvious reading of "personalization owns FR-18-20."

**Unit B compliance:** FR-9 is capability-mapped to `delivery`/`worker`. It "owns its validation and its audit-log write" per AD-5 — a named application command, exactly as required.

**The incompatibility:** AD-4 gives `catalog` a named sole writer ("the `ingestion` module is the sole writer of `catalog` event records"). No equivalent sentence exists for `personal`-schema entities. `REMINDER_SLOT` is reachable from at least three FRs mapped to two different modules — FR-9 (`delivery`), FR-20 (`personalization`, default plan at personal-event creation), and FR-24 (`personalization`, the Detail Screen's reminder picker). AD-5 only regulates *how* a write happens (a named command with validation + audit) — it says nothing about *which module* may own a given entity's writes outside `catalog`. So Unit A and Unit B are each individually AD-5-compliant, and together they are two independently-invented mutation paths into the same table, with no guarantee they apply the same validation (Unit B's picker presumably also creates the matching `SCHEDULED_SEND` rows and respects Quiet Hours at creation time; nothing forces Unit A's inline default-reminder write to do the same). This is precisely the failure mode AD-5's own "Prevents" clause names — "two builders inventing two mutation paths for the same entity" — and AD-5 as written does not close it for anything outside `catalog`.

**Proposed AD-15 — Every `personal`-schema entity gets AD-4's treatment: one named owning module per entity, stated in the Capability Map, not inferred from FR-to-module mapping.**
- Extend AD-4's pattern schema-wide. State explicitly, per entity: `REMINDER_SLOT` and `SCHEDULED_SEND` → sole writer `delivery`. `PERSONAL_EVENT` → sole writer `personalization`. `PULSE_DIGEST`/`DIGEST_CARD` → sole writer `personalization`. `SUBSCRIPTION` → sole writer `identity`. `USER` → sole writer `identity`.
- Concretely for this hole: `personalization`'s FR-20 default-reminder step and FR-24's Detail Screen picker both call `delivery.save-reminder-plan` through `delivery`'s published `app` interface (AD-2) rather than writing `REMINDER_SLOT` themselves.

---

## HOLE 3 (HIGH) — Preference Graph is load-bearing and entirely absent from the ERD; it collides with the declared `INTEREST` entity

**Units:**
- **Unit A** — `identity`'s onboarding command (FR-1): writes `USER ||--o{ INTEREST` rows from the 3 interest chips the user explicitly picked (or skipped).
- **Unit B** — `personalization`'s dismissal recorder (FR-25): "a dismissal is recorded as a negative signal in the Preference Graph," with a 60-day decay and 180-day expiry, feeding `preference_graph_match` — 40% of the Confidence Pulse formula (FR-22) and a direct input to FR-5's personalized-ranking slots.

**Unit A compliance:** Onboarding is ≤3 skippable steps (FR-1); `INTEREST` is the only entity the ERD offers for "declares." Writing to it is the only compliant home available.

**Unit B compliance:** FR-25 names the Preference Graph as the write target; FR-5/FR-22 name it as a read input. `personalization` owns both FRs per the capability map.

**The incompatibility:** the Glossary defines **Preference Graph** as a distinct concept from **Interest** — "Per-user behavior-derived data structure (dwell, swipes, dismissals, saves)... Built incrementally," explicitly separate from the user-declared onboarding chips. Yet the Core Entities ERD has no `PREFERENCE_SIGNAL`/`PREFERENCE_GRAPH` entity at all — only `INTEREST`. A builder implementing FR-25 has two AD-compliant-looking choices, both bad: (a) reuse `INTEREST` and add decayed behavioral-weight columns to it, which now makes `identity`'s explicit-choice write path (user-editable in Settings, no decay) and `personalization`'s algorithmic-decay write path (FR-25's 60/180-day half-life) two owners of one row with contradictory invariants — exactly the "conflicting state-mutation paths... with different invariants" failure the review brief calls out by name; or (b) invent an unmodeled table with no schema placement, no capability-map entry, and no AD governing it. Either way, the spine is silent on the one entity that FR-5/FR-22/FR-25 all depend on.

**Proposed AD-16 — Preference Graph is a first-class, append-only, versioned signal log, structurally distinct from user-declared Interest.**
- Add `PREFERENCE_SIGNAL` to the ERD: schema `personal`, sole writer `personalization`, append-only (dwell/swipe/dismiss/save events with a decay-eligible timestamp), read by FR-5/FR-22's `preference_graph_match` as an aggregate over this log — never by mutating `INTEREST`.
- `INTEREST` remains `identity`-owned, user-editable, and is a **cold-start seed** input only; once `PREFERENCE_SIGNAL` exists for a category, `INTEREST` is not algorithmically rewritten.

---

## HOLE 4 (HIGH) — WHY_THIS_REASON's key is ambiguous: per-composition-instance, or per-(user, event) durable?

**Units:**
- **Unit A** — `personalization`'s `compose-digest.ts` (FR-5): recomposes the Pulse Digest daily, scoring each candidate event and producing a `DIGEST_CARD` plus its `WHY_THIS_REASON`.
- **Unit B** — `personalization`'s `get-event-detail.ts` (FR-24): renders the Detail Screen's "Why-this breakdown" for an event the user saved days ago and that is no longer in *today's* digest.

**Unit A compliance:** AD-10 — "Why-this reasons, confidence, and source attribution are written alongside the recommendation that produced them." The recommendation here is *today's* digest composition; writing a fresh `WHY_THIS_REASON` tied to today's `DIGEST_CARD` is a direct reading of AD-10.

**Unit B compliance:** FR-24 — "the Detail Screen always shows the Why-this breakdown" — and FR-21 — "Same tags appear on the Pulse Card and on the Detail Screen." Reading back whatever `WHY_THIS_REASON` exists for the event satisfies AD-10's "read back verbatim... never recomputed at render time."

**The incompatibility:** the ERD gives `WHY_THIS_REASON` **two parents** — `EVENT_CLUSTER ||--o{ WHY_THIS_REASON : explained_by` and `DIGEST_CARD ||--o{ WHY_THIS_REASON : carries` — without saying which relationship is the identity and which is provenance. If Unit A's reading is "one new row per digest composition" (plausible, since a `Pulse Card` is explicitly "a *projection*... at a specific composition time, not a separate entity" per the Glossary — the same logic could extend to its reason), then Unit B, querying for "the" `WHY_THIS_REASON` for an event the user saved on day 1 and is viewing on day 10, has no current `DIGEST_CARD` to key off — the reason may not exist, may be stale, or (if multiple digests included the event on different days with different scores) may be ambiguous among several rows. AD-10's "read back verbatim by card, detail screen, and email" guarantee silently breaks the moment the originating digest composition is no longer "today's."

**Proposed AD-17 — WHY_THIS_REASON is durably keyed by `(user_id, event_cluster_id)`; DIGEST_CARD holds a pointer, never a copy.**
- Exactly one `WHY_THIS_REASON` row exists per `(user_id, event_cluster_id)`. Each digest composition **updates it in place** (new score, new tags, new timestamp) rather than inserting a new row.
- `DIGEST_CARD` stores a foreign value pointing at this row's id (not a duplicate of its contents). The Detail Screen and reminder/state-change emails all read the same row, so "read back verbatim" holds regardless of how long ago the event was last in a digest.

---

## HOLE 5 (MEDIUM-HIGH) — "Confidence" is one Consistency Convention covering four structurally unrelated scores

**Units:**
- **Unit A** — `ingestion`'s extraction command, writing `EVENT_RECORD.extraction_confidence` (FR-14: LLM decode-time output, quarantine floor 0.7, auto-reject floor 0.5).
- **Unit B** — `personalization`'s digest composition, writing the Confidence Pulse `relevance_score` (FR-22: a weighted sum of four components — `preference_graph_match`, `source_reliability`, `recency_fit`, `novelty_vs_exploration` — bucketed at 0.25/0.45/0.65/0.85 with a ±0.02 hysteresis band).

**Both comply, to the letter, with the Consistency Convention:** *"Confidence — `numeric(3,2)` in `[0,1]`. Presentation thresholds live in one shared module, never inline."* Both are `numeric(3,2)` in `[0,1]`. Both intend their thresholds to live in "one shared module."

**The incompatibility:** the PRD independently defines **four** confidence-shaped fields with different owners, different inputs, and different recompute triggers: `extraction_confidence` (Unit A, `ingestion`, immutable once written), `tz_inference_confidence` (FR-60, `ingestion`, thresholds at 0.7/0.9, different meaning again — timezone resolvability, not relevance), `relevance_score`/Confidence Pulse (Unit B, `personalization`, hysteresis-banded, recomputed every composition), and Source Reliability Score (FR-16, Bayesian posterior mean, thresholds at 0.3/0.32, min-N gated at 30 observations). The convention's singular phrasing — "Confidence... thresholds live in **one** shared module" — reads as one Value Object with one bucket table. A builder who takes that literally either (a) collides two unrelated threshold sets in one table (0.7 means "quarantine" for extraction but "flag for editorial" for timezone — same number, opposite severity, same shared module), or (b) forks a second "shared" module the moment they notice the collision, silently reintroducing the "never inline" rule's exact failure mode it exists to prevent.

**Proposed AD-18 — "Confidence" is not one Value Object. Every confidence-typed field is named and thresholded independently.**
- `shared/confidence-thresholds.ts` exports one named export per field — `extractionConfidence`, `tzInferenceConfidence`, `relevanceScore`, `sourceReliability` — each documenting owning module, inputs, and recompute cadence in its own comment block. No module may reuse another field's bucket boundaries by numeric coincidence.

---

## HOLE 6 (MEDIUM-HIGH) — EventReport / the editorial review queue is a real MVP entity, absent from the ERD, and needs a cross-module atomic write nothing specifies

**Units:**
- **Unit A** — `personalization`'s "Report this event" command (FR-59), on the Detail Screen it owns (FR-21–25 → `personalization`).
- **Unit B** — `ingestion`'s editorial-queue admission logic (FR-57), which the spine's own Deferred table assigns: *"[editorial review] reads `catalog` and writes through `ingestion` commands like any other client."*

**Unit A compliance:** the Detail Screen, its CTAs, and its rate limiting (5/day) are all `personalization`'s territory per the capability map.

**Unit B compliance:** the Deferred table is explicit that editorial-queue writes go through `ingestion`.

**The incompatibility:** FR-59 requires *one user tap* to durably do two things: create the `EventReport` record (User, Event, category, timestamp — retained 24 months) **and** enqueue the event in the FR-57 queue with priority `user_reported`. Neither the ERD nor any AD names which module owns `EventReport`, which schema it lives in, or how the two writes stay atomic. A builder following Unit A's ownership naturally writes `EventReport` into `personal` (it's about a user's action) and then calls into `ingestion`'s queue-admission command — but if that second call fails after the first commits, the user sees "Thanks — we'll review this" for a report that never reached the queue, and no AD says who is responsible for the resulting inconsistency. A different builder, following Unit B's "writes through ingestion" framing literally, might have `ingestion` write `EventReport` itself directly into a catalog-adjacent table — which works for queue admission but now needs a value-reference to `personal.User.id`, and duplicates the report-record concept `personalization`'s Detail Screen already assumed it owned.

**Proposed AD-19 — `EVENT_REPORT` and `REVIEW_QUEUE_ENTRY` are named ERD entities, owned by `ingestion`, written by one command.**
- Add both to the Core Entities ERD, schema `catalog` (or a dedicated `review` schema `ingestion` alone writes to), sole writer `ingestion`.
- `file-user-report.ts` is `ingestion`'s single command: it validates the 5/day rate limit (reading `personal.User` and prior `EVENT_REPORT` rows as data, not via a join — AD-3-compliant), writes the report row and the queue-admission row in one transaction, and is the **only** entry point `personalization`'s Detail Screen calls (through `ingestion`'s published `app` interface, per AD-2) — `personalization` never writes its own copy.

---

## HOLE 7 (MEDIUM) — the Detail Screen is one named UX surface but two owners, and AD-12's session-independence guarantee depends on which one wins

**Units:**
- **Unit A** — `catalog`+`web`'s public Event page (FR-26–28, capability-mapped to `catalog`/`web`, governed by AD-12): statically generated/ISR'd, Schema.org JSON-LD, no session dependency.
- **Unit B** — `personalization`+`web`'s Detail Screen (FR-21–25, capability-mapped to `personalization`): server-renders "similar events attended," neighbor count, and the Why-this breakdown for an authenticated in-app user.

**Unit A compliance:** AD-12 to the letter — "Public event pages render fully without a session and are statically generated or ISR'd... Personalized content on a public page arrives only via a separate client-side request."

**Unit B compliance:** the Glossary's Detail Screen definition is fully server-rendered by design for the authenticated case — nothing in AD-12 constrains an *authenticated, in-app* surface; it constrains the *public* one.

**The incompatibility:** the Glossary names **one** "Detail Screen" ("The expanded view of a Pulse Card. Shows:...") and FR-26 says the public Event URL itself "includes a 'Save to Pulse' CTA," while UJ-5's share flow has a friend land on "the event detail" via the public link. The naming convention elsewhere insists on exactly one component per named UX surface (`Surface.{RouteName}`). If Unit B's implementation is reused, unmodified, as the destination of a public share-link (the natural reading of "one Detail Screen"), the same server-rendered why-this/neighbor-count logic that's correct for an authenticated tap now executes on a route an anonymous visitor can hit — precisely the coupling AD-12 exists to prevent — without either builder having violated their own AD reading.

**Proposed AD-20 — a UX surface with both a public and an authenticated audience is two components, not one.**
- Name them explicitly: `Surface.EventDetail.Public` (owned by `catalog`+`web`, AD-12-governed, generic content only, personalization hydrated client-side) and `Surface.EventDetail.Authenticated` (owned by `personalization`+`web`, full server-render permitted). A share-link always resolves to `.Public`; the in-app tap from a Pulse Card always resolves to `.Authenticated`. The Consistency Convention's naming rule is amended to require this split whenever a surface's audience spans the session boundary.

---

## HOLE 8 (MEDIUM) — Quiet Hours needs a UTC→local conversion inside the dispatch decision, which AD-6 says never happens in domain logic — and its config/enforcement halves have two different owners

**Units:**
- **Unit A** — `delivery`'s sweep dispatch decision (FR-12/FR-9–12, capability-mapped to `delivery`/`worker`, governed by AD-6/AD-7): must decide, for a `due_at` in UTC, whether "now" falls inside the user's Quiet Hours window.
- **Unit B** — the Pro per-day-of-week Quiet Hours config (FR-51, capability-mapped to `identity`/`adapters/billing`, governed by AD-5 only — **not** AD-6).

**Unit A compliance:** AD-7's sweep operates on `(due_at, status)`; AD-6 says "conflict detection operates only in UTC." Deferring a send to "the Quiet Hours window end" (FR-12) is a dispatch-time decision the sweep must make.

**Unit B compliance:** FR-51 — "Quiet Hours windows are stored as wall-clock local time, recomputed on timezone change / DST event" — and the capability map assigns this to `identity`, governed only by AD-5 (no AD-6 obligation stated).

**The incompatibility:** to decide "is now inside Tuesday's 10pm–9am window," the sweep must convert its own UTC `due_at`/`now()` into the user's current IANA-local wall-clock, including today's DST offset — a timezone conversion happening inside the *dispatch decision*, i.e., domain/application logic in the worker runtime. AD-6 states this "happens at the presentation edge, never in domain logic," with no named exception for deferral logic. Meanwhile the capability map's own governance column silently exempts FR-51 from AD-6 (only AD-5 listed), so `identity` — the config owner — never has to reconcile local-time storage with AD-6's UTC-only rule, and `delivery` — the enforcement owner, bound by AD-6 — is left holding a conversion the rule says shouldn't exist in domain code. Two owners, one boundary condition no AD schedules a home for.

**Proposed AD-21 — Quiet Hours evaluation is a named, singular exception to AD-6, owned end to end by one module.**
- Move FR-51's config storage to `delivery` (co-located with the enforcement it exists for) instead of `identity`.
- The one permitted UTC→local conversion in domain code lives in exactly one pure function, `shared/time/isWithinQuietHours(nowUtc, ianaTz, windows): boolean`, called only from the sweep's dispatch decision — named explicitly in AD-6's text as the sole carve-out, so no other module reads AD-6 as license to do its own local-time math.

---

## Minor / worth tightening (lower severity, included for completeness)

- **Source Reliability Score's "dismissal rate" has no canonical formula or owner.** FR-16 computes it from "user dismissal rate" (a `personalization`-owned, `personal`-schema signal keyed by `event_cluster_id`) but writes the result to `catalog.SOURCE` (an `ingestion`-owned field, per AD-4). Nothing says which module computes the rate, so two independently-built aggregations (e.g., dismissals ÷ impressions vs. dismissals ÷ total-events-from-source) could each look correct and disagree. Tighten AD-4 or add a line to FR-16's implementation note: `personalization` exposes `getDismissalCountsByCluster()` through its `app` interface; `ingestion`'s weekly recompute job does the cluster→source rollup itself, once, in one place.
- **AD-4's text says "sole writer of `catalog` event records," not "sole writer of the `catalog` schema."** `VENUE` and `SOURCE` are catalog-schema entities the rule doesn't literally name. Almost certainly meant to cover them too — tighten the wording to "sole writer of the `catalog` schema" to remove the gap outright rather than relying on inference.
- **AD-8's gateway abstracts two providers (Anthropic for extraction, OpenAI for embeddings) with no named call-shape normalization.** Not a forced bypass at MVP — no MVP feature needs a model outside extraction/embedding/enrichment — but the Stack table pins `@anthropic-ai/sdk` and never pins an OpenAI SDK version, which is the one loose thread AD-8's "no module imports a provider SDK" discipline should catch. Add the missing pin.

---

## Summary table

| # | Hole | Severity | New/Tightened AD |
|---|---|---|---|
| 1 | SCHEDULED_SEND reschedule-vs-sweep race on postponement | Critical | AD-14 |
| 2 | REMINDER_SLOT has no sole writer across personalization/delivery | High | AD-15 |
| 3 | Preference Graph unmodeled, collides with declared INTEREST | High | AD-16 |
| 4 | WHY_THIS_REASON keying ambiguous (per-composition vs. durable) | High | AD-17 |
| 5 | "Confidence" convention conflates 4 unrelated scores | Medium-High | AD-18 |
| 6 | EventReport / review queue unmodeled, needs atomic 2-write | Medium-High | AD-19 |
| 7 | Detail Screen is one surface with two audiences, one AD-12 risk | Medium | AD-20 |
| 8 | Quiet Hours needs local-time math AD-6 forbids; split ownership | Medium | AD-21 |
| — | Source Reliability "dismissal rate" formula/owner unstated | Minor | tighten FR-16 impl note |
| — | AD-4 wording covers "event records," not the whole schema | Minor | reword AD-4 |
| — | OpenAI SDK unpinned in Stack table | Minor | add pin |
