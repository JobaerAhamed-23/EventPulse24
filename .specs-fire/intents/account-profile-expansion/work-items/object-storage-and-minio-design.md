---
work_item: object-storage-and-minio
intent: account-profile-expansion
created: 2026-11-19
mode: validate
checkpoint_1: approved
---

# Design: Object Storage, From Nothing — MinIO Beside Postgres

## Summary

The backend stores no files. This adds the capability and **nothing that uses it**: a
`BlobPort`, an S3 adapter, an in-memory adapter for tests, MinIO in `docker-compose`,
validated settings, and an idempotent bucket.

**The shape was not a free choice.** `backend/ports/` and `backend/adapters/` with
`ports/registry.py` resolving a dotted path out of `settings.ADAPTERS` is how this
project reaches **every** external system — email, billing, calendar, geo, throttle,
revalidation, LLM, fetch — and an import-linter contract forbids `apps` from importing
`adapters` at all. **So object storage is a port, not `django-storages`.** Reaching for
Django's `STORAGES` would have put an un-portable, un-fakeable dependency inside the app
layer, and it would have been the first external system in the codebase that is not
behind a port.

That decision also settles the testing criterion for free: the in-memory adapter *is*
how tests run without MinIO, exactly as `InMemoryThrottleAdapter` and
`FakeRevalidationAdapter` already work.

## Scope

**In Scope:**
- `ports/blob.py` — the port, its value objects and its errors
- `adapters/blob/s3.py` — the real adapter, pointed at MinIO locally and at a bucket in production
- `adapters/blob/memory.py` — the test and CI adapter
- MinIO and an idempotent bucket in `docker-compose.yml`
- Settings in `config/env.py` and a startup system check in `config/checks.py`
- `.env.example`, `make doctor`, `README`, `runbook.md`
- **The public-versus-signed URL decision**, because the bucket policy follows from it

**Out of Scope:**
- Any model field, endpoint, UI or image validation — those are the next three items
- Pillow and image decoding (see Risks — it is not installed either)
- A production bucket, its IAM policy and its CDN; this designs the seam they plug into

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage seam | **A `BlobPort` + adapters**, registered in `ports/registry.py` and `config/adapters.py` | Every external system in this codebase is behind a port, and the `apps \| adapters` contract forbids anything else. `STORAGES` would be the first exception, and it would be un-fakeable in tests. |
| Client library | **`boto3`**, pinned exactly | Production is S3-compatible; MinIO speaks the same API. `django-storages` is unnecessary once we are not using Django's storage API, and the `minio` SDK would be a client we then have to swap at deploy. |
| Local service | **MinIO in `docker-compose`**, bound to `127.0.0.1` from an `.env` port | The user's explicit choice over a `MEDIA_ROOT` volume. It also matches **Mailpit's** precedent exactly: a real local service standing in for a real remote one, rather than a fake. |
| Which adapter runs locally | **The S3 adapter, against MinIO**, even in `ADAPTER_MODE=fake` | `config/adapters.py` already does this for email: *"Email still really sends, to Mailpit."* MinIO is Mailpit for bytes. Tests override to memory in `settings_test.py`. |
| Bucket bootstrap | A **one-shot `minio/mc` job** running `mb --ignore-existing`, invoked explicitly by `make up` | Idempotent by construction, no Python, no ordering subtlety in the app. See Risks for why it is *invoked* rather than left to `up --wait`. |
| URL exposure | **Private bucket; the app mints a presigned URL** | The project's posture is that nothing is public that need not be — calendar credentials encrypted, the city kept out of `__str__`, no PII in logs. A public-read bucket is also a one-line misconfiguration away from listing. An avatar is a photograph of a real person. |
| URL stability | **A stable app-owned URL that redirects to a fresh presign** — *revised after the probe, see Amendment 1* | Quantizing the signature was probed and **rejected**: it is reachable only by monkeypatching a non-public botocore global, which races under a threaded server. A stable app URL gives the browser something cacheable without touching botocore internals. |
| Endpoint split | **Two settings**: the endpoint the API dials, and the endpoint a signature is minted for | The API container reaches MinIO by service name; the browser reaches it at `127.0.0.1`. One setting cannot be both, and a URL that works from the API and 404s in the browser is the expected first bug. |
| Key shape | **Opaque and random**, no email, no name, no user id | AD-13: a key is a second place PII lives at rest. It also makes the key unguessable, which matters if the URL decision is ever revisited. |
| Settings validation | `config/env.py` fields **plus** a `config/checks.py` system check | `check_credential_key` is the exact precedent: config is parsed by pydantic-settings, and the *semantic* "this is configured coherently" check is a Django check so `manage.py check` (which CI runs) fails before first use, not at first upload. |

