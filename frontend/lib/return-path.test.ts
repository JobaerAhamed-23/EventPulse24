import { describe, expect, it } from "vitest";

import { returnPath, signInUrl } from "@/lib/return-path";

/**
 * The `next` guard.
 *
 * **This is the open-redirect rule, and it is the reason this module exists.** A `next`
 * parameter taken from the query string and used as a redirect target is the classic open
 * redirect: a link like `/signin?next=https://attacker.example/steal` sends a visitor
 * who has just typed their password to somebody else's site, with the site's own domain
 * lending its credibility.
 *
 * So each test below is a spelling of an attack. If one of them starts returning
 * something other than `/`, a redirect goes somewhere it should not.
 */
describe("returnPath", () => {
  it("accepts a path on this site", () => {
    expect(returnPath("/pricing")).toBe("/pricing");
    expect(returnPath("/settings/reminders")).toBe("/settings/reminders");
  });

  it("accepts a path with a query string of its own", () => {
    expect(returnPath("/pricing?plan=yearly")).toBe("/pricing?plan=yearly");
  });

  it("rejects an absolute URL", () => {
    expect(returnPath("https://attacker.example/steal")).toBe("/");
    expect(returnPath("http://attacker.example/steal")).toBe("/");
  });

  it("rejects a protocol-relative URL, which is a host and not a path", () => {
    // `//evil.example` starts with `/` but browsers read it as a host.
    expect(returnPath("//attacker.example")).toBe("/");
    expect(returnPath("//attacker.example/steal")).toBe("/");
  });

  it("rejects a backslash, which some browsers read as a slash", () => {
    // `/\attacker.example` is another spelling of `//attacker.example`.
    expect(returnPath("/\\attacker.example")).toBe("/");
    expect(returnPath("/pricing\\..\\evil")).toBe("/");
  });

  it("rejects a scheme, which is not a path", () => {
    expect(returnPath("javascript:alert(1)")).toBe("/");
    expect(returnPath("data:text/html,<script>alert(1)</script>")).toBe("/");
  });

  it("rejects a relative path, because it is not a path on this site", () => {
    expect(returnPath("pricing")).toBe("/");
    expect(returnPath("./pricing")).toBe("/");
    expect(returnPath("../pricing")).toBe("/");
  });

  it("falls back to the home for anything that is not a string", () => {
    expect(returnPath(null)).toBe("/");
    expect(returnPath(undefined)).toBe("/");
    expect(returnPath("")).toBe("/");
    expect(returnPath("   ")).toBe("/");
  });
});

describe("signInUrl", () => {
  it("encodes the path, so it cannot break out of the query string", () => {
    expect(signInUrl("/pricing")).toBe("/signin?next=%2Fpricing");
  });

  it("keeps a path's own query string intact", () => {
    // The `?` must survive the round trip rather than becoming a second parameter of the
    // sign-in URL.
    expect(signInUrl("/pricing?plan=yearly")).toBe("/signin?next=%2Fpricing%3Fplan%3Dyearly");
  });
});
