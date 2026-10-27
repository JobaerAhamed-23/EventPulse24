---
name: 'review-multilens'
type: architecture-review
reviews: architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md
method: 'bmad-review — lenses: adversarial, edge-case-hunter, structure, prose (after structure)'
created: '2026-10-27'
---

# Multi-lens Review — ARCHITECTURE-SPINE.md

Content class: **docs** (architecture spine that defines behavior). Lenses run: adversarial, edge-case-hunter, structure, then prose on top of structure. Verification-gap was skipped because it applies to code only.

Findings count: adversarial 36 · edge-case-hunter 45 · structure 18 (+1 PRESERVE) · prose 36.

## Cross-lens overlaps (signal)

When two or more lenses find the same issue independently, that issue is the most likely to be real:

| Theme | Lenses |
| --- | --- |
| AD-17 re-validates catalog state "inside the same transaction" that claims a `personal` send. AD-3 forbids that transaction. | adversarial, edge-case |
| Propagation enqueue is a dual write with no outbox, so "Redis loss never costs a reminder" is false | adversarial, edge-case |
| AD-7 idempotency key is unstable (`scheduled_for` changes) and undefined for PersonalEvent / Pulse Ping | adversarial, edge-case, prose |
| Single beat process has no liveness check and no deploy overlap guard | adversarial, edge-case |
| A postponement over 30 days creates a new Event and orphans saves, plans and sends on the old id | adversarial, edge-case |
| `EVENT_FIT` is owned in AD-16 but missing from the ERD and schema lists | adversarial, structure |
| `web` module doesn't exist; `catalog` app owns nothing and has no stated role | adversarial, structure |
| "Confidence Pulse" vs "Relevance Pulse" is undefined, which breaks the spine's own no-synonym rule | adversarial, structure |
| PRD amendments (FR-3, FR-50, FR-14, Glossary split, new nouns) are scattered and not landed | adversarial, structure |
| Python "3.13 — the only version" is wrong (3.12 also qualifies) | adversarial, prose |
| AD-1 SEV-1 citation (PRD §10.5 doesn't list latency) | adversarial, prose |
| Errors live in `domain/` (Conventions) vs `shared/` (source tree) | adversarial, prose |
| Deployment diagram node still labelled "OQ-4" | adversarial, structure |

Spot-verified against PRD and memlog during assembly: AD-8 model flip (memlog line 120), Glossary default 5d/2d/1d/1hr vs FR-9/FR-20 1d+1hr (PRD lines 212, 377, 611), SEV-1 definition (PRD line 1352), nine retention categories (PRD lines 1316–1325), FR-13 floor of ≥40 sources (PRD FR-13).

---

## Lens: adversarial

```json
[
{"lens":"adversarial","location":"AD-8 Rule (fallback); Stack 'Claude (extraction)'; frontmatter updated","trigger_condition":"Spine says sonnet-5 primary / haiku-4-5 fallback; memlog 2026-09-06 records the user flipping to haiku primary / sonnet fallback with three accepted risks; `updated` still 2026-09-04","guard_snippet":"Rewrite AD-8 + Stack row to haiku-4-5 primary, sonnet-5 fallback; add the three accepted risks (re-baseline 0.5/0.7 gates; route identity/±30d date arithmetic to editorial; FR-29 runbook note); bump `updated`","potential_consequence":"Builders wire the reversed order — ~2x happy-path cost against the $0.50/MAU ceiling, silently undoing a ratified decision"},
{"lens":"adversarial","location":"AD-8 Rule (confidence gate); Conventions 'Confidence'","trigger_condition":"0.5/0.7 gates presented as fixed though the model flip makes them provisional until re-baselined","guard_snippet":"Mark gates as tuning anchors pending re-baseline on a labeled sample; add a pre-launch task/OQ","potential_consequence":"Shifted confidence distribution floods editorial or auto-rejects valid events"},
{"lens":"adversarial","location":"AD-3 Accepted cost vs AD-17 Rule","trigger_condition":"AD-17 re-validates catalog state 'inside the same transaction that claims the send' — catalog and personal are separate DATABASES; AD-3 says no transaction spans both","guard_snippet":"Claim tx is personal-only; propagation stamps catalog_state_version on SCHEDULED_SEND and sweep compares it","potential_consequence":"Builder believes it atomic; postponement between reads still sends a reminder for a moved event"},
{"lens":"adversarial","location":"AD-7 (schedule never in broker) + AD-17","trigger_condition":"Propagation is itself an in-flight broker job; 'enqueue after append' is a dual write with no outbox","guard_snippet":"Outbox: EVENT_STATE_CHANGE.propagated_at + periodic reconciler; enqueue via transaction.on_commit; define where a re-queued send goes","potential_consequence":"After Redis loss or crash, reminders fire for cancelled/moved events — the SEV-1 the spine says cannot happen"},
{"lens":"adversarial","location":"AD-7 Rule (broker); Structural Seed 'Not a platform-cron fallback'","trigger_condition":"Tick comes from one beat via Redis; no liveness monitoring or failover","guard_snippet":"last-sweep-at heartbeat, alert >2 min; supervised single-instance beat; optional worker self-tick; state Redis outage = delayed, not lost","potential_consequence":"Silent outage blows ±5 min reminder / ±15 min digest SLA for all users"},
{"lens":"adversarial","location":"AD-7 idempotency key","trigger_condition":"scheduled_for changes on recompute; PersonalEvent sends have no catalog event_id; Pulse Ping has no event","guard_snippet":"Key on stable identity (user_id, subject_type, subject_id, slot, original_slot_instant) or a once-minted row UUID; Pulse Ping = user_id + local_date","potential_consequence":"Double delivery after recompute; builders invent divergent keys"},
{"lens":"adversarial","location":"AD-14 / AD-2 / AD-5 / AD-16 (Django admin)","trigger_condition":"ModelAdmin save/delete/bulk actions write models directly; AD-5 forbids writes outside commands, AD-16 says editorial acts only via ingestion commands","guard_snippet":"Catalog ModelAdmins read-only; approve/reject/edit/merge are admin actions calling ingestion commands; lint/test that editorial.admin never .save()/.delete()s catalog models","potential_consequence":"First editor Save becomes a second catalog writer, skipping AD-4, AD-5 audit, AD-17 propagation"},
{"lens":"adversarial","location":"AD-3 Enforcement / AD-14 (contrib app routing)","trigger_condition":"No routing for auth, sessions, contenttypes, admin LogEntry; LogEntry FKs users and logs catalog changes; editorial actor attribution in catalog references personal users","guard_snippet":"Routing table for every installed app; actor attribution as opaque id with no FK, retained per audit category; extend AD-3 spike to admin/LogEntry","potential_consequence":"Router migrations/admin logging fail, or auth duplicated across schemas eroding isolation and deletion"},
{"lens":"adversarial","location":"AD-3 Enforcement / Database (Neon)","trigger_condition":"Per-connection search_path is unreliable under Neon's pooled (PgBouncer transaction-mode) endpoint; spike covers only migrations","guard_snippet":"Extend spike to pooling, or mandate direct endpoint, or schema-qualified db_table names","potential_consequence":"Queries silently hit the wrong schema under pooling"},
{"lens":"adversarial","location":"AD-3 / AD-10 (reverse flows)","trigger_condition":"Source Reliability (dismissal rate), FR-5 popularity, Event Fit, FR-59 repeat-reporter all need personal→catalog or catalog→personal-report flows; only catalog→personal propagation is defined","guard_snippet":"New AD: personal→catalog only as anonymized aggregates via one owned job with k-anonymity floor; REVIEW_ITEM outcomes flow back via opaque report id","potential_consequence":"Wall violated by direct reads, or features quietly skipped"},
{"lens":"adversarial","location":"Core entities ERD vs schema lists vs AD-16","trigger_condition":"EVENT_FIT owned in AD-16 but absent from ERD and catalog schema list","guard_snippet":"Add EVENT_FIT (EVENT ||--o{ EVENT_FIT keyed by city) to ERD and catalog list","potential_consequence":"No agreed storage shape; risk of render-time computation violating AD-10"},
{"lens":"adversarial","location":"Core entities (missing MVP entities)","trigger_condition":"No entity for saves/Saved Collections, Quiet Hours windows, digest delivery time, calendar connections/ICS credentials, ConflictResolution, audit log, LLM cost row, email delivery events, data exports — all unowned despite AD-16","guard_snippet":"Add SAVE, SAVED_COLLECTION, QUIET_HOURS_WINDOW, USER_SETTINGS, CALENDAR_CONNECTION, CONFLICT_RESOLUTION, AUDIT_LOG, LLM_CALL_COST, EMAIL_DELIVERY_EVENT, DATA_EXPORT with schema, owner, retention","potential_consequence":"Competing tables/names/owners; AD-15 retention coverage misses them"},
{"lens":"adversarial","location":"Core entities ERD — REMINDER_PLAN / SCHEDULED_SEND","trigger_condition":"PERSONAL_EVENT produces SCHEDULED_SEND bypassing REMINDER_PLAN (contradicts AD-16); no cross-wall event_id shown; Pulse Ping/digest sends have no producer","guard_snippet":"REMINDER_PLAN → (PERSONAL_EVENT | opaque event_id) → SCHEDULED_SEND; USER → SCHEDULED_SEND for ping/digest; annotate 'id only, no FK'","potential_consequence":"Two send-generation paths; digest SLA has no mechanism"},
{"lens":"adversarial","location":"AD-16 (default is a constant) vs PRD §3 Glossary","trigger_condition":"Spine: default 1d + 1hr (FR-9/FR-20). Glossary (PRD line 212): default 5d, 2d, 1d, 1hr. Contradiction not surfaced","guard_snippet":"OQ/PRD amendment fixing the Glossary, or state FR overrides Glossary","potential_consequence":"Builder following the Glossary ships 4 defaults, quadrupling notifications"},
{"lens":"adversarial","location":"AD-18 / AD-8 / AD-10 / OQ-6 vs PRD FR-3, FR-50, FR-14, §3, §11.2","trigger_condition":"Spine binds FRs it contradicts (OAuth/CalDAV, multi-provider fallback, Confidence Pulse on Event record, missing new nouns); no amendment has landed; only FR-14 is mentioned","guard_snippet":"'Pending PRD amendments (blocking)' section; hold status: draft or scope binds until landed","potential_consequence":"Stories traced to PRD build OAuth/CalDAV and a second LLM vendor"},
{"lens":"adversarial","location":"Structural Seed — Secrets row vs AD-18","trigger_condition":"Lists OAuth tokens and CalDAV passwords; MVP stores secret ICS URLs and ships neither","guard_snippet":"'Every calendar credential (secret ICS URL at MVP; OAuth later) encrypted at rest (AD-18)'","potential_consequence":"ICS URLs stored plaintext"},
{"lens":"adversarial","location":"AD-10 vs Conventions 'Confidence' / DIGEST_COMPOSITION text","trigger_condition":"AD-10 uses Relevance Pulse + Event Fit; Conventions/Core entities still say Confidence Pulse; 'four scores' omits Event Fit; UX component is Indicator.Confidence","guard_snippet":"One term per concept; list five scores; say which indicator variant renders each","potential_consequence":"Spine commits the synonym violation it forbids; the two 1–5 indicators get conflated"},
{"lens":"adversarial","location":"AD-4 Rule","trigger_condition":"Only cosine ≥0.95 band cited; PRD FR-15 also defines 0.85–0.95 'watch' and <0.85 no-action","guard_snippet":"Add the watch band; both thresholds in shared module","potential_consequence":"Watch band never built; early dedup-degradation signal lost"},
{"lens":"adversarial","location":"AD-4 Rule (state) — >±30d","trigger_condition":"New Event created; nothing says what happens to saves/plans/sends/compositions on the old id","guard_snippet":"Old Event gets terminal superseded_by; AD-17 cancels old sends and notifies (FR-54) with re-save option","potential_consequence":"Reminders for a vacated date, or silent loss of the save"},
{"lens":"adversarial","location":"AD-1 Prevents","trigger_condition":"Claims PRD §10.5 classifies a <500ms p95 breach as SEV-1; §10.5 SEV-1 (PRD line 1352) lists delivery broken >5%, reminder dispatch, breach, harmful content — not latency","guard_snippet":"Cite §11.1 for the budget and drop the SEV-1 claim","potential_consequence":"Inflated citation undermines traceability; severity misclassified"},
{"lens":"adversarial","location":"AD-1 / AD-11 / AD-7 — digest composition runtime","trigger_condition":"Never stated whether composition runs in API on request or in worker ahead of delivery; personalization→LLM edge unexplained","guard_snippet":"Compose in worker via a per-user due-index entry before local delivery time; persist; API serves read-only; no synchronous LLM from personalization","potential_consequence":"Composition lands in a request path, breaking <500ms/<3s and ±15 min digest SLA"},
{"lens":"adversarial","location":"AD-20 / FR-10 — Pulse Ping stream","trigger_condition":"Pulse Ping stream unclassified; FR-11 per-event reminder unsubscribe on transactional stream unspecified","guard_snippet":"Enumerate every send type → stream; unsubscribe mechanism per type","potential_consequence":"The 'second sender inherits default' failure recurs for Pulse Ping"},
{"lens":"adversarial","location":"Stack — Python row","trigger_condition":"'the only version both declare' is false — intersection is {3.12, 3.13}","guard_snippet":"'the newest version both declare (3.12 also qualifies)'","potential_consequence":"Wrong justification in a table treated as verified"},
{"lens":"adversarial","location":"Stack `instructor` vs AD-8","trigger_condition":"AD-8 says no hand-written validate-and-retry; instructor's core feature is validate-and-retry","guard_snippet":"Drop instructor, or use for schema conversion only with max_retries=0; all retry/fallback in gateway","potential_consequence":"Hidden retries multiply cost and confuse the 2-failure pause counter"},
{"lens":"adversarial","location":"Layer table / source tree shared/ / domain/confidence.py","trigger_condition":"shared/ absent from layer table; domain (stdlib-only) needs thresholds in shared/; errors in domain/ vs shared/; diagram lists a postgres adapter the tree lacks","guard_snippet":"Add shared/ to layer table with import rules, or move thresholds into domain/; reconcile errors; reconcile postgres adapter","potential_consequence":"import-linter fails day one or gets loosened ad hoc"},
{"lens":"adversarial","location":"Layer table — composition root","trigger_condition":"Apps may not import adapters, but nowhere binds adapters to ports","guard_snippet":"Name config/wiring.py as the only non-test importer of adapters.*; add import-linter contract","potential_consequence":"Apps import adapters directly; ports-and-adapters collapses"},
{"lens":"adversarial","location":"Capability → Architecture Map","trigger_condition":"`web` module doesn't exist; `catalog` app owns nothing yet carries FR-26–28 and collides with schema name; FR-49, FR-2, FR-56 lack governing AD","guard_snippet":"web → frontend; define catalog app as read-only query app or rename; add FR-2/FR-49 rows","potential_consequence":"Stories routed to a non-existent module; Pulse Preview and collections unowned"},
{"lens":"adversarial","location":"AD-12 / Deployment — cross-origin auth, SEO uptime","trigger_condition":"Vercel frontend + separate API host with no cookie domain/SameSite/CSRF/CORS model; 99.9% SEO uptime rides on a single ~$5 API host for uncached pages","guard_snippet":"Auth AD: API on sibling subdomain, SameSite=Lax cookie on registrable domain, Django CSRF, CORS allowlist; serve stale ISR on API failure","potential_consequence":"Login breaks under third-party-cookie blocking, or tokens drift to localStorage; SEO pages 500"},
{"lens":"adversarial","location":"AD-19 'No endpoint absent from the schema'","trigger_condition":"Admin, RFC 8058 unsubscribe POST, Stripe and source webhooks sit outside the client schema","guard_snippet":"Scope to frontend-consumed endpoints; list sanctioned non-schema surfaces with their auth/signature rules","potential_consequence":"Rule violated day one; webhook signature verification has no home"},
{"lens":"adversarial","location":"AD-15 Binds 'all seven retention categories' / AD-3 deletion","trigger_condition":"PRD §10.2 lists nine categories; EventReport retained 24 months vs 30-day deletion; PITR backups retain deleted data","guard_snippet":"Enumerate nine; resolve EventReport on deletion (pseudonymize); state backup window vs 30-day guarantee","potential_consequence":"Uncovered categories; compliance exposure"},
{"lens":"adversarial","location":"Database (Neon Free) / AD-7 cadence","trigger_condition":"≤60s sweep keeps Neon compute permanently awake; cost path ignores it","guard_snippet":"State always-on compute in Cost path; size Phase 1 paid compute","potential_consequence":"Free tier exhausted mid-month, DB suspends, reminders stop"},
{"lens":"adversarial","location":"Structural Seed deployment diagram","trigger_condition":"Omits Redis; email node labelled resolved 'OQ-4'; no inbound Stripe/source webhook or FR-56 inbound-email path","guard_snippet":"Add Redis edges; relabel email node (AD-20); add inbound webhook and inbound-email edges","potential_consequence":"Provisioning from the diagram misses the broker or inbound email"},
{"lens":"adversarial","location":"Open Questions OQ-5","trigger_condition":"Asks 'which 20 sources'; FR-13 floor is ≥40 with ≥15 per beachhead city and a mix (≤20% crawl)","guard_snippet":"Restate against FR-13 floor and mix","potential_consequence":"Sourcing planned at half the launch gate"},
{"lens":"adversarial","location":"Conventions 'UI system' vs DESIGN.md/EXPERIENCE.md","trigger_condition":"'vanilla components' in a React app is ambiguous (React vs Custom Elements); Tailwind 4 pinned but not reconciled with token contract","guard_snippet":"State React function components with no kit satisfy 'None'; Tailwind only as a utility layer over token custom properties, or drop it","potential_consequence":"Split component models; Tailwind default palette bypasses tokens"},
{"lens":"adversarial","location":"AD-18 freshness / FR-50 / FR-58","trigger_condition":"Floating (TZID-less) and all-day ICS times unhandled; FR-50 disconnect purge within 24h has no mechanism","guard_snippet":"Floating → profile tz, flagged inferred; all-day UTC span rule; disconnect enqueues purge by connection id","potential_consequence":"Mis-detected conflicts; imported events linger after disconnect"},
{"lens":"adversarial","location":"AD-14 vs AD-17 (state_history)","trigger_condition":"Editorial approve/reject/merge appended to state_history, the log whose appends trigger propagation","guard_snippet":"Editorial audit to an audit log; only lifecycle changes append to EVENT_STATE_CHANGE; define which edits are lifecycle","potential_consequence":"Spurious propagation, or ad hoc filtering that misses real edits"}
]
```

## Lens: edge-case-hunter

```json
[
{"lens":"edge-case-hunter","location":"AD-4 Rule (state)","trigger_condition":"Postponement of exactly 30 days — inclusive/exclusive, elapsed vs calendar days unstated","guard_snippet":"keep_id = abs(new_start_utc - original_start_utc) <= timedelta(days=30)  # shared constant, inclusive, UTC elapsed","potential_consequence":"Identical events split differently"},
{"lens":"edge-case-hunter","location":"AD-4 Rule (state)","trigger_condition":"Chained 20-day postponements drift far past original","guard_snippet":"compare cumulative drift against original_start_utc, never last start","potential_consequence":"Event a year away keeps its id"},
{"lens":"edge-case-hunter","location":"AD-4 / AD-17","trigger_condition":">30d postponement orphans saves/sends on old event_id","guard_snippet":"append state_change(old,'superseded_by',new); delivery cancels old sends and re-plans","potential_consequence":"Reminders for old date, none for new"},
{"lens":"edge-case-hunter","location":"AD-4 match rules","trigger_condition":"Postponed record without source_event_id fails rule (b) because start changed","guard_snippet":"no rule matches but url/venue+title match within 30d → review as possible_postponement","potential_consequence":"Ingested as new event; old one stays live"},
{"lens":"edge-case-hunter","location":"AD-4 recurring","trigger_condition":"Series occurrence postponed onto another occurrence's slot","guard_snippet":"rule (b) match with same series_id but different source_event_id → do_not_merge","potential_consequence":"Two occurrences auto-merged"},
{"lens":"edge-case-hunter","location":"AD-6","trigger_condition":"tz_inference_confidence NULL","guard_snippet":"eligible = conf is not None and conf >= TZ_GATE","potential_consequence":"SQL NULL < 0.7 is not true → event slips into digests"},
{"lens":"edge-case-hunter","location":"AD-6","trigger_condition":"Source wall-clock start in a DST gap or overlap","guard_snippet":"nonexistent → shift_forward; ambiguous → fold=0 and lower tz confidence","potential_consequence":"UTC off by one hour"},
{"lens":"edge-case-hunter","location":"AD-7 idempotency key","trigger_condition":"Pulse Ping has no event_id; PersonalEvent sends use personal_event_id","guard_snippet":"key = user_id:kind:(target_id|local_date):slot:...  kind ∈ {reminder, personal_reminder, pulse_ping, state_notice}","potential_consequence":"NULL/colliding keys → wrong dedupe or double send"},
{"lens":"edge-case-hunter","location":"AD-7 key includes scheduled_for","trigger_condition":"due_at recompute changes key on a claimed/sent row","guard_snippet":"recompute only WHERE status='pending'; never rekey sent rows","potential_consequence":"Same reminder sent twice"},
{"lens":"edge-case-hunter","location":"AD-7 send boundary","trigger_condition":"Crash after provider accepts but before status=sent commits","guard_snippet":"pass key as provider Idempotency-Key, or record provider_message_id before the call","potential_consequence":"Duplicate email; send-boundary dedupe location unspecified"},
{"lens":"edge-case-hunter","location":"AD-7 single writer","trigger_condition":"Row claimed then worker dies","guard_snippet":"claimed_until lease; sweep reclaims expired claims","potential_consequence":"Reminder silently never sent"},
{"lens":"edge-case-hunter","location":"AD-7 tick","trigger_condition":"Workers down while beat keeps enqueuing ticks","guard_snippet":"tick options expires=55; advisory-lock single-flight sweep","potential_consequence":"Stale tick flood and concurrent sweeps on recovery"},
{"lens":"edge-case-hunter","location":"AD-7 Redis loss","trigger_condition":"Sweep finds rows hours past due","guard_snippet":"past staleness[slot] or event start → 'expired'; Pulse Ping expires at local day end","potential_consequence":"1hr reminder after the event; two pings in a day"},
{"lens":"edge-case-hunter","location":"Structural Seed (single beat)","trigger_condition":"Beat dies or hangs","guard_snippet":"heartbeat row per tick; alert if stale >180s; worker fallback sweep","potential_consequence":"Silent SEV-1"},
{"lens":"edge-case-hunter","location":"Structural Seed (single beat)","trigger_condition":"Rolling deploy overlaps old and new beat","guard_snippet":"pg_try_advisory_lock(BEAT_LOCK) at start; exit if not acquired","potential_consequence":"Double-fired ticks"},
{"lens":"edge-case-hunter","location":"AD-7 quiet hours","trigger_condition":"Window crosses midnight (22:00–07:00)","guard_snippet":"wrap-aware in_window and end_date computation","potential_consequence":"Deferral to wrong day"},
{"lens":"edge-case-hunter","location":"AD-7 quiet hours","trigger_condition":"start == end or 24h window","guard_snippet":"validate at save: start != end and duration < 24h","potential_consequence":"Deferral never resolves"},
{"lens":"edge-case-hunter","location":"AD-7 quiet hours","trigger_condition":"Deferral pushes a reminder past event start","guard_snippet":"pull back before window or drop with reason='quiet_hours_after_start'","potential_consequence":"'Never dropped' delivers a 1hr reminder after the event"},
{"lens":"edge-case-hunter","location":"AD-7 quiet hours / DST","trigger_condition":"Window end wall-clock nonexistent or ambiguous","guard_snippet":"resolve_local(..., nonexistent='shift_forward', ambiguous='earliest')","potential_consequence":"Off by an hour or raises"},
{"lens":"edge-case-hunter","location":"AD-7 recompute triggers","trigger_condition":"User changes tz / Quiet Hours / digest time with pending sends","guard_snippet":"settings commands enqueue delivery.recompute_pending(user_id)","potential_consequence":"Breaks FR-7 new-local-time guarantee"},
{"lens":"edge-case-hunter","location":"AD-7 / FR-51 tier","trigger_condition":"Pro lapses to Free with per-day windows pending","guard_snippet":"on subscription change: recompute_pending against tier window set","potential_consequence":"Wrong windows applied"},
{"lens":"edge-case-hunter","location":"AD-7 / FR-51 per-day windows","trigger_condition":"Friday window crosses into Saturday's window","guard_snippet":"owning window by start-day; merge overlaps, latest end","potential_consequence":"Deferral ends inside the next window"},
{"lens":"edge-case-hunter","location":"AD-7 Pulse Ping DST/day","trigger_condition":"Ping precomputed across DST or tz change mid-day","guard_snippet":"materialize per local date; unique(user_id, local_date)","potential_consequence":"Hour off, or 0/2 pings in a day"},
{"lens":"edge-case-hunter","location":"AD-7 Pulse Ping qualification","trigger_condition":"FR-10 48h qualifying set changes before send","guard_snippet":"re-evaluate at claim; else 'suppressed'","potential_consequence":"Ping with zero qualifying events"},
{"lens":"edge-case-hunter","location":"AD-7 / FR-7","trigger_condition":"Digest composition late/failed when ping due","guard_snippet":"ping requires composed digest, else FR-1 cached fallback","potential_consequence":"Ping links to missing/stale digest"},
{"lens":"edge-case-hunter","location":"AD-17 vs AD-3","trigger_condition":"Sweep checks catalog state inside a personal transaction","guard_snippet":"compare send.event_version copied in by propagation; never read catalog inside claim","potential_consequence":"The race AD-17 targets remains"},
{"lens":"edge-case-hunter","location":"AD-17 re-queue","trigger_condition":"Event moved but propagation hasn't rewritten the send","guard_snippet":"status='held_for_propagation'; propagation releases","potential_consequence":"Re-claimed every 60s with no target due_at"},
{"lens":"edge-case-hunter","location":"AD-17 state branches","trigger_condition":"Event cancelled / sold out / location-moved / rejected","guard_snippet":"cancelled|rejected → cancel; sold_out|location_moved → send; time_moved → hold","potential_consequence":"Reminders for cancelled events"},
{"lens":"edge-case-hunter","location":"AD-17 enqueue","trigger_condition":"State change commits but enqueue fails/lost","guard_snippet":"outbox column propagated_at + re-enqueue job","potential_consequence":"Postponement never reaches users"},
{"lens":"edge-case-hunter","location":"AD-17 ordering","trigger_condition":"Two changes propagate out of order","guard_snippet":"apply only if seq > last_applied_seq; per-event advisory lock","potential_consequence":"Old postpone overwrites newer cancel"},
{"lens":"edge-case-hunter","location":"AD-17 partial run","trigger_condition":"Propagation fails midway over thousands of users","guard_snippet":"idempotent per (state_change_id, user_id); resume cursor","potential_consequence":"Duplicate or missing notices"},
{"lens":"edge-case-hunter","location":"AD-17 save race","trigger_condition":"User saves while propagation already passed them","guard_snippet":"plan creation checks event version; re-propagate if newer","potential_consequence":"Plan scheduled against old start"},
{"lens":"edge-case-hunter","location":"AD-17 / FR-54 notices","trigger_condition":"State notice during Quiet Hours / second change same day / muted event","guard_snippet":"notices are SCHEDULED_SEND rows: quiet-shifted, unique(user,event,local_date), skip if muted","potential_consequence":"Breaks quiet hours / one-per-day / mute"},
{"lens":"edge-case-hunter","location":"AD-3 account deletion","trigger_condition":"Deletion while a send is claimed/in flight","guard_snippet":"USER.status='deleting' first; claim requires active","potential_consequence":"Email after deletion request"},
{"lens":"edge-case-hunter","location":"AD-3 cross-schema writes","trigger_condition":"EVENT_REPORT commits but REVIEW_ITEM write fails","guard_snippet":"write REVIEW_ITEM first with report_ref idempotency key; retry unlinked","potential_consequence":"Lost report or orphan review item"},
{"lens":"edge-case-hunter","location":"AD-3 no FKs","trigger_condition":"Catalog event removed/archived while personal rows reference it","guard_snippet":"emit removed/archived state change; propagation cancels; readers treat missing as tombstone","potential_consequence":"Dangling references, broken Detail Screens"},
{"lens":"edge-case-hunter","location":"AD-14 merge","trigger_condition":"Editorial merges two separately saved event_ids","guard_snippet":"merged_into state change; propagation re-points and dedupes per user","potential_consequence":"Duplicate reminders"},
{"lens":"edge-case-hunter","location":"AD-8 / Conventions confidence","trigger_condition":"0.695 rounds to 0.70 in numeric(3,2)","guard_snippet":"quantize once in confidence.py (ROUND_HALF_DOWN), gate on stored value","potential_consequence":"Below-gate event auto-published"},
{"lens":"edge-case-hunter","location":"AD-8 fallback","trigger_condition":"'2 consecutive failures' scope undefined (call/source/record)","guard_snippet":"counter per source_id, reset on success; poison record quarantines record not source","potential_consequence":"One bad page pauses a source, or a failing source never pauses"},
{"lens":"edge-case-hunter","location":"AD-8 paused source","trigger_condition":"No resume path for a paused source with live events","guard_snippet":"auto-probe every N min; full state re-poll on resume","potential_consequence":"Cancellations missed; FR-53 4h SLA broken"},
{"lens":"edge-case-hunter","location":"AD-8 cost row","trigger_condition":"Call fails after consuming tokens — no result transaction","guard_snippet":"cost row in its own transaction from usage (or estimate on error)","potential_consequence":"Failed/fallback calls uncosted"},
{"lens":"edge-case-hunter","location":"AD-7 broker jobs","trigger_condition":"Task exceeds Redis visibility_timeout or worker dies pre-ack","guard_snippet":"acks_late; visibility_timeout > max runtime; idempotent tasks","potential_consequence":"Long jobs run twice or vanish"},
{"lens":"edge-case-hunter","location":"AD-16 default plan","trigger_condition":"PERSONAL_EVENT commits, attach-default-plan fails","guard_snippet":"one transaction.atomic(using='personal') for both","potential_consequence":"Personal event with no reminders"},
{"lens":"edge-case-hunter","location":"AD-18 ICS","trigger_condition":"Upstream event deleted/moved, or URL returns 404/410","guard_snippet":"missing UID → delete + cancel sends; 404/410 → revoke credential, stop asserting conflicts","potential_consequence":"Reminders/conflicts for removed events"},
{"lens":"edge-case-hunter","location":"AD-15 retention sweep","trigger_condition":"Sweep interrupted midway","guard_snippet":"per-table idempotent batches with checkpoint; deletion completes only when all tables report done","potential_consequence":"Partial purge breaks 30-day guarantee undetected"}
]
```

## Lens: structure

**Purpose:** a lookup reference for epic and story authors and builders. **Model:** Reference/Database, with an Explanation opener. **Length:** 6,396 words.

| # | Location | Recommendation | Rationale |
| --- | --- | --- | --- |
| 1 | §Invariants & Rules | Add a compact AD index table (AD, one-line rule, concern group, key Binds). Keep the numbers stable. | No overview of 20 ADs; related rules sit far apart. ~+150 words |
| 2 | AD-20 lines 214–257 | MOVE the whole-system diagram to the end of Design Paradigm or the start of Structural Seed, with a caption. | The main system picture is filed under an email rule |
| 3 | AD-3 spike, AD-8 FR-14 note, Stack Open pins, OQ-3/OQ-6 | MERGE into Open Questions, plus a "PRD amendments required" list. Leave cross-refs at the original spots. | Blockers are scattered across 5 places |
| 4 | §Open Questions | CUT the resolved OQ-1 to OQ-4 rows (the decisions live in ADs, the history in memlog). Fold OQ-3's remaining action into OQ-6. Sort the rows. | Revision history and redundancy. ~-155 words |
| 5 | Conventions "new nouns" vs OQ-6 vs AD-10 | One authoritative list of 4 new nouns | The two lists have already drifted |
| 6 | AD-16 table vs Core entities | Add a Schema column to AD-16 and point Core entities to it. State the `catalog` app's role. | `EVENT_FIT` has already drifted |
| 7 | Capability Map | MOVE it near the top. Replace `web` with `frontend`. | It's the most-used lookup for downstream readers |
| 8 | Conventions UI / Theming / Motion | CONDENSE to one row pointing at DESIGN.md and EXPERIENCE.md | It copies UX design details, which will drift. ~-100 words |
| 9 | Conventions State mutation / Auth / Tests / thresholds | CONDENSE to the convention plus (AD-n). Keep the Confidence row. | Redundant with the ADs. ~-60 words |
| 10 | Design Paradigm vs AD-1 | CONDENSE AD-1 to only what's new in it | Repeats the overview. ~-50 words |
| 11 | AD-7 | MOVE the django-celery-beat version rationale to Stack "Not used" | Version detail inside an invariant, and duplicated |
| 12 | AD-8 embeddings | MOVE the quantization tuning to Stack or Deferred | Detail too early for an invariant |
| 13 | Deployment & environments | CONDENSE rows to choice plus constraint, and the cron paragraph to one line. PRESERVE the Launch gate. | Decision-record content. ~-140 words |
| 14 | AD-19 last sentence; Deferred vector store | CUT the narration of how decisions changed | History doesn't help builders |
| 15 | AD-10 | Keep the Risk 11 phrase once. Drop the "projection" repeat from AD-10. | Redundant within one AD |
| 16 | Confidence Pulse vs Relevance Pulse | QUESTION: define the relationship, or pick the Glossary term | An undefined synonym in a doc that bans synonyms |
| 17 | Deployment diagram "OQ-4" | Relabel it "2 streams (AD-20)" | Stale cross-reference |
| 18 | AD headings `[ADOPTED]` | State it once, or put it in the index. Tag only exceptions. | Easier to scan |
| — | Top callout, layer table and diagrams, ER diagram, AD-10 "Why both exist", Binds and Capability Map | PRESERVE | They help comprehension |

Net if all are accepted: about −540 words (−8.4%). The highest-impact changes don't depend on cuts: #1, #2, #3 and #6.

## Lens: prose (after structure)

Voice to preserve: terse and declarative, bold on the load-bearing parts, labelled sub-rules.

| # | Location | Original | Revised / question | Why |
| --- | --- | --- | --- | --- |
| 1 | Launch gate and every Vercel mention | Vercel plan must be on **Pro before the Pro tier's Stripe checkout** | "Vercel Pro plan before Stripe checkout for the EventPulse24 Pro tier" | "Pro" names two different things |
| 2 | Design Paradigm ¶2, first diagram, source tree | worker runtime (long-lived loop) / management command loop | "Celery worker and beat" | The process model contradicts AD-7 |
| 3 | AD-2 Prevents | the wall is a convention | the module boundary is a convention | "the wall" means the schema boundary elsewhere |
| 4 | AD-3 Rule | Composition happens in the application layer | Data from both schemas is combined in the application layer | Collides with digest composition |
| 5 | AD-2, 5, 14, 16; diagram | published service interface / named command / ingestion services / commands | Choose one term for the boundary and one for what it exposes | One write path has five names |
| 6 | AD-8 confidence gate | <0.5 auto-rejects; <0.7 routes… The threshold lives… | 0.5 to <0.7 routes…; Both thresholds live… | Overlapping ranges; there are two thresholds |
| 7 | AD-7 key | `scheduled_for` / `slot` | Name it `due_at` and define `slot` | The key fields are undefined |
| 8 | AD-4, AD-14 | `state_history` | `state_history` (`EVENT_STATE_CHANGE` rows) | Link the two names |
| 9 | AD-11 Prevents | discovering… ceiling…, and protecting the budget | "…and long work eroding the read-path latency budget" | Not parallel |
| 10 | AD-20 Prevents | Opens with a design statement | Open with the failure | Matches every other Prevents line |
| 11 | AD-1 Prevents | — which PRD §10.5 classifies as SEV-1 | Clarify the antecedent (and see the adversarial finding: the claim is wrong) | Ambiguous "which" |
| 12 | AD-3 Accepted cost | this is the direct consequence of AD-17's… | "AD-17's propagation rule follows directly from this cost" | Causality reads backwards |
| 13 | AD-18 Prevents | when Google classifies it | even though Google classifies it | Concession, not time |
| 14 | AD-8 embeddings | directs to Voyage AI | recommends Voyage AI | Missing object |
| 15 | AD-7 quiet hours | never re-delivered next day | "moves to the end of the quiet-hours window; never dropped, never sent twice" | Ambiguous |
| 16 | AD-16 | hardcode the default plan as 1d + 1hr | specify… two reminders: 1 day and 1 hour before the start | Specs specify; code hardcodes |
| 17 | Conventions i18n | English-only catalogue | English-only message catalog | Collides with `catalog`; US spelling |
| 18 | Stack Python | the only version… both declare | the newest version… both support | Factually wrong |
| 19 | Stack intro | The code owns these once it exists | "Once code exists, its lockfiles are the source of truth" | Ambiguous |
| 20 | AD-5 | writes to the database directly | writes outside a named command | The Postgres adapter does write directly |
| 21 | AD-10 Why both exist | forbids that surface depending | forbids that surface from depending | Grammar |
| 22 | AD-10 durability | renders no explanation rather than recomputing one if none exists | "if none exists, renders no explanation rather than computing one" | Logic and parse order |
| 23 | AD-15 | all three paths | name them (retention sweep, deletion, export) | Reader has to count back |
| 24 | AD-12 | cold-start acquisition path | marketplace cold-start acquisition path | Collides with the hosting sense of "cold start" |
| 25 | Conventions Errors | defined in `domain/` | Choose `domain/` or `shared/` | Two homes |
| 26 | AD-8 fallback | after 2 consecutive failures | after two consecutive fallback failures | What fails is unclear; spell out the number |
| 27 | Conventions Error shape | the UX spine's voice | the voice in EXPERIENCE.md | "UX spine" is undefined |
| 28 | Open pins | Claude 4.7+ use… ~30% | Claude models from 4.7 onward use… about 30% | Mechanics |
| 29 | AD-7 | the entire ±5 min budget | ±5-minute delivery budget (PRD §10.4). Also unify Celery Beat / beat scheduler / beat process and define "tick". | Undefined source; three names for one component |
| 30 | Design Paradigm ¶2; AD-6 | Two backend deploys —; All instants stored | There are two…; All instants are stored | Fragments |
| 31 | Various | Ids, modelled, per-model, e.g., 200/202, + | IDs, modeled, per model, for example, 200 or 202, and | Microsoft style mechanics |
| 32 | Various | <500ms, ≤60s, 24h, 1hr | <500 ms, ≤60 seconds, 24 hours | Units are written four ways |
| 33 | AD-7, AD-20 Binds | FR-9–12, FR-5–8 | FR-5–8, FR-9–12 | Ordering |
| 34 | AD-3 Enforcement | with different `search_path`… roles `GRANT` | "each with its own `search_path`… each role is granted privileges…" | Agreement; SQL used as a verb |
| 35 | Layer table, AD-1, AD-19 | three names for the generated client | "the generated OpenAPI client" everywhere | One artifact, three names |
| 36 | Headings | Invariants & Rules | Invariants and rules (sentence case) | Low priority; apply after the structure changes |

---

# Re-review after pulling `main` (2026-10-27)

`ARCHITECTURE-SPINE.md` is **byte-identical** to the reviewed version: its last commit is still 17551d8. Every finding above still stands. The pull changed the spine's **sources**: the PRD (Amendment A-8), the addendum, and DESIGN.md / EXPERIENCE.md (UX amendments A-9 to A-21, including 14 routes). It also added `traceability/TRACEABILITY.md`. This section reviews the unchanged spine against those updated sources.

## Spine is now stale against its sources

```json
[
{"lens":"adversarial","location":"frontmatter scope / binds; Capability Map","trigger_condition":"PRD Amendment A-8 (2026-09-06) lifts FR-32 Timeline and FR-33 Conflict-Aware Scheduling to MVP (45 MVP FRs). Spine still says '43 MVP FRs', binds FR-1..30 + FR-48..60, and has no Capability Map row for either (TRACEABILITY.md Section B: 2 MISSING).","guard_snippet":"Update scope to 45 FRs; add FR-32, FR-33 to binds; add Capability Map rows (personalization + frontend; AD-3, AD-6, AD-10, AD-16, AD-17).","potential_consequence":"Epics for two MVP features are written with no governing AD, so the cross-wall logic below gets invented per story."},
{"lens":"adversarial","location":"AD-3 / AD-16 vs FR-33 (A-8)","trigger_condition":"FR-33 detects overlap between a saved PUBLIC event (catalog) and a saved PERSONAL event (personal), >15 min in UTC, and keeps an immutable history of conflict pairs for /conflicts. Spine has no conflict-pair entity, no owner, no retention category, and no statement of where the cross-wall comparison runs.","guard_snippet":"Add CONFLICT_PAIR (personal schema; owner personalization; catalog event_id by value, no FK; retention category), with the UTC overlap rule in domain/conflict.py; ConflictResolution recorded per pair.","potential_consequence":"Builders join across the wall, which AD-3 makes impossible, or each surface (Pulse Card, Timeline, /conflicts) computes conflicts separately and the symmetric indicator disagrees."},
{"lens":"edge-case-hunter","location":"AD-17 vs FR-33 edge case (c)","trigger_condition":"FR-33 requires conflict recompute on cancel/postpone/move (indicator removed from a cancelled or moved partner). AD-17 propagation only rewrites SCHEDULED_SEND (delivery). Nothing re-evaluates conflict pairs.","guard_snippet":"AD-17: propagation fans out to every personal-side consumer of event time — delivery (sends) and personalization (conflict pairs, cached cards).","potential_consequence":"A cancelled concert keeps showing a conflict marker against the user's dinner, and /conflicts shows a stale active count."},
{"lens":"adversarial","location":"AD-10 vs UX A-10/A-11/A-12 Browse (/browse)","trigger_condition":"New authed /browse route lists ALL public events in the city (today+7d) with why-tags and tag:<token> search. Those events have no DIGEST_COMPOSITION for the user, so AD-10 leaves two options: show no explanation, or fall back to Event Fit, which AD-10 forbids on authenticated surfaces.","guard_snippet":"Decide in AD-10: either Browse is a sanctioned Event-Fit surface (and say so explicitly with its own indicator), or Browse cards carry no tags/indicator. Also: Browse has no PRD FR. Get one added, or record it as a UX-only amendment.","potential_consequence":"The first Browse builder silently substitutes Event Fit for Relevance Pulse — the trust-collapse failure AD-10 names."},
{"lens":"adversarial","location":"Capability Map / Stack vs Browse keyword search (A-11)","trigger_condition":"Inline keyword search with AND-matched tokens over headline/where/why-tags is a catalog read capability the spine never mentions (no search index, no latency budget, no owner).","guard_snippet":"Name the mechanism (e.g. Postgres full-text/trigram on catalog, owned by the catalog read app) and hold it to the PRD §11.1 read API <300 ms p95.","potential_consequence":"Ad-hoc ILIKE scans over the event table, or a search dependency added without a spine decision."},
{"lens":"adversarial","location":"AD-14 / Conventions Auth / AD-18 vs UX A-20 (/signin, /signup, /reset-password)","trigger_condition":"UX now locks email+password sign-in, password reset, an account-enumeration rule, AND an 'OAuth stack' (Google/Apple/Outlook) on /signup. The spine only says django.contrib.auth; it has no social-login provider, no reset-token flow, and AD-18 says MVP calendar is ICS-only. It's unclear if the signup OAuth is identity, calendar, or both (aria-label says 'Continue with calendar provider').","guard_snippet":"Add an identity AD: auth methods at MVP, the library (e.g. django-allauth) or hand-rolled choice, whether provider OAuth grants calendar scope, password-reset token lifetime, and enumeration-safe responses at the API edge (not just the UI).","potential_consequence":"Either OAuth calendar scopes sneak back in through signup, reopening the CASA/verification question OQ-1 closed, or identity gets built three different ways."},
{"lens":"adversarial","location":"AD-18 vs PRD FR-3 / FR-50 / A-7 (still unamended)","trigger_condition":"After the pull, the PRD still specifies Google OAuth 2.0, Apple CalDAV, and Microsoft Graph (FR-3, FR-50, A-7). Spine AD-18 ships ICS-only. The earlier finding is unchanged, but the UX OAuth stack now makes the gap visible in mockups.","guard_snippet":"Land the FR-3/FR-50 amendment, or reopen AD-18.","potential_consequence":"Three documents disagree on how calendars connect."},
{"lens":"adversarial","location":"Conventions 'Ids' vs UX route /events/:id","trigger_condition":"Spine: public event URLs use a slug, never the primary key. UX route table: public, anon-readable /events/:id (plus /p/:slug for share links).","guard_snippet":"State that :id in /events/:id is the public slug, or change the route to /events/:slug.","potential_consequence":"UUIDv7 PKs leak into public SEO URLs (and creation-time ordering with them)."},
{"lens":"edge-case-hunter","location":"AD-15 / FR-52 vs UX A-17 export modal","trigger_condition":"Export eligibility now depends on the user's jurisdiction (free in EU/UK/CA/BR/AU, Pro elsewhere). Download link expires after 7 days. The spine has no jurisdiction attribute, no source for it (geo-IP vs. declared), and no DATA_EXPORT artifact entity or retention.","guard_snippet":"Add USER.jurisdiction with a defined source and an update rule; add a DATA_EXPORT entity (personal, owner identity, 7-day link expiry, retention category).","potential_consequence":"A VPN or travel changes a user's legal entitlement, or export archives linger with no retention sweep."},
{"lens":"adversarial","location":"Spine vs amendment ledger","trigger_condition":"The word 'Amendment' does not appear in the spine. The PRD is at A-8 and UX at A-21, on independent counters (TRACEABILITY.md ledger).","guard_snippet":"Add a 'Sources as of' line naming the PRD/UX amendment levels the spine was reconciled against.","potential_consequence":"No one can tell which source amendments the spine has absorbed."}
]
```

## Still unaddressed after the pull (verified)

- **AD-8 model order:** the spine still says Sonnet is primary; the memlog says Haiku.
- **Reminder Plan default:** the PRD Glossary still says 5d, 2d, 1d, 1hr (prd.md:212), while FR-9 and FR-20 say 1d + 1hr.
- **FR-3 and FR-50:** still specify OAuth, CalDAV and Microsoft Graph.
- **Everything else above** stands, because the spine text is unchanged.

---

# Must-fix pass applied (2026-10-27)

| # | Must-fix | Where it was fixed |
| --- | --- | --- |
| 1 | AD-8 model order | Spine AD-8 and Stack row: Haiku primary, Sonnet fallback, three accepted risks, gates marked as tuning anchors |
| 2 | FR-32 / FR-33 coverage | Spine frontmatter (45 FRs, binds), new **AD-21**, `SAVED_EVENT` and `CONFLICT_PAIR` entities, ownership table, ERD, schema lists, Capability Map rows |
| 3 | AD-17 cross-schema transaction and lost propagation | Spine AD-17 rewritten: `personal`-only claim plus `event_version` check and `held_for_propagation`; `EVENT_STATE_CHANGE` outbox with reconciler; versioned, idempotent per-user application; residual window named as accepted cost. AD-4 adds `superseded_by` for postponements beyond ±30 days |
| 4 | AD-7 idempotency key | Spine AD-7 "Rule (send key)": minted once, per-kind shapes, recompute never rekeys |
| 5 | Calendar / login decision | Spine AD-18: identity-only OIDC sign-in, `CALENDAR_CONNECTION` entity, Secrets row. PRD **Amendment A-9**: FR-3, FR-50, UJ-2, UJ-3, FR-31 note, Open Q #2, §10.2, §11.2 changed to ICS/webcal at MVP |
| 6 | Glossary Reminder Plan default | PRD §3 Glossary: default is 1d + 1hr (A-9) |

**Still open (outside these documents):** `EXPERIENCE.md` `/signup` still labels the OAuth stack "Continue with calendar provider" and cites calendar-connect parity. It needs a UX amendment saying the stack is identity-only. The should-fix and later items above are untouched.
