---
id: real-feeds-and-e2e-proof
title: Real Feeds & End-to-End Proof
intent: event-catalog-ingestion
complexity: medium
mode: confirm
status: completed
depends_on:
  - source-registry-commands-admin
  - ingestion-scheduling
  - public-catalog-read-api
created: 2026-10-28
run_id: run-eventpulse24-018
completed_at: 2026-10-28T16:59:11.153Z
---

# Work Item: Real Feeds & End-to-End Proof

## Description

Prove the whole intent end to end. An automated test runs from fixture source to catalog to API. In addition, 2–3 real, ToS-safe public feeds are registered and ingested on the local stack. Docs are updated so an operator can do the same on Ubuntu or macOS.

## Acceptance Criteria

- [ ] An end-to-end test (fake fetch adapter, all three methods):
  1. registers sources through commands
  2. runs the tick and lets the jobs execute (eager or inline)
  3. reads `GET /api/catalog/events` and asserts the expected events, tz fields and dedup results
  4. re-runs the tick and asserts nothing changes
- [ ] The user picks 2–3 real public feeds at the plan checkpoint. Each has a recorded ToS/robots note, and the set covers at least two of JSON-LD, RSS and ICS.
- [ ] The feeds are registered by an idempotent management command or seed, not a data migration, so CI never touches the network.
- [ ] **Editorial group (AD-14, handed on from run-eventpulse24-014):** the same idempotent command, or a sibling one, creates an `editorial` group with per-model permissions:
  - `add`/`change`/`view` on `ingestion.Source`, `ingestion.Venue` and `ingestion.TosReview`
  - `view` on `Event`, `EventStateChange` and `IngestionAuditEntry`

  The local operator account uses that group, not superuser. A test asserts the group's exact permission set.
- [ ] On the local stack (`docker compose up -d` + `make dev`), the real sources ingest via the worker, and events appear in admin and in the API.
- [ ] The run's walkthrough records the observed counts (new, rejected by reason, ambiguous, tz-review-pending).
- [ ] Live network calls are never part of CI. The real-feed check is a documented manual step.
- [ ] Docs:
  - a section in `README.md` or `docs/` on registering a source, triggering ingestion and reading the catalog API
  - the fake vs HTTP fetch adapter settings explained
- [ ] The full CI pipeline is green: lint, types, `import-linter`, tests, coverage gates, the OpenAPI/client contract check.
- [ ] The intent's success criteria are checked off in the walkthrough.

## Technical Notes

- **OQ-5 is still open:** the chosen feeds are local proof sources, not the launch corpus. The 40-source floor is untouched.
- **Respect the feeds:** use the source's declared cadence, an identifying user-agent, and no aggressive polling.

## Dependencies

- source-registry-commands-admin
- ingestion-scheduling
- public-catalog-read-api