## Data Models Affected

**None.** No model, no migration, no retention category — this item stores nothing that
belongs to a user. AD-15 bites on the next item, where the key lands on `User`.

## Technical Approach

### Architecture

```
  apps/…                      ← never imports adapters (import-linter: apps | adapters)
    │
    │ ports.registry.get_blob_port()
    ▼
  ports/blob.py                BlobPort (ABC)
    │                            put(key, data, *, content_type) -> None
    │                            delete(key) -> None
    │                            url_for(key) -> str
    │                            open(key) -> bytes            (export + tests)
    │                          BlobError / BlobNotFound
    ├───────────────┬──────────────────────────────┐
    ▼               ▼                              ▼
  adapters/blob/  adapters/blob/              config/adapters.py
    s3.py           memory.py                   ADAPTERS["blob"] = …
    │  boto3        dict in process
    ▼
  MinIO (compose, 127.0.0.1:${EP_MINIO_PORT})   →  S3 / R2 in production
    ▲
    └── one-shot minio/mc job: mb --ignore-existing   (make up)
```

### Settings (`config/env.py`)

```
blob_endpoint: str            # what the API dials      (http://minio:9000 | https://…)
blob_public_endpoint: str     # what a signature is for (http://127.0.0.1:9000 | https://cdn…)
blob_region: str = "us-east-1"
blob_bucket: str
blob_access_key: str
blob_secret_key: str
blob_url_ttl_seconds: int     # the presign window
```

A `model_validator(mode="after")` requires the credentials **when the S3 adapter is
selected**, following `real_calendars_need_a_real_fetch` and
`owner_role_requires_owner_url`, which are the two existing validators of exactly this
shape. A `BLOB_ADAPTER` switch (`s3` | `memory`) follows `THROTTLE_ADAPTERS`, which
exists for the same reason: a port whose local behaviour sometimes needs the real
service and sometimes does not.

### Database Changes

None.

## Affected Files

| File | Action | Purpose |
|------|--------|---------|
| `backend/ports/blob.py` | create | The port, its errors and its value objects |
| `backend/ports/registry.py` | modify | `PORT_KEYS[BlobPort] = "blob"`, `get_blob_port()` |
| `backend/adapters/blob/__init__.py` | create | Package |
| `backend/adapters/blob/s3.py` | create | boto3 against MinIO or a bucket |
| `backend/adapters/blob/memory.py` | create | In-process store for tests and CI |
| `backend/config/adapters.py` | modify | `FAKE_ADAPTERS["blob"]`, `BLOB_ADAPTERS` |
| `backend/config/env.py` | modify | The seven settings and their validator |
| `backend/config/settings.py` | modify | Surface them into `ADAPTERS` / module constants |
| `backend/config/settings_test.py` | modify | Force the memory adapter in tests |
| `backend/config/checks.py` | modify | `check_blob_storage` — fails `manage.py check` when incoherent |
| `backend/pyproject.toml` | modify | Pin `boto3` exactly |
| `docker-compose.yml` | modify | MinIO service, volume, health check, `mc` bootstrap job |
| `Makefile` | modify | `up` invokes the bucket job; a `minio` console target |
| `.env.example` | modify | Ports and dev-only placeholder credentials |
| `scripts/doctor.sh` | modify | Check the new ports |
| `README.md`, `docs/runbook.md` | modify | Console access; what to do when the bucket is missing |
| `backend/tests/…` | create | Port contract tests run against **both** adapters |

## Security Considerations

- **No credential in the repository.** `.env.example` carries dev-only placeholders, as
  it already does for `DJANGO_SECRET_KEY` and `CALENDAR_CREDENTIAL_KEY`, each labelled
  *"must be replaced in production (secret store)"*. CI must pass with none of them set.
- **The bucket is private.** No public-read policy, no bucket listing, no anonymous
  `GET`. The presigned URL is the only way in.
- **No PII in the key** (AD-13), and no key in any log line — the logger allowlist is
  not widened.
- **MinIO is bound to `127.0.0.1`**, like every other service in this compose file.
- **Preview environments never write to real infrastructure** (constitution): preview
  points at its own bucket or at the memory adapter, and this is stated in the settings
  docstring rather than left to whoever deploys it.
