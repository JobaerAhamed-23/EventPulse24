---
id: schema-router-spike
title: AD-3 Schema Router Spike
intent: project-scaffold
complexity: high
mode: validate
status: completed
depends_on:
  - backend-skeleton
created: 2026-10-27
run_id: run-eventpulse24-003
completed_at: 2026-10-27T11:20:13.522Z
---

# Work Item: AD-3 Schema Router Spike

## Description

Prove — before anything relies on it — that the AD-3 data wall works under Django 6.1: public data in schema `catalog`, personal data in schema `personal`, exposed as two Django `DATABASES` entries on one Postgres with different `search_path`s, behind a database router, so the ORM itself refuses cross-schema relations and joins.

## Acceptance Criteria

- [ ] `DATABASES` has `default` (= `personal` schema) and `catalog` entries, each connecting with its own role and `options=-c search_path=<schema>` *(reworded per design D1a)*
- [ ] A database router maps each app to its schema (`ingestion`, `catalog`, `editorial` → `catalog`; `identity`, `personalization`, `delivery` → alias `default` (schema `personal`)) *(reworded per design D1a)* for `db_for_read`, `db_for_write`, `allow_relation`, `allow_migrate`
- [ ] `allow_relation` returns False across the two databases; Django's own tables (auth, contenttypes, sessions, admin) have an explicit, documented home
- [ ] `manage.py migrate --database=catalog` and `--database=default` each create tables only in their own schema (verified by querying `information_schema`)
- [ ] Test: a cross-schema FK between spike models is refused (ORM error / system check), and a cross-schema join cannot be expressed through the ORM
- [ ] Test: role `ep_catalog` cannot read `personal.*` and `ep_personal` cannot read `catalog.*` (permission denied)
- [ ] Test: `transaction.atomic(using=...)` is per-schema, documented as the accepted cost
- [ ] Spike models used only for tests live in a test app and are not shipped as features
- [ ] Findings (what worked, any Django 6.1 caveats) recorded in the run walkthrough and, if they change the rule, raised against the spine

## Technical Notes

- Spine AD-3: 'Spike required: confirm the search_path-per-connection pattern behaves correctly under Django 6.1 migrations (allow_migrate per database) before this is relied on.'
- Open decisions for the design doc: where `django.contrib.auth`/`User` lives (identity owns USER → `personal`), how `default` is used, migration role vs runtime roles, and test-database creation for two schemas in one Postgres.

## Dependencies

- backend-skeleton
