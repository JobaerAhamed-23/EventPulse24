/**
 * The CSRF token, on every state-changing request (D13).
 *
 * Django's `CsrfViewMiddleware` does not protect a Django Ninja endpoint — Ninja marks
 * every view it builds `csrf_exempt` — so the backend checks the token itself, in
 * `apps/identity/api_auth.py`, for **every** unsafe request: the auth endpoints and,
 * through the shared resolver, the personal ones. The browser's half of that contract is
 * here.
 *
 * The contract is Django's own: the `csrftoken` cookie's value is echoed in the
 * `X-CSRFToken` header. `GET /api/auth/csrf` sets the cookie, so a visitor who has not
 * made one yet can get one.
 *
 * **The cookie is read per request, never cached.** Django rotates the CSRF token on
 * sign-in (`login()` cycles it), so a token read once at page load is wrong for every
 * write after the user signs in — the request is refused with `csrf_failed`, which looks
 * exactly like a bug in the form. Reading `document.cookie` costs nothing and is always
 * right.
 *
 * **There is no retry on a refusal.** With the cookie read fresh, the remaining causes —
 * the cookie cleared mid-form, an origin that `CSRF_TRUSTED_ORIGINS` does not list — are
 * not fixed by sending the same request again. The API's own message ("Your session needs
 * refreshing. Reload the page and try again.") says what will work, and the forms show it.
 *
 * This module does not import `openapi-fetch`: AD-19 keeps that import to
 * `lib/backend-client.ts`, the one module allowed to build a client. The middleware is
 * typed structurally instead, which is also what makes it testable without a client.
 */

/** Django's cookie name. Its value is what the header must carry. */
export const CSRF_COOKIE = "csrftoken";

/** Django's header name. `CsrfViewMiddleware` reads this one. */
export const CSRF_HEADER = "X-CSRFToken";

/** The methods that change something. Django checks exactly these. */
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/** The shape of `document.cookie` a reader needs. Narrow enough to stub in a test. */
export type CookieSource = () => string;

/**
 * The `csrftoken` value from a cookie string, or `null` when it is not there.
 *
 * The match is anchored on the name so a cookie whose name merely *ends* with
 * `csrftoken` cannot be mistaken for it.
 */
export function readCsrfCookie(cookies: string): string | null {
  for (const part of cookies.split(";")) {
    const separator = part.indexOf("=");
    if (separator === -1) continue;
    if (part.slice(0, separator).trim() !== CSRF_COOKIE) continue;
    const value = part.slice(separator + 1).trim();
    return value === "" ? null : decodeURIComponent(value);
  }
  return null;
}

/** What the middleware is given: how to read cookies, and how to ask for a token. */
export type CsrfMiddlewareOptions = {
  /** Reads the current cookie string. Defaults to `document.cookie`. */
  readCookies?: CookieSource;
  /**
   * Asks the API for a token, which it issues by setting the cookie.
   *
   * It is a `GET`, so it never comes back through this middleware's unsafe-method
   * branch — there is no recursion to guard against.
   */
  requestToken: () => Promise<unknown>;
};

/**
 * The `onRequest` half of an openapi-fetch middleware: it adds `X-CSRFToken` to every
 * unsafe request, fetching a token first when the visitor has none.
 *
 * A safe request is returned untouched — a `GET` changes nothing, and `GET
 * /api/auth/csrf` must not depend on a token it is about to issue.
 */
export function csrfOnRequest({ readCookies, requestToken }: CsrfMiddlewareOptions) {
  const cookies: CookieSource = readCookies ?? (() => document.cookie);

  return async ({ request }: { request: Request }): Promise<Request | undefined> => {
    if (!UNSAFE_METHODS.has(request.method.toUpperCase())) return undefined;

    let token = readCsrfCookie(cookies());
    if (token === null) {
      // No cookie yet: the visitor has made no request that issued one. Ask for it, then
      // read it from the cookie the response set.
      await requestToken();
      token = readCsrfCookie(cookies());
    }
    // Still nothing: the API could not be reached, or it did not set the cookie. Send the
    // request anyway and let the API's refusal be the answer — inventing a token here
    // would turn a server problem into a silent, unexplained no-op.
    if (token === null) return undefined;

    request.headers.set(CSRF_HEADER, token);
    return request;
  };
}
