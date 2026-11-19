---
run: run-eventpulse24-050
work_item: object-storage-and-minio
intent: account-profile-expansion
generated: 2026-11-19
status: passed
---

# Test Report: Object Storage, From Nothing — MinIO Beside Postgres

## Summary

| Category | Passed | Failed | Skipped |
|----------|--------|--------|---------|
| Backend (full suite) | **7502** | **0** | **0** |
| `tests/adapters/test_blob.py` | 29 | 0 | 0 |

**The first fully-green, fully-unskipped backend run.** It was 7495 passed / 7 skipped
before: those 7 are the S3-parameterised adapter tests, which had never executed because
no object store could be started. They now run against a real one.

## The three proofs run 041 could not make

### 1. `make up` end to end, twice, on a store that had never existed

`docker volume ls` confirmed only `eventpulse24_pgdata` existed — the MinIO volume had
never been created, so the first `make up` **is** the fresh-clone case. (A `down -v` was
deliberately not used: it would also destroy the Postgres volume, which holds real local
data.)

| Run | Result |
|---|---|
| `make up` (fresh) | MinIO **Healthy** on its own `mc ready local` healthcheck; `Bucket created successfully`; `bucket ready: eventpulse24-blobs (private)` |
| `make up` (again) | exit 0 — the compose profile trick works as designed |
| `make buckets` (again) | exit 0 — `mc mb --ignore-existing` is idempotent |

The `profiles: ["bootstrap"]` mitigation that run 041 measured as *required, not
precautionary* is confirmed: `up -d --wait` does not trip over the one-shot service.

### 2. The bucket job against real `mc`

`mc --version` → `RELEASE.2026-11-12T00-00-00Z`. The job set its alias, created the
bucket, set **no anonymous policy**, and printed `bucket ready: … (private)`.

### 3. The privacy probe — against the project's own bucket

Not a generic container: `http://127.0.0.1:9000`, bucket `eventpulse24-blobs`, the
project's own credentials.

```
RESULT signed=200 unsigned=403 expired=403 anon_put=ClientError
VERDICT PASS
```

The probe object was removed from the dev bucket afterwards.

## The candidates were measured before one was chosen

The same four questions, against every pullable candidate:

| Store | signed | **unsigned** | **expired** | **anon PUT** | Verdict |
|---|---|---|---|---|---|
| `pgsty/minio` | 200 | **403** | **403** | `ClientError` | **PASS** |
| `dxflrs/garage` v1.0.1 | 200 | **403** | **400** | `AccessDenied` | **PASS** |
| `localstack` 3.8.1 | 200 | 200 | 200 | **ACCEPTED** | FAIL |
| `chrislusf/seaweedfs` | 200 | 200 | 200 | **ACCEPTED** | FAIL |

**SeaweedFS reproduced run 041's finding exactly**, which is worth stating: the earlier
measurement was right, and re-running it cost a minute. LocalStack fails identically to
`adobe/s3mock`. Garage returns **400** on the expired URL rather than 403 — it rejects the
stale signature at parse time.

## Acceptance Criteria Validation

- ✅ **A MinIO service in `docker-compose.yml` beside Postgres and Redis**, own volume, healthcheck, console port bound to localhost — shipped in run 041, now *verified running*.
- ✅ **Bucket creation that is idempotent** — `make up` twice and `make buckets` twice, all exit 0.
- ✅ **Settings validated once at startup through pydantic-settings** — `manage.py check` reports `no issues` where it previously raised `E008`.
- ✅ **No credential defaulted to a live value and none committed** — `.env.example` carries dev-only placeholders; `.env` is gitignored.
- ✅ **A storage backend registered in Django's `STORAGES`, used by nothing yet.**
- ✅ **The decision recorded: public keys vs signed short-lived URLs** — signed, and now *measured*: unsigned and expired both refused.

## Verification performed

| Check | Result |
|---|---|
| Full backend suite | **7502 passed, 0 failed, 0 skipped** |
| `tests/adapters/test_blob.py` | 29 passed (was 22 passed + **7 skipped**) |
| `manage.py check` | no issues (was `E008`) |
| `make client` | succeeds **without** the `BLOB_ADAPTER=memory` workaround |
| Generated client | unchanged — no API change this run |
| `ruff check .` | clean |
| `lint-imports` | 20 contracts kept, 0 broken |
| `docker compose config` | valid |

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| `docker login` could never have unblocked this | **High** | **Diagnosed.** `minio/minio` is **404 on Docker Hub** — deleted September 2026 — while `hello-world` pulls fine. Docker reports *absent* and *forbidden* with the same sentence, and that ambiguity cost this project days. |
| An existing `.env` silently lacks every `BLOB_*` key | **Medium** | **Worked around locally; still open for others.** `make env` refuses to overwrite an existing `.env`, so anyone whose `.env` predates the blob work gets `E008` and no hint that their *file* is the problem. The E008 message names the keys, which is good, but `make env` says only "leaving it unchanged". Worth a `make doctor` check. |
| `mc mb --ignore-existing` prints "Bucket created successfully" when the bucket already exists | Low | **Noted, not changed.** Cosmetic; exit 0 is the contract and it holds. |

## Ready for Completion

- [x] All tests passing — 7502, nothing skipped
- [x] Coverage target met — the S3 adapter is exercised against a real store for the first time
- [x] All acceptance criteria validated (6 of 6)
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-050*
