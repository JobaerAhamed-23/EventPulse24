import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DevFakeBillingPortalPage from "@/app/dev/fake-billing/portal/page";

vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

/**
 * The fake customer portal.
 *
 * **The portal has to offer the cancellation**, because the local path that exercises
 * item 2's `subscription_ended` webhook starts here. A stand-in that could only be
 * closed would make the cancellation path unwalkable locally.
 */
describe("DevFakeBillingPortalPage", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("doesn't exist in production builds", async () => {
    vi.stubEnv("NODE_ENV", "production");

    await expect(DevFakeBillingPortalPage({ searchParams: Promise.resolve({}) })).rejects.toThrow(
      "NEXT_NOT_FOUND",
    );
  });

  it("says plainly that it is a development stand-in", async () => {
    vi.stubEnv("NODE_ENV", "development");

    const panel = render(await DevFakeBillingPortalPage({ searchParams: Promise.resolve({}) }));

    expect(panel.container.textContent).toContain("Development stand-in");
  });

  it("offers the cancellation, so the ended-subscription path is walkable", async () => {
    vi.stubEnv("NODE_ENV", "development");

    const panel = render(await DevFakeBillingPortalPage({ searchParams: Promise.resolve({}) }));

    expect(panel.getByText("Cancel the subscription")).toBeInTheDocument();
    expect(panel.getByText("Close the portal")).toBeInTheDocument();
  });

  it("shows the return URL the adapter put in the query string", async () => {
    vi.stubEnv("NODE_ENV", "development");

    const panel = render(
      await DevFakeBillingPortalPage({
        searchParams: Promise.resolve({ next: "http://localhost:3000/settings/billing" }),
      }),
    );

    // The path is shown, not the whole URL: the page reduces a same-origin URL to its
    // path, so what it renders is plainly a location on this site.
    expect(panel.container.textContent).toContain("/settings/billing");
  });

  it("refuses a return URL on another site", async () => {
    vi.stubEnv("NODE_ENV", "development");

    const panel = render(
      await DevFakeBillingPortalPage({
        searchParams: Promise.resolve({ next: "https://attacker.example/steal" }),
      }),
    );

    expect(panel.container.textContent).not.toContain("attacker.example");
  });

  it("renders without a return URL", async () => {
    vi.stubEnv("NODE_ENV", "development");

    const panel = render(await DevFakeBillingPortalPage({ searchParams: Promise.resolve({}) }));

    expect(panel.container.textContent).toContain("no return URL");
  });
});
