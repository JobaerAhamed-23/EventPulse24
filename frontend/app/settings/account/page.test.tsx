/**
 * `/settings/account` — the plan, the portal, and Download my data.
 *
 * **The state worth testing hardest is `past_due`.** `is_pro` is true for it, so a screen
 * built on the entitlement bool alone would render a person whose card failed exactly like
 * a person with no problem at all — and this is the only place in the product where a
 * failed payment is visible. The test that asserts a past-due user is *not* shown as "free"
 * is the regression guard for that.
 *
 * **The second is placement.** `data-export` settled that export is ungated; this screen
 * must not re-gate it by putting the control inside a Pro-only block. So there is a test
 * that a Free account sees the export control.
 */
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsAccountPage from "@/app/settings/account/page";

const readBillingAccount = vi.fn();
const getSession = vi.fn();

vi.mock("@/lib/billing-account-read", () => ({
  readBillingAccount: () => readBillingAccount(),
}));

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings/account",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
  redirect: vi.fn(),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  name: "",
  onboarding: { completed: true, current_step: null },
};

/** The account, as the server sends it. */
function accountOf(overrides: Record<string, unknown> = {}) {
  return {
    status: null,
    plan: null,
    period_end: null,
    is_pro: false,
    needs_payment: false,
    had_pro: false,
    ...overrides,
  };
}

function serve(overrides: Record<string, unknown> = {}) {
  readBillingAccount.mockResolvedValue({ kind: "found", account: accountOf(overrides) });
}

beforeEach(() => {
  readBillingAccount.mockReset();
  getSession.mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  serve();
});

/** The plan block, scoped — the page has more than one region. */
function planBlock(): HTMLElement {
  return screen.getByRole("region", { name: "Your plan" });
}

