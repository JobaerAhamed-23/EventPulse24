import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PersonalEventsSection } from "@/components/personal-events-section";

/**
 * The server-side read (AD-19).
 *
 * The section reads the user's own events through the generated client and hands them to
 * the client island. The read is a **server** read: the list is rendered from data the
 * server already had, and no `fetch` is used.
 *
 * The property that matters most here is the quiet failure. The section must not be able
 * to fail the build or show an error page — a signed-out visitor, a missing API base URL
 * and a down API all mean the same thing to the caller: no personal events.
 */

const GET = vi.fn();
const apiBaseUrl = vi.fn();
const sessionHeaders = vi.fn();

/** The panel refreshes the route after every successful write; the spy says it did. */
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, replace: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/lib/backend-client", () => ({
  api: { GET: (...args: unknown[]) => GET(...args) },
}));

vi.mock("@/lib/api-base-url", () => ({
  apiBaseUrl: (...args: unknown[]) => apiBaseUrl(...args),
}));

vi.mock("@/lib/session", () => ({
  sessionHeaders: () => sessionHeaders(),
}));

const EVENT = {
  id: "44444444-4444-4444-4444-444444444444",
  name: "Dinner with Rahul",
  start_time_utc: "2026-11-07T00:30:00Z",
  start_time_tz: "America/New_York",
  end_time_utc: null,
  location: null,
  notes: null,
  version: 1,
};

beforeEach(() => {
  GET.mockReset();
  apiBaseUrl.mockReset();
  // A base URL is present by default: the "no base URL" case is the one that opts out.
  apiBaseUrl.mockReturnValue("http://127.0.0.1:8000");
  sessionHeaders.mockReset();
  sessionHeaders.mockResolvedValue({ cookie: "sessionid=abc; csrftoken=tok" });
});

describe("PersonalEventsSection", () => {
  it("reads the user's own events through the generated client", async () => {
    GET.mockResolvedValue({ data: { items: [EVENT] }, error: undefined });

    render(await PersonalEventsSection());

    expect(GET).toHaveBeenCalledWith("/api/personal/events", {
      headers: { cookie: "sessionid=abc; csrftoken=tok" },
    });
    expect(screen.getByText("Dinner with Rahul")).toBeInTheDocument();
  });

  it("carries the visitor's session, so a signed-in user sees their own events", async () => {
    // This read runs on the Next.js server, which has no session of its own. Without the
    // forwarded cookie the API answers 401, the quiet-failure path turns that into an
    // empty list, and a signed-in user is told they have no personal events while the
    // same read from their browser lists them.
    GET.mockResolvedValue({ data: { items: [EVENT] }, error: undefined });

    render(await PersonalEventsSection());

    const [, options] = GET.mock.calls[0];
    expect(options?.headers?.cookie).toBe("sessionid=abc; csrftoken=tok");
  });

  it("shows an empty list rather than an error when the read fails", async () => {
    // A signed-out visitor has no personal events. That is a true statement about them,
    // not a failure worth an error page (AD-12: the personal surface is session-based).
    GET.mockResolvedValue({ data: undefined, error: { code: "unauthorized", message: "no" } });

    render(await PersonalEventsSection());

    expect(screen.getByText("You haven't added any personal events yet.")).toBeInTheDocument();
  });

  it("shows an empty list rather than throwing when the request itself fails", async () => {
    // The API is down. The section's contract says the read fails quietly, so the failure
    // is caught rather than becoming an error page.
    GET.mockRejectedValue(new Error("ECONNREFUSED"));

    render(await PersonalEventsSection());

    expect(screen.getByText("You haven't added any personal events yet.")).toBeInTheDocument();
  });

  it("does not read at all when there is no API base URL to read from", async () => {
    // A build machine, or a deploy with no API_BASE_URL set. Reaching for the API anyway
    // would fail with an invalid-URL error rather than an empty list.
    apiBaseUrl.mockReturnValue(undefined);

    render(await PersonalEventsSection());

    expect(GET).not.toHaveBeenCalled();
    expect(screen.getByText("You haven't added any personal events yet.")).toBeInTheDocument();
  });
});
