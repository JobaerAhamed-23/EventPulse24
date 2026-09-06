---
title: "Rubric Review — ARCHITECTURE-SPINE.md"
target: _bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md
against:
  - _bmad-output/planning-artifacts/prds/prd-EventPulse24-2026-08-19/prd.md
  - _bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/EXPERIENCE.md
reviewed: 2026-09-04
reviewer: rubric-reviewer (Claude)
---

# Rubric Review — EventPulse24 Architecture Spine

## Verdict

The spine is a genuinely lean, mostly well-formed set of invariants — AD-1/2/4/5/6/7/8/9/10/12/13 each name a real divergence and a testable rule. But it has one launch-gating MVP capability (FR-57, the editorial review queue) that falls through the floor entirely — no AD binds it, it's missing from the Capability→Architecture Map, and it's explicitly waved off in Deferred as "not architectural" even though it's MVP-scoped and SLA-bound. Compounding that, there is no architectural treatment anywhere of internal/admin authorization (who can approve/reject events, who sees the AI Cost Dashboard) — a real gap given the spine otherwise insists on mechanical enforcement over convention. Several other invariants (schema separation, no-long-work-in-request) are stated without the same mechanical-enforcement discipline the spine itself demands elsewhere, and the Capability→Architecture Map has cross-reference drift from the ADs' own `Binds` fields.

## CRITICAL

### C-1. FR-57 (Editorial Review Queue) has no architectural home — despite being MVP-scoped and launch-gating

FR-57 is one of the 43 MVP FRs (PRD §6.1 lists it explicitly: "FR-13, FR-14, FR-15, FR-16, FR-17, FR-56, **FR-57**, FR-60"). It carries real invariants: a 24-hour review SLA for user-reported events (vs. daily cadence otherwise), Approve/Reject/Edit as the only terminal actions, queue size and latency tracked on the AI Cost Dashboard, and it's the human-override path the PRD calls "the trust infrastructure" (§4.4 FR-57, realizing "Trust through transparency").

The spine:
- Does not bind FR-57 to any AD (`grep` the "Binds:" lines of AD-1..13 — FR-57 never appears).
- Omits FR-57 from the **Capability → Architecture Map** entirely (the FR-13–17/56/60 row does not include it).
- Explicitly dismisses it in **Deferred**: "Editorial review queue tooling | An operational surface, not an architectural boundary — reads `catalog` and writes through `ingestion` commands like any other client."

That framing doesn't hold up: FR-57 isn't a Phase-2-or-later nicety that "nothing built today depends on the answer" (the Deferred test) — it is itself an MVP capability with a codified SLA, and FR-59 (which the spine *does* bind, to AD-9/AD-10) explicitly feeds into it ("the Event is added to the editorial review queue"). Two MVP FRs land in the same queue, and only one has an architectural owner.

