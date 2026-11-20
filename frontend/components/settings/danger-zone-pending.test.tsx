/**
 * The danger zone's pending state — **the way back.**
 *
 * **What these tests hold.**
 *
 * 1. **It names the server's date.** The destruction date the server computed, and the
 *    date the request was made — not a countdown recomputed in the browser.
 * 2. **The cancel calls the right endpoint**, literally, so the contract-coverage test
 *    can see it.
 * 3. **Cancelling is not presented as an error.** The endpoint answers the same way
 *    whether or not anything was pending, and the surface reflects that.
 * 4. **A failed cancel keeps the pending state.** A cancel that silently cleared the
 *    screen would tell the user the deletion was stopped when it was not.
 * 5. **axe-core passes.**
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DangerZonePending } from "@/components/settings/danger-zone-pending";

const del = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    DELETE: (...args: unknown[]) => del(...args),
  },
}));

/** The server's two moments, for an account with a deletion pending. */
const SCHEDULED_FOR = "2026-12-20T00:00:00+00:00";
const REQUESTED_AT = "2026-11-20T00:00:00+00:00";

beforeEach(() => {
  del.mockReset();
  del.mockResolvedValue({ data: { status: "cancelled" } });
});

/** The serious and critical violations on the rendered island. */
async function audit(): Promise<string[]> {
  const results = await axe.run(document.body, {
    resultTypes: ["violations"],
    rules: { "color-contrast": { enabled: false } },
  });
  return results.violations
    .filter((violation) => violation.impact === "serious" || violation.impact === "critical")
    .map(
      (violation) => `${violation.id}: ${violation.nodes.map((node) => node.target).join(", ")}`,
    );
}

describe("the pending state", () => {
  it("names the date the account will be destroyed", () => {
    /** **The server's date, rendered.**
     *
     * A person deciding whether to cancel needs to know *when* the account dies. The
     * date was computed once, by the server, and this renders that moment — it does not
     * add thirty days to anything. */
    render(<DangerZonePending scheduledFor={SCHEDULED_FOR} requestedAt={REQUESTED_AT} />);

    const date = screen.getByText(/december 20, 2026/i);
    expect(date).toBeInTheDocument();
    expect(date.closest("[data-pending-line]")?.textContent).toMatch(/will be deleted on/i);
  });

  it("names the day the request was made", () => {
    /** **"You asked on the 3rd"** — which is possible only because the server computed
     * it, and it differs from the destruction date by exactly the grace period. */
    render(<DangerZonePending scheduledFor={SCHEDULED_FOR} requestedAt={REQUESTED_AT} />);

    expect(screen.getByText(/november 20, 2026/i)).toBeInTheDocument();
  });

  it("does not compute a countdown of its own", () => {
    /** **No duration, and no "30 days".**
     *
     * A number typed into a frontend is the mistake the mail templates already made: a
     * number that keeps saying "30 days" after the constant says otherwise. The screen
     * has the date; it does not need to re-derive a deadline. */
    render(<DangerZonePending scheduledFor={SCHEDULED_FOR} requestedAt={REQUESTED_AT} />);

    expect(screen.queryByText(/\b30 days\b/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/\b30-day\b/i)).not.toBeInTheDocument();
  });

  it("says that nothing has been deleted yet", () => {
    /** **The truth the whole promise rests on.** The account keeps working for the
     * whole grace period, and a person who has not read the mail needs to be told. */
    render(<DangerZonePending scheduledFor={SCHEDULED_FOR} requestedAt={REQUESTED_AT} />);

    expect(screen.getByText(/nothing has been deleted yet/i)).toBeInTheDocument();
  });

  it("does not claim the deletion cannot be undone", () => {
    /** **It can be undone — that is the entire point of this button.** */
    render(<DangerZonePending scheduledFor={SCHEDULED_FOR} requestedAt={REQUESTED_AT} />);

    expect(screen.queryByText(/cannot be undone/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/permanent/i)).not.toBeInTheDocument();
  });

  it("says nothing about a date it cannot read", () => {
    /** **An unparseable date is not a reason to invent one.** */
    const { container } = render(
      <DangerZonePending scheduledFor="not-a-date" requestedAt={REQUESTED_AT} />,
    );

    expect(container.querySelector("[data-pending-date]")).toBeNull();
    expect(screen.getByText(/your account has a pending deletion/i)).toBeInTheDocument();
  });

  it("has zero serious or critical axe-core violations", async () => {
    render(<DangerZonePending scheduledFor={SCHEDULED_FOR} requestedAt={REQUESTED_AT} />);

    expect(await audit()).toEqual([]);
  });
});

