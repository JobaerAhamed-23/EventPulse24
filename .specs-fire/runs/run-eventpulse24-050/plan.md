---
run: run-eventpulse24-050
work_item: object-storage-and-minio
intent: account-profile-expansion
mode: validate
checkpoint: plan
approved_at: 2026-11-19
---

# Implementation Plan: Object Storage, From Nothing — MinIO Beside Postgres

## Approach

**This run is verification, not construction.** Run 041 wrote the whole item — the blob
port, the memory and S3 adapters, the settings validation, the compose services and the
bucket job — and left three things unproved, recording that *"none of them is a code
change"*:

1. `make up` end to end, twice, on a clean store
2. The bucket job against real `mc`
3. The privacy probe: an unsigned URL and an expired URL must both be **refused**

All three waited on an image that could not be pulled. The single code change in this run
is the image reference.

**Checkpoint 1 (design) was approved on 2026-11-19 before run 041.** This plan is the
second checkpoint, and it is short because the design did not change — only the registry
the bytes come from.

## The blocker was misdiagnosed, and that is why it lasted

Run 041 recorded *"The repository is denied on Docker Hub and quay.io … so it is access,
not a tag typo. The user's decision is to keep MinIO and `docker login`."*

**`docker login` could never have worked.** Measured this run:

| Probe | Result |
|---|---|
| `docker pull hello-world` | succeeds — daemon, network, Hub access all fine |
| `hub.docker.com/v2/repositories/minio/minio/` | **404 `object not found`** |
| `docker system info` | no username — never logged in |
| `quay.io/minio/minio` | 401 to anonymous |

MinIO **deleted** `minio/minio` and `minio/mc` from Docker Hub in September 2026. Docker
reports a missing repository and a forbidden one with the same sentence — *"may require
'docker login'"* — and that single ambiguous message sent this project chasing credentials
for a repository that does not exist.

## Files to Modify

| File | Changes |
|------|---------|
| `docker-compose.yml` | `minio/minio` → `pgsty/minio@sha256:b6bfe7…`, `minio/mc` → `pgsty/mc@sha256:b53227…`, each with the evidence for the choice |
| `.specs-fire/.../work-items/object-storage-and-minio.md` | frontmatter → completed |

**Not committed, but required locally:** `.env` predates the blob work and `make env`
never overwrites an existing file, so an existing developer's `.env` silently lacks every
`BLOB_*` key. That is the `E008` this project has been seeing. Appended from
`.env.example`.

## Tests

| Test | Coverage |
|-----------|----------|
| `backend/tests/adapters/test_blob.py` | Its 7 S3-parameterised tests had been **skipping** for want of a store. They now run. |
| Full backend suite | Expected to go from 7495 passed / 7 skipped to **7502 passed / 0 skipped** |

## Technical Details

### Why `pgsty/minio`, and why pinned by digest

It is a third-party republish of the real binaries — `minio --version` inside the image
reports `RELEASE.2026-08-04T00-00-00Z`, AGPLv3; `mc --version` reports
`RELEASE.2026-11-12T00-00-00Z`. It needs no change to the compose service, the env vars,
the entrypoint or the backend: the design holds exactly as written.

**The digest pin is the point.** A tag on somebody else's repository can be moved under
us; a digest cannot. Re-pinning is a deliberate act, never a floating tag.

### The candidates were measured, not chosen on reputation

Run 041's privacy probe, applied to every pullable candidate — a presigned GET must
succeed, an unsigned GET must be refused, an expired presigned GET must be refused, and an
anonymous PUT must be refused:

| Store | signed | unsigned | expired | anon PUT | Verdict |
|---|---|---|---|---|---|
| `pgsty/minio` | 200 | **403** | **403** | refused | **PASS** |
| `dxflrs/garage` v1.0.1 | 200 | **403** | **400** | refused | **PASS** |
| `localstack` 3.8.1 | 200 | 200 | 200 | **ACCEPTED** | FAIL |
| `chrislusf/seaweedfs` | 200 | 200 | 200 | **ACCEPTED** | FAIL |

LocalStack fails exactly as `adobe/s3mock` did. SeaweedFS reproduced run 041's finding
precisely. Either would make *"the bucket is private"* false locally while every backend
test stayed green.

**Garage is the first-party alternative and it passes**, but it needs a node layout, an
`rpc_secret` and explicit key grants before it serves a byte — a design revision rather
than an image swap — and it is S3-*compatible* rather than S3, which weakens the "same
client, different endpoint" argument that chose MinIO over a `MEDIA_ROOT` volume. It is
recorded in `docker-compose.yml` as the fallback if a third-party image is ever judged
unacceptable.

### Verification

1. `make up` on a store that has never existed → bucket present.
2. `make up` again, and `make buckets` again → both exit 0.
3. The privacy probe against the **project's own bucket**, not a generic container.
4. `manage.py check` → E008 clears.
5. `tests/adapters/test_blob.py` → 0 skipped.
6. Full suite, `ruff`, `lint-imports`.
7. `make client` without the `BLOB_ADAPTER=memory` workaround.

## Based on Design Doc

Reference: `.specs-fire/intents/account-profile-expansion/work-items/object-storage-and-minio-design.md`

---
*Plan approved at checkpoint. Execution follows.*
