# EventPulse24

AI-powered event discovery and notification platform. It collects events from many sources, deduplicates them, and delivers personalized Pulse Digests, reminders and conflict-aware scheduling.

## Quick start

Prerequisites: Docker (Compose v2), `make`, `uv`, Node.js 24 LTS and `pnpm`. Follow the guide for your OS:

- **Ubuntu:** [docs/setup/ubuntu.md](docs/setup/ubuntu.md)
- **macOS:** [docs/setup/macos.md](docs/setup/macos.md)

```bash
make env        # create .env from .env.example
make doctor     # check prerequisites and ports
make up         # start Postgres 18 + pgvector, Redis, Mailpit
make db-check   # verify the database is ready
make migrate    # create the tables in both schemas (catalog, personal)
make web-install   # install the frontend dependencies
make dev        # API, worker, beat and Next.js together; Ctrl-C stops all
```

Then open <http://127.0.0.1:3000/dev/health>: personal database, catalog database and Redis should all be green. The browser only talks to Next.js; it forwards `/api/*` to Django (`API_BASE_URL`), so there's no CORS. Each process also runs on its own: `make api`, `make worker`, `make beat` (exactly one), `make web`.

Changed an API endpoint? Run `make client`: it exports the OpenAPI schema and regenerates the frontend's typed client in `frontend/lib/api/` (never edit those files by hand; a test fails until they match).

Already set up before? Run `make db-init && make migrate` to bring an existing database up to date (keeps data).

Run `make` to list all commands. The Mailpit inbox is at <http://127.0.0.1:8025>; `make send-test-email` puts a message there. With `ADAPTER_MODE=fake` (the default) the AI, embeddings, billing and calendar run on local stand-ins, so no API keys are needed.

Before pushing, run `make coverage-backend && make lint-backend && make test-web && make lint-web`. **CI (`.github/workflows/ci.yml`) runs these same targets** on every push and pull request, plus the contract check (`make client` must leave `frontend/lib/api/` unchanged) and a frontend production build. `lint-backend` covers Ruff, the format check and the architecture's import contracts (`make lint-imports` runs only the contracts).

## Local ingestion

The catalog is filled by the ingestion pipeline: a **source** (a feed a person registered) is
fetched, parsed, deduplicated and written into the catalog. This section is the whole local
loop, from an empty database to events in the API.

### 1. Seed the local stack

```bash
make manage ARGS="seed_local_stack"
```

The command is **idempotent** — run it as often as you like. It registers:

- the **proof sources**, one per acquisition method (JSON-LD, RSS, ICS), each with its own
  approved terms-of-service review;
- the **venues** those events name, with their IANA timezone;
- the **`editorial` group** and the local **operator** account.

It is a *client* of the published ingestion services, never a direct write, so every source,
venue and review gets its audit row. Two feed sets live in committed data files:

| File | Feed set | Used by |
|---|---|---|
| `backend/config/local_feeds.fixtures.json` | recorded fixtures, served by the fake fetch adapter | CI and the default local run |
| `backend/config/local_feeds.json` | the real public feeds (MMFA) | the manual real-feed run below |

```bash
make manage ARGS="seed_local_stack --list"   # print the feed set and each ToS note
make manage ARGS="seed_local_stack --real"   # register the real feeds instead
```

The **editorial group** holds exactly twelve permissions — add/change/view on `Source`,
`Venue` and `TosReview`, and view on `Event`, `EventStateChange` and `IngestionAuditEntry`.
`delete` is deliberately absent: sources are paused, never deleted. The operator is staff but
**never** a superuser, and the command demotes it if something else made it one.

To register a source by hand instead, use the Django admin (`/admin/`). The form calls the
same services, so the FR-17 rule holds there too: **a `crawl` source needs an approved
terms-of-service review before it can be ingested.** `rss`, `jsonld` and `ics` do not.

### 2. Trigger the ingestion

The worker polls. `make dev` runs everything (API, worker, beat, web); on its own:

```bash
make worker   # the Celery worker: runs the ingest jobs
make beat     # the 60 s tick scheduler — exactly one at a time
```

Every 60 seconds the tick claims the sources that are due (a source is due when its last
attempt is older than its `ingestion_cadence`) and enqueues one ingest job per claim.

To ingest one source right now, without waiting for the tick:

```bash
make manage ARGS="ingest_source <source-id> --sync"
```

The source ids are in the Django admin, under **Ingestion → Sources**
(`/admin/ingestion/source/`).

`--sync` runs it in this process and prints the counts; without it the job is enqueued and a
worker runs it.

### 3. Read the catalog

```bash
curl "http://127.0.0.1:8000/api/catalog/events?city=Montgomery"
```

`GET /api/catalog/events` lists the published, not-yet-started events, soonest first. Query
parameters: `city` (exact, case-insensitive), `starts_after`, `starts_before`, `page`
(default 1), `page_size` (default 20, max 100). The body is
`{items, page, page_size, total, has_next}`. `GET /api/catalog/events/{id}` returns one event
(404 when it is not public). **Neither endpoint uses a session or sets a cookie.**

### 4. The fetch adapter: fake or real

`ADAPTER_MODE=fake` (the default) serves every fetch from the recorded fixtures in
`backend/tests/fixtures/sources/` — no network, so CI is deterministic. `SOURCE_FETCH=http`
overrides the mode for the fetch port alone, leaving every other adapter fake.