describe("cancelling", () => {
  it("calls the cancel endpoint, literally", async () => {
    /** **The path is written out, not held in a variable.**
     *
     * `tests/endpoint-coverage.test.ts` matches `\.DELETE\s*\(\s*"/api/auth/profile/deletion"`
     * — the method and the path have to be adjacent. A path in a variable would not be
     * found, and the exemption this call site replaces would then be hiding a real one. */
    render(<DangerZonePending scheduledFor={SCHEDULED_FOR} requestedAt={REQUESTED_AT} />);

    fireEvent.click(screen.getByRole("button", { name: /keep my account/i }));

    await waitFor(() => expect(del).toHaveBeenCalledOnce());
    expect(del.mock.calls[0][0]).toBe("/api/auth/profile/deletion");
  });

  it("tells the container that the cancellation landed", async () => {
    /** **The container decides which state shows**, so it has to be told. */
    const onCancelled = vi.fn();
    render(
      <DangerZonePending
        scheduledFor={SCHEDULED_FOR}
        requestedAt={REQUESTED_AT}
        onCancelled={onCancelled}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /keep my account/i }));

    await waitFor(() => expect(onCancelled).toHaveBeenCalledOnce());
  });

  it("does not present a successful cancel as an error", async () => {
    /** **Cancelling is a success.**
     *
     * The endpoint answers the same way whether or not anything was pending — the
     * caller wanted no pending deletion and has none either way. **A surface that
     * apologised for cancelling something that was already gone would be wrong about
     * what just happened.** */
    render(<DangerZonePending scheduledFor={SCHEDULED_FOR} requestedAt={REQUESTED_AT} />);

    fireEvent.click(screen.getByRole("button", { name: /keep my account/i }));

    await waitFor(() => expect(del).toHaveBeenCalledOnce());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows the API's own refusal verbatim when the cancel fails", async () => {
    /** **The API's words, because the API wrote them for the person.** */
    del.mockResolvedValue({
      error: { code: "invalid_state", message: "We couldn't cancel that just now." },
    });
    render(<DangerZonePending scheduledFor={SCHEDULED_FOR} requestedAt={REQUESTED_AT} />);

    fireEvent.click(screen.getByRole("button", { name: /keep my account/i }));

    expect(await screen.findByText("We couldn't cancel that just now.")).toBeInTheDocument();
  });

  it("keeps the pending state when the cancel fails", async () => {
    /** **The most important failure in this file.**
     *
     * A cancel that failed did not stop anything. A screen that cleared the pending
     * state anyway would tell the person their account was safe when it is scheduled
     * for destruction — **the exact failure this surface exists to prevent.** */
    del.mockResolvedValue({ error: { code: "invalid_state", message: "Nope." } });
    render(<DangerZonePending scheduledFor={SCHEDULED_FOR} requestedAt={REQUESTED_AT} />);

    fireEvent.click(screen.getByRole("button", { name: /keep my account/i }));

    expect(await screen.findByText("Nope.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /keep my account/i })).toBeInTheDocument();
    expect(screen.getByText(/december 20, 2026/i)).toBeInTheDocument();
  });

  it("shows the offline line when the request never reached the API", async () => {
    del.mockRejectedValue(new Error("offline"));
    render(<DangerZonePending scheduledFor={SCHEDULED_FOR} requestedAt={REQUESTED_AT} />);

    fireEvent.click(screen.getByRole("button", { name: /keep my account/i }));

    expect(await screen.findByText(/couldn't cancel that/i)).toBeInTheDocument();
  });

  it("does not tell the container anything when the cancel fails", async () => {
    /** **The container must not swap the row on a failure.** */
    const onCancelled = vi.fn();
    del.mockResolvedValue({ error: { code: "invalid_state", message: "Nope." } });
    render(
      <DangerZonePending
        scheduledFor={SCHEDULED_FOR}
        requestedAt={REQUESTED_AT}
        onCancelled={onCancelled}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /keep my account/i }));

    expect(await screen.findByText("Nope.")).toBeInTheDocument();
    expect(onCancelled).not.toHaveBeenCalled();
  });

  it("does not send a second cancel while one is in flight", async () => {
    /** **One request per press.** The button is disabled while the request runs. */
    let release: (() => void) | undefined;
    del.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = () => resolve({ data: { status: "cancelled" } });
        }),
    );
    render(<DangerZonePending scheduledFor={SCHEDULED_FOR} requestedAt={REQUESTED_AT} />);

    const button = screen.getByRole("button", { name: /keep my account/i });
    fireEvent.click(button);
    await waitFor(() => expect(button).toBeDisabled());

    fireEvent.click(button);
    expect(del).toHaveBeenCalledOnce();

    release?.();
  });
});