describe("a free account", () => {
  it("says so, and points at pricing quietly", async () => {
    render(await SettingsAccountPage());

    expect(within(planBlock()).getByText("You’re on the free plan.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "See what Pro adds" })).toHaveAttribute(
      "href",
      "/pricing",
    );
  });

  it("offers no portal button, because there is nothing to manage", async () => {
    render(await SettingsAccountPage());

    expect(screen.queryByRole("button", { name: /Manage subscription/ })).toBeNull();
  });

  it("still gets Download my data", async () => {
    // **The acceptance criterion by name**: the export must not be gated by placement.
    render(await SettingsAccountPage());

    expect(screen.getByRole("region", { name: "Download my data" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Email me my data" })).toBeTruthy();
  });
});

describe("a lapsed account", () => {
  it("is told their Pro plan ended, not shown a blank free screen", async () => {
    serve({ status: "canceled", had_pro: true, period_end: "2027-03-03T12:00:00+00:00" });

    render(await SettingsAccountPage());

    expect(within(planBlock()).getByText(/Your Pro plan ended on/)).toBeTruthy();
  });

  it("says it plainly even when no end date is known", async () => {
    serve({ status: "expired", had_pro: true, period_end: null });

    render(await SettingsAccountPage());

    expect(within(planBlock()).getByText("Your Pro plan has ended.")).toBeTruthy();
  });

  it("does not claim a brand-new account once had Pro", async () => {
    serve({ status: null, had_pro: false });

    render(await SettingsAccountPage());

    expect(within(planBlock()).queryByText(/Pro plan ended/)).toBeNull();
    expect(within(planBlock()).queryByText(/Pro plan has ended/)).toBeNull();
  });
});

describe("an active Pro account", () => {
  beforeEach(() => {
    serve({
      status: "active",
      plan: "yearly",
      is_pro: true,
      had_pro: true,
      period_end: "2027-03-03T12:00:00+00:00",
    });
  });

  it("says they are on Pro", async () => {
    render(await SettingsAccountPage());

    expect(within(planBlock()).getByText("You’re on Pro.")).toBeTruthy();
  });

  it("states when the term runs out, and never calls it a renewal", async () => {
    // **`cancel_at_period_end` is not modelled**, so "renews" would be a reassuring lie
    // told to the person most likely to be reading this — somebody who just cancelled.
    render(await SettingsAccountPage());

    expect(within(planBlock()).getByText(/Your plan runs until/)).toBeTruthy();
    expect(planBlock().textContent).not.toMatch(/renew/i);
  });

  it("offers the portal, and builds no cancel flow of its own", async () => {
    render(await SettingsAccountPage());

    expect(screen.getByRole("button", { name: "Manage subscription" })).toBeTruthy();
    // Cancellation is Stripe's: a local control would be a second write path into
    // subscription state for the webhook to reconcile against.
    expect(screen.queryByRole("button", { name: /cancel/i })).toBeNull();
  });

  it("does not point an existing subscriber at the pricing page", async () => {
    render(await SettingsAccountPage());

    expect(screen.queryByRole("link", { name: "See what Pro adds" })).toBeNull();
  });
});

describe("a past-due account", () => {
  beforeEach(() => {
    serve({
      status: "past_due",
      plan: "monthly",
      is_pro: true,
      needs_payment: true,
      had_pro: true,
      period_end: "2027-03-03T12:00:00+00:00",
    });
  });

  it("is never rendered as a free account", async () => {
    // **The regression this screen exists to prevent.** `is_pro` is true here, so a
    // screen reading only that bool would look identical to an untroubled Pro account —
    // and one reading it as "not active" would hide the problem entirely.
    render(await SettingsAccountPage());

    expect(within(planBlock()).queryByText("You’re on the free plan.")).toBeNull();
    expect(within(planBlock()).getByText("You’re on Pro.")).toBeTruthy();
  });

  it("says a payment failed, and what to do about it", async () => {
    render(await SettingsAccountPage());

    expect(within(planBlock()).getByText(/We couldn’t take your last payment/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Update payment" })).toBeTruthy();
  });

  it("does not also show the ordinary term line", async () => {
    // Two sentences about the same term would bury the one that matters.
    render(await SettingsAccountPage());

    expect(within(planBlock()).queryByText(/Your plan runs until/)).toBeNull();
  });

  it("never shows the processor's own word for it", async () => {
    render(await SettingsAccountPage());

    // "past_due" is a word from a payment processor, not from a person.
    expect(planBlock().textContent).not.toContain("past_due");
  });
});

describe("the shell", () => {
  it("marks Settings as the active sidenav item", async () => {
    render(await SettingsAccountPage());

    const sidenav = screen.getByRole("complementary", { name: "Primary" });
    expect(within(sidenav).getByRole("link", { name: "Settings" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("shows the unavailable state when the read fails", async () => {
    // **An account screen that rendered "free plan" because the API blinked** would tell
    // a paying subscriber they are not one.
    readBillingAccount.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsAccountPage());

    expect(screen.queryByRole("region", { name: "Your plan" })).toBeNull();
  });

  it("shows the signed-out state without reading a plan", async () => {
    getSession.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsAccountPage());

    expect(screen.queryByRole("region", { name: "Your plan" })).toBeNull();
  });
});

describe("the city, which is the profile screen's", () => {
  it("is not edited here", async () => {
    /**
     * **One editing surface, not two.** Two copies of one control are two places to
     * keep in sync and two answers when they drift — which is the failure this move
     * exists to end, not to duplicate.
     */
    render(await SettingsAccountPage());

    expect(screen.queryByRole("combobox", { name: /city/i })).not.toBeInTheDocument();
  });

  it("is not named here either, now that nothing points here for it", async () => {
    /**
     * **The signpost was for the links, and the links were repointed.** A row reading
     * "your city now sits under Profile" earned its place while Browse's "Change city"
     * still arrived on this route; `components/browse/browse-hero.tsx` and
     * `browse-states.tsx` now link to `/settings/profile` directly, and
     * `tests/browse-rendering.test.tsx` holds them to it.
     *
     * What is left without them is a heading over a sentence over nothing, between the
     * plan and the export, on a screen about neither.
     */
    const { container } = render(await SettingsAccountPage());

    expect(screen.queryByRole("heading", { name: "City" })).not.toBeInTheDocument();
    expect(container.querySelector("[data-city-moved-note]")).toBeNull();
  });

  it("does not promise a city in the screen's own subheading", async () => {
    /** The subheading said "Your plan, your city, and your data." while the row was
     * here. A heading that lists a thing the screen does not have is the same lie as a
     * link that goes nowhere. */
    render(await SettingsAccountPage());

    expect(screen.getByText("Your plan, and your data.")).toBeInTheDocument();
  });

  it("still says where the zone is not, by not mentioning it", async () => {
    /** The zone was never here, and the move did not bring it. This is the guard on the
     * one above: a screen that grew a zone control would fail it. */
    render(await SettingsAccountPage());

    expect(screen.queryByRole("combobox", { name: /time ?zone/i })).not.toBeInTheDocument();
  });
});