| Variable | Default | What it does |
|---|---|---|
| `SOURCE_FETCH` | follows `ADAPTER_MODE` | `fake` or `http` |
| `SOURCE_FETCH_USER_AGENT` | `EventPulse24-SourceFetcher/0.1 (+https://github.com/JobaerAhamed-23/EventPulse24)` | the identifying user agent |
| `SOURCE_FETCH_MAX_BYTES` | `10485760` | the largest body accepted |
| `SOURCE_FETCH_DNS_TIMEOUT` | `3.0` | seconds |
| `SOURCE_FETCH_CONNECT_TIMEOUT` | `5.0` | seconds |
| `SOURCE_FETCH_READ_TIMEOUT` | `15.0` | seconds |
| `SOURCE_FETCH_WRITE_TIMEOUT` | `5.0` | seconds |
| `SOURCE_FETCH_TOTAL_TIMEOUT` | `30.0` | seconds |
| `SOURCE_FETCH_MAX_REDIRECTS` | `5` | redirects followed |
| `SOURCE_FETCH_ALLOWED_PORTS` | `80,443` | the ports a fetch may reach |

### 5. The manual real-feed run

This is the one step that touches the network, so it is **not** part of CI and not part of
`make dev`:

```bash
SOURCE_FETCH=http make manage ARGS="seed_local_stack --real"
make up && make dev
```

The MMFA feeds are registered and then ingested on the next tick (or immediately with
`SOURCE_FETCH=http make manage ARGS="ingest_source <id> --sync"`). Their robots note is
honoured: `Crawl-delay: 10`, and only `/wp-admin/` is disallowed. The JSON-LD URL redirects
once, to `/programs-events/calendar/`; the fetcher follows it and the source keeps its
registered URL.

**CI never does this.** The end-to-end suite (`backend/tests/e2e/`) runs the same chain —
seed, tick, ingest, catalog API, tick again — entirely against the recorded fixtures.

## Pro entitlement, locally

Pro is not a flag you flip. Entitlement is a `Subscription` row, and the **only** thing
that writes one is the inbound billing webhook (`POST /api/webhooks/billing`) from the
provider's signed event — a completed checkout grants nothing on its own, because
granting on a redirect the client controls is the open-redirect bug in a checkout flow.
`backend/tests/e2e/test_pro_tier_proof.py` asserts that rule, and it is worth keeping.

So the local command **posts the fake webhook** rather than writing the row:

```bash
make grant-pro EMAIL=you@example.test      # grant
make revoke-pro EMAIL=you@example.test      # cancel
```

Both need the API running (`make api`) and `ADAPTER_MODE=fake` (the default). The account
is created if it does not exist yet, with the password `localpro123`; an existing
account's password is never changed. `PLAN=yearly` grants the yearly plan.

**What it does.** `make grant-pro` mints a checkout session at `/dev/fake-billing` and
posts the provider's `subscription_started` event; `make revoke-pro` posts
`subscription_ended`. The entitlement arrives through the real receiver — signature
verification, event translation, the ordering guard, the audit write — so the local
environment is a rehearsal of the real one rather than a shortcut around it. The audit
row records `stripe_webhook` as the actor, exactly as a payment would.

**A cancellation is a transition, not a deletion.** The row becomes `CANCELED` and is
kept, as `BILLING_RECORDS` retention requires. Nothing you saved, built or configured is
touched: a lapse removes the effect of your Pro features, not the rows behind them.

**Two things that bite.** `past_due` counts as Pro — a failed payment leaves someone
entitled while they fix it in the portal — so only `CANCELED` (or no row at all) means
Free. And the webhook's `occurred_at` is stamped *now* on every run, because
`Subscription.last_event_at` is the ordering guard and a stale timestamp is declined.

The same path is available by hand, if you want to see the wire format:

```bash
curl -X POST http://127.0.0.1:8000/api/webhooks/billing \
  -H 'Content-Type: application/json' \
  -H 'Stripe-Signature: fake-signature' \
  -d '{"kind":"subscription_started","event_id":"evt_1","occurred_at":'$(date +%s)',
       "customer_ref":"cus_local","subscription_ref":"sub_local",
       "user_id":"<USER_UUID>","plan":"monthly"}'
```

## Repository layout

| Path | What |
|---|---|
| `backend/` | Django + Ninja backend (uv project, Python 3.13) |
| `frontend/` | Next.js 16 client (pnpm, Node 24); design tokens in `frontend/styles/` |
| `docker-compose.yml`, `docker/` | Local infrastructure |
| `scripts/` | `doctor.sh` (prerequisite checks), `db-check.sh` (database checks) |
| `docs/setup/` | Per-OS setup guides |
| `_bmad-output/planning-artifacts/` | PRD, UX design, architecture spine |
| `.specs-fire/` | FIRE intents, work items, runs and project standards |

## Architecture

The architecture spine is the binding reference for all code:
[`_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md`](_bmad-output/planning-artifacts/architecture/architecture-EventPulse24-2026-09-04/ARCHITECTURE-SPINE.md).
A condensed view and coding standards live in [`.specs-fire/standards/`](.specs-fire/standards/).
