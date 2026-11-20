---
id: legal-copy-draft
title: Draft the Terms and Privacy copy from what the code actually does
intent: broken-links-and-legal-pages
complexity: medium
mode: confirm
status: pending
depends_on:
  - legal-page-routes
created: 2026-11-20
---

# Work Item: Copy that is true, and says it is a draft

## Description

Write the body of `/terms` and `/privacy`.

**The governing rule is that every claim is checked against running code.** A privacy policy
that overstates a product's discipline is worse than no policy: it converts an honest gap
into a false statement made to a user at the moment they are agreeing to it. Where the code
and the PRD disagree, **the code wins and the divergence is recorded** — exactly as A-25 did
for FR-22's formula.

**No binding legal text is produced here.** The output describes as-built behaviour in plain
language, carries the draft banner `legal-page-routes` builds, and goes to counsel
afterwards. Nothing in it may imply review has happened.

### This product can describe itself unusually well

The privacy document should be **generated from or verified against** the machine-readable
sources, not composed freehand:

- **`backend/shared/retention.py`** — `RetentionCategory` holds PRD §10.2's nine categories
  with their windows. System checks `eventpulse.E003/E004` fail the build on any concrete
  model lacking a valid category, and `tests/identity/test_deletion_retention_walk.py` walks
  the registry asserting every categorised model is classified. **A retention table derived
  from this enum is true by construction**, and `PRD_CATEGORIES` is already the tuple
  "the categories users see".
- **`DELETION_GRACE_PERIOD = timedelta(days=30)`** (`shared/constants.py:1065`) — the 30-day
  figure, and the live cancel-within-grace flow shipped in run-054.
- **`backend/adapters/`** — the complete list of who data reaches: Stripe (billing), SMTP
  (email), Voyage (embeddings), MinIO/S3 (blob), header-based geo, ICS fetch. Short, and
  worth stating plainly.
- **`apps/identity/services/data_export.py` + `export_serializer.py`** — FR-52 export, the
  "right to know" half of the compliance table.
- **`apps/identity/services/deletion.py`** — the retention walk, and its own documented
  honesty about the avatar surviving in the bucket for the grace period. **If the policy
  claims deletion is immediate, that comment proves it wrong.**

### Two commitments worth stating because they are kept

PRD §10.2 makes two absolutes that the code currently honours, and which most competitors
cannot write down: **no user-data model training**, and **no third-party data sales — "not
now, not ever."** State them, and state the LLM-provider training-opt-out configuration
only if it is actually configured — verify in `adapters/llm/` rather than assuming.

## Acceptance Criteria

- [ ] `/privacy` carries a retention table whose categories and windows **match
      `RetentionCategory`**, with a test that fails if the enum and the page diverge
- [ ] Every factual claim traces to code, and the work item's walkthrough lists claim →
      evidence. A claim with no evidence is cut, not softened
- [ ] The deletion section states the **30-day grace period** and is accurate about what
      survives it — including the avatar-in-bucket behaviour `deletion.py` documents, if it
      is still true at build time
- [ ] The third-party section lists the real adapters and no others
- [ ] Rights already built (export, deletion, correction, cancel-deletion) are described
      **with the routes a user actually uses**, not in the abstract
- [ ] `/terms` covers at minimum: what the service is, acceptable use, that public event
      data is third-party content governed by source ToS (FR-17), account termination, Pro
      billing and refunds as `adapters/billing/stripe.py` implements them, and disclaimers
      about event accuracy — **the product aggregates other people's listings and cannot
      guarantee them**
- [ ] Both documents state the draft status in their own text, not only in the banner
- [ ] Any gap found between PRD §10.2's promises and the code is **reported in the run, not
      papered over in the copy**
- [ ] Reading level is plain. A privacy policy nobody can read fails §10.2's own words:
      *"in plain language"*

## Technical Notes

- Start from PRD §10.2 and §10.5's regulatory table as a **checklist of what must be
  disclosed**, then write each disclosure from code. Do not paste the PRD; it is an internal
  planning document written in a different register.
- The jurisdictional copy in Amendment A-17 (export free in EU/UK/CA/BR/AU, Pro required
  elsewhere) is a live behaviour with user-visible consequences — the privacy page should
  not contradict it.
- Expect to find at least one divergence. The retention registry is enforced; prose promises
  elsewhere are not. **Finding one is a success, not a blocker.**

## Dependencies

- legal-page-routes
