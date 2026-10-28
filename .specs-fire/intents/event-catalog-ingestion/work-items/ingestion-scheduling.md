---
id: ingestion-scheduling
title: Ingestion Scheduling & Freshness
intent: event-catalog-ingestion
complexity: medium
mode: confirm
status: pending
depends_on: [ingest-pipeline-and-lifecycle]
created: 2026-10-28
---

# Work Item: Ingestion Scheduling & Freshness

## Description

Run sources on their declared cadence from the existing single 60s beat tick, as Celery pipeline jobs (AD-7, AD-11). Flag sources that have gone stale (FR-13), and add a manual trigger for operators and local development.

## Acceptance Criteria

- [ ] `worker.tasks.tick` calls a "find due sources" step. It selects active sources whose `last_ingested_at + cadence <= now` (never-ingested sources included) and enqueues one `ingest_source` Celery job per due source.
- [ ] `beat_schedule` stays exactly one 60s tick, and `tests/worker/test_tick.py` is unchanged and green.
- [ ] No double runs: a source already queued or running is not enqueued again by later ticks. Use a claim timestamp or lock on `Source`, or the pipeline's own concurrency guard. Two concurrent workers never ingest the same source at once.
- [ ] Freshness: the tick flags any active source with no successful ingestion within 2× its expected cadence. The flag is visible in admin, and it clears on the next success.
- [ ] Management command `manage.py ingest_source <source_id> [--sync]` runs one source immediately, inline or enqueued.
- [ ] The worker job wraps the `ingestion` command only. The worker never imports an API module (contract `worker-not-api`).
- [ ] Tests cover:
  - due selection at cadence boundaries
  - a paused source is never due
  - no duplicate enqueue across two ticks
  - stale flagging at exactly 2× cadence
  - the management command
  - `beat_schedule` unchanged

## Technical Notes

- **Spine references:** AD-7 (the tick is Celery Beat, never a platform cron; the broker carries pipeline jobs), AD-11, AD-1 (worker runtime separation).
- **Clock control:** use time freezing in tests; the testing standards require explicit UTC.

## Dependencies

- ingest-pipeline-and-lifecycle
