import { describe, expect, it } from "vitest";

import { OFFLINE_MESSAGE, readApiError } from "@/lib/api-errors";

/**
 * The API's errors, read for display.
 *
 * The payloads below are the ones the running API actually produced (probed through the
 * proxy on 2026-10-30), not invented shapes.
 */

describe("readApiError", () => {
  it("reads a plain error", () => {
    expect(
      readApiError({
        code: "invalid_credentials",
        message: "That email and password don't match.",
      }),
    ).toEqual({
      code: "invalid_credentials",
      message: "That email and password don't match.",
      fieldErrors: {},
    });
  });

  it("reads the field errors from details", () => {
    // Django's own password validator message, routed to the password field.
    expect(
      readApiError({
        code: "invalid_input",
        message: "That password doesn't meet our requirements.",
        details: { errors: [{ loc: ["password"], msg: "This password is too common." }] },
      }).fieldErrors,
    ).toEqual({ password: "This password is too common." });
  });

  it("takes the last segment of a nested loc as the field", () => {
    expect(
      readApiError({
        code: "invalid_input",
        message: "Some details need another look.",
        details: {
          errors: [{ loc: ["body", "payload", "email"], msg: "Enter an email address." }],
        },
      }).fieldErrors,
    ).toEqual({ email: "Enter an email address." });
  });

  it("keeps the first message per field", () => {
    const { fieldErrors } = readApiError({
      code: "invalid_input",
      message: "That password doesn't meet our requirements.",
      details: {
        errors: [
          { loc: ["password"], msg: "This password is too short." },
          { loc: ["password"], msg: "This password is too common." },
        ],
      },
    });

    expect(fieldErrors).toEqual({ password: "This password is too short." });
  });

  it("ignores a non-field error, which the form-level message carries", () => {
    const failure = readApiError({
      code: "invalid_input",
      message: "Some details need another look.",
      details: { errors: [{ loc: [], msg: "Something was wrong." }] },
    });

    expect(failure.fieldErrors).toEqual({});
    expect(failure.message).toBe("Some details need another look.");
  });

  it.each([
    ["null details", { code: "rate_limited", message: "Slow down.", details: null }],
    ["no details", { code: "rate_limited", message: "Slow down." }],
    ["details without errors", { code: "x", message: "y", details: { other: 1 } }],
    ["errors that are not a list", { code: "x", message: "y", details: { errors: "nope" } }],
    ["a malformed entry", { code: "x", message: "y", details: { errors: [{ loc: "password" }] } }],
  ])("survives %s", (_name, payload) => {
    expect(readApiError(payload).fieldErrors).toEqual({});
  });

  it.each([
    ["a thrown network failure", new TypeError("Failed to fetch")],
    ["undefined", undefined],
    ["a string", "gateway timeout"],
    ["something else's error shape", { detail: "Not Found" }],
  ])("falls back to the offline message for %s", (_name, value) => {
    expect(readApiError(value)).toEqual({
      code: null,
      message: OFFLINE_MESSAGE,
      fieldErrors: {},
    });
  });
});
