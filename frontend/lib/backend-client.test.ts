import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The CSRF middleware is **registered on the real client**.
 *
 * `csrf.test.ts` proves the middleware behaves; this proves it is actually wired to the
 * client the app uses. Those are different failures: a middleware written and never
 * registered passes every test of its own and refuses every write in production.
 *
 * The client is imported fresh per test, because the registration happens once at module
 * load.
 */

const fetchMock = vi.fn();

/**
 * In the browser the client's base URL is `""`, so every request is a **relative** path
 * (`/api/…`) that the browser resolves against the page it is on — that is what keeps the
 * session cookie first-party. jsdom does not supply `fetch`, so the `Request` here is
 * Node's, which rejects a relative URL outright (`ERR_INVALID_URL`).
 *
 * This stub does what the browser does: resolve a relative path against the page's
 * origin. It does not change what is under test — the request's method, headers and body
 * are untouched.
 */
class BrowserRequest extends Request {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    const resolved =
      typeof input === "string" && input.startsWith("/")
        ? new URL(input, window.location.origin)
        : input;
    super(resolved, init);
  }
}

async function freshClient() {
  vi.resetModules();
  const client = await import("@/lib/backend-client");
  return client.api;
}

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(
    new Response(JSON.stringify({ status: "ok" }), {
      status: 200,
      headers: { "content-type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("Request", BrowserRequest);
  document.cookie = "csrftoken=live-token";
});

afterEach(() => {
  vi.unstubAllGlobals();
  // Clear the cookie for the next test.
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("the backend client in the browser", () => {
  it("sends the CSRF token on a write", async () => {
    const api = await freshClient();

    await api.POST("/api/auth/signout");

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.method).toBe("POST");
    expect(request.headers.get("X-CSRFToken")).toBe("live-token");
  });

  it("sends the CSRF token on a personal-event write, which predates this item", async () => {
    // These endpoints were built before CSRF was enforced. They are covered because the
    // middleware is on the client, not on the call sites.
    const api = await freshClient();

    await api.POST("/api/personal/events", {
      body: {
        name: "Dinner",
        start_time_utc: "2026-12-01T18:00:00Z",
        start_time_tz: "UTC",
      },
    });

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.headers.get("X-CSRFToken")).toBe("live-token");
  });

  it("sends no CSRF token on a read", async () => {
    const api = await freshClient();

    await api.GET("/api/personal/events");

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.headers.get("X-CSRFToken")).toBeNull();
  });
});
