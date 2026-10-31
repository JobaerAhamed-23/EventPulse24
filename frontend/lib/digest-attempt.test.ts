import { describe, expect, it } from "vitest";

import { RETRY_PARAM, attemptFromQuery } from "@/lib/digest-attempt";

/**
 * The consecutive-failure count.
 *
 * **§5's error rule is stateful**: the first failure says "Try again", the second
 * *consecutive* one says "Refresh page." The count that decides between them travels in
 * the retry link's URL, because the retry is a navigation and a render cannot write a
 * cookie.
 *
 * The interesting cases are the edges: the query string is typed by anyone, so every
 * malformed value has to read as a first attempt rather than crash the home page.
 */

describe("the count itself", () => {
  it("names the parameter the retry link sets", () => {
    expect(RETRY_PARAM).toBe("retry");
  });

  it("reads a fresh visit as no prior failures", () => {
    expect(attemptFromQuery(undefined)).toBe(0);
  });

  it("reads the retry link's value as one prior failure", () => {
    // This is the distinction the label turns on: the first failure has zero prior
    // failures, so it says "Try again"; the retry has one, so it says "Refresh page.".
    expect(attemptFromQuery("1")).toBe(1);
  });

  it("reads a malformed value as no failures, because the query is untrusted input", () => {
    expect(attemptFromQuery("not a number")).toBe(0);
    expect(attemptFromQuery("-1")).toBe(0);
    expect(attemptFromQuery("0")).toBe(0);
    expect(attemptFromQuery("")).toBe(0);
    expect(attemptFromQuery("Infinity")).toBe(0);
  });

  it("reads a repeated parameter as no failures rather than guessing which one counts", () => {
    // `?retry=1&retry=2` arrives as an array. The link sets one value, so a list is not
    // one of ours.
    expect(attemptFromQuery(["1", "2"])).toBe(0);
  });

  it("floors a fractional count", () => {
    expect(attemptFromQuery("2.7")).toBe(2);
  });
});
