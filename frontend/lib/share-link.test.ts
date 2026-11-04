// @vitest-environment jsdom
/**
 * The shared URL, and the three claims it makes.
 *
 * **This module is one string, so the tests are three claims about it:**
 *
 * 1. **The path is the public page's** — `/events/{slug}`, never `/events/{uuid}`.
 *    The uuid is the *personal* URL, and a friend who opened it would meet a sign-in
 *    wall instead of the event.
 * 2. **There is no second shape** — no query parameter, no fragment, no token.
 * 3. **The origin is the site's public one**, and the browser's own origin is the
 *    fallback when the deployment has not set one.
 */
import { describe, expect, it } from "vitest";

import { publicEventUrl, shareOrigin } from "@/lib/share-link";

describe("the public event URL", () => {
  it("is the public page's path", () => {
    expect(
      publicEventUrl("designing-for-calm-2026-08-28-a1b2c3", "https://eventpulse24.test"),
    ).toBe("https://eventpulse24.test/events/designing-for-calm-2026-08-28-a1b2c3");
  });

  it("is never the event's id", () => {
    // **The mistake this function exists to prevent.** The uuid is the signed-in Detail
    // Screen's URL — a friend who opened it would be asked to sign in instead of being
    // shown the event.
    const url = publicEventUrl("designing-for-calm-2026-08-28-a1b2c3", "https://eventpulse24.test");

    expect(url).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);
  });

  it("carries no query, no fragment and no token", () => {
    // **One URL for one document.** A second shape would be a URL the public page does
    // not canonicalise to, and a crawler that fetched it would record two documents.
    const url = publicEventUrl("designing-for-calm-2026-08-28-a1b2c3", "https://eventpulse24.test");

    expect(url).not.toContain("?");
    expect(url).not.toContain("#");
    expect(url).not.toContain("shared_by");
  });

  it("is relative when no origin is known", () => {
    // A relative path names the right document; a wrong absolute URL names the wrong
    // site, which is worse.
    expect(publicEventUrl("designing-for-calm-2026-08-28-a1b2c3")).toBe(
      "/events/designing-for-calm-2026-08-28-a1b2c3",
    );
    expect(publicEventUrl("designing-for-calm-2026-08-28-a1b2c3", null)).toBe(
      "/events/designing-for-calm-2026-08-28-a1b2c3",
    );
  });

  it("does not double the slash between the origin and the path", () => {
    expect(publicEventUrl("slug-1", "https://eventpulse24.test/")).toBe(
      "https://eventpulse24.test/events/slug-1",
    );
  });
});

describe("the share origin", () => {
  it("is the configured origin when there is one", () => {
    // **The configured origin is the site's public address** — the same one the
    // canonical link and the Open Graph URL resolve against, so the shared URL and the
    // page's own canonical cannot disagree.
    expect(shareOrigin("https://eventpulse24.test")).toBe("https://eventpulse24.test");
  });

  it("falls back to the browser's own origin", () => {
    // **The address the user is actually at**, which is never wrong for the person
    // receiving the link — and the right answer when the deployment has not set
    // `PUBLIC_SITE_URL`.
    expect(shareOrigin(null)).toBe(window.location.origin);
    expect(shareOrigin(undefined)).toBe(window.location.origin);
  });

  it("never ends in a slash", () => {
    expect(shareOrigin("https://eventpulse24.test/")).toBe("https://eventpulse24.test");
  });
});
