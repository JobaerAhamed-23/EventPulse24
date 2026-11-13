import { beforeEach, describe, expect, it, vi } from "vitest";

import { getSession, homeRoute, sessionHeaders } from "@/lib/session";

/**
 * Who the request is from, and where `/` sends them.
 *
 * Two properties matter most here, and both were found by probing the running stack:
 *
 *   - the read **forwards the visitor's cookies**, without which every server-side read
 *     is anonymous and a signed-in user sees an empty home;
 *   - a failure to *reach* the API is not the same as "anonymous", so a blip does not
 *     bounce a signed-in user out to the public preview.
 */

const GET = vi.fn();
const apiBaseUrl = vi.fn();
const cookies = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { GET: (...args: unknown[]) => GET(...args) },
}));

vi.mock("@/lib/api-base-url", () => ({
  apiBaseUrl: (...args: unknown[]) => apiBaseUrl(...args),
}));

vi.mock("next/headers", () => ({
  cookies: () => cookies(),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  name: "",
  onboarding: { completed: true, current_step: null },
};

/** An openapi-fetch response: `data` on success, `error` plus the raw `response` otherwise. */
function ok(data: unknown) {
  return { data, error: undefined, response: new Response(null, { status: 200 }) };
}

function failed(status: number) {
  return {
    data: undefined,
    error: { code: "not_authenticated", message: "Please sign in to continue." },
    response: new Response(null, { status }),
  };
}

beforeEach(() => {
  GET.mockReset();
  apiBaseUrl.mockReset();
  cookies.mockReset();
  apiBaseUrl.mockReturnValue("http://127.0.0.1:8000");
  cookies.mockResolvedValue({ toString: () => "sessionid=abc; csrftoken=tok" });
});

describe("sessionHeaders", () => {
  it("forwards the visitor's whole cookie string", async () => {
    expect(await sessionHeaders()).toEqual({ cookie: "sessionid=abc; csrftoken=tok" });
  });
});

describe("getSession", () => {
  it("reads /api/auth/me with the visitor's cookies", async () => {
    // Without this header the Next.js server asks Django as *itself* — no session — and
    // every personal read on the page comes back empty for a signed-in user.
    GET.mockResolvedValue(ok(USER));

    const session = await getSession();

    expect(GET).toHaveBeenCalledWith("/api/auth/me", {
      headers: { cookie: "sessionid=abc; csrftoken=tok" },
    });
    expect(session).toEqual({ kind: "signed-in", user: USER });
  });

  it("is anonymous on a 401", async () => {
    GET.mockResolvedValue(failed(401));

    expect(await getSession()).toEqual({ kind: "anonymous" });
  });

  it("is unavailable on a server error", async () => {
    GET.mockResolvedValue(failed(500));

    expect(await getSession()).toEqual({ kind: "unavailable" });
  });

  it("is unavailable when the request throws", async () => {
    GET.mockRejectedValue(new Error("connect ECONNREFUSED"));

    expect(await getSession()).toEqual({ kind: "unavailable" });
  });

  it("is unavailable, and asks nothing, with no API base URL", async () => {
    apiBaseUrl.mockReturnValue(undefined);

    expect(await getSession()).toEqual({ kind: "unavailable" });
    expect(GET).not.toHaveBeenCalled();
  });
});

describe("homeRoute", () => {
  it("sends an anonymous visitor to the public preview", () => {
    expect(homeRoute({ kind: "anonymous" })).toBe("/preview");
  });

  it("sends a signed-in user who hasn't finished onboarding to /onboarding", () => {
    const session = {
      kind: "signed-in",
      user: { ...USER, onboarding: { completed: false, current_step: 2 } },
    } as const;

    expect(homeRoute(session)).toBe("/onboarding");
  });

  it("keeps an onboarded user on the home", () => {
    expect(homeRoute({ kind: "signed-in", user: USER })).toBeNull();
  });

  it("keeps a visitor on the home when the API is unavailable, rather than treating them as anonymous", () => {
    // A failed request is not evidence that someone is signed out. Redirecting here would
    // throw a signed-in user out to the marketing page because one call failed.
    expect(homeRoute({ kind: "unavailable" })).toBeNull();
  });
});
