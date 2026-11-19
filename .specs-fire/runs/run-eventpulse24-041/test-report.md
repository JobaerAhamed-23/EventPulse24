---
run: run-eventpulse24-041
work_item: object-storage-and-minio
intent: account-profile-expansion
date: 2026-11-19
---

# Report: Object Storage, From Nothing

**Done except the container, and the container is blocked on image access, not on code.**

## What the probes decided, before any code was written

The design put two probes ahead of implementation. **Both changed the design**, which is
the only reason to run a probe first.

### The quantized presigned URL was rejected

Measured against `boto3 1.42.6` / `botocore 1.42.97`:

| Probe | Result |
|---|---|
| Two presigns 1.2s apart identical | `False` |
| A `before-sign` hook can fix the timestamp | `False` — overwritten |
| `SigV4Auth.add_auth` guards an existing `request.context['timestamp']` | `False` |
| Freezing `botocore.auth.get_current_datetime` gives a stable URL | `True` |
| That function is public API | `False` |

The only mechanism that works swaps a module-level global botocore does not publish, and
Django serves threaded. **A cacheable avatar URL is not worth a data race in the signing
path.** So the stable URL moved into the app, and `avatar-endpoint-and-contract` gained
the redirect endpoint and two cache rules.

### The compose risk was real

| Probe | Result |
|---|---|
| `up -d --wait` with a one-shot service exiting 0 | **exit 1** |
| The same, behind `profiles: ["bootstrap"]` | exit 0 |
| `docker compose run --rm createbuckets` | exit 0 |
| The same again | exit 0 — idempotent |

Measured on Compose v2.27.0-desktop.2. The mitigation was required, not precautionary.

## Tests

| Suite | Result |
|---|---|
| `tests/adapters/test_blob.py` (memory) | 19 passed |
| `tests/adapters/test_blob.py` (s3, against a real server) | **18 passed** |
| `tests/config/` | 203 passed with the blob tests |
| `tests/architecture/` | 1049 passed |
| `lint-imports` | 20 contracts kept, 0 broken |
| `ruff check` / `ruff format --check` | clean |
| `manage.py check` | passes configured; **E008 with an actionable hint** when not |

**One contract suite, parameterised over both adapters**, so the fake cannot answer a
differently-shaped question than the real one.

### Every test was probed for its ability to fail

| Mutation | Result |
|---|---|
| Key traversal rule removed | 3 failed |
| `delete` of a missing key raises | 1 failed |
| Memory adapter always keeps its own store (the throttle bug, reintroduced) | 1 failed |
| E008 never fires | 5 failed |
| E008 echoes the storage dict into the hint | 2 failed |
| A non-blob adapter imports boto3 | `s3-sdk` **BROKEN** |

Restoring each returned the suite to green.

### The S3 adapter was proved against a real S3 server

All 18 S3-parameterised tests passed: round-trip, replace, delete, delete-of-absent,
`BlobNotFound` on a missing key, URL minting. **A URL minted by the adapter was fetched by
`curl`, from outside the process, and returned 200** — so the endpoint split and the
signing path are right.

## What is NOT proved, and why

**The privacy property.** Against `adobe/s3mock`, an **unsigned** URL returned 200 and an
**expired** URL (`ttl=1`, fetched 3s later) returned 200. The mock ignores authentication.
`chrislusf/seaweedfs` is likewise wide open by default — anonymous create-bucket, PUT and
GET all returned 200. **A store that ignores signatures makes "the bucket is private"
false locally while every test passes**, so neither is usable as the local store.

**MinIO itself cannot be pulled here.** The repository is denied on Docker Hub *and*
quay.io, for `latest`, for old releases and for `minio/mc`, while `hello-world` pulls
fine. The tag in `docker-compose.yml` was then verified against minio/minio's **GitHub
releases** (`RELEASE.2025-10-15T17-29-55Z`) and **still denied** — so it is access, not a
tag typo. The user's decision is to keep MinIO and `docker login`.

**So three things await a working pull**, and none of them is a code change:
1. `make up` end to end, twice, on a clean clone
2. The bucket job against real `mc`
3. The privacy probe: an unsigned URL and an expired URL must both be **refused**

## Pre-existing failures, not caused by this work

`tests/delivery/test_preferences_api.py` fails three tests with
`ScheduledSend.DoesNotExist`. **Verified pre-existing**: they fail identically on the
unmodified base commit `b8c6b21`, in a separate worktree with its own dependency set
(`python-dateutil 3.0.0`). They are therefore *not* the `dateutil` downgrade that `boto3`
forced — which was the first suspicion, and it was wrong.
