/**
 * The plan block: four states, and the one door out of them.
 *
 * **The state worth testing hardest is `past_due`.** `isPro` is true for it, so anything
 * built on that bool alone renders a person whose card failed exactly like a person with
 * none — and this is the only place in the product where a failed payment is visible.
 *
 * **The second is the date.** `cancel_at_period_end` is modelled nowhere in this product,
 * so "renews" cannot be said truthfully. The test that asserts the word never appears is
 * what stops a future reader "improving" the copy into a lie.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PlanSummary } from "@/components/settings/plan-summary";

const POST = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { POST: (...args: unknown[]) => POST(...args) },
}));

const assign = vi.fn();

beforeEach(() => {
  POST.mockReset();
  POST.mockResolvedValue({ data: { url: "https://portal.test/session" } });
  assign.mockReset();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { assign },
  });
});

function renderPlan(props: Partial<React.ComponentProps<typeof PlanSummary>> = {}) {
  return render(
    <PlanSummary
      status={props.status ?? null}
      isPro={props.isPro ?? false}
      needsPayment={props.needsPayment ?? false}
      hadPro={props.hadPro ?? false}
      periodEnd={props.periodEnd ?? null}
    />,
  );
}

const PRO = {
  status: "active",
  isPro: true,
  hadPro: true,
  periodEnd: "2027-03-03T12:00:00+00:00",
};

const PAST_DUE = { ...PRO, status: "past_due", needsPayment: true };

describe("a free account", () => {
  it("says so and links to pricing", () => {
    renderPlan();

    expect(screen.getByText("You’re on the free plan.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "See what Pro adds" })).toHaveAttribute(
      "href",
      "/pricing",
    );
  });

  it("has no portal control", () => {
    renderPlan();

    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("an active Pro account", () => {
  it("states the term without calling it a renewal", () => {
    renderPlan(PRO);

    expect(screen.getByText(/Your plan runs until/)).toBeTruthy();
    // `cancel_at_period_end` is not modelled, so "renews" would be a reassuring lie told
    // to someone who cancelled five minutes ago and came here to check.
    expect(document.body.textContent).not.toMatch(/renew/i);
  });

  it("renders the date in a form a person reads", () => {
    renderPlan(PRO);

    expect(screen.getByText(/2027/)).toBeTruthy();
    expect(document.body.textContent).not.toContain("2027-03-03T12:00:00+00:00");
  });

  it("says nothing about a term when the server sent no date", () => {
    renderPlan({ ...PRO, periodEnd: null });

    expect(screen.queryByText(/Your plan runs until/)).toBeNull();
    expect(screen.getByText("You’re on Pro.")).toBeTruthy();
  });

  it("offers Manage subscription and no local cancel", () => {
    renderPlan(PRO);

    expect(screen.getByRole("button", { name: "Manage subscription" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /cancel/i })).toBeNull();
  });
});

describe("a past-due account", () => {
  it("is Pro, not free", () => {
    renderPlan(PAST_DUE);

    expect(screen.getByText("You’re on Pro.")).toBeTruthy();
    expect(screen.queryByText("You’re on the free plan.")).toBeNull();
  });

  it("says a payment failed and labels the action for it", () => {
    renderPlan(PAST_DUE);

    expect(screen.getByText(/We couldn’t take your last payment/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Update payment" })).toBeTruthy();
  });

  it("does not bury that under the ordinary term line", () => {
    renderPlan(PAST_DUE);

    expect(screen.queryByText(/Your plan runs until/)).toBeNull();
  });

  it("never shows the processor's own word", () => {
    renderPlan(PAST_DUE);

    expect(document.body.textContent).not.toContain("past_due");
  });
});

describe("a lapsed account", () => {
  it("is told when Pro ended", () => {
    renderPlan({ status: "canceled", hadPro: true, periodEnd: "2027-03-03T12:00:00+00:00" });

    expect(screen.getByText(/Your Pro plan ended on/)).toBeTruthy();
  });

  it("is still offered the way back", () => {
    renderPlan({ status: "expired", hadPro: true });

    expect(screen.getByRole("link", { name: "See what Pro adds" })).toBeTruthy();
  });
});

describe("the portal", () => {
  it("mints a session and follows the URL it returns", async () => {
    renderPlan(PRO);

    fireEvent.click(screen.getByRole("button", { name: "Manage subscription" }));

    await waitFor(() => expect(POST).toHaveBeenCalledWith("/api/billing/portal"));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://portal.test/session"));
  });

  it("cannot be opened twice at once", async () => {
    let release: (value: unknown) => void = () => {};
    POST.mockReturnValue(new Promise((resolve) => (release = resolve)));
    renderPlan(PRO);

    fireEvent.click(screen.getByRole("button", { name: "Manage subscription" }));
    const button = screen.getByRole("button", { name: "Opening…" });

    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");

    release({ data: { url: "https://portal.test/session" } });
    await waitFor(() => expect(assign).toHaveBeenCalled());
  });

  it("shows the server's refusal and stays where it is", async () => {
    POST.mockResolvedValue({
      error: { code: "no_subscription", message: "You don’t have a subscription." },
      response: { status: 409 },
    });
    renderPlan(PRO);

    fireEvent.click(screen.getByRole("button", { name: "Manage subscription" }));

    expect(await screen.findByText("You don’t have a subscription.")).toBeTruthy();
    expect(assign).not.toHaveBeenCalled();
  });

  it("falls back to its own line when the request never reached the API", async () => {
    POST.mockRejectedValue(new Error("offline"));
    renderPlan(PRO);

    fireEvent.click(screen.getByRole("button", { name: "Manage subscription" }));

    expect(await screen.findByText("Couldn't open your plan. Try again in a moment.")).toBeTruthy();
  });

  it("shows a line even when the refusal carried no sentence", async () => {
    // A refusal with no message must not render as no refusal at all.
    POST.mockResolvedValue({
      error: { code: "server_error", message: "" },
      response: { status: 500 },
    });
    renderPlan(PRO);

    fireEvent.click(screen.getByRole("button", { name: "Manage subscription" }));

    expect(await screen.findByText("Couldn't open your plan. Try again in a moment.")).toBeTruthy();
  });
});
