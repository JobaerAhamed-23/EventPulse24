# Handoff — run-eventpulse24-057

Written 2026-11-20, end of the session that completed items 1–4.
Branch `city-picker-and-auto-collection`, working tree clean, nothing pushed.

## How to resume

```
/specsmd-fire-builder
```

It scans disk, finds this active run, reads `current_item` from `state.yaml`, and picks up
at the next work item. No re-planning. Nothing here needs to be pasted in — this file is
for the human, not the agent.

## Where things stand

4 of 11 items complete. Run scope is `wide`.

| # | Item | Mode | Status |
|---|---|---|---|
| 1 | `city-catalog-dataset` | confirm | ✅ `e39d367` |
| 2 | `source-city-timezone` | validate | ✅ `6dd8d96` |
| 3 | `api-source-parser` | confirm | ✅ `2a0a647` |
| 4 | `city-choices-endpoint` | confirm | ✅ `d1a9218` |
| 5 | `stored-city-is-the-picked-city` | **validate** | ◀ next, in_progress |
| 6 | `city-provider-templates` | confirm | pending |
| 7 | `city-provisioning-service` | validate | pending |
| 8 | `provisioning-probation` | confirm | pending |
| 9 | `browse-collecting-states` | confirm | pending |
| 10 | `city-coverage-request` | confirm | pending |
| 11 | `home-city-dropdown-catalog` | confirm | pending |

Item 5 is `validate` mode, so it stops for plan approval before implementing.

Suite at HEAD: **7907 passed, 0 failed**, 97.44% overall, `domain/` 100%.

## Decisions already taken (do not re-litigate)

| Decision | Taken | Where it is recorded |
|---|---|---|
| ~150 hand-verified cities, not thousands | landed at 165 across 95 countries | `walkthrough-city-catalog-dataset.md` |
| `TZ_SCORE_CITY_ZONE = 0.90`, no `tz_review_pending` | publishes clean; DST caps still flag genuinely doubtful readings | `walkthrough-source-city-timezone.md` |
| `_content_hash` includes `city_tz` | D7 precedent; without it a source that gains a zone never re-resolves | same |
| API key never stored | key-less `Source.url`; added at fetch with `credential=True`; `strip_key` on the way back | `walkthrough-api-source-parser.md` |
| Choices endpoint throttled, own scope | plus a long cache TTL (1h browser / 1d edge) | `walkthrough-city-choices-endpoint.md` |

## Facts the remaining items need

**For item 6 (`city-provider-templates`)** — verified against live Ticketmaster docs during
item 3, so do not re-check:

- `city` **is** an official Discovery v2 Event Search parameter. The feared fallback
  (`countryCode` plus client-side filtering) is not needed.
- `latlong` is **deprecated** in favour of `geoPoint`, which takes a geohash. No template
  should use `latlong`.
- **Put no API key in a URL template.** The URL a template builds is stored on the `Source`;
  `apps/ingestion/services/provider_keys.py` adds the key at fetch time. A template that
  carried one would write a secret into a column and a 24-month audit row.
- Build URLs against host `app.ticketmaster.com` — `providers.READERS` and
  `provider_keys.PROVIDER_KEYS` both match that host **exactly**, never by suffix.

**For item 7 (`city-provisioning-service`)**:

- Refusing to create an `api` source when `TICKETMASTER_API_KEY` is empty belongs here.
  The ingest layer deliberately fetches without the key and lets the provider's 401 land in
  `last_error_code`, where an editor can see it, rather than hiding the misconfiguration.
- Populate `Source.city_tz` from the catalog's `tz` column at registration. That is the
  whole reason item 2 exists.

**For item 11 (`home-city-dropdown-catalog`)**:

- `GET /api/public/cities` is live and in the generated client (`frontend/lib/api/schema.ts`).
- `home-city.tsx`'s docstring still claims the choices come from `preview/cities`. Item 4's
  AC 6 deliberately left that correction to item 11, where the claim actually stops being true.

## Environment gotchas

- **Docker on this machine is macOS**, so `systemctl --user start docker-desktop` does not
  exist. Use `open -a Docker`, wait for the daemon, then `make up`.
- **Never run `ruff format .` from the repo root.** `backend/tests/shared/test_retention_published.py`
  has pre-existing formatting drift on this branch and gets reformatted every time, adding
  an unrelated file to the diff. It happened twice this session. Format only the
  directories being worked in, e.g. `ruff format apps tests config` from `backend/`.
  `ruff format --check .` reporting exactly one file is therefore expected and is not new.
- Backend commands go through `uv run --directory backend …` (see `UV_BACKEND` in the Makefile).
- Changing the API surface requires `make client` (regenerates `openapi.json` **and**
  `schema.ts`); `tests/api/test_contract.py` fails until you do.

## Practices this run has been holding to

- **Every whole-dataset invariant is mutation-checked** before a test report is written —
  the rule that a test must be able to fail. It earned its keep: it caught two tests in
  item 4 that could not fail, both of which the green suite had hidden.
- Architecture guards are treated as right by default. Item 3's parser was renamed out of
  the AD-5 surface rather than teaching the discovery an exception; item 4 turned two
  counting guards into checking guards.
- Every work item's artifacts are `plan-`, `test-report-`, `review-report-` and
  `walkthrough-<item-id>.md` in this folder. A run-level `walkthrough.md` is still owed at
  run completion, matching runs 055 and 056.

## Still open

- Nothing is pushed and no PR exists.
- Items 5–11 remain. Item 5 (`stored-city-is-the-picked-city`) is `validate`, so expect a
  design-doc checkpoint and a plan checkpoint.
