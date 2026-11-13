import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PricingRoute from "@/app/pricing/page";

/**
 * The route's own rules.
 *
 * **The page is public.** A signed-out visitor reads it, and chooses a plan without
 * meeting an authentication error. That is why the route never redirects an anonymous
 * visitor away — a redirect would make the page unreachable for the people a pricing
 * page exists for.
 *
 * **The tier is read on the server.** `getSession()` answers *who*; the entitlement read
 * answers *whether they are Pro*. Both are needed, and the route must not skip the
 * entitlement read for a signed-in user — a Free user shown as Pro would be told they
 * already pay, and a Pro user shown as Free would be shown a buy button.
 */

const getSession = vi.fn();
const GET = vi.fn();

vi.mock("@/lib/session", () => ({
  getSession: () => getSession(),
  sessionHeaders: async () => ({ cookie: "sessionid=abc" }),
}));

vi.mock("@/lib/backend-client", () => ({
  api: { GET: (...args: unknown[]) => GET(...args) },
}));

// The buy button is a client island and calls `useRouter`. The route test renders the
// whole screen, so the router has to exist — the app router is not mounted in a unit
// test, and the hook throws without it.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  redirect: vi.fn(),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  name: "",
  onboarding: { completed: true, current_step: null },
};

beforeEach(() => {
  getSession.mockReset();
  GET.mockReset();
});

describe("/pricing", () => {
  it("renders for an anonymous visitor, without asking the entitlement read", async () => {
    getSession.mockResolvedValue({ kind: "anonymous" });

    render(await PricingRoute());

    expect(
      screen.getByRole("heading", { level: 1, name: "Two ways to keep calm." }),
    ).toBeInTheDocument();
    // **No pointless request.** There is nobody to read the entitlement for.
    expect(GET).not.toHaveBeenCalled();
  });

  it("routes a signed-out visitor to sign-in when they choose a plan", async () => {
    getSession.mockResolvedValue({ kind: "anonymous" });

    render(await PricingRoute());

    expect(screen.getByRole("link", { name: "Sign in to buy" })).toHaveAttribute(
      "href",
      "/signin?next=%2Fpricing",
    );
  });

  it("shows a Free user the checkout button, after reading their entitlement", async () => {
    getSession.mockResolvedValue({ kind: "signed-in", user: USER });
    GET.mockResolvedValue({ data: { is_pro: false }, error: undefined });

    render(await PricingRoute());

    expect(screen.getByRole("button", { name: "Continue to checkout →" })).toBeInTheDocument();
    expect(GET).toHaveBeenCalledWith("/api/billing/subscription", {
      headers: { cookie: "sessionid=abc" },
    });
  });

  it("shows a Pro user their plan and no buy button", async () => {
    getSession.mockResolvedValue({ kind: "signed-in", user: USER });
    GET.mockResolvedValue({ data: { is_pro: true }, error: undefined });

    render(await PricingRoute());

    expect(screen.getByRole("button", { name: /You’re on Pro/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Continue to checkout/ })).not.toBeInTheDocument();
  });

  it("renders the tiers rather than failing when the entitlement read cannot be made", async () => {
    getSession.mockResolvedValue({ kind: "signed-in", user: USER });
    GET.mockRejectedValue(new TypeError("Failed to fetch"));

    render(await PricingRoute());

    // **The honest direction to be wrong in.** The tier is unknown, so the page shows
    // Free; if the visitor is in fact Pro, the checkout refuses and the page swaps
    // itself. A page that failed to render would be worse than a page that is briefly
    // one state behind.
    expect(screen.getByRole("button", { name: "Continue to checkout →" })).toBeInTheDocument();
  });

  it("renders for a session the API could not answer, without claiming they are signed out", async () => {
    getSession.mockResolvedValue({ kind: "unavailable" });

    render(await PricingRoute());

    expect(
      screen.getByRole("heading", { level: 1, name: "Two ways to keep calm." }),
    ).toBeInTheDocument();
    // **Not folded into "signed out".** `lib/session.ts` is explicit that telling a
    // signed-in user they are anonymous because the API blinked "would be a lie about
    // who they are" — and "Sign in to buy" is that lie in a button.
    expect(screen.queryByRole("link", { name: "Sign in to buy" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue to checkout →" })).toBeInTheDocument();
    expect(GET).not.toHaveBeenCalled();
  });

  it("is rendered per request, because it depends on the session", async () => {
    const page = await import("@/app/pricing/page");

    expect(page.dynamic).toBe("force-dynamic");
  });

  it("is reachable from the pre-auth footer", async () => {
    getSession.mockResolvedValue({ kind: "anonymous" });

    render(await PricingRoute());

    expect(screen.getByRole("link", { name: "Pricing" })).toHaveAttribute("href", "/pricing");
  });
});
