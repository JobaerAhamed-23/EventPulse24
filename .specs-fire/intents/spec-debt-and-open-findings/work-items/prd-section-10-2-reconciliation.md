---
id: prd-section-10-2-reconciliation
title: §10.2 publishes two retention windows that do not exist and one opt-out
  that is not configured
intent: spec-debt-and-open-findings
complexity: low
mode: confirm
status: completed
depends_on: []
created: 2026-11-20
run_id: run-eventpulse24-056
completed_at: 2026-11-20T12:16:25.129Z
---

# Work Item: Make §10.2 true

## Description

Two findings from run-055, both in the PRD rather than the code. **No code changes here** —
this item is amendments, and it comes first because the inventory work item publishes §10.2
to users.

### A-27 — the two retention categories that have no models

§10.2 publishes nine categories. `RetentionCategory` declares nine. **Seven are used.**

| Category | §10.2 promises | Reality |
|---|---|---|
| `EMAIL_DELIVERY_EVENTS` | *"sent, opened, clicked: retained 90 days for spam-complaint monitoring; aggregated counts beyond"* | **No model.** `apps/delivery/email_api.py` records that the storage behind SM-2 "is not" built |
| `ANALYTICS_AGGREGATES` | *"retained indefinitely (no PII)"* | **No model**, and no analytics vendor anywhere — no PostHog, Segment, Mixpanel, Sentry or GA |

**The product collects less than the PRD says it does.** That is the right direction for a
mistake to run, and it is still a mistake: `/privacy` publishes this list to users, and a
document promising to retain open-and-click data for 90 days describes surveillance that
does not happen.

**The enum members stay.** `deletion.py` references both — `EMAIL_DELIVERY_EVENTS` is in
`PURGED_CATEGORIES` and `ANALYTICS_AGGREGATES` in `UNTOUCHED_CATEGORIES` — and the walk
test asserts every category is classified. Removing them would be a code change with a
migration-shaped blast radius, to delete two lines of foresight. **A-27 corrects the
document and leaves the registry ready.**

### A-28 — the training-opt-out sentence

> *"Where the LLM provider's terms permit opt-out of training-data retention, the system
> is configured to opt out at the API level."*

**`adapters/llm/voyage.py` configures no such thing.** The adapter posts `input`,
`model`, `input_type` and `dimensions` to `/v1/embeddings`; there is no retention or
training parameter, and no account-level setting is recorded anywhere in the repo.

**The exposure is genuinely small, and the sentence is still false.** `embed_event()`
sends `event_embedding_text(title=…, description=…)` from the public `Event` row — public
listings, not personal data. So the clause guards against something that cannot currently
happen. But it is written as a statement of fact about configuration, and §10.2 is the
document a due-diligence questionnaire gets answered from.

**A-28 states what is true and what would make the original sentence true**, rather than
deleting the commitment: no personal data reaches the provider; no opt-out is configured;
if personal data is ever embedded, the opt-out becomes a prerequisite rather than a
nicety.

## Acceptance Criteria

- [ ] **A-27** at §10.2 in `prd.md`: both categories withdrawn from the published list,
      with the evidence (no model declares them; no analytics vendor exists) and the note
      that the enum members remain because `deletion.py` classifies them
- [ ] **A-28** at §10.2: the opt-out sentence corrected to the verified position, naming
      `adapters/llm/voyage.py` and `embed_event()`, and stating the condition under which
      a real opt-out becomes required
- [ ] A-27 and A-28 follow A-25 and A-26's inline form, dated, with reasoning
- [ ] A-26 is the highest number currently in use — **verified before writing**, including
      inside `EXPERIENCE.md`'s `updated_note`
- [ ] `TRACEABILITY.md` F-6 and F-7 marked closed, naming the amendments
- [ ] **No code changes.** If this item touches a `.py` or `.tsx` file, its scope has
      slipped

## Technical Notes

- §10.5's regulatory tables are **not** amended. They require a privacy policy to exist
  and say what it must disclose; they make no claim about these two categories.
- The published retention table on `/privacy` already omits both, so **A-27 brings the PRD
  into line with the page**, not the other way round. Say so in the amendment: the page
  was written from the registry and found the divergence.

## Dependencies

(none)