- **A presigned URL is a bearer token for one object.** Its TTL is a setting, it is
  minted per object, and it is never logged.

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| ~~Presign quantization may not be expressible with pinned boto3.~~ **Probed: it is not, safely.** | Resolved | Replaced by the redirect endpoint in Amendment 1. |
| **A stable URL serves a stale picture after a replacement.** The URL no longer changes when the object does. | High — a user replaces their picture and keeps seeing the old one | The stable URL carries a short **version segment derived from the stored key**, which changes on every upload. A new picture is a new URL; cache invalidation is automatic. |
| **A cached redirect can outlive the signature it points at.** | Medium — a broken image until the cache entry expires | The redirect's `max-age` must be **strictly less** than the presign TTL, asserted by a test that reads both from the same settings. |
| **`docker compose up -d --wait` may treat an exited one-shot container as a failure.** | Medium — `make up` would break for everyone, including a clean clone. | Measure it against the pinned compose. The design therefore has `make up` **invoke** the bucket job as its own `docker compose run --rm` step rather than depend on `--wait` tolerating it. |
| **The endpoint split is easy to get wrong and fails only in the browser.** | High — the picture works in every backend test and is broken on every page. | Two explicit settings, named for who dials them, and an acceptance criterion that a signature minted by the API is fetched **from outside the compose network**. |
| **CORS.** The browser fetching a presigned URL from a different origin needs MinIO to allow it. | Medium — a bug that appears only in the browser, again. | Settle it here, with the bucket's CORS configured in the same bootstrap job, not discovered in the UI item. |
| **boto3 is a large dependency** with a wide transitive surface, in a project that pins exactly and reviews dependencies. | Low | It is the reference S3 client and is what a production bucket expects. Pin it exactly and note it in the PR, as the constitution requires for dependency changes. |
| **Pillow is not installed either.** No image decoding exists. | Medium — but for the **next** item | Flagged here so it is budgeted: `avatar-model-and-command` needs a decoder for sniffing and dimensions, and that is a second dependency decision with its own CVE history. |
| **An orphaned object has no sweeper.** Nothing deletes what nothing points at. | Low now, higher later | Out of scope here; named in the next item, which owns deletion on replace. |

## Amendments — what the probes actually found

Both probes the checklist put first have been run. **Each one changed something**, which
is why they were first.

### Amendment 1 — the quantized presign is rejected, and the design moves the URL

**Measured** against `boto3 1.42.6` / `botocore 1.42.97`:

| Probe | Result |
|---|---|
| Two presigns 1.2s apart are identical | `False` — the URL churns per render, as feared |
| A `before-sign` event hook can fix the timestamp | `False` — **the hook is overwritten** |
| `SigV4Auth.add_auth` guards an existing `request.context['timestamp']` | `False` — it assigns unconditionally |
| Freezing `botocore.auth.get_current_datetime` produces a stable URL | `True` — but see below |
| `get_current_datetime` is public API | `False` — not in `botocore.auth.__all__` |

The source is unambiguous:

```python
def add_auth(self, request):
    ...
    datetime_now = get_current_datetime()
    request.context['timestamp'] = datetime_now.strftime(SIGV4_TIMESTAMP)
```

There is no seam. The only thing that works is swapping a **module-level global** that
botocore does not publish — and Django serves threaded, so two requests signing at once
race on it. **A stable avatar URL is not worth a data race in the signing path.**

**So the URL moves into the app.** `me` returns a stable, app-owned URL carrying a
version segment derived from the stored key; that endpoint mints a fresh presign and
**302s** to it. The browser caches by the stable URL; a new picture mints a new version
segment and therefore a new URL, so replacement invalidates the cache by construction.

**This is a change to an approved design, and it reaches one item forward**:
`avatar-endpoint-and-contract` gains the redirect endpoint, and its acceptance criteria
need the two cache rules above. That item has not started.

**It also shrinks two risks.** An `<img>` load is not CORS-restricted unless the tag
opts in, so the CORS risk was overstated in the original table; and the endpoint split
now has exactly one place that mints a signature, instead of every render.

### Amendment 2 — the compose risk is real, and the fix is measured

| Probe | Result |
|---|---|
| `docker compose up -d --wait` with a one-shot service exiting **0** | **`EXIT_CODE=1`** — `container … exited (0)` is reported as a failure |
| The same, with the job behind `profiles: ["bootstrap"]` | `UP_EXIT=0` |
| `docker compose run --rm createbuckets` | `RUN_EXIT=0` |
| The same command a second time | `RUN_TWICE_EXIT=0` — idempotent |

Measured on **Docker Compose v2.27.0-desktop.2**, the version on this machine. So the
bucket job sits behind a `bootstrap` profile — which keeps it out of `up --wait`
entirely — and `make up` invokes it as an explicit `docker compose run --rm` step. The
mitigation the design guessed at is **required**, not precautionary.


### Amendment 3 — MinIO cannot be pulled here, and most substitutes are not private

