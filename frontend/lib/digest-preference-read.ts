import { apiBaseUrl } from "@/lib/api-base-url";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

/**
 * The user's Pulse Digest preference, read on the server.
 *
 * **This is the screen's only source of truth for the opt-out.** The value lives on
 * `DigestPreference.include_personal_events` (FR-19), and the digest's composition
 * service reads that column. A settings screen that guessed would be a screen that
 * lies — so it reads.
 *
 * **The read carries the visitor's cookies.** A server-side read without them is
 * anonymous, and an anonymous read of somebody's digest preference is nobody's
 * preference — which would render the toggle in the wrong state, and send the wrong
 * value back on the next save.
 *
 * **This module is server-only.** It reaches `sessionHeaders()`, and so `next/headers` —
 * a `"use client"` component importing it breaks the production build.
 *
 * **Two answers, not one.** `found` is the server's answer; `unavailable` is a failure
 * to answer. They are deliberately not folded together: a failed read must not render
 * as "the opt-out is off", because that is a setting the user never changed.
 */

/**
 * The three fields the digest settings screen needs.
 *
 * **Narrower than the API's `DigestPreferenceOut` on purpose.** The city is not one of
 * them, and returning it would be an invitation to send it back. The delivery time and
 * the timezone are here because the endpoint requires both — it has no "change one
 * field" mode, so a caller that changes the opt-out must round-trip the pair
 * unchanged.
 */
export type DigestPreference = {
  /** The local wall clock the digest arrives at — `HH:MM:SS`, or `null` if unset. */
  readonly delivery_time: string | null;
  /** The IANA zone the wall clock belongs to — or `null` if unset. */
  readonly timezone: string | null;
  /** Whether personal events appear in the digest. The server's answer, verbatim. */
  readonly include_personal_events: boolean;
};

/**
 * The user's digest preference, or why there isn't one.
 *
 * `found` — the server's answer.
 * `unavailable` — the request failed, there was no API to ask, or the answer carried
 * no payload.
 */
export type DigestPreferenceRead =
  { kind: "found"; preference: DigestPreference } | { kind: "unavailable" };

/**
 * The user's digest preference, or `unavailable`.
 *
 * **The base URL may be missing** (a build machine, a misconfigured deploy), the
 * request may fail (the API is down), or the API may answer with an error (the visitor
 * is not signed in). None of those is a reason to crash the page, and none is a reason
 * to pretend the opt-out is off.
 */
export async function readDigestPreference(): Promise<DigestPreferenceRead> {
  if (!apiBaseUrl()) return { kind: "unavailable" };

  try {
    const response = await api.GET("/api/personal/onboarding", {
      headers: await sessionHeaders(),
    });
    if (!response.data) return { kind: "unavailable" };
    return {
      kind: "found",
      preference: {
        // **Verbatim, not normalised.** The delivery time and the timezone travel
        // together because the endpoint refuses to half-apply the pair, so a caller
        // that changes the opt-out sends both back exactly as they were read. A `null`
        // here is a real state — a user who has not finished onboarding — and it must
        // survive the round-trip unchanged.
        delivery_time: response.data.digest.delivery_time ?? null,
        timezone: response.data.digest.timezone ?? null,
        // **The server's answer, not our default.** The backend defaults this to `true`,
        // and the screen's job is to show what the server believes — not what we assume
        // a user who never touched the setting would want.
        include_personal_events: response.data.digest.include_personal_events,
      },
    };
  } catch {
    return { kind: "unavailable" };
  }
}
