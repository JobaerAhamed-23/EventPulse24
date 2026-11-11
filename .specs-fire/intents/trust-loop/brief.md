---
id: trust-loop
title: Trust Loop — User Reports, Editorial Review Queue & Source Reliability
status: completed
created: 2026-11-10
completed_at: 2026-11-11T06:03:02.125Z
---

# Intent: Trust Loop — User Reports, Editorial Review Queue & Source Reliability

## Goal

Close the trust loop the PRD describes and the code has never had. A user can flag a bad event (**FR-59**), an editor can act on the flag (**FR-57**), and the editor's verdicts feed a per-Source reliability score (**FR-16**) that the Pulse Digest ranking finally consumes.

The three requirements are one mechanism, not three features. Reports and quarantined events feed the queue. Rejections and upheld reports feed the score. A collapsing score feeds the queue back. The score feeds ranking. Building any one of them alone leaves a half-loop with nothing to act on or nothing acting on it.

It is the only open MVP gap with no external blocker. FR-14's LLM path needs a real provider, FR-53 webhooks need OQ-5 sources, and the Pro tier needs billing. This intent builds entirely on ingestion, the Event model, the Detail Screen and the ranking domain, all of which have shipped.

## Users

- **The signed-in user who sees something wrong**: the wrong date, the wrong venue, an event that doesn't exist, or a duplicate. Today the Detail Screen gives them no way to say so. The product's "trust through transparency" principle currently runs in one direction only.
- **The editor or on-call engineer.** There is no queue, no Approve, Reject or Edit, and no way to release an event the system has already quarantined. The `editorial` app exists and is empty: `apps/editorial/__init__.py` says "Owns nothing; acts only through ingestion commands (AD-14)", and its `admin.py` and `models.py` are blank.
- **Every digest reader.** Ranking runs with a hole in it: `domain/ranking.py:28` reads "`source_reliability` — Absent — FR-16 is unbuilt; `Source` has no score field."

## Problem

- **Events can already get stuck, with no exit.** `domain/confidence.py` gates any event with `tz_inference_confidence < 0.70` to `Gate.IN_REVIEW`, which ingestion stores as `Event.publication_status = in_review`. The docstring says such an event is "stored, never in a digest until editorial review." No editorial review exists, so the event never comes out. Every public read (`catalog_read.py`, `event_fit/reads.py`, `digest_read.py`) correctly treats it as absent, so it is silently lost.
- **FR-59 and FR-57 are named but not built.** `apps/personalization/__init__.py:4` lists `EventReport` as owned, and `apps/ingestion/__init__.py:3` lists `ReviewItem`. Neither model exists. `event-catalog-ingestion` deferred the review queue as a "follow-up intent", and `event-state-sync` deferred it again ("Still open from `event-catalog-ingestion`").
- **FR-16 has no field, no job and no consumer.** `Source` carries no score, so the PRD's guardrails (Bayesian smoothing, the minimum-N threshold, spike detection) have nothing to run against, and ranking's 0.25 term is missing.

## Success Criteria

**FR-59: report this event**
- The Detail Screen's secondary action row gains a small flag action, not a primary button. It opens a modal with exactly four single-select categories: "Wrong date or time", "Wrong venue or address", "Doesn't exist or is cancelled", and "Duplicate of another event". There is no free-text field.
- One tap after choosing a category submits the report. The user sees the toast "Thanks — we'll review this."
- Each report creates an `EventReport` (user, event id, category, timestamp) in `personal`. It is capped at **5 per user per day**, declared through the existing throttle port rather than hand-rolled.
- **A report never changes the event's visibility.** It stays live in the digest and on public pages until an editor decides.

**FR-57: the editorial review queue**
- `ReviewItem` lives in `catalog` (owned by `ingestion`). It carries **no user identity** across the wall (AD-3). Its reason is one of:
  - `user_reported`: raised by an `EventReport`, with a 24-hour SLA.
  - `in_review`: any event in `publication_status = in_review`. This includes the timezone-confidence events already stranded, which get a backfill.
  - `source_reliability`: raised by the FR-16 escalation below. This item concerns a Source, not an Event.
- Several reports on one event collapse onto one open `ReviewItem` with a count. They do not create a stack of duplicates.
- The surface is **Django admin**, under a dedicated editorial group with per-model permissions and no routine superuser (AD-14). Editors can take three actions:
  - **Approve:** publish the event and close the item.
  - **Edit:** correct the fields, then publish.
  - **Reject:** a **soft reject**. The event moves to a non-public rejected publication state. It is never deleted.
- Every action goes through an `ingestion` command. If it changes a lifecycle field it bumps `event_version`, it is attributed to the acting editor, and it is appended to the audit history (AD-5, AD-14). The admin never calls `obj.save()`, following the pattern of the existing `apps/ingestion/admin.py`.
- When an action changes what saved users should know (a reject, or an edit that moves the time), it reaches them through the **existing AD-17 propagation path**, as a versioned `EventStateChange`, and is not wired up separately.
- The admin shows the queue size, the age of the oldest open item, and the user-reported items past their 24-hour SLA.

**FR-16: the source reliability score**
- Each `Source` carries a score in [0, 1]: the posterior mean of a beta-binomial model with **α = β = 5**. A new source starts at **0.50**.
- The score does not move until the source has **30 observations**. Below that, it can never drop below **0.32**.
- MVP inputs are **editorial rejects and upheld user reports** (negative) and **approvals** (positive). Dismissal rate (FR-25) is unbuilt. It is left as a documented, named input seam, not faked.
- The score is recomputed **at least weekly** by a scheduled job. Each recompute is recorded, so a week-over-week comparison is possible.
- **Escalation, never removal:** a source with a score below 0.3 and at least 30 observations, or one whose score falls 3× or more week over week, raises a `source_reliability` `ReviewItem`. A low score never pauses, removes or hides a source.
- `domain/ranking.py` consumes the real `source_reliability`. A test proves that a low-scoring source's event ranks below an otherwise-identical event from a high-scoring source in the Pulse Digest.

