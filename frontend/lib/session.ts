/**
 * Who is making this request, read on the **server** (FR-4, AD-12).
 *
 * A server component has no ambient session. The browser holds the `sessionid` cookie for
 * this site's origin, and the Next.js server is a *different* HTTP client: when it calls
 * Django it sends its own (empty) cookie jar unless the visitor's cookies are forwarded
 * explicitly. Without that, every server-side read is anonymous — which showed up as a
 * signed-in user's own home page telling them they had no personal events, while the same
 * read from the browser listed them.
 *
 * So every server-side read of a personal endpoint carries `sessionHeaders()`, and the
 * session itself is read through `GET /api/auth/me`.
 *
 * **The three answers are folded into three cases**, because the routing has to be
 * decidable:
 *
 *   - `signed-in` — a 200, with the user and the onboarding status.
 *   - `anonymous` — a 401. The normal answer for a visitor without a session.
 *   - `unavailable` — anything else: a 500, a thrown request, or no `API_BASE_URL` (a
 *     build machine). It is deliberately **not** folded into `anonymous`: sending a
 *     signed-in user to the anonymous preview because the API blinked would be a lie
 *     about who they are, and it would bounce them out of their own account.
 */
import { cookies } from "next/headers";

import type { components } from "@/lib/api/schema";
import { apiBaseUrl } from "@/lib/api-base-url";
import { api } from "@/lib/backend-client";

export type CurrentUser = components["schemas"]["CurrentUserOut"];

export type Session =
  { kind: "signed-in"; user: CurrentUser } | { kind: "anonymous" } | { kind: "unavailable" };

/**
 * The visitor's own cookies, as headers for a server-side API call.
 *
 * The whole cookie string is forwarded rather than the session cookie alone: Django reads
 * `sessionid` and `csrftoken` from it, and a server-side read that dropped one of them
 * would be anonymous for a reason no one could see at the call site.
 */
export async function sessionHeaders(): Promise<{ cookie: string }> {
  const store = await cookies();
  return { cookie: store.toString() };
}

/** The signed-in user, or why there isn't one. */
export async function getSession(): Promise<Session> {
  // No base URL: there is nothing to ask. This is the build machine's case, and it is
  // "unavailable" rather than "anonymous" for the same reason a 500 is — the question was
  // never put to the API.
  if (!apiBaseUrl()) return { kind: "unavailable" };

  try {
    const response = await api.GET("/api/auth/me", { headers: await sessionHeaders() });
    if (response.data) return { kind: "signed-in", user: response.data };
    // 401 is the API's normal answer for "no session". Any other status is a failure to
    // answer the question, not an answer.
    if (response.response.status === 401) return { kind: "anonymous" };
    return { kind: "unavailable" };
  } catch {
    return { kind: "unavailable" };
  }
}

/**
 * Where `/` sends this visitor, or `null` to render the home itself.
 *
 * This is a **pure function** of the session, which is the point: the routing rule is the
 * part worth pinning with tests, and it can be driven directly rather than through a
 * rendered page.
 *
 * The rules come from the work item:
 *
 *   - anonymous → `/preview` (the public preview, AD-12);
 *   - signed in but not finished onboarding → `/onboarding` (FR-1 resumes at the step);
 *   - signed in and onboarded → the placeholder home;
 *   - unavailable → the home, which shows the calm "couldn't reach Pulse" state. Not the
 *     preview: a signed-in user is not anonymous because a request failed.
 */
export function homeRoute(session: Session): string | null {
  if (session.kind === "anonymous") return "/preview";
  if (session.kind === "signed-in" && !session.user.onboarding.completed) return "/onboarding";
  return null;
}
