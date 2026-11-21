/**
 * **Ask us to cover this city** — the one way out of the no-sources state.
 *
 * **The control is a client island and this file is its contract.** The page decides
 * *where* it appears; the control owns the write, the four states, and what the reader
 * is told.
 *
 * **The four states are the point.** Idle, busy, recorded, failed — and the two rules
 * that make them honest:
 *
 * - **After a success the button is *replaced*, not disabled.** A disabled "Ask us to
 *   cover this city" reads as a broken control: it looks like something the reader
 *   could still do and cannot.
 * - **A failure never leaves a confirmation behind.** The confirmation is set only on a
 *   2xx, so a refused request cannot put "we'll go and look" on the screen — which
 *   would be a claim about the world that nothing supports (AD-10).
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CoverageRequestControl } from "@/components/browse/coverage-request-control";
import type { components } from "@/lib/api/schema";

const POST = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    POST: (...args: unknown[]) => POST(...args),
  },
}));

/**
 * The request's body, **as the generated contract states it**.
 *
 * **The type is the point** (AD-19): a body that does not match the API is a compile
 * error here rather than a request the server refuses.
 */
type CoverageRequestBody = components["schemas"]["CoverageRequestIn"];

beforeEach(() => {
  POST.mockReset();
  POST.mockResolvedValue({
    data: { city: "Brooklyn", created: true, recorded: true, request_count: 1 },
    response: { status: 201 },
  });
});

function renderControl() {
  return render(<CoverageRequestControl city="Brooklyn" />);
}

/** The ask button, by its accessible name. */
function askButton(): HTMLElement {
  return screen.getByRole("button", { name: "Ask us to cover this city" });
}

/** Press the ask and wait for the request to land. */
async function ask() {
  fireEvent.click(askButton());
  await waitFor(() => expect(POST).toHaveBeenCalled());
}

describe("the idle state", () => {
  it("offers a button named for the ask", () => {
    renderControl();

    expect(askButton()).toBeInTheDocument();
  });

  it("shows the words, not a glyph", () => {
    // **The house rule is a visible label, never an icon-only button** (WCAG 1.1.1).
    renderControl();

    expect(askButton().textContent).toContain("Ask us to cover this city");
  });

  it("is enabled", () => {
    renderControl();

    expect(askButton()).not.toBeDisabled();
  });

  it("shows no confirmation and no failure", () => {
    renderControl();

    expect(document.querySelector("[data-coverage-recorded]")).toBeNull();
    expect(document.querySelector("[data-coverage-failed]")).toBeNull();
  });
});

describe("the request", () => {
  it("posts the city to the coverage-request endpoint", async () => {
    renderControl();

    await ask();

    const [path, options] = POST.mock.calls[0] as [string, { body: CoverageRequestBody }];
    expect(path).toBe("/api/catalog/coverage-requests");
    expect(options.body).toEqual({ city: "Brooklyn" });
  });

  it("goes through the generated client", async () => {
    // AD-19: the frontend reaches the backend only through the generated client.
    renderControl();

    await ask();

    const [path] = POST.mock.calls[0] as [string];
    expect(path).toBe("/api/catalog/coverage-requests");
  });

  it("carries no user id", async () => {
    // **The reader comes from the session.** A body carrying a user id is the classic
    // way scoping goes wrong — the client asserts *who it is* and the server believes
    // it — and the contract's body has no such field.
    renderControl();

    await ask();

    const [, options] = POST.mock.calls[0] as [string, { body: CoverageRequestBody }];
    expect(Object.keys(options.body)).toEqual(["city"]);
  });
});

describe("the busy state", () => {
  it("disables the button while the request is in flight", async () => {
    renderControl();

    // **The promise never resolves during the assertion**, so the control is caught
    // mid-flight — which is the only moment the busy state exists.
    POST.mockImplementation(() => new Promise(() => {}));

    fireEvent.click(askButton());

    await waitFor(() => expect(askButton()).toBeDisabled());
  });

  it("says so to assistive technology", async () => {
    // **A disabled button is removed from the tab order**, so the reader would
    // otherwise hear nothing at all about the wait.
    renderControl();
    POST.mockImplementation(() => new Promise(() => {}));

    fireEvent.click(askButton());

    await waitFor(() => expect(askButton()).toHaveAttribute("aria-busy", "true"));
  });

  it("shows a quiet dot and not a spinner", async () => {
    // `EXPERIENCE.md` §"No spinners, anywhere": a spinner is a visual urgency badge,
    // and asking for coverage is not urgent.
    renderControl();
    POST.mockImplementation(() => new Promise(() => {}));

    fireEvent.click(askButton());

    await waitFor(() => expect(document.querySelector("[data-coverage-busy]")).toBeTruthy());
    expect(document.querySelector(".animate-spin")).toBeNull();
  });

  it("cannot be pressed twice", async () => {
    renderControl();
    POST.mockImplementation(() => new Promise(() => {}));

    fireEvent.click(askButton());
    await waitFor(() => expect(askButton()).toBeDisabled());
    fireEvent.click(askButton());

    expect(POST).toHaveBeenCalledTimes(1);
  });
});

