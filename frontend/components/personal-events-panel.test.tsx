import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PersonalEventsPanel } from "@/components/personal-events-panel";

/**
 * The panel's round trip (D60–D64).
 *
 * The panel is the only place that knows the flow: a create is a 201 with no conflict,
 * and a **409 means the event was written and a prompt is pending** — not a failed
 * write. So the panel opens the conflict sheet from the 409's `details`, and posts the
 * user's choice to the resolve endpoint with the id the 409 carried.
 */

const POST = vi.fn();
const PATCH = vi.fn();

/** The panel refreshes the route after every successful write; the spy says it did. */
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, replace: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/lib/backend-client", () => ({
  api: {
    POST: (...args: unknown[]) => POST(...args),
    PATCH: (...args: unknown[]) => PATCH(...args),
  },
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

const CONFLICT_DETAILS = {
  event_id: "55555555-5555-5555-5555-555555555555",
  conflicts: [
    {
      pair_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      kind: "time",
      actions: ["keep_both", "edit_new", "delete_new"],
      other: {
        id: "66666666-6666-6666-6666-666666666666",
        name: "Free tech meetup",
        start_time_utc: "2026-11-06T22:30:00Z",
        end_time_utc: "2026-11-06T23:30:00Z",
      },
    },
  ],
};

beforeEach(() => {
  POST.mockReset();
  PATCH.mockReset();
  refresh.mockReset();
});

/**
 * The backend's answer, keyed by the path.
 *
 * The mock answers by **path**, not by call order: the create answers with a 409, and
 * the resolve answers with a success. A mock that answers by order would silently
 * change meaning the moment a second call is added.
 */
function mockBackend(overrides: Record<string, unknown> = {}): void {
  POST.mockImplementation((path: string) => {
    if (path.includes("/resolve")) {
      return Promise.resolve({
        data: { pair_id: CONFLICT_DETAILS.conflicts[0].pair_id, kind: "time" },
        error: undefined,
      });
    }
    return Promise.resolve(
      overrides[path] ?? {
        data: undefined,
        error: {
          code: "scheduling_conflict",
          message: "That overlaps with another event.",
          details: CONFLICT_DETAILS,
        },
      },
    );
  });
}

/** Open the create form, fill it and submit. */
async function submitCreate(): Promise<void> {
  fireEvent.click(screen.getByRole("button", { name: "Add event" }));
  fireEvent.change(screen.getByLabelText(/Name/), { target: { value: "Dinner with Rahul" } });
  fireEvent.change(screen.getByLabelText(/^Date/), { target: { value: "2026-11-06" } });
  fireEvent.change(screen.getByLabelText(/Start time/), { target: { value: "19:30" } });
  fireEvent.change(screen.getByLabelText(/Timezone/), { target: { value: "America/New_York" } });
  fireEvent.click(screen.getByRole("button", { name: "Save to my Pulse" }));
}

