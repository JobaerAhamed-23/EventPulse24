import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DetailActions } from "@/components/detail/detail-actions";

/**
 * The Detail Screen's action row.
 *
 * **The Save button's state is known before the user presses it** — `personal.saved` is
 * the user's own save row, read by the API, not a tag on a composition that may have
 * been composed days ago.
 *
 * **A refused save is shown calmly rather than swallowed.** A button that silently
 * fails is the failure this screen is careful about everywhere else.
 */
const POST = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { POST: (...args: unknown[]) => POST(...args) },
}));

beforeEach(() => {
  POST.mockReset();
  POST.mockResolvedValue({ data: {}, response: { status: 200 } });
});

describe("the action row", () => {
  it("offers Save and Share", () => {
    render(<DetailActions eventId="event-1" saved={false} />);

    expect(screen.getByRole("button", { name: "Save to Pulse" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Share" })).toBeInTheDocument();
  });

  it("shows the saved state when the user has already saved the event", () => {
    render(<DetailActions eventId="event-1" saved />);

    expect(screen.getByRole("button", { name: "Saved to your Pulse" })).toBeInTheDocument();
    // The unsaved label is gone entirely — the row shows one state, not both.
    expect(screen.queryByRole("button", { name: "Save to Pulse" })).not.toBeInTheDocument();
  });

  it("posts the save with the event's id", async () => {
    render(<DetailActions eventId="event-1" saved={false} />);

    screen.getByRole("button", { name: "Save to Pulse" }).click();

    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith("/api/personal/saved-events/{catalog_event_id}", {
        params: { path: { catalog_event_id: "event-1" } },
      }),
    );
  });

  it("shows the saved state once the save succeeds", async () => {
    render(<DetailActions eventId="event-1" saved={false} />);

    screen.getByRole("button", { name: "Save to Pulse" }).click();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Saved to your Pulse" })).toBeInTheDocument(),
    );
  });

  it("says so calmly when the save is refused", async () => {
    // A refusal is shown rather than swallowed — a button that silently fails is the
    // failure this screen is careful about everywhere else.
    POST.mockResolvedValue({ data: undefined, response: { status: 409 } });

    render(<DetailActions eventId="event-1" saved={false} />);

    screen.getByRole("button", { name: "Save to Pulse" }).click();

    await waitFor(() => expect(screen.getByText(/Couldn't save that/)).toBeInTheDocument());
    // And the button is still there, still saying "Save to Pulse" — the save did not
    // happen, and the screen does not pretend it did.
    expect(screen.getByRole("button", { name: "Save to Pulse" })).toBeInTheDocument();
  });

  it("shows a clashing save as saved, and names the overlap", async () => {
    // The real API's 409 for a save: the save row was written, then the clash was found.
    // "Couldn't save that" would be false — the event is saved.
    POST.mockResolvedValue({
      data: undefined,
      error: {
        code: "scheduling_conflict",
        message: "That clashes with something else already on your calendar.",
        details: {
          event_id: "saved-1",
          conflicts: [
            {
              pair_id: "pair-1",
              kind: "overlap",
              actions: ["delete_new", "edit_new", "keep_both"],
              new_side: {
                kind: "saved_event",
                id: "saved-1",
                name: "Free tech meetup",
                start_time_utc: "2026-11-03T14:30:00Z",
                end_time_utc: "2026-11-03T15:30:00Z",
              },
              other_side: {
                kind: "personal_event",
                id: "personal-1",
                name: "Dentist",
                start_time_utc: "2026-11-03T15:00:00Z",
                end_time_utc: "2026-11-03T16:00:00Z",
              },
            },
          ],
        },
      },
      response: { status: 409 },
    });

    render(<DetailActions eventId="event-1" saved={false} />);

    screen.getByRole("button", { name: "Save to Pulse" }).click();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Saved to your Pulse" })).toBeInTheDocument(),
    );
    expect(screen.getByRole("status")).toHaveTextContent("It overlaps “Dentist” on your calendar.");
    expect(screen.queryByText(/Couldn't save that/)).not.toBeInTheDocument();
  });

  it("does not post when the event is already saved", () => {
    render(<DetailActions eventId="event-1" saved />);

    screen.getByRole("button", { name: "Saved to your Pulse" }).click();

    expect(POST).not.toHaveBeenCalled();
  });
});
