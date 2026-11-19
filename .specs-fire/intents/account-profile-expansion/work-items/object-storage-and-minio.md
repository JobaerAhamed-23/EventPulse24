---
id: object-storage-and-minio
title: Object Storage, From Nothing — MinIO Beside Postgres
intent: account-profile-expansion
complexity: high
mode: validate
status: completed
depends_on: []
created: 2026-11-19
run_id: run-eventpulse24-050
completed_at: 2026-11-19T16:31:10.173Z
---

# Work Item: Object Storage, From Nothing — MinIO Beside Postgres

## Description

**The backend stores no files at all today.** `grep` over `backend/config/`,
`backend/pyproject.toml` and `docker-compose.yml` finds no `MEDIA_ROOT`, no `STORAGES`,
no `DEFAULT_FILE_STORAGE`, no `boto3` and no S3 of any kind. This item is the whole of
that gap, and **nothing else in this intent can start until it closes**.

**MinIO, in `docker-compose`, reached over the S3 API** — the choice the user made
explicitly over a local `MEDIA_ROOT` volume, and the reason is that the volume would
have to be torn out before any real deploy. An S3 client pointed at MinIO is the same
client pointed at a bucket, with a different endpoint.

What this item delivers:

1. A **MinIO service** in `docker-compose.yml` next to Postgres and Redis, with its own
   named volume, a health check, and the console port exposed for local use only.
2. **Bucket creation that is idempotent** — `make up` on a fresh clone must end with the
   bucket present, and running it twice must not fail.
3. **Settings**, validated once at startup through the existing pydantic-settings
   config, as the constitution requires: endpoint, region, bucket, access key, secret
   key, and whether URLs are signed. **No credential is defaulted to a live value and
   none is committed** — `.env.example` gains the keys with dev-only placeholders.
4. A **storage backend** registered in Django's `STORAGES`, used by nothing yet.
5. The **decision, recorded**: public object keys versus signed short-lived URLs. This
   is the open question the brief names, and it is settled here because the bucket's
   policy follows from it.

**It is deliberately not the avatar.** No model field, no endpoint, no UI — those are
the next three items. An item that stood up storage *and* used it would be two
architectures reviewed as one.

## Acceptance Criteria

- [ ] `docker-compose.yml` runs MinIO with a named volume and a health check, and
      `make up` on a clean checkout leaves it healthy
- [ ] The bucket exists after `make up`, and running `make up` a second time **succeeds**
- [ ] Settings are validated at startup through pydantic-settings; a missing or empty
      required key **fails fast with a named error**, not at first upload
- [ ] No credential, key or secret is committed; `.env.example` carries placeholders only
- [ ] A probe uploads a byte string and reads it back through the configured storage,
      proving the client reaches MinIO over the S3 API
- [ ] The public-versus-signed decision is **recorded in the module docstring with its
      rationale**, and the bucket policy matches it
- [ ] The test suite does **not** require a running MinIO: storage is faked or pointed at
      a temp backend in tests, and that seam is explicit
- [ ] CI passes without MinIO credentials in the repository
- [ ] `README` / `runbook.md` say how to reach the console and what to do when the
      bucket is missing
- [ ] Every test added can fail — verified by a mutation probe per test

## Technical Notes

- **Probe before choosing the client.** `boto3` and `django-storages` are the obvious
  pair, but check what is already pinned in `backend/pyproject.toml` before adding
  either — the project pins deliberately and the constitution requires trusted sources.
- **The endpoint differs between the host and the compose network.** The backend
  container reaches MinIO at its service name; a browser given a signed URL reaches it
  at `localhost`. **If signed URLs are chosen, this split is load-bearing** and a URL
  that works from the API container and 404s in the browser is the expected first bug.
- **Preview environments never write to real infrastructure** (constitution). Say what
  preview points at.
- **No PII in the object key.** An email or a name in a key is PII at rest in a second
  place (AD-13); keys should be opaque.

## Dependencies

(none)
