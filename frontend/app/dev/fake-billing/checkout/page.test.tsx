import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DevFakeBillingCheckoutPage from "@/app/dev/fake-billing/checkout/page";

vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

/**
 * The fake checkout page.
 *
 * **The query parameters are the contract with `FakeBillingAdapter`**, which mints
 * `?session=…&plan=…&next=…`. The tests pin those three names, because a rename on
 * either side silently breaks the local paid path — the page would still render, just
 * with an empty session and an unknown plan.
 *
 * **The page grants nothing.** There is no test asserting that completing a checkout
 * makes a user Pro, because it does not and must not; the webhook is what does that.
 */
describe("DevFakeBillingCheckoutPage", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("doesn't exist in production builds", async () => {
    vi.stubEnv("NODE_ENV", "production");

    await expect(
      DevFakeBillingCheckoutPage({
        searchParams: Promise.resolve({ session: "fake_cs_1", plan: "monthly" }),
      }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("shows the plan the adapter named", async () => {
    vi.stubEnv("NODE_ENV", "development");

    const panel = render(
      await DevFakeBillingCheckoutPage({
        searchParams: Promise.resolve({ session: "fake_cs_1", plan: "monthly" }),
      }),
    );

    expect(panel.container.textContent).toContain("Pro monthly");
    expect(panel.container.textContent).toContain("$4.99/month");
  });

  it("shows the session the adapter minted", async () => {
    vi.stubEnv("NODE_ENV", "development");

    const panel = render(
      await DevFakeBillingCheckoutPage({
        searchParams: Promise.resolve({ session: "fake_cs_abc123", plan: "yearly" }),
      }),
    );

    expect(panel.container.textContent).toContain("fake_cs_abc123");
    expect(panel.container.textContent).toContain("Pro yearly");
  });

  it("says plainly that it is a development stand-in", async () => {
    vi.stubEnv("NODE_ENV", "development");

    const panel = render(
      await DevFakeBillingCheckoutPage({
        searchParams: Promise.resolve({ session: "fake_cs_1", plan: "monthly" }),
      }),
    );

    expect(panel.container.textContent).toContain("Development stand-in");
  });

  it("offers both outcomes, so the paid and abandoned paths are both walkable", async () => {
    vi.stubEnv("NODE_ENV", "development");

    const panel = render(
      await DevFakeBillingCheckoutPage({
        searchParams: Promise.resolve({
          session: "fake_cs_1",
          plan: "monthly",
          next: "http://localhost:3000/settings/account?checkout=complete",
        }),
      }),
    );

    expect(panel.getByText("Complete checkout")).toBeInTheDocument();
    expect(panel.getByText("Cancel")).toBeInTheDocument();
  });

  it("says that completing does not grant Pro", async () => {
    vi.stubEnv("NODE_ENV", "development");

    const panel = render(
      await DevFakeBillingCheckoutPage({
        searchParams: Promise.resolve({
          session: "fake_cs_1",
          plan: "monthly",
          next: "http://localhost:3000/settings/account?checkout=complete",
        }),
      }),
    );

    // The webhook, not the redirect, is what moves the subscription. A page that said
    // otherwise would teach the wrong thing about how the product works.
    expect(panel.container.textContent).toContain("webhook");
  });

  it("refuses a return URL on another site, and offers no link to it", async () => {
    vi.stubEnv("NODE_ENV", "development");

    const panel = render(
      await DevFakeBillingCheckoutPage({
        searchParams: Promise.resolve({
          session: "fake_cs_1",
          plan: "monthly",
          next: "https://attacker.example/steal",
        }),
      }),
    );

    // The query string is attacker-controllable by anyone who can hand a developer a
    // link, and this page turns `next` into the target of a clickable link. A target on
    // another site is refused outright, so there is no link to it at all.
    expect(panel.container.textContent).not.toContain("attacker.example");
    expect(panel.queryByText("Complete checkout")).not.toBeInTheDocument();
  });

  it("keeps the success path and its query string", async () => {
    vi.stubEnv("NODE_ENV", "development");

    const panel = render(
      await DevFakeBillingCheckoutPage({
        searchParams: Promise.resolve({
          session: "fake_cs_1",
          plan: "monthly",
          next: "http://localhost:3000/settings/account?checkout=complete",
        }),
      }),
    );

    const link = panel.getByText("Complete checkout");
    expect(link.getAttribute("href")).toBe("/settings/account?checkout=complete");
  });

  it("shows a plan it does not recognise rather than hiding it", async () => {
    vi.stubEnv("NODE_ENV", "development");

    const panel = render(
      await DevFakeBillingCheckoutPage({
        searchParams: Promise.resolve({ session: "fake_cs_1", plan: "weekly" }),
      }),
    );

    expect(panel.container.textContent).toContain("weekly");
  });

  it("renders without a session or a plan", async () => {
    vi.stubEnv("NODE_ENV", "development");

    const panel = render(await DevFakeBillingCheckoutPage({ searchParams: Promise.resolve({}) }));

    expect(panel.container.textContent).toContain("Unknown plan");
  });
});
