import { describe, expect, it } from "vitest";

import {
  MAX_PATH_LENGTH,
  MAX_PATHS,
  bearerToken,
  isValidPayload,
  secretMatches,
} from "@/lib/revalidation";

/**
 * The revalidation signal's contract.
 *
 * **This module is the edge's front door, and it is the only place a stranger can
 * reach.** The `/revalidate` handler is machine-to-machine, but the *parsing* of what
 * arrives there is ordinary input handling — and a bug in it is either a denial of
 * service (a body that floods the cache with invalidations) or, worse, an open door
 * (a body that invalidates paths we do not serve).
 *
 * **The bounds are the contract, and they are asserted at their edges.** A limit of
 * "100 paths" that is really "101 paths" is not a limit, and a limit of "1024
 * characters" that is really "no limit" is not a limit either. So every bound is
 * tested on both sides: one below it, exactly at it, and one above it.
 */

describe("secretMatches", () => {
  it("refuses everything when no secret is configured", () => {
    // **A missing configuration fails closed.** A deployment with no
    // `REVALIDATION_SECRET` has no shared secret to check against, so accepting any
    // request would let anyone invalidate our caches.
    expect(secretMatches("anything", undefined)).toEqual({ ok: false, configured: false });
  });

  it("refuses a request that carries no secret", () => {
    expect(secretMatches(null, "the-secret")).toEqual({ ok: false, configured: true });
    expect(secretMatches("", "the-secret")).toEqual({ ok: false, configured: true });
  });

  it("accepts the exact secret", () => {
    expect(secretMatches("the-secret", "the-secret")).toEqual({ ok: true, configured: true });
  });

  it("refuses a secret of a different length", () => {
    // **The lengths are compared first**, because `timingSafeEqual` throws when they
    // differ. A different length is refused rather than crashing the handler.
    expect(secretMatches("short", "the-secret")).toEqual({ ok: false, configured: true });
    expect(secretMatches("the-secret-and-then-some", "the-secret")).toEqual({
      ok: false,
      configured: true,
    });
  });

  it("refuses a secret of the same length but different content", () => {
    expect(secretMatches("the-secrez", "the-secret")).toEqual({ ok: false, configured: true });
  });

  it("does not compare a secret of a different length character by character", () => {
    // **A secret's length is not a secret worth hiding** — the code says so
    // explicitly — so a length mismatch is refused plainly rather than being padded
    // and compared.
    expect(secretMatches("a", "b")).toEqual({ ok: false, configured: true });
  });
});

describe("bearerToken", () => {
  it("reads the token out of a bearer header", () => {
    expect(bearerToken("Bearer the-secret")).toBe("the-secret");
  });

  it("accepts a lowercase scheme, because HTTP's scheme is case-insensitive", () => {
    // **RFC 7235: the scheme is case-insensitive.** A caller that sends `bearer`
    // is not an attacker, and refusing them would be a bug in our parser.
    expect(bearerToken("bearer the-secret")).toBe("the-secret");
    expect(bearerToken("BEARER the-secret")).toBe("the-secret");
  });

  it("trims the header before reading it", () => {
    expect(bearerToken("  Bearer the-secret  ")).toBe("the-secret");
  });

  it("reads a token that contains spaces, because only the scheme is separated", () => {
    // **The scheme is one space, then the token.** A token with a space in it is
    // still a token, and truncating it at the first space would compare a prefix
    // against a secret — which is a way to *guess* a secret a character at a time.
    expect(bearerToken("Bearer the secret")).toBe("the secret");
  });

  it("refuses a header that is not a bearer", () => {
    expect(bearerToken("Basic the-secret")).toBeNull();
    expect(bearerToken("the-secret")).toBeNull();
    expect(bearerToken("Bearer")).toBeNull();
    expect(bearerToken("Bearer ")).toBeNull();
  });

  it("refuses a missing header", () => {
    expect(bearerToken(null)).toBeNull();
  });
});

