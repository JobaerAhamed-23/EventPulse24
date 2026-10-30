import { afterEach, describe, expect, it } from "vitest";

import { CHOICE_COOKIE, previewQuery, readChoice, rememberChoice } from "@/lib/preview-choice";

/**
 * The visitor's location choice.
 *
 * FR-2 asks for a cookie that lasts the session, and AD-12 asks for a page that does not
 * vary per visitor — which is why this is written and read in the browser and never sent
 * to the server as a preference.
 */

afterEach(() => {
  document.cookie = `${CHOICE_COOKIE}=; Path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
});

describe("readChoice", () => {
  it("is unasked when there is no cookie", () => {
    expect(readChoice("")).toEqual({ kind: "unasked" });
  });

  it("reads the opt-out", () => {
    expect(readChoice(`${CHOICE_COOKIE}=off`)).toEqual({ kind: "opted-out" });
  });

  it("reads a chosen city", () => {
    expect(readChoice(`${CHOICE_COOKIE}=Brooklyn`)).toEqual({ kind: "city", city: "Brooklyn" });
  });

  it("decodes a city with a space in it", () => {
    expect(readChoice(`${CHOICE_COOKIE}=San%20Francisco`)).toEqual({
      kind: "city",
      city: "San Francisco",
    });
  });

  it("finds it among other cookies", () => {
    expect(readChoice(`sessionid=abc; ${CHOICE_COOKIE}=Queens; theme=dark`)).toEqual({
      kind: "city",
      city: "Queens",
    });
  });
});

describe("rememberChoice", () => {
  it("writes the city, and reads back the same choice", () => {
    rememberChoice({ kind: "city", city: "Brooklyn" });

    expect(readChoice(document.cookie)).toEqual({ kind: "city", city: "Brooklyn" });
  });

  it("writes the opt-out", () => {
    rememberChoice({ kind: "opted-out" });

    expect(readChoice(document.cookie)).toEqual({ kind: "opted-out" });
  });

  it("is a session cookie: no Max-Age and no Expires", () => {
    // FR-2 says the choice "persists in a cookie for the session". A dated cookie would
    // be a longer promise about someone's location than was asked for.
    let written = "";
    const jar = Object.getOwnPropertyDescriptor(Document.prototype, "cookie");
    Object.defineProperty(document, "cookie", {
      configurable: true,
      set(value: string) {
        written = value;
      },
      get: () => "",
    });

    rememberChoice({ kind: "city", city: "Brooklyn" });

    if (jar) Object.defineProperty(document, "cookie", jar);
    expect(written).toContain("SameSite=Lax");
    expect(written.toLowerCase()).not.toContain("max-age");
    expect(written.toLowerCase()).not.toContain("expires");
  });
});

describe("previewQuery", () => {
  it("asks for nothing when the visitor has not chosen, so geo decides", () => {
    expect(previewQuery({ kind: "unasked" })).toEqual({});
  });

  it("switches the location off for an opt-out", () => {
    // `use_geo=false` is what makes the backend not consult the header at all. Leaving it
    // out and ignoring the answer would be a promise nobody could check.
    expect(previewQuery({ kind: "opted-out" })).toEqual({ use_geo: false });
  });

  it("names the chosen city", () => {
    expect(previewQuery({ kind: "city", city: "Queens" })).toEqual({ city: "Queens" });
  });
});
