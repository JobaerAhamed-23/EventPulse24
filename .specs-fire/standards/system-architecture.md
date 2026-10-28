# System Architecture

> Condensed from `_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md`. **The spine is authoritative.** Read it for full AD rules, rationale and accepted costs.

## Overview

EventPulse24 discovers events from many sources (global, national, local) using crawling and AI extraction. It deduplicates them into a canonical catalog and delivers each user a personalized Pulse Digest, reminders and state-change notices. Users also manage Personal Events, imported calendars, a Unified Timeline and conflict-aware scheduling. The MVP binds FR-1..30, FR-32..33 and FR-48..60.

## System Context

A web-first product. Anonymous visitors reach ISR'd public event pages (SEO acquisition). Signed-in users get a personalized digest, a timeline and reminders by email and in-app. Internal editorial and operations staff use Django admin.

### Context Diagram

```
browser ──► Vercel (Next.js) ──OpenAPI──► API runtime (Django Ninja) ──► Neon PG18 (catalog | personal)
                                              │
                                              └──► Stripe
worker runtime (Celery worker + beat) ──► Neon PG18
     ├──► Anthropic + Voyage (via one LLM gateway)
     ├──► email provider (transactional + bulk streams) ──► user inbox
     ├──► event sources (partnership · API · RSS/ICS · crawl)
     └──► ICS/webcal feeds (Google · Apple · Outlook)
Redis ── broker for tick + pipeline jobs only
```

### Users

- **Visitor**: anonymous. Browses public event pages and Pulse Preview (Event Fit only, no session).
- **Free user**: onboarding, Pulse Digest, saves (1 per 24h), reminders, personal events.
- **Pro user**: Stripe subscription. Lifted limits and calendar features (FR-48..52).
- **Editorial reviewer**: Django admin review queue (FR-57). Acts through `ingestion` commands.
- **Operator / cost viewer**: AI Cost Dashboard (FR-29), on-call runbook.

### External Systems

- **Anthropic Claude**: extraction and enrichment (`claude-haiku-4-5` primary, `claude-sonnet-5` fallback)
- **Voyage AI**: embeddings (`voyage-4-lite`), which only route review candidates
- **Event sources**: partnerships, APIs, RSS/ICS, crawl. Untrusted input.
- **Calendar providers**: read-only ICS/webcal import at MVP
- **Email provider** (Resend or Postmark): separate transactional and bulk streams, RFC 8058
- **Stripe**: Checkout + Customer Portal
- **OIDC providers** (Google/Apple/Microsoft): sign-in only, never calendar scopes

## Architecture Pattern

**Pattern**: Django modular monolith with ports-and-adapters at every external edge. Two Python runtimes come from one repo, plus a separate Next.js client.
**Rationale**: One codebase and one database keep MVP velocity high. Import-linter-enforced boundaries keep modules splittable later. Separating runtimes by *workload* protects the <500ms p95 read path from crawl and LLM batches (AD-1).

## Component Architecture

### Components

#### ingestion
- **Purpose**: turn sources into canonical Events
- **Responsibilities**: crawl/fetch, LLM extraction, Event Identity dedup, state changes + outbox, Event Fit
- **Dependencies**: LLM gateway, crawl adapter. **Sole writer of `catalog`.**

#### catalog
- **Purpose**: public read surface for Events
- **Responsibilities**: public event pages and SEO data, schema.org JSON-LD
- **Dependencies**: reads `catalog` via `ingestion` read interface

#### personalization
- **Purpose**: the user's world
- **Responsibilities**: interests, PreferenceGraph, SavedEvent snapshots, PersonalEvent, CalendarConnection, ConflictPair, Pulse Digest composition (Relevance Pulse), EventReport, Timeline query
- **Dependencies**: `delivery` services (default ReminderPlan), `ingestion` read interface, calendar port

#### delivery
- **Purpose**: getting messages out on time, exactly once
- **Responsibilities**: ReminderPlan, ScheduledSend, due-index sweep, quiet hours, idempotent sends
- **Dependencies**: email port (explicit stream), `ingestion` read interface (version check)

#### identity
- **Purpose**: accounts and billing state
- **Responsibilities**: User, auth (email+password, OIDC sign-in), Subscription
- **Dependencies**: billing adapter

#### editorial
- **Purpose**: human review
- **Responsibilities**: review queue, AI cost dashboard (Django admin)
- **Dependencies**: `ingestion` commands only. Owns nothing.

### Component Diagram

```
           Next.js frontend (generated client only)
                         │
                 API runtime (Ninja)            worker runtime (sweep · pipeline · retention)
                         │                                   │
   ┌──────────┬──────────┼───────────┬───────────┬───────────┤
identity  personalization  catalog  delivery  ingestion ◄── editorial
                         │                       │
                  ports ◄┴── adapters (llm · email · calendar · crawl · billing · logging)
                         │
                 domain (pure, stdlib only)
```

### Browser → API path

```
browser ──/api/*──► Next.js proxy.ts (same origin) ──API_BASE_URL──► Django Ninja
```
The browser never calls Django directly: no CORS; cookies stay first-party on any hosting. The address is read per request. **Open for the auth intent:** the CSRF origin check (see coding-standards, "CSRF hand-off").

