import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DetailActions, type DetailConflict } from "@/components/detail/detail-actions";
import { DetailConflictMark } from "@/components/conflicts/detail-conflict-mark";

/**
 * The mark in the header, and the prompt in the action row — **across the island
 * boundary**.
 *
 * **The header is server-rendered content and the prompt lives in a client island.**
 * The title, the times and the badges are facts the server decided (AD-10), and the
 * prompt is a sheet that has to be inside an island that owns a write. So the mark
 * *announces* the open and the island *listens* — see `lib/conflict-open.ts`.
 *
 * **This is the whole point of the file.** A test that renders the mark alone proves
 * the button exists; a test that renders the island alone proves the prompt opens.
 * Only rendering both proves the user can get from the mark to the prompt, which is
 * the journey the mark exists for.
 */
const POST = vi.fn();
const GET = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    POST: (...args: unknown[]) => POST(...args),
    GET: (...args: unknown[]) => GET(...args),
  },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));

const PAYLOAD_CONFLICT: DetailConflict = {
  pair_id: "pair-1",
  kind: "time",
  saved_side_id: "saved-1",
  other_side: {
    kind: "personal_event",
    id: "personal-1",
    name: "Dentist",
    start_time_utc: "2026-11-03T15:00:00Z",
    end_time_utc: "2026-11-03T16:00:00Z",
  },
  actions: ["keep_both", "edit_new", "skip_public"],
};

beforeEach(() => {
  POST.mockReset();
  GET.mockReset();
  POST.mockResolvedValue({ data: {}, response: { status: 200 } });
  GET.mockResolvedValue({ data: undefined, response: { status: 200 } });
});

/** The header's mark and the action row's island, on one page. */
function renderScreen() {
  return render(
    <>
      <DetailConflictMark eventId="event-1" />
      <DetailActions
        eventId="event-1"
        saved
        conflict={PAYLOAD_CONFLICT}
        eventName="Free tech meetup"
        startTimeUtc="2026-11-03T14:30:00Z"
        endTimeUtc="2026-11-03T15:30:00Z"
      />
    </>,
  );
}

describe("the mark and the prompt", () => {
  it("opens the prompt when the mark is pressed", async () => {
    renderScreen();

    expect(screen.queryByRole("dialog", { name: "Schedule conflict" })).not.toBeInTheDocument();

    screen.getByRole("button", { name: "Schedule conflict. Choose how to handle it." }).click();

    await waitFor(() =>
      expect(screen.getByRole("dialog", { name: "Schedule conflict" })).toBeInTheDocument(),
    );
  });

  it("offers the payload's own choices, named after the events", async () => {
    renderScreen();

    screen.getByRole("button", { name: "Schedule conflict. Choose how to handle it." }).click();

    await waitFor(() =>
      expect(screen.getByRole("dialog", { name: "Schedule conflict" })).toBeInTheDocument(),
    );
    // **The payload's pair** — the saved side is the event on screen, and the other side
    // is the user's own personal event.
    expect(screen.getByRole("button", { name: /Move Dentist/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Skip Free tech meetup/ })).toBeInTheDocument();
  });

  it("ignores a mark for a different event", async () => {
    render(
      <>
        <DetailConflictMark eventId="event-2" />
        <DetailActions
          eventId="event-1"
          saved
          conflict={PAYLOAD_CONFLICT}
          eventName="Free tech meetup"
          startTimeUtc="2026-11-03T14:30:00Z"
          endTimeUtc="2026-11-03T15:30:00Z"
        />
      </>,
    );

    screen.getByRole("button", { name: "Schedule conflict. Choose how to handle it." }).click();

    // The signal carries the event's id, so an island for another event ignores it.
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Schedule conflict" })).not.toBeInTheDocument(),
    );
  });

  it("stops listening when the island unmounts", async () => {
    const { unmount } = renderScreen();

    unmount();

    // A listener left behind would open a prompt for an event that is no longer on
    // screen. Nothing throws, and nothing opens.
    expect(() => {
      window.dispatchEvent(
        new CustomEvent("eventpulse:detail-conflict-open", {
          detail: { eventId: "event-1" },
        }),
      );
    }).not.toThrow();
    expect(screen.queryByRole("dialog", { name: "Schedule conflict" })).not.toBeInTheDocument();
  });
});
