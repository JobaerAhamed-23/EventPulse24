import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SavedEventsSection } from "@/components/saved-events-section";

/**
 * The saved-events read on the home.
 *
 * Like the personal read beside it, this runs on the Next.js server and must carry the
 * visitor's cookies — without them Django sees an anonymous client, answers 401, and the
 * section quietly shows "nothing saved" to someone who has saved things.
 */

const GET = vi.fn();
const apiBaseUrl = vi.fn();
const sessionHeaders = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { GET: (...args: unknown[]) => GET(...args) },
}));

vi.mock("@/lib/api-base-url", () => ({
  apiBaseUrl: (...args: unknown[]) => apiBaseUrl(...args),
}));

vi.mock("@/lib/session", () => ({
  sessionHeaders: () => sessionHeaders(),
}));

const SAVED = {
  id: "55555555-5555-5555-5555-555555555555",
  event_id: "66666666-6666-6666-6666-666666666666",
  title: "Brooklyn Night Market",
  canonical_url: "https://example.test/events/night-market",
  start_time_utc: "2026-11-07T23:00:00Z",
  start_time_tz: "America/New_York",
  end_time_utc: null,
  venue_name: "Industry City",
  venue_city: "Brooklyn",
  event_version: 3,
  current_version: 3,
  stale: false,
};

beforeEach(() => {
  GET.mockReset();
  apiBaseUrl.mockReset();
  sessionHeaders.mockReset();
  apiBaseUrl.mockReturnValue("http://127.0.0.1:8000");
  sessionHeaders.mockResolvedValue({ cookie: "sessionid=abc" });
});

describe("SavedEventsSection", () => {
  it("reads the saved events with the visitor's session", async () => {
    GET.mockResolvedValue({ data: { items: [SAVED], omitted: 0 }, error: undefined });

    render(await SavedEventsSection());

    expect(GET).toHaveBeenCalledWith("/api/personal/saved-events", {
      headers: { cookie: "sessionid=abc" },
    });
    expect(screen.getByText("Brooklyn Night Market")).toBeInTheDocument();
  });

  it("shows the local date, time and city", async () => {
    GET.mockResolvedValue({ data: { items: [SAVED], omitted: 0 }, error: undefined });

    render(await SavedEventsSection());

    // 23:00 UTC is 18:00 in New York on that date.
    expect(screen.getByText("2026-11-07 · 18:00 · Brooklyn")).toBeInTheDocument();
  });

  it("pairs the stripe colour with a visible label, so colour is never the only signal", async () => {
    GET.mockResolvedValue({ data: { items: [SAVED], omitted: 0 }, error: undefined });

    render(await SavedEventsSection());

    expect(screen.getByText("Saved")).toBeInTheDocument();
  });

  it("says how many saves are no longer available, rather than dropping them silently", async () => {
    // The API counts them for exactly this reason: their catalog event is gone, so there
    // is no title to list, but the user should still know something of theirs vanished.
    GET.mockResolvedValue({ data: { items: [SAVED], omitted: 2 }, error: undefined });

    render(await SavedEventsSection());

    expect(screen.getByText("2 saved events are no longer available.")).toBeInTheDocument();
  });

  it("says it in the singular for one", async () => {
    GET.mockResolvedValue({ data: { items: [SAVED], omitted: 1 }, error: undefined });

    render(await SavedEventsSection());

    expect(screen.getByText("1 saved event is no longer available.")).toBeInTheDocument();
  });

  it("says nothing about omissions when there are none", async () => {
    GET.mockResolvedValue({ data: { items: [SAVED], omitted: 0 }, error: undefined });

    render(await SavedEventsSection());

    expect(screen.queryByText(/no longer available/)).toBeNull();
  });

  it("says so plainly when nothing is saved", async () => {
    GET.mockResolvedValue({ data: { items: [], omitted: 0 }, error: undefined });

    render(await SavedEventsSection());

    expect(screen.getByText("You haven't saved any events yet.")).toBeInTheDocument();
  });

  it("shows an empty list rather than an error when the read fails", async () => {
    GET.mockResolvedValue({ data: undefined, error: { code: "x", message: "y" } });

    render(await SavedEventsSection());

    expect(screen.getByText("You haven't saved any events yet.")).toBeInTheDocument();
  });

  it("asks nothing when there is no API base URL, so the build never needs a live API", async () => {
    apiBaseUrl.mockReturnValue(undefined);

    render(await SavedEventsSection());

    expect(GET).not.toHaveBeenCalled();
    expect(screen.getByText("You haven't saved any events yet.")).toBeInTheDocument();
  });

  it("survives a thrown request", async () => {
    GET.mockRejectedValue(new Error("connect ECONNREFUSED"));

    render(await SavedEventsSection());

    expect(screen.getByText("You haven't saved any events yet.")).toBeInTheDocument();
  });
});
