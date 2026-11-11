import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChoosePlanButton } from "@/components/pricing/choose-plan-button";

/**
 * The buy button's four outcomes.
 *
 * **The one that matters most is the 409.** A Pro user whose page was rendered before
 * their plan landed would be shown a buy button — and the server refusing that click is
 * the only thing that catches it. So the 409 must swap the page to its Pro state rather
 * than showing a failure: a buy button for somebody who already pays is a control that
 * cannot work, and the server has just said so.
 *
 * **The 401 is a routing, not an error.** A signed-out visitor is *expected* on this
 * page — it is public — so "you are not signed in" is answered by sending them to sign
 * in, with a return path so they come back here.
 */

const POST = vi.fn();
const push = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { POST: (...args: unknown[]) => POST(...args) },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn() }),
}));

/** `window.location.assign` is the navigation to the provider's page. */
const assign = vi.fn();

beforeEach(() => {
  POST.mockReset();
  push.mockReset();
  assign.mockReset();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...window.location, assign },
  });
});

describe("ChoosePlanButton", () => {
  it("starts a checkout for the chosen plan and follows the returned URL", async () => {
    POST.mockResolvedValue({
      data: { url: "https://checkout.example/session/abc" },
      error: undefined,
    });
    render(<ChoosePlanButton cycle="monthly" signedIn />);

    fireEvent.click(screen.getByRole("button", { name: "Continue to checkout →" }));

    await vi.waitFor(() => {
      expect(assign).toHaveBeenCalledWith("https://checkout.example/session/abc");
    });
    // **The plan is the only thing sent.** The endpoint derives the redirect URLs
    // itself; a client that could name them could send a paying user elsewhere.
    expect(POST).toHaveBeenCalledWith("/api/billing/checkout", { body: { plan: "monthly" } });
  });

  it("sends the yearly plan when the annual option is chosen", async () => {
    POST.mockResolvedValue({ data: { url: "https://checkout.example/s" }, error: undefined });
    render(<ChoosePlanButton cycle="yearly" signedIn />);

    fireEvent.click(screen.getByRole("button", { name: "Continue to checkout →" }));

    await vi.waitFor(() => {
      expect(POST).toHaveBeenCalledWith("/api/billing/checkout", { body: { plan: "yearly" } });
    });
  });

  it("sends a signed-out visitor to sign-in, with a way back", () => {
    render(<ChoosePlanButton cycle="monthly" signedIn={false} />);

    const link = screen.getByRole("link", { name: "Sign in to buy" });

    expect(link).toHaveAttribute("href", "/signin?next=%2Fpricing");
    // **No request is made.** A visitor with no session cannot buy, and the answer is
    // the sign-in route rather than a failed call.
    expect(POST).not.toHaveBeenCalled();
  });

  it("routes to sign-in when the session has gone away mid-click", async () => {
    POST.mockResolvedValue({
      data: undefined,
      error: { code: "unauthenticated", message: "Sign in to continue." },
      response: { status: 401 },
    });
    render(<ChoosePlanButton cycle="monthly" signedIn />);

    fireEvent.click(screen.getByRole("button", { name: "Continue to checkout →" }));

    await vi.waitFor(() => {
      expect(push).toHaveBeenCalledWith("/signin?next=%2Fpricing");
    });
  });

  it("swaps to the Pro state when the server says the user already subscribes", async () => {
    const onAlreadyPro = vi.fn();
    POST.mockResolvedValue({
      data: undefined,
      error: { code: "already_subscribed", message: "Your Pro subscription is already active." },
      response: { status: 409 },
    });
    render(<ChoosePlanButton cycle="monthly" signedIn onAlreadyPro={onAlreadyPro} />);

    fireEvent.click(screen.getByRole("button", { name: "Continue to checkout →" }));

    await vi.waitFor(() => {
      expect(onAlreadyPro).toHaveBeenCalled();
    });
    // **Not a failure.** The page changes state rather than showing an error.
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
  });

  it("shows the API's own words when the checkout fails", async () => {
    POST.mockResolvedValue({
      data: undefined,
      error: { code: "provider_error", message: "The payment provider is unreachable right now." },
      response: { status: 502 },
    });
    render(<ChoosePlanButton cycle="monthly" signedIn />);

    fireEvent.click(screen.getByRole("button", { name: "Continue to checkout →" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "The payment provider is unreachable right now.",
    );
  });

  it("shows the offline line when the request never reaches the API", async () => {
    POST.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<ChoosePlanButton cycle="monthly" signedIn />);

    fireEvent.click(screen.getByRole("button", { name: "Continue to checkout →" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Couldn't reach Pulse. Try again.");
    // **The button comes back.** A button that stays disabled after a failure is a
    // button the user has to reload the page to use again.
    expect(screen.getByRole("button", { name: "Continue to checkout →" })).toBeEnabled();
  });

  it("offers no modal, ever", async () => {
    POST.mockResolvedValue({
      data: undefined,
      error: { code: "provider_error", message: "Nope." },
      response: { status: 502 },
    });
    const { container } = render(<ChoosePlanButton cycle="monthly" signedIn />);

    fireEvent.click(screen.getByRole("button", { name: "Continue to checkout →" }));

    await screen.findByRole("status");
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(container.querySelector('[role="alertdialog"]')).toBeNull();
  });
});
