---
id: project-scaffold
title: Project Scaffold & Architecture Enforcement
status: completed
created: 2026-10-27
completed_at: 2026-10-28T04:32:34.614Z
---

# Intent: Project Scaffold & Architecture Enforcement

## Goal

A runnable, architecture-enforced base for EventPulse24. Backend and frontend skeletons that every later feature intent builds on, running locally on **Ubuntu and macOS with the same setup**.

## Users

The developer (working on an Ubuntu 20.04 machine and a Mac) and any AI agent writing code in this repo.

## Problem

There is no code yet. Without enforced boundaries from the first commit, the Architecture Spine's invariants (AD-1..AD-21) turn into suggestions that later code silently violates. Without a repeatable local setup, the two development machines drift apart. Ubuntu 20.04 also cannot easily install PostgreSQL 18 + pgvector natively, and this machine already runs PG12 (:5432), PG16 (:5434) and Redis (:6379), which must not be disturbed.

## Success Criteria

- On **both** Ubuntu and macOS, `docker compose up -d` + `make dev` brings up:
  - Postgres 18 + pgvector, Redis and Mailpit in Docker
  - the Django API, Celery worker, Celery beat and Next.js on the host
- A `/health` request flows Next.js → generated TS client → Django Ninja → both DB schemas (`catalog`, `personal`), and the page renders the result
- AD-3 spike: the two-`DATABASES` router migrates both schemas correctly under Django 6.1, and a test proves a cross-schema FK/join is refused
- `import-linter` contracts pass, and a test proves they catch a deliberate violation (AD-2)
- `manage.py check` fails when a model holding user data declares no retention category (AD-15)
- Celery beat fires a static 60s no-op tick that the worker executes (AD-7 seed)
- Shared foundations exist:
  - domain error types + one Ninja exception handler with the `{code, message, details?}` shape
  - UUIDv7 ids
  - pydantic-settings config
  - a JSON logger with an allowlist redaction (AD-13)
  - the design-token CSS layer
- GitHub Actions CI runs every gate and passes
- `docs/setup/macos.md`, `docs/setup/ubuntu.md`, `scripts/doctor.sh` and a README quick start exist and have been followed successfully

## Constraints

- Hybrid local dev: infrastructure in Docker Compose, app processes native with hot reload
- Docker ports chosen to avoid existing services: Postgres **5440** (5433 turned out to be taken by the `pgdb_books` container), Redis **6380**, Mailpit **1025** (SMTP) / **8025** (UI). All connection settings come from `.env`, so a native PG18 + pgvector can be swapped in via `DATABASE_URL` alone.
- `pgvector/pgvector:pg18` image (multi-arch: amd64 + Apple Silicon arm64)
- Python 3.13 via **uv**; Django 6.1.1, Django Ninja 1.7.0, Pydantic 2.13.5, Celery 5.6.3 (static `beat_schedule`, no `django-celery-beat`)
- Next.js 16.3 + React 19.2 + TypeScript 5 + Tailwind 4 via **pnpm**; no UI component library, no animation library
- Fake adapters for LLM, email and billing by default, so no API keys are needed to run locally
- No feature models or feature endpoints in this intent; only what the spike and the enforcement tests need
- Binding source: `_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md` and `.specs-fire/standards/`

## Notes

- Spine §AD-3 marks the `search_path`-per-connection + `allow_migrate` spike as **required before relied on**, so it is a first-class deliverable here.
- Neon, Vercel and Railway are out of scope; they belong to a later deployment intent.
