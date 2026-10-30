/**
 * The API's errors, read for display — **verbatim**.
 *
 * Every API error has the same shape (`backend/config/errors.py`): a stable `code`, a
 * calm `message` written for the user, and optional `details.errors[{loc, msg}]` for the
 * fields that failed. The frontend's job is to put those words on the screen, not to
 * write its own.
 *
 * That is a rule, not a preference. The auth endpoints are **enumeration-safe** (AD-18):
 * a wrong password and an unknown address produce one byte-identical answer, "That email
 * and password don't match." A friendlier frontend that split that into "we don't know
 * that email" and "wrong password" would hand back the account oracle the backend spent
 * the whole item removing. So the message is shown as it arrives.
 */

import type { components } from "@/lib/api/schema";

type ErrorOut = components["schemas"]["ErrorOut"];

/** What the API said: one message for the form, and a message per field that failed. */
export type ApiError = {
  /** The API's own `code` (`invalid_credentials`, `invalid_reset_token`, …), if it said one. */
  code: string | null;
  /** The API's own message, or the offline fallback. Shown as-is. */
  message: string;
  /** The field errors, keyed by field name (`email`, `password`). The API's own wording. */
  fieldErrors: Record<string, string>;
};

/**
 * What the user sees when the request never reached the API.
 *
 * `EXPERIENCE.md` §6: errors are honest and brief — "Couldn't reach Pulse. Try again."
 * This is the only message in this module the frontend writes, because it is the only
 * case where the API did not speak.
 */
export const OFFLINE_MESSAGE = "Couldn't reach Pulse. Try again.";

function isErrorOut(value: unknown): value is ErrorOut {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return typeof candidate.code === "string" && typeof candidate.message === "string";
}

/**
 * The field errors from `details.errors`, keyed by field.
 *
 * `loc` is a path (`["password"]`, and for a nested body `["body", "password"]`), so the
 * **last** segment is the field. A `loc` of `[]` is a non-field error; it is left out
 * here and the form-level message carries it.
 */
function fieldErrorsFrom(details: ErrorOut["details"]): Record<string, string> {
  const found: Record<string, string> = {};
  if (typeof details !== "object" || details === null) return found;
  const errors = (details as Record<string, unknown>).errors;
  if (!Array.isArray(errors)) return found;

  for (const item of errors) {
    if (typeof item !== "object" || item === null) continue;
    const entry = item as Record<string, unknown>;
    const { loc, msg } = entry;
    if (!Array.isArray(loc) || loc.length === 0 || typeof msg !== "string") continue;
    const field = loc[loc.length - 1];
    if (typeof field !== "string") continue;
    // The first message per field wins: Django's validators can report several, and a
    // field shows one line. The rest are the same verdict said again.
    found[field] ??= msg;
  }
  return found;
}

/**
 * Read an error from the generated client into something a form can render.
 *
 * `error` is the `error` member of an openapi-fetch response — the parsed body of a
 * non-2xx answer — or anything thrown while making the request.
 */
export function readApiError(error: unknown): ApiError {
  if (isErrorOut(error)) {
    return {
      code: error.code,
      message: error.message,
      fieldErrors: fieldErrorsFrom(error.details),
    };
  }
  // Not the project's error shape: the request failed before the API could answer, or
  // something else answered. Either way the API said nothing to quote.
  return { code: null, message: OFFLINE_MESSAGE, fieldErrors: {} };
}