**MinIO's images are unavailable in this environment.** Not a bad tag: the *repository*
is denied.

| Pull attempt | Result |
|---|---|
| `minio/minio:latest`, `:RELEASE.2024-01-16…`, `:RELEASE.2023-09-30…` | `pull access denied … repository does not exist or may require 'docker login'` |
| `quay.io/minio/minio:…` | `unauthorized: access to the requested resource is not authorized` |
| `minio/mc:latest` | same denial |
| `hello-world` | **OK** — so the registry itself is reachable |
| Docker Hub API for `minio/minio` tags | `{"message":"object not found"}` |

**The port and adapters do not care.** That is the payoff of the seam: the S3 adapter was
proved against a real S3 server (below), and swapping the container changes two image
lines in `docker-compose.yml` and nothing else.

**But the substitute must enforce signatures, and most do not.** This was measured, and
it is the finding that matters:

| Candidate | Pull | Anonymous access |
|---|---|---|
| `adobe/s3mock` | OK | **Wide open.** An unsigned URL returned **200**, and a URL with `ttl=1` fetched 3 seconds later also returned **200** |
| `chrislusf/seaweedfs` | OK | **Wide open by default.** Anonymous create-bucket, PUT and GET all returned **200**; enforcing needs an identities config |
| `localstack/localstack:latest` | OK | **Will not run**: exits 55 demanding `LOCALSTACK_AUTH_TOKEN`; `latest` is now the licensed image |
| `dxflrs/garage` | OK | Not yet measured; it has no anonymous mode unless one is granted |
| `minio/minio` | **denied** | — |

**A store that ignores signatures makes the design's central claim false locally while
every test passes.** "The bucket is private, and the signature is the read permission"
would be untrue in development, and the first place anyone would find out is production.
So `adobe/s3mock` and an unconfigured SeaweedFS are **disqualified as the local store** —
not because they are bad, but because they would make the privacy property untestable.

**What was proved anyway.** With a real S3 server listening, the full contract suite
passes against the **S3 adapter**: 18 tests covering round-trip, replace, delete,
delete-of-absent, `BlobNotFound` on a missing key, and URL minting. A URL minted by the
adapter was fetched **by curl, from outside the process**, and returned **200** — so the
endpoint split and the signing path are correct. The privacy half of that probe is the
part the mock could not answer.

**Decided by the user: MinIO stays, and the pull is resolved with `docker login`.** The
image tag was then verified against minio/minio's GitHub releases
(`RELEASE.2025-10-15T17-29-55Z`, with `minio/mc:RELEASE.2025-08-13T08-35-41Z`) and the
pull was **still denied**, which confirms the obstacle is access rather than a bad tag.

**Three acceptance criteria therefore remain open**, and none of them is a code change:
`make up` end to end twice on a clean clone; the bucket job against real `mc`; and the
privacy probe — an unsigned URL and an expired URL must both be **refused**, which is the
check neither mock could answer.


## Implementation Checklist

- [x] ~~Probe `boto3`'s presign~~ — **done, see Amendment 1**
- [x] ~~Probe `docker compose up -d --wait` with a one-shot container~~ — **done, see Amendment 2**
- [ ] `ports/blob.py` — port, errors, docstring recording why storage is a port
- [ ] Register in `ports/registry.py` (`PORT_KEYS`, `get_blob_port`)
- [ ] `adapters/blob/memory.py` first, so the port's tests exist before the real client
- [ ] `adapters/blob/s3.py`
- [ ] One **contract test suite run against both adapters**, so the fake cannot drift from the real one
- [ ] `config/env.py` settings + validator; `config/adapters.py` entries; `settings_test.py` override
- [ ] `config/checks.py` — `check_blob_storage`, following `check_credential_key`
- [ ] Pin `boto3` in `backend/pyproject.toml`; `uv lock`
- [ ] MinIO + volume + health check + `mc` bootstrap in `docker-compose.yml`; CORS set in the same job
- [ ] `Makefile`: `up` runs the bucket job; a console target
- [ ] `.env.example`, `scripts/doctor.sh`, `README.md`, `docs/runbook.md`
- [x] Round-trip probe: put a byte string, fetch it **from outside the process** with a minted URL — done, 200
- [ ] `make up` twice on a clean clone — second run succeeds — **blocked: image pull denied**
- [ ] The privacy probe: an unsigned URL and an expired URL are both **refused** — **blocked: no conforming store available locally**
- [x] Full backend suite green **with no object store running**
- [x] `manage.py check` fails loudly with the settings blanked (E008)
- [x] Mutation probe per test: confirm each one can fail — 6 mutations, each failed the right tests

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-11-19*