describe("PersonalEventsPanel", () => {
  it("says so when there are no personal events", () => {
    render(<PersonalEventsPanel />);

    expect(screen.getByText("You haven't added any personal events yet.")).toBeInTheDocument();
  });

  it("lists the events it is given", () => {
    render(<PersonalEventsPanel events={[EVENT]} />);

    expect(screen.getByText("Dinner with Rahul")).toBeInTheDocument();
  });

  it("draws no Add button of its own when the page already has one", () => {
    render(<PersonalEventsPanel events={[EVENT]} addButton={false} />);

    expect(screen.getByRole("heading", { name: "Your personal events" })).toBeInTheDocument();
    expect(screen.getByText("Dinner with Rahul")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add event" })).toBeNull();
  });

  it("mounts only the sheets when the nav asks for sheetsOnly", () => {
    // The nav's Add needs the round trip, not the panel: the whole panel in the sidenav
    // wedged a headline into the rail, and beside the bottom-tab bar it became a third
    // column that squeezed the mobile page.
    const { container } = render(<PersonalEventsPanel sheetsOnly events={[EVENT]} />);

    expect(screen.queryByRole("heading", { name: "Your personal events" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add event" })).toBeNull();
    expect(screen.queryByText("Dinner with Rahul")).toBeNull();
    expect(container.querySelectorAll("dialog").length).toBeGreaterThan(0);
  });

  describe("the warm-personal pairing", () => {
    it("pairs the stripe with the visible word 'Personal'", () => {
      render(<PersonalEventsPanel events={[EVENT]} />);

      // The stripe is decorative; the word carries the meaning. Colour alone is never
      // the only carrier (WCAG 1.4.1).
      expect(screen.getByText("Personal")).toBeInTheDocument();
    });

    it("uses the warm-personal token for the stripe", () => {
      render(<PersonalEventsPanel events={[EVENT]} />);

      const stripe = screen.getByText("Personal").previousElementSibling;
      expect(stripe).toHaveClass("bg-warm-personal");
    });
  });

  describe("the create", () => {
    it("posts the body the form produced", async () => {
      POST.mockResolvedValue({ data: EVENT, error: undefined });
      render(<PersonalEventsPanel />);

      await submitCreate();

      await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));
      expect(POST).toHaveBeenCalledWith("/api/personal/events", {
        body: {
          name: "Dinner with Rahul",
          start_time_utc: "2026-11-07T00:30:00Z",
          start_time_tz: "America/New_York",
          end_time_utc: null,
          location: null,
          notes: null,
        },
      });
    });

    it("closes the form when there is no conflict", async () => {
      POST.mockResolvedValue({ data: EVENT, error: undefined });
      render(<PersonalEventsPanel />);

      await submitCreate();

      await waitFor(() =>
        expect(
          screen.queryByRole("dialog", { name: "Add personal event" }),
        ).not.toBeInTheDocument(),
      );
    });

    it("says the event was added, and refreshes the page's list", async () => {
      // A saved event used to look like nothing happened: the form closed, and the list
      // was a server read that never re-ran.
      POST.mockResolvedValue({ data: EVENT, error: undefined });
      render(<PersonalEventsPanel />);

      await submitCreate();

      await waitFor(() =>
        expect(screen.getByText('"Dinner with Rahul" was added.')).toBeInTheDocument(),
      );
      expect(refresh).toHaveBeenCalledTimes(1);
    });

    it("does not refresh when the write failed", async () => {
      POST.mockResolvedValue({ data: undefined, error: { code: "bad_request", message: "no" } });
      render(<PersonalEventsPanel />);

      await submitCreate();

      await waitFor(() => expect(screen.getByText(/couldn't save that/)).toBeInTheDocument());
      expect(refresh).not.toHaveBeenCalled();
    });

    it("refreshes on a 409 too, because the event was written", async () => {
      mockBackend();
      render(<PersonalEventsPanel />);

      await submitCreate();

      await waitFor(() => expect(refresh).toHaveBeenCalled());
    });

    it("does not open the conflict sheet when there is no conflict", async () => {
      POST.mockResolvedValue({ data: EVENT, error: undefined });
      render(<PersonalEventsPanel />);

      await submitCreate();

      await waitFor(() => expect(POST).toHaveBeenCalled());
      expect(screen.queryByRole("dialog", { name: "Schedule conflict" })).not.toBeInTheDocument();
    });

    it("reports a write that failed for another reason", async () => {
      POST.mockResolvedValue({
        data: undefined,
        error: { code: "bad_request", message: "nope" },
      });
      render(<PersonalEventsPanel />);

      await submitCreate();

      await waitFor(() =>
        expect(screen.getByText("We couldn't save that. Try again.")).toBeInTheDocument(),
      );
    });
  });

  describe("the 409", () => {
    beforeEach(() => {
      mockBackend();
    });

    it("opens the conflict sheet — the event was written, the prompt is pending", async () => {
      render(<PersonalEventsPanel />);

      await submitCreate();

      await waitFor(() =>
        expect(screen.getByRole("dialog", { name: "Schedule conflict" })).toBeInTheDocument(),
      );
    });

    it("closes the create form, so there is one sheet at a time", async () => {
      render(<PersonalEventsPanel />);

      await submitCreate();

      await waitFor(() =>
        expect(
          screen.queryByRole("dialog", { name: "Add personal event" }),
        ).not.toBeInTheDocument(),
      );
    });

    it("shows the event the 409 said was written", async () => {
      render(<PersonalEventsPanel />);

      await submitCreate();

      await waitFor(() => expect(screen.getByText("Free tech meetup")).toBeInTheDocument());
    });

    it("posts the chosen resolution with the new side's id", async () => {
      mockBackend();
      render(<PersonalEventsPanel />);

      await submitCreate();
      await waitFor(() =>
        expect(screen.getByRole("dialog", { name: "Schedule conflict" })).toBeInTheDocument(),
      );

      fireEvent.click(screen.getByText("Keep both — I'll manage"));

      await waitFor(() => expect(POST).toHaveBeenCalledTimes(2));
      expect(POST).toHaveBeenLastCalledWith("/api/personal/events/conflicts/{pair_id}/resolve", {
        params: { path: { pair_id: CONFLICT_DETAILS.conflicts[0].pair_id } },
        body: { resolution: "keep_both", new_side_id: CONFLICT_DETAILS.event_id },
      });
    });

    it("closes the prompt once the choice is recorded", async () => {
      render(<PersonalEventsPanel />);

      await submitCreate();
      await waitFor(() =>
        expect(screen.getByRole("dialog", { name: "Schedule conflict" })).toBeInTheDocument(),
      );

      fireEvent.click(screen.getByText("Keep both — I'll manage"));

      await waitFor(() =>
        expect(screen.queryByRole("dialog", { name: "Schedule conflict" })).not.toBeInTheDocument(),
      );
    });

    it("reports a resolution that could not be recorded", async () => {
      render(<PersonalEventsPanel />);

      await submitCreate();
      await waitFor(() =>
        expect(screen.getByRole("dialog", { name: "Schedule conflict" })).toBeInTheDocument(),
      );

      POST.mockResolvedValueOnce({
        data: undefined,
        error: { code: "server_error", message: "nope" },
      });
      fireEvent.click(screen.getByText("Keep both — I'll manage"));

      await waitFor(() =>
        expect(screen.getByText("We couldn't record that choice. Try again.")).toBeInTheDocument(),
      );
      // The prompt stays open: the conflict has not been answered.
      expect(screen.getByRole("dialog", { name: "Schedule conflict" })).toBeInTheDocument();
    });
  });

  describe("the edit opened from the prompt", () => {
    it("opens the new event with the start time pre-highlighted", async () => {
      mockBackend();
      render(<PersonalEventsPanel />);

      await submitCreate();
      await waitFor(() =>
        expect(screen.getByRole("dialog", { name: "Schedule conflict" })).toBeInTheDocument(),
      );

      fireEvent.click(screen.getByText("Edit the new one"));

      await waitFor(() =>
        expect(screen.getByRole("dialog", { name: "Edit personal event" })).toBeInTheDocument(),
      );
      expect(
        screen.getByText("This is the time that overlaps. Shift it to fix it."),
      ).toBeInTheDocument();
    });

    it("edits through the PATCH endpoint", async () => {
      PATCH.mockResolvedValue({ data: EVENT, error: undefined });
      mockBackend();
      render(<PersonalEventsPanel />);

      await submitCreate();
      await waitFor(() =>
        expect(screen.getByRole("dialog", { name: "Schedule conflict" })).toBeInTheDocument(),
      );

      fireEvent.click(screen.getByText("Edit the new one"));
      await waitFor(() =>
        expect(screen.getByRole("dialog", { name: "Edit personal event" })).toBeInTheDocument(),
      );

      fireEvent.click(screen.getByRole("button", { name: "Save event" }));

      await waitFor(() => expect(PATCH).toHaveBeenCalledTimes(1));
      expect(PATCH).toHaveBeenCalledWith(
        "/api/personal/events/{event_id}",
        expect.objectContaining({
          params: { path: { event_id: CONFLICT_DETAILS.event_id } },
        }),
      );
    });
  });
});