describe("the recorded state", () => {
  it("confirms that we have been asked", async () => {
    renderControl();

    await ask();

    await waitFor(() =>
      expect(
        screen.getByText("Thanks — we'll go and look for sources in this city."),
      ).toBeInTheDocument(),
    );
  });

  it("replaces the button rather than disabling it", async () => {
    // **A disabled "Ask us to cover this city" reads as a broken control** — it looks
    // like something the reader could still do and cannot. The confirmation takes its
    // place instead.
    renderControl();

    await ask();

    await waitFor(() => expect(document.querySelector("[data-coverage-recorded]")).toBeTruthy());
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("announces itself politely", async () => {
    // **The reader pressed a button and the surface changed under them** — a screen
    // reader user is the one who most needs to hear that it did.
    renderControl();

    await ask();

    await waitFor(() => {
      const recorded = document.querySelector("[data-coverage-recorded]");
      expect(recorded?.getAttribute("role")).toBe("status");
      expect(recorded?.getAttribute("aria-live")).toBe("polite");
    });
  });

  it("does not show the count", async () => {
    // **The count is on the wire and not on the screen.** A reader told "you are the
    // 47th person to ask" is being told something about a crowd, and the product's
    // voice is calm.
    renderControl();

    await ask();

    await waitFor(() => expect(document.querySelector("[data-coverage-recorded]")).toBeTruthy());
    expect(document.body.textContent ?? "").not.toContain("47");
    expect(document.body.textContent ?? "").not.toMatch(/request_count/i);
  });

  it("shows no failure", async () => {
    renderControl();

    await ask();

    await waitFor(() => expect(document.querySelector("[data-coverage-recorded]")).toBeTruthy());
    expect(document.querySelector("[data-coverage-failed]")).toBeNull();
  });
});

describe("the failed state", () => {
  it("shows the server's own sentence", async () => {
    // **The message is the API's own words** — `lib/api-errors.ts` exists so the
    // frontend quotes the API rather than writing its own.
    POST.mockResolvedValue({
      data: undefined,
      error: {
        code: "rate_limited",
        message: "You've asked us to cover enough cities for today. Please try again tomorrow.",
      },
      response: { status: 429 },
    });

    renderControl();

    await ask();

    await waitFor(() =>
      expect(
        screen.getByText(
          "You've asked us to cover enough cities for today. Please try again tomorrow.",
        ),
      ).toBeInTheDocument(),
    );
  });

  it("announces itself as an alert", async () => {
    // **The failure is not the outcome the reader was waiting for**, and an alert is
    // announced without the focus moving.
    POST.mockResolvedValue({
      data: undefined,
      error: { code: "rate_limited", message: "Enough for today." },
      response: { status: 429 },
    });

    renderControl();

    await ask();

    await waitFor(() => {
      const failed = document.querySelector("[data-coverage-failed]");
      expect(failed?.getAttribute("role")).toBe("alert");
    });
  });

  it("puts the button back", async () => {
    // **The ask did not happen**, so the way to make it happen is still there.
    POST.mockResolvedValue({
      data: undefined,
      error: { code: "rate_limited", message: "Enough for today." },
      response: { status: 429 },
    });

    renderControl();

    await ask();

    await waitFor(() => expect(document.querySelector("[data-coverage-failed]")).toBeTruthy());
    expect(askButton()).not.toBeDisabled();
  });

  it("shows no confirmation", async () => {
    // **A failure never leaves a false confirmation behind.** "We'll go and look" would
    // be a claim about the world that nothing supports.
    POST.mockResolvedValue({
      data: undefined,
      error: { code: "unknown_home_city", message: "We don't have that city." },
      response: { status: 422 },
    });

    renderControl();

    await ask();

    await waitFor(() => expect(document.querySelector("[data-coverage-failed]")).toBeTruthy());
    expect(document.querySelector("[data-coverage-recorded]")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("can be retried", async () => {
    POST.mockResolvedValue({
      data: undefined,
      error: { code: "rate_limited", message: "Enough for today." },
      response: { status: 429 },
    });

    renderControl();

    await ask();
    await waitFor(() => expect(document.querySelector("[data-coverage-failed]")).toBeTruthy());

    POST.mockResolvedValue({
      data: { city: "Brooklyn", created: true, recorded: true, request_count: 2 },
      response: { status: 201 },
    });
    fireEvent.click(askButton());

    await waitFor(() => expect(POST).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(document.querySelector("[data-coverage-recorded]")).toBeTruthy());
  });
});

describe("a network failure", () => {
  beforeEach(() => {
    POST.mockRejectedValue(new Error("offline"));
  });

  it("shows the offline sentence", async () => {
    // **The one message the frontend owns** — because in this case the API never spoke.
    renderControl();

    await ask();

    await waitFor(() =>
      expect(screen.getByText("Couldn't reach Pulse. Try again.")).toBeInTheDocument(),
    );
  });

  it("shows no confirmation", async () => {
    renderControl();

    await ask();

    await waitFor(() =>
      expect(screen.getByText("Couldn't reach Pulse. Try again.")).toBeInTheDocument(),
    );
    expect(document.querySelector("[data-coverage-recorded]")).toBeNull();
  });

  it("offers the button again", async () => {
    renderControl();

    await ask();

    await waitFor(() =>
      expect(screen.getByText("Couldn't reach Pulse. Try again.")).toBeInTheDocument(),
    );
    expect(askButton()).not.toBeDisabled();
  });
});
