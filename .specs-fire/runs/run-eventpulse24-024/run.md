---
id: run-eventpulse24-024
scope: wide
work_items:
  - id: city-canonicalization
    intent: public-pages-and-seo
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: public-event-read-by-slug
    intent: public-pages-and-seo
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: schema-org-jsonld
    intent: public-pages-and-seo
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: city-page-read-api
    intent: public-pages-and-seo
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: revalidation-signal
    intent: public-pages-and-seo
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: frontend-public-event-page
    intent: public-pages-and-seo
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: frontend-city-page
    intent: public-pages-and-seo
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: sitemap-and-robots
    intent: public-pages-and-seo
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: share-control
    intent: public-pages-and-seo
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: e2e-proof-and-contract-tests
    intent: public-pages-and-seo
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-11-01T15:18:49.012Z
completed: 2026-11-04T11:56:14.537Z
---

# Run: run-eventpulse24-024

## Scope
wide (10 work items)

## Work Items
1. **city-canonicalization** (validate) — completed
2. **public-event-read-by-slug** (confirm) — completed
3. **schema-org-jsonld** (confirm) — completed
4. **city-page-read-api** (confirm) — completed
5. **revalidation-signal** (validate) — completed
6. **frontend-public-event-page** (confirm) — completed
7. **frontend-city-page** (confirm) — completed
8. **sitemap-and-robots** (confirm) — completed
9. **share-control** (validate) — completed
10. **e2e-proof-and-contract-tests** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `backend/tests/e2e/public_pages_fixtures.py`: The catalog the public-pages proof walks: cities, published events, an in_review event, current Event Fit rows, and the way to move an event on so a fit row falls stale behind it.
- `backend/tests/e2e/test_public_pages_proof.py`: The 34-test backend proof of the anonymous public path: no cookie jar at any hop, the JSON-LD in the server-rendered HTML, structured data agreeing with the rendered page, the revalidation round trip without a timer, the stale fit absent from the city page, in_review invisible from every direction, the sitemap with no 404s, and the authed surfaces unbroken.
- `backend/tests/e2e/test_public_pages_contract.py`: The 28-test contract file asserting on the source of the eight public modules: the public reads carry no session at all, the authed reads do, the branch sits where it should, and the canonical URL and the noindex live in the right branch.
- `backend/tests/e2e/test_contract_stripper_proof.py`: The 17-test proof of the contract file's own comment stripper: it removes comments and nothing else, and it reaches the end of every asserted file.
- `backend/tests/e2e/mutation_probe_public_pages_e2e.py`: The 9-probe harness that plants a bug in each guarded behaviour and refuses to count a suite run that could not run as a catch.
- `frontend/tests/public-crawl-proof.test.tsx`: The 24-test frontend crawl proof: the anonymous hop from the city page to the event page, the JSON-LD in the server-rendered markup, the Save to Pulse CTA, and the noindex and canonical in the right branch.

## Files Modified
- `backend/tests/e2e/conftest.py`: Added the revalidation outbox's broker seam, so the proof can assert the revalidation round trip without waiting for a timer.
- `.specsmd/fire/agents/builder/skills/run-execute/scripts/complete-run.cjs`: Promoted the intent's own status in state.yaml from its work items, so a finished intent no longer reads `in_progress`. The expected status is derived, not asserted, so it cannot drift from the work items.

## Decisions
- **How to make 'no session' structural rather than incidental**: A separate proof suite with its own cookie-less HTTP client, rather than omitting a login step from the existing authed suite. (Omitting a login step is a step a later change can silently restore. A client with no cookie jar at all cannot be signed in by accident, so the assertion survives refactoring.)
- **How to prove each assertion can fail**: Plant a CALL - not an import - in each guarded behaviour, run the exact suite named, and require a real test failure rather than any non-zero exit code. (A suite that could not be collected is a false green: it did not catch the bug, it failed to run. The harness reads the exit code and the output, and a run that collected no tests is reported as a failure to catch.)
- **How to assert on source text without the comments**: A string- and regex-aware scanner rather than a pair of regexes. (The regex stripper ate the tail of any URL and truncated a file at the first regex literal whose body holds a //. One of the eight asserted modules carries a regex literal, so this was a live trap rather than a theoretical one.)
- **Whether to build the stale EventFit row by writing a wrong version**: Build it the way it really happens - move the event on through the write path, and let the fit fall behind. (A helper that could write a deliberately wrong event_version describes a row the write path can never produce, and it would have been a second, wrong way to say the same thing.)
- **How to assert the JSON-LD is crawlable**: Assert against the server-rendered markup with JavaScript disabled, parsing the ld+json script out of the HTML and validating it as a Schema.org Event. (The crawler's actual conditions are no JavaScript and server-rendered HTML. A test that renders the page in jsdom with scripts running would prove something the crawler never sees.)


## Summary

- Work items completed: 10
- Files created: 6
- Files modified: 1
- Tests added: 103
- Coverage: 99.05%
- Completed: 2026-11-04T11:56:14.537Z
