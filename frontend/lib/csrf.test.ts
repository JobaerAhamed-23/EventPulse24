import { beforeEach, describe, expect, it, vi } from "vitest";

import { CSRF_HEADER, csrfOnRequest, readCsrfCookie } from "@/lib/csrf";

/**
 * The browser's half of the CSRF contract (D13).
 *
 * The backend refuses every unsafe request that does not carry the token, so these are
 * the tests standing between the forms and a 403 on every write.
 */

const requestToken = vi.fn();

beforeEach(() => {
  requestToken.mockReset();
  requestToken.mockResolvedValue(undefined);
});

function middleware(cookies: () => string) {
  return csrfOnRequest({ readCookies: cookies, requestToken });
}

describe("readCsrfCookie", () => {
  it("finds the token among other cookies", () => {
    expect(readCsrfCookie("sessionid=abc; csrftoken=the-token; theme=dark")).toBe("the-token");
  });

  it("is null when there is no csrftoken", () => {
    expect(readCsrfCookie("sessionid=abc; theme=dark")).toBeNull();
  });

  it("is null for an empty cookie string", () => {
    expect(readCsrfCookie("")).toBeNull();
  });

  it("does not match a cookie whose name merely ends with csrftoken", () => {
    expect(readCsrfCookie("notcsrftoken=wrong")).toBeNull();
  });

  it("decodes a percent-encoded value", () => {
    expect(readCsrfCookie("csrftoken=a%2Bb")).toBe("a+b");
  });
});

describe("the CSRF middleware", () => {
  it("adds the header to an unsafe request", async () => {
    const onRequest = middleware(() => "csrftoken=tok-1");
    const request = new Request("https://example.test/api/auth/signin", { method: "POST" });

    const result = await onRequest({ request });

    expect(result?.headers.get(CSRF_HEADER)).toBe("tok-1");
    expect(requestToken).not.toHaveBeenCalled();
  });

  it.each(["POST", "PUT", "PATCH", "DELETE"])("covers %s", async (method) => {
    const onRequest = middleware(() => "csrftoken=tok-1");
    const request = new Request("https://example.test/api/personal/events", { method });

    expect((await onRequest({ request }))?.headers.get(CSRF_HEADER)).toBe("tok-1");
  });

  it("leaves a GET alone", async () => {
    const onRequest = middleware(() => "csrftoken=tok-1");
    const request = new Request("https://example.test/api/personal/events");

    const result = await onRequest({ request });

    expect(result).toBeUndefined();
    expect(request.headers.get(CSRF_HEADER)).toBeNull();
  });

  it("reads the cookie fresh on every request, because Django rotates it on sign-in", async () => {
    // Probed against the real stack: `login()` cycles the CSRF token and the sign-in
    // response sets a new `csrftoken`. A token captured before sign-in is refused with
    // `csrf_failed` on the next write — so a middleware that cached it would break every
    // write a user makes after signing in.
    let cookies = "csrftoken=before-signin";
    const onRequest = middleware(() => cookies);

    const first = await onRequest({
      request: new Request("https://example.test/api/auth/signin", { method: "POST" }),
    });
    expect(first?.headers.get(CSRF_HEADER)).toBe("before-signin");

    cookies = "csrftoken=after-signin";
    const second = await onRequest({
      request: new Request("https://example.test/api/personal/events", { method: "POST" }),
    });
    expect(second?.headers.get(CSRF_HEADER)).toBe("after-signin");
  });

  it("asks the API for a token when the visitor has no cookie yet", async () => {
    let cookies = "";
    requestToken.mockImplementation(async () => {
      // The real endpoint issues the token by setting the cookie.
      cookies = "csrftoken=issued";
    });
    const onRequest = middleware(() => cookies);

    const result = await onRequest({
      request: new Request("https://example.test/api/auth/signup", { method: "POST" }),
    });

    expect(requestToken).toHaveBeenCalledTimes(1);
    expect(result?.headers.get(CSRF_HEADER)).toBe("issued");
  });

  it("sends the request without a header when no token can be had", async () => {
    // The API is unreachable. The request goes anyway and the API's own refusal is the
    // answer — inventing a token would make this a silent no-op instead.
    const onRequest = middleware(() => "");

    const request = new Request("https://example.test/api/auth/signin", { method: "POST" });
    const result = await onRequest({ request });

    expect(result).toBeUndefined();
    expect(request.headers.get(CSRF_HEADER)).toBeNull();
  });
});
