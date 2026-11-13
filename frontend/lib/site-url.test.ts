import { afterEach, describe, expect, it, vi } from "vitest";

import { siteUrl } from "@/lib/site-url";

/**
 * The site's public origin.
 *
 * **This value decides what a share card points at.** Next resolves a relative OG image
 * against the metadata's `metadataBase`, and without one it falls back to
 * `http://localhost:3000` — so a card would name `localhost` as its image and show
 * nothing at all. The origin is therefore not a nicety; it is the difference between a
 * share card that renders and one that does not.
 *
 * **And it is the *public* origin.** In a deployed environment the Next.js server's own
 * address is often internal — the same distinction the backend draws between
 * `FRONTEND_BASE_URL` (the public origin) and `FRONTEND_REVALIDATION_URL` (the
 * server-to-server address).
 */
const ORIGINAL_ENV = { ...process.env };

afterEach(() => {
  // **`vi.unstubAllEnvs` puts the environment back exactly as it was.** A test that
  // left `NODE_ENV` as "production" would make every test after it resolve the
  // production branch — and the failure would land in a file that has nothing to do
  // with this one.
  vi.unstubAllEnvs();
  process.env = { ...ORIGINAL_ENV };
});

/**
 * **Removes the origin, the way an unconfigured deployment has it.**
 *
 * **Why not `vi.stubEnv("PUBLIC_SITE_URL", undefined)`.** That reads as the obvious way
 * to say "unset", and it works — the *first* time. It is not repeatable: once
 * `vi.unstubAllEnvs()` has run, a second `stubEnv(name, undefined)` is **silently
 * ignored**, and the variable keeps the value it had before. So `PUBLIC_SITE_URL` —
 * which `.env` sets, and which `make` exports into the shell — survived into the next
 * test, and the "unset" case quietly became the "configured" case.
 *
 * **The failure was order-dependent, which is what made it look like a product bug.**
 * Run alone, the test passed; run after its sibling, it failed. A test that only fails
 * in company is a test that is really testing the company it keeps.
 *
 * **So the key is deleted outright.** `delete` is unambiguous, repeatable, and does not
 * depend on a stub registry's memory of what it did last time.
 */
function unsetOrigin(): void {
  delete process.env.PUBLIC_SITE_URL;
}

describe("siteUrl", () => {
  it("reads the configured origin", () => {
    vi.stubEnv("PUBLIC_SITE_URL", "https://eventpulse24.test");

    expect(siteUrl()?.href).toBe("https://eventpulse24.test/");
  });

  it("falls back to the local origin in development", () => {
    unsetOrigin();
    vi.stubEnv("NODE_ENV", "development");

    expect(siteUrl()?.href).toBe("http://127.0.0.1:3000/");
  });

  it("claims nothing in production when it is not configured", () => {
    // **An unset origin is a deployment mistake, and it says so.** Next emits its own
    // warning and falls back to `localhost`; returning `undefined` lets that happen
    // loudly rather than shipping a card that points at a loopback address.
    unsetOrigin();
    vi.stubEnv("NODE_ENV", "production");

    expect(siteUrl()).toBeUndefined();
  });

  it("takes the configured origin in production when it is set", () => {
    vi.stubEnv("PUBLIC_SITE_URL", "https://eventpulse24.test");
    vi.stubEnv("NODE_ENV", "production");

    expect(siteUrl()?.origin).toBe("https://eventpulse24.test");
  });
});
