// The revalidation signal's contract (FR-26, FR-27).
//
// **The signal carries paths and a version, and no event data.** No title, no status, no
// time, no venue. That is deliberate: the direction of data flow between the frontend and
// the backend is unchanged. The frontend still holds no domain logic and still gets every
// fact through the generated API client — the backend is only telling it *which cached
// pages are now wrong*, never *what is true*.
//
// **The secret is compared, not parsed.** `timingSafeEqual` is constant-time, so a
// caller cannot learn the secret by timing its guesses. A plain `===` compares
// character by character and returns at the first difference.

import { timingSafeEqual } from "node:crypto";

/** The body the backend posts. */
export type RevalidationPayload = {
  paths: string[];
  event_version: number;
};

/** The most paths one signal may name. A bound, so a malformed caller cannot flood us. */
export const MAX_PATHS = 100;

/** The longest path one signal may name. Mirrors Next's own 1024-character limit. */
export const MAX_PATH_LENGTH = 1024;

/**
 * Whether the request carries our secret.
 *
 * **An absent secret is not an empty secret.** A deployment with no `REVALIDATION_SECRET`
 * configured has no shared secret to check against, so *every* request must be refused —
 * otherwise the endpoint would accept anything. That is why `configured` is separate from
 * `matches`: a missing configuration is a deployment fault, and it fails closed.
 */
export function secretMatches(
  provided: string | null,
  expected: string | undefined,
): { ok: boolean; configured: boolean } {
  if (!expected) {
    // Not configured: refuse everything rather than accept anything.
    return { ok: false, configured: false };
  }
  if (!provided) {
    return { ok: false, configured: true };
  }
  const a = Buffer.from(provided, "utf8");
  const b = Buffer.from(expected, "utf8");
  // `timingSafeEqual` throws when the lengths differ, so lengths are compared first — and
  // the length of the *secret* is not a secret worth hiding.
  if (a.length !== b.length) {
    return { ok: false, configured: true };
  }
  return { ok: timingSafeEqual(a, b), configured: true };
}

/** Whether a body is a well-formed revalidation payload. */
export function isValidPayload(value: unknown): value is RevalidationPayload {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  if (!Array.isArray(candidate.paths)) {
    return false;
  }
  if (candidate.paths.length === 0 || candidate.paths.length > MAX_PATHS) {
    return false;
  }
  for (const path of candidate.paths) {
    if (typeof path !== "string" || path.length === 0 || path.length > MAX_PATH_LENGTH) {
      return false;
    }
    // A path is a path on *our* site. A caller cannot name a host, a protocol, or another
    // site's path — so there is no way to make the frontend revalidate something it does
    // not serve.
    if (!path.startsWith("/") || path.startsWith("//")) {
      return false;
    }
  }
  if (typeof candidate.event_version !== "number" || !Number.isInteger(candidate.event_version)) {
    return false;
  }
  if (candidate.event_version < 1) {
    return false;
  }
  return true;
}

/** The `Authorization` header's bearer token, or `null` when there is none. */
export function bearerToken(header: string | null): string | null {
  if (!header) {
    return null;
  }
  const match = /^Bearer\s+(.+)$/i.exec(header.trim());
  return match ? match[1] : null;
}
