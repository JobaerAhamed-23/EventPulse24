import { beforeEach, describe, expect, it, vi } from "vitest";

import { cookieStore, type CookieStore } from "@/tests/cookie-store";

/**
 * The consecutive-failure count.
 *
 * **§5's error rule is stateful**: the first failure says "Try again", the second
 * *consecutive* one says "Refresh page." The count that decides between them lives in
 * a cookie the server owns, because the retry is a navigation and a client-side counter
 * cannot survive one.
 *
 * The interesting cases are the edges: a malformed cookie, a success between two
 * failures, and the difference between "how many failures have happened" and "how many
 * happened before this one" — which is exactly the distinction the label turns on.
 */

let jar: CookieStore;

vi.mock("next/headers", () => ({
  cookies: async () => jar,
}));

const { ATTEMPT_COOKIE, attemptFromCookie, clearAttempt, readAttempt, recordFailure } =
  await import("@/lib/digest-attempt");

beforeEach(() => {
  jar = cookieStore();
});

describe("the count itself", () => {
  it("reads a missing cookie as no failures", () => {
    expect(attemptFromCookie(undefined)).toBe(0);
  });

  it("reads a well-formed cookie", () => {
    expect(attemptFromCookie("3")).toBe(3);
  });

  it("reads a malformed cookie as no failures, because the cookie is untrusted input", () => {
    // The cookie is user-writable. Anything that is not a positive integer is "no
    // failures yet" — a crash here would be a crash on every visit.
    expect(attemptFromCookie("not a number")).toBe(0);
    expect(attemptFromCookie("-1")).toBe(0);
    expect(attemptFromCookie("0")).toBe(0);
    expect(attemptFromCookie("")).toBe(0);
    expect(attemptFromCookie("Infinity")).toBe(0);
  });

  it("floors a fractional count", () => {
    expect(attemptFromCookie("2.7")).toBe(2);
  });
});

describe("recording a failure", () => {
  it("records the first failure and reports no prior failures", async () => {
    // This is the distinction the label turns on: the first failure has zero prior
    // failures, so the error state says "Try again". Returning the new total would
    // make the first failure say "Refresh page.".
    expect(await recordFailure()).toBe(0);
    expect(jar.get(ATTEMPT_COOKIE)?.value).toBe("1");
  });

  it("records the second failure and reports one prior failure", async () => {
    await recordFailure();
    expect(await recordFailure()).toBe(1);
    expect(jar.get(ATTEMPT_COOKIE)?.value).toBe("2");
  });

  it("counts up across many failures", async () => {
    for (let index = 0; index < 4; index += 1) await recordFailure();
    expect(jar.get(ATTEMPT_COOKIE)?.value).toBe("4");
  });
});

describe("reading the count", () => {
  it("reads what was recorded", async () => {
    await recordFailure();
    await recordFailure();
    expect(await readAttempt()).toBe(2);
  });

  it("reads zero when nothing was recorded", async () => {
    expect(await readAttempt()).toBe(0);
  });
});

describe("clearing the count", () => {
  it("forgets the failures, so a success breaks the run", async () => {
    await recordFailure();
    await recordFailure();
    expect(await readAttempt()).toBe(2);

    await clearAttempt();

    expect(await readAttempt()).toBe(0);
    expect(jar.get(ATTEMPT_COOKIE)).toBeUndefined();
  });

  it("is safe to clear when there was nothing to clear", async () => {
    await expect(clearAttempt()).resolves.toBeUndefined();
  });
});
