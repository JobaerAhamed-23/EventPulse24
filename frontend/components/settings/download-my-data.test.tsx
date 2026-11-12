/**
 * FR-52's request control, and the promise its copy makes.
 *
 * **Three things worth proving that a screenshot cannot show:**
 *
 * 1. **It does not pretend to download.** The export is built by a worker and arrives by
 *    email; a control that implied a file was coming back would read as broken when none
 *    appeared.
 * 2. **Asking twice is not an error.** The backend joins a second request to the one in
 *    flight, so the UI must say the same calm thing rather than reporting a conflict the
 *    user did not cause.
 * 3. **The failure keeps the screen usable.** Nothing is lost by a failed request — there
 *    is nothing to lose — so the line says so and the button stays available.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DownloadMyData } from "@/components/settings/download-my-data";

const POST = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { POST: (...args: unknown[]) => POST(...args) },
}));

/** The server's answer to an accepted request. */
function accepted(overrides: Record<string, unknown> = {}) {
  return {
    data: {
      id: "01a1cb44-0000-7000-8000-000000000000",
      status: "pending",
      requested_at: "2026-11-12T06:00:00+00:00",
      completed_at: null,
      expires_at: null,
      due_by: "2026-11-13T06:00:00+00:00",
      ...overrides,
    },
    response: { status: 202 },
  };
}

beforeEach(() => {
  POST.mockReset();
  POST.mockResolvedValue(accepted());
});

function clickRequest() {
  fireEvent.click(screen.getByRole("button", { name: "Email me my data" }));
}

describe("the control", () => {
  it("offers to email the data, not to download it", () => {
    // **The copy is the honesty.** The links arrive by mail; a button saying "Download"
    // that produced no file would read as a bug.
    render(<DownloadMyData />);

    expect(screen.getByRole("button", { name: "Email me my data" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^download/i })).toBeNull();
  });

  it("says what the export contains", () => {
    render(<DownloadMyData />);

    expect(screen.getByText(/JSON and as a calendar file/)).toBeTruthy();
  });
});

describe("requesting", () => {
  it("posts once and says it will arrive by email within 24 hours", async () => {
    render(<DownloadMyData />);

    clickRequest();

    await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));
    expect(POST).toHaveBeenCalledWith("/api/exports");
    expect(
      await screen.findByText("On its way. We'll email your data within 24 hours."),
    ).toBeTruthy();
  });

  it("announces the confirmation without moving focus", async () => {
    render(<DownloadMyData />);

    clickRequest();

    // A live region that was always present is what makes the text's *arrival*
    // announceable; a `role="alert"` would interrupt for something that is not urgent.
    const status = screen.getByRole("status");
    await waitFor(() => expect(status.textContent).toContain("On its way."));
  });

  it("sends no body, because the user comes from the session", async () => {
    render(<DownloadMyData />);

    clickRequest();

    await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));
    // AD-12: a payload naming a user would be a payload that could name another one.
    const [, body] = POST.mock.calls[0] as [string, unknown];
    expect(body).toBeUndefined();
  });
});

describe("asking twice", () => {
  it("is not reported as a failure", async () => {
    // The backend joins the second request to the first — a partial unique constraint
    // makes that a database fact — so there is nothing here for the user to fix.
    render(<DownloadMyData />);

    clickRequest();
    await screen.findByText("On its way. We'll email your data within 24 hours.");
    clickRequest();

    await waitFor(() => expect(POST).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("On its way. We'll email your data within 24 hours.")).toBeTruthy();
  });

  it("cannot be double-submitted while the first is in flight", async () => {
    let release: (value: unknown) => void = () => {};
    POST.mockReturnValue(new Promise((resolve) => (release = resolve)));
    render(<DownloadMyData />);

    clickRequest();
    const button = screen.getByRole("button", { name: "Starting…" });

    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");

    release(accepted());
    await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));
  });
});

describe("when the request fails", () => {
  it("says so and leaves the control usable", async () => {
    POST.mockResolvedValue({
      error: { code: "server_error", message: "" },
      response: { status: 500 },
    });
    render(<DownloadMyData />);

    clickRequest();

    expect(await screen.findByText("Couldn't start that. Try again in a moment.")).toBeTruthy();
    // Nothing was lost — there was nothing to lose — so the button is still there.
    expect(screen.getByRole("button", { name: "Email me my data" })).not.toBeDisabled();
  });

  it("shows the server's own sentence when it sent one", async () => {
    POST.mockResolvedValue({
      error: { code: "rate_limited", message: "Too many requests." },
      response: { status: 429 },
    });
    render(<DownloadMyData />);

    clickRequest();

    expect(await screen.findByText("Too many requests.")).toBeTruthy();
  });

  it("survives a request that never reached the API", async () => {
    POST.mockRejectedValue(new Error("offline"));
    render(<DownloadMyData />);

    clickRequest();

    expect(await screen.findByText("Couldn't start that. Try again in a moment.")).toBeTruthy();
  });

  it("clears the failure when the user tries again", async () => {
    POST.mockResolvedValueOnce({
      error: { code: "server_error", message: "" },
      response: { status: 500 },
    });
    render(<DownloadMyData />);

    clickRequest();
    await screen.findByText("Couldn't start that. Try again in a moment.");

    POST.mockResolvedValue(accepted());
    clickRequest();

    await screen.findByText("On its way. We'll email your data within 24 hours.");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
