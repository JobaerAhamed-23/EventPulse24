/**
 * A cookie store for tests that render a server component.
 *
 * **Next's `cookies()` throws outside a request scope**, so a test that renders a page
 * which reads a cookie needs a stand-in for the request's cookie jar. This is that
 * stand-in: a `Map`, and the four methods the store exposes.
 *
 * **It is a real store, not a spy.** `set` and `delete` actually change what `get`
 * returns, so a test can assert on a page's *effect* — "the failure count went up" —
 * rather than on the fact that a method was called. A spy would only prove the method
 * was called; the store proves the cookie ended up holding the right value.
 */
export type CookieStore = {
  get: (name: string) => { name: string; value: string } | undefined;
  set: (
    name: string,
    value: string,
    options?: { maxAge?: number; path?: string; sameSite?: string },
  ) => void;
  delete: (name: string) => void;
  toString: () => string;
};

/** An empty store. */
export function cookieStore(): CookieStore {
  const jar = new Map<string, string>();

  return {
    get: (name) => (jar.has(name) ? { name, value: jar.get(name) as string } : undefined),
    set: (name, value) => {
      jar.set(name, value);
    },
    delete: (name) => {
      jar.delete(name);
    },
    toString: () => [...jar.entries()].map(([name, value]) => `${name}=${value}`).join("; "),
  };
}
