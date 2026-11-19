---
run: run-eventpulse24-050
work_item: object-storage-and-minio
intent: account-profile-expansion
generated: 2026-11-19
mode: validate
---

# Walkthrough: Object Storage, From Nothing — the block that was never a login

## What this run did

**Unblocked five work items by changing one line**, and proved the three things run 041
could not.

`object-storage-and-minio` had been `blocked` since 2026-11-19 morning with its
implementation complete — the blob port, both adapters, the settings validation, the
compose services, the bucket job. Three proofs waited on an image that would not pull, and
behind them sat the whole avatar thread.

**The backend suite is now 7502 passed, 0 failed, 0 skipped** — the first fully-green,
fully-unskipped run. Seven of those tests are the S3 adapter's, which had never executed
because no object store could be started.

## The block was misdiagnosed, and that is why it lasted

Run 041 concluded: *"The repository is denied on Docker Hub **and** quay.io … so it is
access, not a tag typo. The user's decision is to keep MinIO and `docker login`."*

**`docker login` could never have worked.**

| Probe | Result |
|---|---|
| `docker pull hello-world` | succeeds — daemon, network and Hub access all fine |
| `hub.docker.com/v2/repositories/minio/minio/` | **HTTP 404 `object not found`** |
| `docker system info` | no username — never logged in |
| `quay.io/minio/minio` | 401 to anonymous |

MinIO **deleted** `minio/minio` and `minio/mc` from Docker Hub in September 2026, having
stopped publishing community images in October 2025.

**The trap is the error message.** Docker reports a repository that is *absent* and one
that is *forbidden* with the same sentence — *"pull access denied … may require 'docker
login'"* — and the two have opposite remedies. Run 041 already had the decisive clue in
its own notes (`hello-world` pulls fine); one more question — *does this repository
exist?* — would have shown the 404. Instead "it is access" was carried forward as settled
fact by four later runs.

**When a pull fails, ask the registry whether the repository exists before reaching for
credentials.**

## The replacement was measured, not chosen on reputation

Run 041 had already disqualified two candidates for a precise reason: `adobe/s3mock` and
`chrislusf/seaweedfs` return **200 to an unsigned URL and 200 to an expired one** — *"a
store that ignores signatures makes 'the bucket is private' false locally while every test
passes."*

So every pullable candidate faced the same four questions:

| Store | signed | **unsigned** | **expired** | **anon PUT** | Verdict |
|---|---|---|---|---|---|
| `pgsty/minio` | 200 | **403** | **403** | refused | **PASS** |
| `dxflrs/garage` v1.0.1 | 200 | **403** | **400** | refused | **PASS** |
| `localstack` 3.8.1 | 200 | 200 | 200 | **ACCEPTED** | FAIL |
| `chrislusf/seaweedfs` | 200 | 200 | 200 | **ACCEPTED** | FAIL |

LocalStack fails exactly as `adobe/s3mock` did. **SeaweedFS reproduced run 041's result
precisely** — the earlier measurement was right, and re-checking it cost a minute. Garage
returns 400 rather than 403 on the expired URL: it rejects the stale signature at parse
time.

## What changed

**Two image references**, pinned by digest:

```yaml
image: pgsty/minio@sha256:b6bfe7239bfc83fb90d31612d9704d86039dd714f7904b3f1ad68f211e602372
image: pgsty/mc@sha256:b532278b7a3747dbab6fe45eebb40a653efa704e6758e24e9d9ec54fc96c1800
```

It is a third-party republish of the real binaries — `minio --version` reports
`RELEASE.2026-08-04T00-00-00Z`, AGPLv3; `mc` reports `RELEASE.2026-11-12T00-00-00Z`. No
other change was needed: same env vars, same entrypoint, same healthcheck. The design
holds as written.

**Pinned by digest precisely because it is third-party.** A tag on somebody else's
repository can be moved under us; a digest cannot.

The compose file now carries the evidence, the Docker-Hub-404 story, and `dxflrs/garage`
as the named first-party fallback — so none of it has to be rediscovered.

## The three proofs

**1. `make up`, twice, on a store that had never existed.** `docker volume ls` showed only
`eventpulse24_pgdata`, so the first run was genuinely the fresh-clone case. MinIO went
Healthy on its own healthcheck; the bucket was created; the second `make up` and a second
`make buckets` both exited 0. Run 041's `profiles: ["bootstrap"]` mitigation — which it
measured as *required, not precautionary* — holds.

(`docker compose down -v` was deliberately **not** used. It would also destroy the
Postgres volume, which holds real local data.)

**2. The bucket job against real `mc`** — alias set, bucket created, **no anonymous
policy**, `bucket ready: eventpulse24-blobs (private)`.

**3. The privacy probe against the project's own bucket** — not a generic container:

```
RESULT signed=200 unsigned=403 expired=403 anon_put=ClientError
VERDICT PASS
```

The probe object was removed afterwards, and all four probe containers were torn down.

## One thing that bit, and will bite the next person

**`.env` predates the blob work, and `make env` never overwrites an existing file.** So
every `BLOB_*` key was simply absent, `manage.py check` raised `E008`, and `make client`
failed — which is why earlier runs needed the `BLOB_ADAPTER=memory` workaround. The E008
message is good: it names the keys. But `make env` says only *"already exists — leaving it
unchanged"*, which is true and unhelpful.

Fixed locally by appending the block from `.env.example`. **Still open for anyone else
whose `.env` predates this work** — a `make doctor` check for missing keys would close it.

## What this unblocks

`account-profile-expansion` goes from 5 blocked/pending to **4 pending, 0 blocked**:

| Work item | Status |
|---|---|
| `avatar-model-and-command` | pending — high, validate, **now unblocked** |
| `avatar-endpoint-and-contract` | pending — medium, confirm |
| `avatar-on-the-shell` | pending — medium, confirm |
| `profile-screen-and-e2e` | pending — medium, confirm |

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-050*
