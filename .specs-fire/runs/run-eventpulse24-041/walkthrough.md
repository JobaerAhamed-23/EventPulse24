---
run: run-eventpulse24-041
work_item: object-storage-and-minio
intent: account-profile-expansion
date: 2026-11-19
---

# Walkthrough: the backend learns to hold bytes

## The shape was not a free choice

The plan said "MinIO plus `django-storages`". Reading the tree said otherwise.

`backend/ports/` and `backend/adapters/` route **every** external system this codebase
touches — email, billing, calendars, geo, the throttle, revalidation, the LLM, source
fetches — through `ports/registry.py`, which resolves a dotted path out of
`settings.ADAPTERS`. An import-linter contract forbids `apps` from importing `adapters`
at all. Django's `STORAGES` would have been the **one** external system sitting inside
the app layer: un-fakeable in tests, un-swappable at deploy.

So object storage is a port. The testing criterion then cost nothing — the in-memory
adapter *is* how the suite runs without a store, exactly as `InMemoryThrottleAdapter`
already works.

**`config/adapters.py` also settled how the local stack behaves**, in its own words about
email: *"Email still really sends, to Mailpit."* MinIO is Mailpit for bytes. A fake object
store would let a wrong endpoint, a missing bucket or an unsigned URL pass the local stack
and fail at a deploy, so fake mode stores bytes for real and only the **test** settings
drop to memory.

## What the port refuses, and why it refuses it there

The key rules live on `BlobPort`'s `@final` methods, the arrangement `EmailPort` uses for
its stream rules — so no adapter can skip them. An empty key names nothing; a leading
slash or a `..` segment is traversal, harmless against S3's flat namespace and dangerous
against any adapter that ever writes to a filesystem; whitespace and control characters do
not survive a URL intact. **A refused key is refused before the store is touched**, which
is asserted rather than assumed.

Keys are opaque (AD-13): a key is a second place PII would live at rest, and it is also
the thing that ends up in a URL.

## The finding that changed the design

The design wanted a presigned URL that is stable within a window, because the shell is
server-rendered on **every** page and a URL that churns per render re-downloads the
picture on every navigation.

It cannot be had safely. `SigV4Auth.add_auth` assigns
`request.context['timestamp'] = get_current_datetime()` **unconditionally**; the
documented `before-sign` hook is overwritten; and the only thing that works is swapping a
module-level global botocore does not publish, in a server that runs threaded.

**A cacheable avatar URL is not worth a data race in the signing path.** So the port
promises a *working* URL and never a *stable* one — pinned by a test that says so in its
docstring — and the stable address moved into the app, where `avatar-endpoint-and-contract`
now carries a redirect endpoint with two cache rules it did not have before.

## Two settings that look redundant and are not

`BLOB_ENDPOINT` is the address this process dials. `BLOB_PUBLIC_ENDPOINT` is the address a
signature is minted for. A SigV4 signature is bound to the host in its canonical request,
so one setting cannot be both — and **getting them the wrong way round produces a URL that
every backend test accepts and no browser can fetch.** That is why `E008`'s hint names
which is which, and why a test asserts the hint does.

## Where the failure is reported, and why in two places

`config/env.py` validates the case an operator asked for by name (`BLOB_ADAPTER=s3`).
`config/checks.py` validates the **resolved** adapter table, which is the usual case,
because the adapter is normally whatever `ADAPTER_MODE` chose and that resolution happens
after `env` is built.

That split is load-bearing, not tidy: a validator that refused the unset case in `env`
would refuse to **boot the test suite**, which runs on the in-memory adapter and dials no
store at all.

## What is still open

The container. MinIO's images are denied here on both registries, for every tag — verified
against its GitHub releases and still denied, so it is access, not a typo. Everything
except `make up` is proved, including the S3 adapter against a real S3 server and a minted
URL fetched by `curl` from outside the process.

**What is not proved is the privacy property**, and that is the one that matters: the two
substitutes that *could* be pulled both serve unsigned and expired URLs with 200. A store
that ignores signatures makes "the bucket is private" false in development while every
test passes.