describe("isValidPayload", () => {
  /** A payload that is valid, so a test can change one thing and see only that. */
  function payload(overrides: Record<string, unknown> = {}) {
    return {
      paths: ["/events/designing-for-calm-2026-08-28-a1b2c3"],
      event_version: 3,
      ...overrides,
    };
  }

  it("accepts a well-formed payload", () => {
    expect(isValidPayload(payload())).toBe(true);
  });

  it("refuses a body that is not an object", () => {
    expect(isValidPayload(null)).toBe(false);
    expect(isValidPayload("a string")).toBe(false);
    expect(isValidPayload(42)).toBe(false);
    expect(isValidPayload([])).toBe(false);
  });

  it("refuses a payload with no paths", () => {
    expect(isValidPayload(payload({ paths: [] }))).toBe(false);
  });

  it("accepts exactly the maximum number of paths", () => {
    // **The bound is a bound, so it is tested on both sides.** A limit of 100 that is
    // really 101 is not a limit.
    const paths = Array.from({ length: MAX_PATHS }, (_, i) => `/events/e-${i}`);
    expect(isValidPayload(payload({ paths }))).toBe(true);
  });

  it("refuses one path more than the maximum", () => {
    const paths = Array.from({ length: MAX_PATHS + 1 }, (_, i) => `/events/e-${i}`);
    expect(isValidPayload(payload({ paths }))).toBe(false);
  });

  it("accepts a path of exactly the maximum length", () => {
    const path = `/${"a".repeat(MAX_PATH_LENGTH - 1)}`;
    expect(path.length).toBe(MAX_PATH_LENGTH);
    expect(isValidPayload(payload({ paths: [path] }))).toBe(true);
  });

  it("refuses a path one character too long", () => {
    const path = `/${"a".repeat(MAX_PATH_LENGTH)}`;
    expect(path.length).toBe(MAX_PATH_LENGTH + 1);
    expect(isValidPayload(payload({ paths: [path] }))).toBe(false);
  });

  it("refuses an empty path", () => {
    expect(isValidPayload(payload({ paths: [""] }))).toBe(false);
  });

  it("refuses a path that is not a path on this site", () => {
    // **A caller cannot name a host or another site's path**, so there is no way to
    // make the frontend revalidate something it does not serve.
    expect(isValidPayload(payload({ paths: ["https://elsewhere.test/x"] }))).toBe(false);
    expect(isValidPayload(payload({ paths: ["events/x"] }))).toBe(false);
  });

  it("refuses a protocol-relative path", () => {
    // **`//host/path` is a protocol-relative URL**, not a path — a browser would read
    // it as a host. A validator that only checked the leading slash would accept it.
    expect(isValidPayload(payload({ paths: ["//elsewhere.test/x"] }))).toBe(false);
  });

  it("accepts the root path", () => {
    // **`/` is a path on this site**, and the revalidation of the root is
    // legitimate — it is the digest's own path.
    expect(isValidPayload(payload({ paths: ["/"] }))).toBe(true);
  });

  it("refuses a path that is not a string", () => {
    expect(isValidPayload(payload({ paths: [42] }))).toBe(false);
    expect(isValidPayload(payload({ paths: [null] }))).toBe(false);
  });

  it("refuses a version that is not a positive integer", () => {
    expect(isValidPayload(payload({ event_version: 0 }))).toBe(false);
    expect(isValidPayload(payload({ event_version: -1 }))).toBe(false);
    expect(isValidPayload(payload({ event_version: 1.5 }))).toBe(false);
    expect(isValidPayload(payload({ event_version: "3" }))).toBe(false);
    expect(isValidPayload(payload({ event_version: null }))).toBe(false);
  });

  it("accepts the first version", () => {
    // **Version 1 is a real version** — an event's first `event_version` — so the
    // bound cannot be "greater than one".
    expect(isValidPayload(payload({ event_version: 1 }))).toBe(true);
  });
});