**Proof**
- An end-to-end test covers the whole chain: a user reports an event, a `ReviewItem` appears, an editor rejects it, the event leaves the digest, the source's observation count rises, and after enough rejects the score and the ranking move. Contract tests cover the new API and its regenerated `frontend/lib/api/schema.ts`.

## Constraints

- **AD-14:** `editorial` owns no tables. It reads `catalog` and writes only through `ingestion` services. Editors are authenticated actors with group and permission grants. Django admin is the MVP surface.
- **AD-3:** `EventReport` lives in `personal` and `ReviewItem` lives in `catalog`. The reference crosses the wall by id only, with no foreign key, and the `ReviewItem` holds no user identity.
- **AD-4:** `ingestion` remains the sole writer of `catalog`, including editorial edits and publication-state changes.
- **AD-5 / AD-17:** every write is a named command with an audit entry. Lifecycle-field changes bump `event_version` and propagate through the existing outbox and consumer.
- **Never delete.** Reject is a state, matching the codebase's existing practice: sources are paused rather than deleted, and the admin disables delete everywhere.
- **Four confidences, never conflated.** The Source Reliability Score is distinct from `extraction_confidence`, `tz_inference_confidence` and the Confidence Pulse. All thresholds (α, β, the minimum N, the floor, the 0.3 escalation line and the spike multiplier) live in `shared/constants.py`.
- **Calm, not punitive.** One report never hides an event, and a low score never removes a source.

**Out of scope:**
- **Free-text reports** (FR-57 and FR-59 put them in Phase 2).
- **The `extraction_confidence < 0.7` trigger.** Structured ingestion always writes `EXTRACTION_CONFIDENCE_STRUCTURED = 1.00` (`shared/constants.py:17`), so nothing reaches that gate until FR-14's LLM path ships. The queue accepts `in_review` events generically, so the LLM path will inherit it at no cost.
- **FR-25 dismissal signals** and the "less like this" prompt.
- **User-facing source blocking** (FR-16 Out of Scope).
- **FR-29 AI Cost Dashboard.** The queue metrics live in admin for now, and the dashboard can read them later.
- **Merging duplicates.** The "Duplicate" report category is recorded and queued, but the AD-14 "merge" editorial action is a later item.

## Notes

**Decisions taken during capture (2026-11-10):**

1. **This intent comes next**, ahead of the AD-17/AD-21 reinstated-conflict defect, FR-25, and settings/OIDC. It is the largest MVP gap with no external dependency.
2. **The editor surface is Django admin**, as AD-14 already specifies, and not a Next.js staff route.
3. **FR-16 runs on reports, rejects and approvals only.** Dismissal is a seam for FR-25.
4. **Reject is a soft reject.** This departs from FR-57's literal "deletes from registry" in favour of the codebase's never-delete, append-only practice. The PRD text should be amended to match.
5. **A report never hides an event.** One user, or a troll, cannot pull an event; only an editor can.

**Open, to settle during decomposition and design:**
- **The shape of the rejected state.** It could be a third `Event.PublicationStatus` value, or a lifecycle `Status` with a new `EventStateChange` kind. The second notifies saved users through AD-17 for free, but widens a seven-kind table that `LIFECYCLE_SEND_BEHAVIOUR` maps exhaustively.
- **What counts as an "upheld" report** for FR-16. It might be a report on an event the editor then rejected or edited, or a report whose category the editor confirms.
- **Where the score is stored.** It could be a field on `Source`, or a `SourceReliabilityScore` history table (a PRD Glossary term, per the Spine's naming row), which the week-over-week spike check needs anyway.
- **The PUBLISH_FLAGGED (`tz_review_pending`) events.** They are published and digest-eligible but flagged. Should they also get a low-priority `ReviewItem`, or stay out of the queue?

**Found during the proof (2026-11-11), deferred to a new work item:**

- **An editorially released event still cannot reach a Pulse Digest.** An editor can take a
  timezone-quarantined event out of `in_review`, and it becomes public — listed, reachable at
  its URL, in the sitemap. It is still absent from every digest, because
  `list_public_candidates` gates the pool on `tz_inference_confidence >= 0.70` and **no
  editorial command moves that column**: `approve_review_item` flips only
  `publication_status`, and `edit_and_publish` carries the old confidence through by design
  (`_incoming_for`: *"the gates stay where the pipeline put them"*), so even an editor
  correcting `start_time_tz` leaves it at 0.60. The only thing that lifts it is the pipeline
  seeing a clean resolution on a later poll — which needs the **source** to fix its own feed,
  the very situation the editor exists to work around. All three paths were probed. The
  behaviour is pinned by `tests/e2e/test_trust_loop_proof.py`
  (`TestTheStrandedEventGetsOut`), which asserts the defect and will fail when it is fixed.
  **Deciding which of the four confidences an editor's verdict may move is a design
  question**, which is why it is a work item and not a patch inside the proof.

**Carried forward, unresolved:** OQ-5 (the real source list and its ToS reviews), the beachhead city, the 40-source / 15-per-city launch floor (FR-13), the AD-17/AD-21 reinstated-conflict defect, and the matching PRD/Spine amendments named in `event-state-sync`.
