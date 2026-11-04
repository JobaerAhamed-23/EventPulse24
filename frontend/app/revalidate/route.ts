// The revalidation route handler (FR-26, FR-27).
//
// **The backend pushes a cache instruction here; this handler invalidates caches.** It
// holds no domain logic and reads no event data: the body names *paths* and a version,
// nothing else. Every fact on a public page still comes from the backend through the
// generated API client (AD-19) — this edge is a cache instruction, not a data source.
//
// **The path is `/revalidate`, not `/api/revalidate`, and that is load-bearing.** The
// proxy rewrites every `/api/:path*` request to Django (`proxy.ts`), so a handler under
// `/api/` would be unreachable — the request would never arrive.
//
// **No cookie is read.** This is a machine-to-machine endpoint: the backend authenticates
// with a shared secret, and a session cookie would be both irrelevant and a liability.
//
// **The order of the checks is the order of the answers.** A request with no secret
// configured gets 503 (the deployment is broken); a request with the wrong secret gets 401
// (the caller is not who they say they are); a malformed body gets 400 (the caller is
// right but the message is wrong). A bad secret never reaches the body parser, so a
// stranger cannot make us parse anything.

import { revalidatePath, revalidateTag } from "next/cache";

import { bearerToken, isValidPayload, secretMatches } from "@/lib/revalidation";

export const dynamic = "force-dynamic";

/** The shared secret, from the deployment's environment. */
function expectedSecret(): string | undefined {
  return process.env.REVALIDATION_SECRET;
}

export async function POST(request: Request): Promise<Response> {
  const { ok, configured } = secretMatches(
    bearerToken(request.headers.get("authorization")),
    expectedSecret(),
  );
  if (!configured) {
    // The deployment has no secret. Failing closed is the only safe answer: accepting
    // every request would let anyone invalidate our caches.
    return Response.json(
      { code: "revalidation_not_configured", message: "Revalidation is not available." },
      { status: 503 },
    );
  }
  if (!ok) {
    return Response.json(
      { code: "invalid_token", message: "Invalid revalidation token." },
      { status: 401 },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json(
      { code: "invalid_body", message: "The request body is not valid JSON." },
      { status: 400 },
    );
  }
  if (!isValidPayload(body)) {
    return Response.json(
      { code: "invalid_body", message: "The request body is not a revalidation request." },
      { status: 400 },
    );
  }

  // **Rebuilding is idempotent, so repeating it is harmless.** An invalidation that is
  // already invalid does nothing; a duplicate signal therefore costs a render at most,
  // and changes nothing about what the page shows.
  //
  // **Two invalidations, because two caches can hold this page.**
  //
  // `revalidatePath` drops the *page* from the Full Route Cache, for any route that
  // lives there. `revalidateTag` drops the *facts* from the data cache — which is
  // where `/events/{slug}`'s payload lives, because that segment is `force-dynamic`
  // (it also serves the personal Detail Screen, and one segment has one rendering
  // mode, so its page is never in the Full Route Cache).
  //
  // **The page invalidation is a no-op for this segment today, and it is kept anyway.**
  // The segment is dynamic, so there is no cached page to drop — but `revalidatePath`
  // is the general form of the instruction, and a future segment that *is* static
  // would need it. Dropping it would mean the signal only worked for the caches that
  // happen to exist today.
  //
  // **The tag is the path itself.** `lib/public-event-read.ts` tags its cached read
  // with the event's own path — `/events/{slug}` — which is the same string the
  // backend's signal names (`domain/revalidation.py`, `EVENT_PATH_PREFIX`). The two
  // must be the same string, or the signal invalidates nothing.
  //
  // **`expire: 0` is "expire now".** Next 16's `revalidateTag` takes a cache-life
  // profile, and a profile with no expiry would leave the entry alive until its own
  // TTL. The signal means "this page is stale *now*", so the entry expires now.
  for (const path of body.paths) {
    revalidatePath(path);
    revalidateTag(path, { expire: 0 });
  }

  return Response.json(
    { revalidated: body.paths.length, event_version: body.event_version },
    { status: 200 },
  );
}

/**
 * The other verbs are refused.
 *
 * **A GET would be a page, and a page is public.** This endpoint must not be
 * indexable, and a GET that "revalidates" would let anyone invalidate our caches with a
 * link. So only POST works, and everything else is 405.
 */
export async function GET(): Promise<Response> {
  return Response.json(
    { code: "method_not_allowed", message: "Use POST." },
    { status: 405, headers: { Allow: "POST" } },
  );
}
