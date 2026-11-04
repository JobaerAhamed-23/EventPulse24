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

describe("siteUrl", () => {
  it("reads the configured origin", () => {
    vi.stubEnv("PUBLIC_SITE_URL", "https://eventpulse24.test");

    expect(siteUrl()?.href).toBe("https://eventpulse24.test/");
  });

  it("falls back to the local origin in development", () => {
    vi.stubEnv("PUBLIC_SITE_URL", undefined);
    vi.stubEnv("NODE_ENV", "development");

    expect(siteUrl()?.href).toBe("http://127.0.0.1:3000/");
  });

  it("claims nothing in production when it is not configured", () => {
    // **An unset origin is a deployment mistake, and it says so.** Next emits its own
    // warning and falls back to `localhost`; returning `undefined` lets that happen
    // loudly rather than shipping a card that points at a loopback address.
    vi.stubEnv("PUBLIC_SITE_URL", undefined);
    vi.stubEnv("NODE_ENV", "production");

    expect(siteUrl()).toBeUndefined();
  });

  it("takes the configured origin in production when it is set", () => {
    vi.stubEnv("PUBLIC_SITE_URL", "https://eventpulse24.test");
    vi.stubEnv("NODE_ENV", "production");

    expect(siteUrl()?.origin).toBe("https://eventpulse24.test");
  });
});