**Fix:** Add an AD (or extend AD-5/AD-9) that pins: (a) the review queue is a distinct, named state on `catalog` records (quarantine/pending/approved/rejected), transitioned only via named commands (ties into AD-5); (b) the 24h vs. daily SLA and queue depth are first-class metrics owned by whichever module also owns the AI Cost Dashboard (AD-8's territory, or a new binding); (c) who is authorized to call Approve/Reject/Edit (see C-2). Move FR-57 out of Deferred and into the Capability→Architecture Map with an explicit AD binding.

### C-2. No architectural treatment of internal/admin authorization anywhere

The spine's only notion of "actor" is end-user: `identity` module owns onboarding/account (FR-1–4) and Pro-tier billing (FR-48–52); the Consistency Conventions' "Auth" row says "Session checked at the surface edge; the application layer receives an explicit actor, never a request object" — but every example of "actor" in the document is a consumer.

Yet the PRD requires real internal-actor surfaces at MVP:
- FR-57's editorial reviewers who Approve/Reject/Edit events (PRD: "reviewed at least daily by the editorial team / on-call engineer").
- FR-29's AI Cost Dashboard, explicitly "Internal-facing."
- FR-13's Source Registry, "internally auditable; every change is logged" — logged by/attributed to whom?
- §10.5's on-call engineer who needs pager access and a runbook.

Nothing in the spine says where these surfaces live in the source tree, what actor type gates them, or how a builder would avoid accidentally exposing cost/reliability data on a route reachable by a regular session. This is exactly the class of divergence the spine's own philosophy (AD-2, AD-5, AD-13: "not by review," "not a convention") says must be pinned, not left to discipline.

**Fix:** Add a role/actor invariant — e.g., "`identity` distinguishes `user` and `internal` actor kinds; internal surfaces (`FR-13` registry mutation, `FR-57` review actions, `FR-29` dashboard reads) require an `internal` actor and live under a route namespace never reachable by a `user` session token." Bind FR-29 and FR-57 to it.

## HIGH

### H-1. AD-3 (schema separation) has no stated mechanical enforcement, unlike its siblings

AD-3 is arguably the single most consequential rule in the document — it's what makes the 30-day deletion guarantee and per-category retention windows (PRD §10.2) enforceable at all. Its Rule says: "No foreign keys and no SQL joins cross that boundary." But nothing says *how* that's checked. Compare to AD-2 ("Enforced mechanically in CI (dependency-cruiser or ESLint boundaries), **not by review**") and AD-13 ("Redaction is enforced by the logger adapter's allowlist, **not by call-site discipline**"). AD-3 gets no such mechanism. A raw SQL query or an ORM join written by any engineer in any module can silently cross the boundary; nothing in Postgres itself prevents a cross-schema join, and Drizzle doesn't forbid it by default.

**Fix:** State the enforcement mechanism explicitly — e.g., "Enforced by a CI query-linter (static analysis of Drizzle query builders/migrations for cross-schema references) and by database role grants: the `personal` schema role has no `SELECT`/`REFERENCES` grant on `catalog`'s FK-eligible columns and vice versa." Without this, AD-3 is a convention dressed as an invariant.

### H-2. No architecture for per-category data retention/purge — only account deletion is covered

PRD §10.2 specifies seven differentiated retention windows: personal/saved events (30 days post-deletion), preference-graph signals (12 months rolling), OAuth tokens (purge on disconnect/deletion), email delivery events (90 days), audit logs (24 months), Source Registry ToS records (7 years), billing records (7 years). AD-3's Rule only addresses "Account deletion is a `personal`-scoped operation that never touches `catalog`" — it says nothing about the other six windows, none of which are triggered by account deletion at all (e.g., preference-graph purge at 12 months happens on an *active* account).

Without an owned mechanism (a generic TTL/retention-tag convention, a scheduled purge job pattern, or per-table ownership), each of these seven windows will likely get implemented ad hoc by whichever engineer touches that table first — precisely the divergence AD-3 exists to prevent, just one layer down.

**Fix:** Add a retention convention to the Consistency Conventions table (or a new AD) — e.g., "Every `personal`-schema table declares a `retention_class` (one of: `active-scoped`, `12mo-rolling`, `24mo-fixed`, `90d-fixed`, `7yr-fixed`); a single scheduled worker job purges by class. No module purges its own table directly."

### H-3. Capability→Architecture Map is internally inconsistent with the ADs' own `Binds` fields

The Map is supposed to be the single cross-reference telling a builder which invariants govern a given FR. It doesn't agree with the ADs it's summarizing in at least four places:

- **AD-7** declares `Binds: FR-9–12, FR-5–8` — but the Map's `FR-5–8 Pulse Digest` row lists only `AD-3, AD-10, AD-11` (no AD-7). Digest *delivery* timing (Pulse Ping dispatch) is governed by the sweep, per AD-7's own text, but a builder reading only the Map would never know that.
- **AD-7**'s binds also omit `FR-53–55`, yet the Map's `FR-53–55` row lists `AD-4, AD-7` — the reverse gap.
- **AD-3** declares `Binds: FR-3, FR-18–20, FR-50, FR-52` — but the Map's `FR-1–4 Onboarding & account` row lists only `AD-5, AD-12` (no AD-3, despite AD-3 explicitly claiming FR-3), and the `FR-48–52 Pro tier` row lists only `AD-5` (no AD-3, despite AD-3 explicitly claiming FR-50 and FR-52 — both of which move personal calendar/export data).

**Fix:** Regenerate the Map mechanically from each AD's `Binds:` field (or vice versa) so the two can't drift, and add the missing AD-3/AD-7 references above.

### H-4. `EventCluster` / `EventRecord` are new domain nouns not in the PRD Glossary — which explicitly forbids that

PRD §3 states, as a load-bearing discipline rule: *"Downstream artifacts (UX, Architecture, Epics, Stories) MUST use these terms exactly. Introducing a synonym is a discipline violation. New domain nouns introduced in §4 land here in the same pass."* The PRD's own glossary defines only **Event** and **Event Identity** (the dedup tuple) — there is no "EventCluster" or "EventRecord" anywhere in the PRD or the UX spine.

The architecture spine's ERD and Consistency Conventions introduce a two-entity split: `EVENT_CLUSTER` (canonical) vs. `EVENT_RECORD` (per-source extracted member), stating "A cluster is the canonical unit; a member is an `EventRecord`." This is a reasonable technical resolution of the PRD's dedup rules (AD-4 is internally consistent about which entity Pulse Cards feature — `EVENT_CLUSTER`), but it's new vocabulary invented silently at the architecture layer, violating the PRD's explicit "introducing a synonym is a discipline violation" rule, and it creates a real translation gap: every epic/story written against PRD/UX language ("Event," "event_id") now has to know it maps to `EventCluster`, not `EventRecord` — a mapping stated nowhere except by inference from the ERD relationships.

**Fix:** Either (a) add `EventCluster` and `EventRecord` to the PRD Glossary as an amendment with an explicit mapping ("PRD's `Event`/`event_id` = architecture's `EventCluster`"), or (b) rename to avoid inventing nouns — e.g., keep `Event` as the canonical entity name and call the per-source extraction a `SourceExtract` or similar, avoiding "Record" as a second Event-like noun.

## MEDIUM

### M-1. Migrations are entirely unaddressed, despite AD-1 creating the exact coordination risk migrations need a rule for

AD-1 deploys web and worker separately from one repo sharing `domain`/`app`/`ports`/`adapters`; Structural Seed adds per-PR Neon-branch previews. Nowhere does the spine say how a schema migration is sequenced relative to those two independent deploys (e.g., can worker ship a migration-dependent change before web redeploys, or vice versa? are migrations required to be backward-compatible for one deploy cycle?). This is a textbook divergence point for two independently-built/deployed units and is currently silent.

**Fix:** Add a line to Structural Seed or a new AD: "Migrations are additive-and-compatible for one full deploy cycle (expand/contract pattern); a migration that only the worker or only the web runtime depends on ships in its own deploy before the dependent runtime redeploys."

### M-2. Rate limiting is required by the PRD but absent from the spine

PRD §11.2 states flatly: "Rate limiting on all public endpoints (per-IP and per-user)." The spine has no AD, Consistency Convention, or Structural Seed entry addressing where rate limiting is enforced (edge middleware? the LLM gateway? per-route?). FR-59 has its own bespoke rate limit (5 reports/user/day) — with no shared mechanism named, each feature is liable to reinvent its own rate-limiting logic inconsistently.

**Fix:** Add a Consistency Conventions row or fold into AD-5/AD-11: "Rate limiting is enforced once, at the surface edge (same layer as auth), keyed by actor + IP; feature-specific caps (e.g., FR-59's 5/day) are business rules on top of, not instead of, the edge limiter."

### M-3. AD-11 ("no long work inside a request") has no mechanical enforcement

Unlike AD-1/AD-2 (dependency-cruiser/ESLint boundaries) or AD-13 (logger allowlist), AD-11's Rule — "No request handler performs crawl, extraction, embedding, or bulk send" — is not backed by any stated structural check. The layer table (`web`/`worker` depend on `app`, `ports`) doesn't by itself prevent an `app` use-case that does synchronous crawl/LLM work from being invoked by a web route handler; nothing stops that use-case from existing or from being called from the wrong runtime.

**Fix:** Either (a) name the mechanism — e.g., "app use-cases callable from `web/` are a statically-declared allowlist; anything importing `adapters/crawl` or `adapters/llm` synchronously is rejected by the same dependency-cruiser rule as AD-2" — or (b) add a request-scoped hard timeout (e.g., 5s) enforced in web middleware as a backstop.

### M-4. AD-7's own claim about dedupe may already answer OQ-4 — or OQ-4 shows the claim doesn't hold

AD-7's Rule states delivery is "at-least-once with dedupe at the send boundary" via a deterministic idempotency key — which, if backed by a unique constraint, should already make a worker *pool* safe from double-sends (the second writer simply loses the race). Yet OQ-4 asks "Is the worker runtime one process or a pool from day one?" and frames a pool as needing "leader election or advisory locks to avoid double sends," as if AD-7's dedupe doesn't already cover it. Either OQ-4 is solved by AD-7 as written (and should say so, framing the open question as pool *efficiency*, not correctness), or AD-7's Rule overstates what dedupe-at-send-boundary actually guarantees and needs a caveat.

**Fix:** Resolve the tension explicitly: state whether the idempotency-key uniqueness constraint alone is sufficient for correctness under a worker pool (in which case OQ-4 is really about lock contention/efficiency, and can say so), or state what additional guarantee (row-level locking via `SELECT ... FOR UPDATE SKIP LOCKED` on the due-index sweep) is required and add it to AD-7's Rule.

### M-5. GDPR/EU compliance posture is only mentioned inside the "Multi-region deployment" Deferred row — contradicting the PRD's explicit independence claim

The spine's only reference to EU/GDPR obligations is buried in Deferred: "Multi-region deployment | English-first, single-region MVP... | Revisit when: EU or APAC rollout is committed." That reads as if EU compliance readiness rides on the multi-region infrastructure decision. But PRD §11.6 says the opposite, explicitly: *"Multi-region rollout (EU, APAC) is Phase 2+. The GDPR / UK GDPR / EU-launch-gate commitments in §10.1 are jurisdiction-dependent and proceed independently of i18n rollout."* A single-region, English-only web app is still reachable by, and legally obligated toward, any EU visitor who signs up — the DPIA gate, EU representative, and Article 17/20 timelines (PRD §10.1) are day-one obligations, not something that waits for a "multi-region rollout" decision.

**Fix:** Remove the implication that GDPR readiness is deferred with multi-region. Add a separate line (Structural Seed or Open Question) capturing the actual architectural question: does data residency / hosting region matter for the DPIA sign-off given Neon's region, and is an EU representative needed at MVP launch regardless of marketing language?

## LOW

### L-1. AD-8's gateway doesn't mention the PRD's provider training-opt-out requirement

PRD §10.2: "Where the LLM provider's terms permit opt-out of training-data retention, the system is configured to opt out at the API level." AD-8 is exactly the single choke point ("No module imports a provider SDK... owns provider selection") where this configuration belongs, but the AD's Rule doesn't mention it. Low severity because it's a configuration detail, not a structural boundary, but it's the kind of requirement that's easy to lose if not pinned to the one place that owns provider calls.

**Fix:** Add one clause to AD-8's Rule: "the gateway sets provider-level no-training/no-retention flags where the provider's API supports them."

### L-2. Performance budgets are referenced only incidentally, not pinned as a shared table

PRD §11.1 sets five concrete budgets (composition <500ms p95 cached / <3s cold, extraction <2s p95, dedup <500ms p95, page load <1.5s LCP, API <300ms p95). The spine mentions the 500ms budget only inside AD-1's `Prevents` clause; the other four appear nowhere. This is likely fine as "seed" (the code will own SLO dashboards), but a one-line table in Structural Seed or Consistency Conventions would make the budgets traceable from the spine itself rather than requiring a jump back to the PRD.

### L-3. Testing strategy and CI/CD pipeline mechanics are thin relative to the PRD's NFR rigor

The Consistency Conventions "Tests" row (domain unit tests, CI check per violable AD, axe-core gate) is a reasonable minimum for a terse spine, and CI/CD is implied via the dependency-cruiser/ESLint mentions in AD-1/AD-2. Given the PRD's emphasis on quarterly accessibility re-audits and fire-drill SEV-1 simulations (§10.5, §11.5), a one-line convention on contract tests for ports/adapters (so a fake adapter can't silently drift from the real one) would close a small gap. Not launch-blocking; flagged for completeness only.
