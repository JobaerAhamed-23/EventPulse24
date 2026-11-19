---
run: run-eventpulse24-052
work_item: avatar-endpoint-and-contract
intent: account-profile-expansion
generated: 2026-11-19
mode: confirm
---

# Walkthrough: Uploading It — a Multipart Endpoint on a Router With No Auth

## What this run built

Three endpoints on `/api/auth` and one field on `me`:

| | |
|---|---|
| `POST /api/auth/profile/avatar` | multipart, one `file` field → the updated profile |
| `DELETE /api/auth/profile/avatar` | removes it; removing nothing is a success |
| `GET /api/auth/profile/avatar/{version}` | 302 → a freshly signed URL |
| `CurrentUserOut.avatar_url` | `""` when unset, so the shell needs no second call |

**7544 backend, 2698 frontend, 0 type errors, 21 contracts kept.**

## The multipart question, answered rather than assumed

The work item said to check whether the project's stack handles `multipart/form-data`
before assuming it, and to solve it here if the generated client could not.

**It was all new** — zero occurrences of `multipart/form-data`, `FormData` or
`UploadedFile` anywhere before this run.

Ninja and the schema generator were fine. **The client was not.** OpenAPI's
`format: binary` has no TypeScript equivalent, so the generated type is `file: string` —
a real `File` would not typecheck — and `openapi-fetch` serialises bodies as JSON unless
told otherwise, while a hand-written `Content-Type` would omit the multipart boundary and
the server would fail to parse the body.

`frontend/lib/avatar-upload.ts` absorbs both, once, with the reasoning written down: one
cast and one `bodySerializer`. The generator is deliberately left alone — fixing the type
properly would mean driving `openapi-typescript` from a Node script instead of the CLI,
changing how `make client` works project-wide for one field. The UI item now inherits
`uploadAvatar(file)` rather than an unknown.

## Two rules that would have drifted

**`max-age` is derived, not written twice.** `AVATAR_REDIRECT_MAX_AGE = BLOB_URL_TTL_SECONDS // 2`,
and the test reads *both* settings. A browser caching the redirect longer than the
signature lives shows a broken picture for exactly the difference — and only after its
cache warms, which is the worst kind of failure to find.

**A stale version is refused, not served.** An old URL may have been shared while it was
current; resolving it to whatever the account holds *now* would leak the current picture
to whoever kept the link.

## The bug that was a supported mode

`BLOB_ADAPTER=memory` is documented as "run with no object store at all". In that mode the
redirect answered **400 Suspicious operation** for every user — the memory adapter mints
`memory://…`, and Django refuses to redirect outside http/https/ftp. **A broken feature
reported as a security event.**

A store that cannot mint a fetchable address now has its bytes served inline. The redirect
is an optimisation for stores that *can* serve — it keeps the bytes off this process — not
the contract. The contract is "the caller's picture". Both paths are tested: the 302
against the real store, the fallback against memory.

## The second guard in two runs that wasn't load-bearing

A mutation probe deleted `require_csrf` from the upload handler and **all twenty tests
still passed.**

`current_user` checks the token too, but *after* resolving the caller. So every signed-in
case is refused either way — and only an **anonymous** tokenless request can tell the two
orders apart: 403 "this could not be shown to come from this site" versus 401 "you are not
signed in". The project already had exactly that test for `PUT /profile`
(`test_the_csrf_check_runs_before_the_resolver`) and I had not carried it over.

Two tests added; the mutation now fails.

**Run 051 found the same shape** — a format allow-list that could be deleted with every
test still green. Both were invisible to reading, because every path ended in a refusal,
just not for the reason the code claimed. Reading proves a path exists; only a probe proves
which path ran.

## Nothing in Django caps a file upload

`DATA_UPLOAD_MAX_MEMORY_SIZE` governs the *non-file* part of a request, and files spool to
disk past `FILE_UPLOAD_MAX_MEMORY_SIZE`. A ten-gigabyte POST would be written to disk
before any of this project's code had an opinion about it.

`UploadSizeLimitMiddleware` refuses on the declared length **before the body is parsed** —
which has to be middleware, because Ninja parses the body when it resolves the handler's
file parameter, so a check inside the handler runs too late.

It treats `Content-Length` as a claim, not a fact, and says so: a request that lies still
meets `read(cap + 1)` in the command. Two cheap checks, and the trustworthy one is the one
that reads.

## A guard answered the checkpoint question for me

At the checkpoint I flagged that this is the first endpoint consumed by the browser's image
loader rather than typed client code, and proposed keeping it on `/api/auth`.

The project's own `endpoint-coverage` test then **failed on exactly that**, because the
endpoint has no frontend caller. It is now in `DECLARED_UNCALLED` with its reason — a
better outcome than my handler comment, because the next person meets the rule rather than
the prose.

## What is left in the intent

| Work item | Status |
|---|---|
| `avatar-on-the-shell` | pending — medium, confirm. `uploadAvatar` is ready for it |
| `profile-screen-and-e2e` | pending — medium, confirm |
| `account-deletion-and-avatar-removal` | pending — high, validate |

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-052*
