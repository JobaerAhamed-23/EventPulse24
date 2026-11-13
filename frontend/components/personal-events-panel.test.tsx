import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
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
const DELETE = vi.fn();

/** The panel refreshes the route after every successful write; the spy says it did. */
const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, replace: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/lib/backend-client", () => ({
  api: {
    POST: (...args: unknown[]) => POST(...args),
    PATCH: (...args: unknown[]) => PATCH(...args),
    DELETE: (...args: unknown[]) => DELETE(...args),
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
      new_side: {
        kind: "personal_event",
        id: "55555555-5555-5555-5555-555555555555",
        name: "Dinner with Rahul",
        start_time_utc: "2026-11-07T00:30:00Z",
        end_time_utc: null,
      },
      other_side: {
        kind: "personal_event",
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
  DELETE.mockReset();
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

/**
 * Fill the create form and submit it.
 *
 * **The sheet is opened by the caller, not by a button in the panel.** The panel's own
 * "Add event" button was deleted with its list branch: every real mount drives the create
 * sheet through `createOpen`, which is what `renderCreate` below does.
 */
async function submitCreate(): Promise<void> {
  fireEvent.change(screen.getByLabelText(/Name/), { target: { value: "Dinner with Rahul" } });
  fireEvent.change(screen.getByLabelText(/^Date/), { target: { value: "2026-11-06" } });
  fireEvent.change(screen.getByLabelText(/Start time/), { target: { value: "19:30" } });
  fireEvent.change(screen.getByLabelText(/Timezone/), { target: { value: "America/New_York" } });
  fireEvent.click(screen.getByRole("button", { name: "Save to my Pulse" }));
}

/**
 * The panel's callers own the sheets' open state, so the harness does too.
 *
 * **A no-op callback cannot close a sheet**, and a test that passed one would assert the
 * sheet stayed open and call it a pass. These wrappers hold the state the sidenav, the
 * digest header and the Timeline each hold in the real app, so "the panel closed the
 * sheet" is observable here exactly as it is there.
 */
function CreateHarness(props: Record<string, unknown>) {
  const [open, setOpen] = useState(true);
  return <PersonalEventsPanel createOpen={open} onCreateOpenChange={setOpen} {...props} />;
}

function EditHarness({ event, ...props }: { event: typeof EVENT } & Record<string, unknown>) {
  const [editingId, setEditingId] = useState<string | null>(event.id);
  return (
    <PersonalEventsPanel
      editingEvents={[event]}
      editingEventId={editingId}
      onEditingEventChange={setEditingId}
      {...props}
    />
  );
}

/** The panel as every real caller mounts it, with the create sheet already open. */
function renderCreate(extra: Record<string, unknown> = {}) {
  return render(<CreateHarness {...extra} />);
}

/** The panel as the Timeline mounts it, with one event open in the edit sheet. */
function renderEditing(event: typeof EVENT, extra: Record<string, unknown> = {}) {
  return render(<EditHarness event={event} {...extra} />);
}

describe("PersonalEventsPanel", () => {
  /**
   * **The list branch and its tests were deleted together.**
   *
   * Six tests lived here — the empty state, the list, the Add button, the `sheetsOnly`
   * switch and the two warm-personal pairing assertions. They covered a branch that
   * nothing in the application rendered: all six mounts of this panel passed
   * `sheetsOnly`, and the `events` prop was supplied only by this file. The tests passed,
   * which is exactly why nobody noticed.
   *
   * The warm-personal pairing (WCAG 1.4.1: colour is never the sole carrier of meaning)
   * is still proven — by the conflict sheet's cards and the Timeline's event blocks,
   * which are surfaces a user can actually reach.
   */

  describe("the create", () => {
    it("posts the body the form produced", async () => {
      POST.mockResolvedValue({ data: EVENT, error: undefined });
      renderCreate();

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
      renderCreate();

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
      renderCreate();

      await submitCreate();

      await waitFor(() =>
        expect(screen.getByText('"Dinner with Rahul" was added.')).toBeInTheDocument(),
      );
      expect(refresh).toHaveBeenCalledTimes(1);
    });

    it("does not refresh when the write failed", async () => {
      POST.mockResolvedValue({ data: undefined, error: { code: "bad_request", message: "no" } });
      renderCreate();

      await submitCreate();

      await waitFor(() => expect(screen.getByText(/couldn't save that/)).toBeInTheDocument());
      expect(refresh).not.toHaveBeenCalled();
    });

    it("refreshes on a 409 too, because the event was written", async () => {
      mockBackend();
      renderCreate();

      await submitCreate();

      await waitFor(() => expect(refresh).toHaveBeenCalled());
    });

    it("does not open the conflict sheet when there is no conflict", async () => {
      POST.mockResolvedValue({ data: EVENT, error: undefined });
      renderCreate();

      await submitCreate();

      await waitFor(() => expect(POST).toHaveBeenCalled());
      expect(screen.queryByRole("dialog", { name: "Schedule conflict" })).not.toBeInTheDocument();
    });

    it("reports a write that failed for another reason", async () => {
      POST.mockResolvedValue({
        data: undefined,
        error: { code: "bad_request", message: "nope" },
      });
      renderCreate();

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
      renderCreate();

      await submitCreate();

      await waitFor(() =>
        expect(screen.getByRole("dialog", { name: "Schedule conflict" })).toBeInTheDocument(),
      );
    });

    it("closes the create form, so there is one sheet at a time", async () => {
      renderCreate();

      await submitCreate();

      await waitFor(() =>
        expect(
          screen.queryByRole("dialog", { name: "Add personal event" }),
        ).not.toBeInTheDocument(),
      );
    });

    it("shows the event the 409 said was written", async () => {
      renderCreate();

      await submitCreate();

      await waitFor(() => expect(screen.getByText("Free tech meetup")).toBeInTheDocument());
    });

    it("posts the chosen resolution with the new side's id", async () => {
      mockBackend();
      renderCreate();

      await submitCreate();
      await waitFor(() =>
        expect(screen.getByRole("dialog", { name: "Schedule conflict" })).toBeInTheDocument(),
      );

      fireEvent.click(screen.getByText("Keep both — I'll manage"));

      await waitFor(() => expect(POST).toHaveBeenCalledTimes(2));
      expect(POST).toHaveBeenLastCalledWith("/api/personal/events/conflicts/{pair_id}/resolve", {
        params: { path: { pair_id: CONFLICT_DETAILS.conflicts[0].pair_id } },
        body: {
          resolution: "keep_both",
          side: { kind: "personal_event", id: CONFLICT_DETAILS.event_id },
        },
      });
    });

    it("closes the prompt once the choice is recorded", async () => {
      renderCreate();

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
      renderCreate();

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
      renderCreate();

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
      renderCreate();

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

  /**
   * The ordinary delete (FR-18) — the edit sheet's danger zone, not the conflict
   * prompt's "delete the new one". It reaches `DELETE /api/personal/events/{event_id}`,
   * which the UI had no caller for at all before this.
   */
  describe("deleting a personal event", () => {
    /** Open the row's edit sheet and press through the danger-zone confirmation. */
    async function confirmDelete(): Promise<void> {
      await waitFor(() =>
        expect(screen.getByRole("dialog", { name: "Edit personal event" })).toBeInTheDocument(),
      );
      fireEvent.click(screen.getByRole("button", { name: "Delete event \u2192" }));
      fireEvent.click(
        screen.getByRole("button", { name: `Delete ${EVENT.name}. This cannot be undone.` }),
      );
    }

    it("deletes the event the sheet is open on, and refreshes the list", async () => {
      DELETE.mockResolvedValue({ data: undefined, error: undefined });
      renderEditing(EVENT);

      await confirmDelete();

      await waitFor(() => expect(DELETE).toHaveBeenCalledTimes(1));
      expect(DELETE).toHaveBeenCalledWith("/api/personal/events/{event_id}", {
        params: { path: { event_id: EVENT.id } },
      });
      await waitFor(() => expect(refresh).toHaveBeenCalled());
      expect(await screen.findByText(`"${EVENT.name}" was deleted.`)).toBeInTheDocument();
      // The sheet is gone: the deletion closed it.
      await waitFor(() =>
        expect(
          screen.queryByRole("dialog", { name: "Edit personal event" }),
        ).not.toBeInTheDocument(),
      );
    });

    it("asks before it deletes — no request leaves on the first press", async () => {
      DELETE.mockResolvedValue({ data: undefined, error: undefined });
      renderEditing(EVENT);

      await waitFor(() =>
        expect(screen.getByRole("dialog", { name: "Edit personal event" })).toBeInTheDocument(),
      );
      fireEvent.click(screen.getByRole("button", { name: "Delete event \u2192" }));

      expect(DELETE).not.toHaveBeenCalled();
    });

    it("keeps the sheet open and says so when the delete is refused", async () => {
      DELETE.mockResolvedValue({
        data: undefined,
        error: { code: "server_error", message: "nope" },
      });
      renderEditing(EVENT);

      await confirmDelete();

      await waitFor(() => expect(DELETE).toHaveBeenCalledTimes(1));
      expect(await screen.findByText("We couldn't delete that. Try again.")).toBeInTheDocument();
      expect(refresh).not.toHaveBeenCalled();
      expect(screen.getByRole("dialog", { name: "Edit personal event" })).toBeInTheDocument();
    });

    it("reports a refused delete to a caller that shows the message itself", async () => {
      DELETE.mockResolvedValue({
        data: undefined,
        error: { code: "server_error", message: "nope" },
      });
      const onFailed = vi.fn();
      renderEditing(EVENT, { onFailed });

      await confirmDelete();

      await waitFor(() =>
        expect(onFailed).toHaveBeenCalledWith("We couldn't delete that. Try again."),
      );
    });

    it("offers no danger zone in the create sheet", async () => {
      renderCreate();

      await waitFor(() =>
        expect(screen.getByRole("dialog", { name: "Add personal event" })).toBeInTheDocument(),
      );

      expect(
        screen.queryByRole("button", { name: "Delete event \u2192" }),
      ).not.toBeInTheDocument();
    });
  });
});