## Data Flow

**Ingestion**: source → `ExtractedRecord` (LLM via gateway, schema-constrained) → Event Identity resolution → `Event` in `catalog` (or review queue if confidence <0.7 or possible duplicate) → Event Fit rollup.

**State change**: `EventStateChange` row with `propagated_at = NULL` in the same `catalog` transaction → `on_commit` enqueue → per-user versioned propagation → `delivery` rewrites sends, `personalization` updates snapshots and conflicts → FR-54 notice.

**Delivery**: beat tick (≤60s) → sweep claims due `ScheduledSend` rows (`FOR UPDATE SKIP LOCKED`, `personal` only) → version check against catalog → send with an idempotency key on the correct stream.

```
sources ─► ingestion ─► catalog.Event ─► EventStateChange (outbox)
                              │                    │
                         Event Fit           propagation ─► personal.SavedEvent / ConflictPair
                              │                    │
                       public pages          delivery.ScheduledSend ─► sweep ─► email
personal.Interest/PreferenceGraph ─► compose digest ─► DigestComposition ─► Pulse Card / email
```

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Frontend | Next.js 16.3 / React 19.2 / Tailwind 4 | Surfaces + ISR public pages |
| API | Django 6.1 + Django Ninja 1.7 | Typed REST + OpenAPI |
| Worker | Celery 5.6.3 + beat | Sweep, pipeline, retention |
| Broker | Redis (managed) | Tick + pipeline jobs only |
| Database | PostgreSQL 18 (Neon) + pgvector 0.8.6 | `catalog` / `personal` schemas |
| AI | Claude Haiku 4.5 / Sonnet 5, Voyage 4 lite | Extraction, embeddings |
| Email | Resend or Postmark | Two streams |
| Billing | Stripe | Pro tier |
| Hosting | Vercel + always-on Python host | Deploys |

## Non-Functional Requirements

### Performance

- **Pulse Digest read path**: <500ms p95 (breach = SEV-1)
- **Reminder delivery**: ±5 min of due time
- **Ingestion SLA**: 4 hours
- **Public SEO pages**: 99.9% uptime

### Security

- Schema-separated public and personal data. No cross-schema joins or FKs (AD-3).
- No PII in logs, redacted at the logger (AD-13)
- Calendar credentials encrypted at rest, revocable (AD-18)
- Source content treated as untrusted input, including prompt injection (AD-9)
- Internal actors authenticated with explicit role grants (AD-14)
- Per-IP and per-user rate limiting at the edge
- Retention per table, swept by a job. Deletion and export use the same registry (AD-15).

### Scalability

Horizontal worker replicas are safe by construction (SKIP LOCKED claims). Public pages scale via ISR. Vectors are quantized and truncated, so the dedicated vector store is deferred to roughly 10M events. Service extraction is deferred until a module's profile diverges.

## Constraints

- **Two database aliases per process** (`default` = personal, `catalog`). Each request or worker can hold 2 connections, and `CONN_MAX_AGE=60` keeps them open: size Neon/pool limits for that. Neon's pooled (transaction-mode) endpoint ignores the `options` startup parameter, so pooled runtime connections rely on the role-level `search_path`; run migrations on the direct endpoint
- Python 3.13 pinned (Django 6.1 ∩ Celery 5.6.3)
- Exactly one Celery beat process. Never a platform cron for the sweep.
- Vercel Pro before Stripe checkout is enabled (hard launch gate)
- UI system "None": no component library and no animation library
- English-only at MVP, with strings externalized from day one
- PRD §3 Glossary terms verbatim. New nouns are added to the Glossary first.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| AD-1 Runtimes | API + worker + Next.js client | Workload isolation protects p95 |
| AD-2 Layering | `domain` stdlib-only, models = entities | Testable core, enforced by import-linter |
| AD-3 Data wall | Two `DATABASES` over one Postgres | ORM makes cross-schema joins impossible |
| AD-4 Dedup | Event Identity tuple only | Embeddings never merge |
| AD-5 Writes | Named commands + audit log | One mutation path per entity |
| AD-6 Time | UTC storage, explicit IANA tz | Kills the timezone bug class |
| AD-7 Delivery | Postgres due-index sweep ≤60s, keyed sends | No per-reminder tasks; Redis loss never loses a reminder |
| AD-8 LLM | One gateway, Haiku → Sonnet fallback | Cost accounting + single retry owner |
| AD-10 Explanations | Persisted Event Fit + Relevance Pulse | Never recomputed at render |
| AD-12 Public surface | Session-free, ISR | SEO uptime decoupled from auth |
| AD-16 Ownership | One owner per entity | `delivery` owns ReminderPlan |
| AD-17 Propagation | Outbox + versioned per-user apply | Catalog changes reach personal safely |
| AD-19 Contract | Generated OpenAPI client | No frontend/backend drift |
| AD-20 Email | Separate transactional/bulk streams | Protect reminder deliverability |
| AD-21 Timeline | Personal-side snapshots, one overlap fn | Consistent conflicts everywhere |

**Open questions**: OQ-5 (the 20 MVP sources and ToS), OQ-6 (new nouns into the Glossary), OQ-7 (Google ICS caching).

---
*Generated by specs.md - fabriqa.ai FIRE Flow*
