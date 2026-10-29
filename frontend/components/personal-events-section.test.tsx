import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PersonalEventsSection } from "@/components/personal-events-section";

/**
 * The server-side read (AD-19).
 *
 * The section reads the user's own events through the generated client and hands them to
 * the client island. The read is a **server** read: the list is rendered from data the
 * server already had, and no `fetch` is used.
 */

const GET = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { GET: (...args: unknown[]) => GET(...args) },
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

describe("PersonalEventsSection", () => {
  it("reads the user's own events through the generated client", async () => {
    GET.mockResolvedValue({ data: { items: [EVENT] }, error: undefined });

    render(await PersonalEventsSection());

    expect(GET).toHaveBeenCalledWith("/api/personal/events");
    expect(screen.getByText("Dinner with Rahul")).toBeInTheDocument();
  });

  it("shows an empty list rather than an error when the read fails", async () => {
    // A signed-out visitor has no personal events. That is a true statement about them,
    // not a failure worth an error page (AD-12: the personal surface is session-based).
    GET.mockResolvedValue({ data: undefined, error: { code: "unauthorized", message: "no" } });

    render(await PersonalEventsSection());

    expect(screen.getByText("You haven't added any personal events yet.")).toBeInTheDocument();
  });
});
