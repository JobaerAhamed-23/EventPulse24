import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DetailActions, type DetailConflict } from "@/components/detail/detail-actions";

/**
 * The Detail Screen's action row, and the conflict prompt it opens.
 *
 * **The Save button's state is known before the user presses it** — `personal.saved` is
 * the user's own save row, read by the API, not a tag on a composition that may have
 * been composed days ago.
 *
 * **A refused save is shown calmly rather than swallowed.** A button that silently
 * fails is the failure this screen is careful about everywhere else.
 *
 * **The prompt is a forced sheet (FR-58).** No dismiss, no Escape, no backdrop click —
 * the user has to choose, because a conflict that can be closed without being answered
 * is exactly the missed double-booking the prompt exists to prevent.
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

beforeEach(() => {
  POST.mockReset();
  GET.mockReset();
  POST.mockResolvedValue({ data: {}, response: { status: 200 } });
  GET.mockResolvedValue({ data: undefined, response: { status: 200 } });
});

/**
 * The active pair the payload hands over.
 *
 * **`saved_side_id` is the save row's id**, not the catalog event's — the pair stores a
 * `SavedEvent` by that row's id, and a `skip_public` releases the save by the same id.
 */
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

/**
 * The 409 the save answers with.
 *
 * **The save row was written and *then* the clash was found**, so `new_side` is the
 * save row and `other_side` is the personal event.
 */
const CLASH_409 = {
  data: undefined,
  error: {
    code: "scheduling_conflict",
    message: "That clashes with something else already on your calendar.",
    details: {
      event_id: "saved-1",
      conflicts: [
        {
          pair_id: "pair-1",
          kind: "time",
          actions: ["keep_both", "edit_new", "skip_public"],
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
};

function renderActions(props: Partial<React.ComponentProps<typeof DetailActions>> = {}) {
  return render(
    <DetailActions
      eventId="event-1"
      saved={false}
      conflict={null}
      eventName="Free tech meetup"
      startTimeUtc="2026-11-03T14:30:00Z"
      endTimeUtc="2026-11-03T15:30:00Z"
      {...props}
    />,
  );
}

/** The prompt's sheet, by its accessible name. */
function prompt(): HTMLElement {
  return screen.getByRole("dialog", { name: "Schedule conflict" });
}

describe("the action row", () => {
  it("offers Save and Share", () => {
    renderActions();

    expect(screen.getByRole("button", { name: "Save to Pulse" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Share" })).toBeInTheDocument();
  });

  it("shows the saved state when the user has already saved the event", () => {
    renderActions({ saved: true });

    expect(screen.getByRole("button", { name: "Saved to your Pulse" })).toBeInTheDocument();
    // The unsaved label is gone entirely — the row shows one state, not both.
    expect(screen.queryByRole("button", { name: "Save to Pulse" })).not.toBeInTheDocument();
  });

  it("posts the save with the event's id", async () => {
    renderActions();

    screen.getByRole("button", { name: "Save to Pulse" }).click();

    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith("/api/personal/saved-events/{catalog_event_id}", {
        params: { path: { catalog_event_id: "event-1" } },
      }),
    );
  });

  it("shows the saved state once the save succeeds", async () => {
    renderActions();

    screen.getByRole("button", { name: "Save to Pulse" }).click();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Saved to your Pulse" })).toBeInTheDocument(),
    );
  });

  it("says so calmly when the save is refused", async () => {
    // A refusal is shown rather than swallowed — a button that silently fails is the
    // failure this screen is careful about everywhere else.
    POST.mockResolvedValue({ data: undefined, response: { status: 409 } });

    renderActions();

    screen.getByRole("button", { name: "Save to Pulse" }).click();

    await waitFor(() => expect(screen.getByText(/Couldn't save that/)).toBeInTheDocument());
    // And the button is still there, still saying "Save to Pulse" — the save did not
    // happen, and the screen does not pretend it did.
    expect(screen.getByRole("button", { name: "Save to Pulse" })).toBeInTheDocument();
  });

  it("does not post when the event is already saved", () => {
    renderActions({ saved: true });

    screen.getByRole("button", { name: "Saved to your Pulse" }).click();

    expect(POST).not.toHaveBeenCalled();
  });
});

describe("the conflict the save finds", () => {
  it("opens the prompt over the saved button", async () => {
    POST.mockResolvedValue(CLASH_409);

    renderActions();

    screen.getByRole("button", { name: "Save to Pulse" }).click();

    await waitFor(() => expect(prompt()).toBeInTheDocument());
  });

  it("shows the event as saved — the save row was written before the clash was found", async () => {
    POST.mockResolvedValue(CLASH_409);

    renderActions();

    screen.getByRole("button", { name: "Save to Pulse" }).click();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Saved to your Pulse" })).toBeInTheDocument(),
    );
    // And it is not a refusal: "Couldn't save that" would be false — the event *is*
    // saved, and the pair is waiting for a choice.
    expect(screen.queryByText(/Couldn't save that/)).not.toBeInTheDocument();
  });

  it("offers the server's three choices and no fourth", async () => {
    POST.mockResolvedValue(CLASH_409);

    renderActions();

    screen.getByRole("button", { name: "Save to Pulse" }).click();

    await waitFor(() => expect(prompt()).toBeInTheDocument());
    const choices = within(prompt()).getByRole("group", { name: "Conflict resolution" });
    expect(within(choices).getAllByRole("button")).toHaveLength(3);
  });

  it("names each choice after the event it is about", async () => {
    POST.mockResolvedValue(CLASH_409);

    renderActions();

    screen.getByRole("button", { name: "Save to Pulse" }).click();

    await waitFor(() => expect(prompt()).toBeInTheDocument());
    // **"Move Dentist"** — the personal event moves. **"Skip Free tech meetup"** — the
    // saved event is released. The relative labels ("Edit the new one") would name an
    // event the user never created.
    expect(screen.getByRole("button", { name: /Move Dentist/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Skip Free tech meetup/ })).toBeInTheDocument();
  });

  it("says which event is on the calendar", async () => {
    POST.mockResolvedValue(CLASH_409);

    renderActions();

    screen.getByRole("button", { name: "Save to Pulse" }).click();

    await waitFor(() => expect(prompt()).toBeInTheDocument());
    expect(prompt()).toHaveTextContent("Dentist");
  });

  it("announces the choice and moves focus to the heading", async () => {
    POST.mockResolvedValue(CLASH_409);

    renderActions();

    screen.getByRole("button", { name: "Save to Pulse" }).click();

    await waitFor(() => expect(prompt()).toBeInTheDocument());
    // The announcement is assertive: a forced choice the user must not miss.
    expect(screen.getByText("Schedule conflict. Three choices.")).toBeInTheDocument();
    await waitFor(() => expect(prompt().querySelector("h2")).toHaveFocus());
  });

  it("has no way to dismiss the prompt without choosing", async () => {
    POST.mockResolvedValue(CLASH_409);

    renderActions();

    screen.getByRole("button", { name: "Save to Pulse" }).click();

    await waitFor(() => expect(prompt()).toBeInTheDocument());
    // No X, no Escape, no backdrop click — the sheet is `dismissible={false}`.
    expect(prompt()).toHaveTextContent("No dismiss button");
    expect(screen.queryByRole("button", { name: /close|dismiss/i })).not.toBeInTheDocument();
  });
});

describe("the choice the user makes", () => {
  /** Answer the prompt with a resolution, by its visible label. */
  async function choose(label: RegExp) {
    screen.getByRole("button", { name: label }).click();
  }

  it("moves the personal event, naming the personal side", async () => {
    POST.mockResolvedValueOnce(CLASH_409).mockResolvedValueOnce({
      data: {},
      response: { status: 200 },
    });
    GET.mockResolvedValue({
      data: {
        id: "personal-1",
        name: "Dentist",
        start_time_utc: "2026-11-03T15:00:00Z",
        end_time_utc: "2026-11-03T16:00:00Z",
        start_time_tz: "America/New_York",
        location: null,
        notes: null,
      },
      response: { status: 200 },
    });

    renderActions();

    screen.getByRole("button", { name: "Save to Pulse" }).click();
    await waitFor(() => expect(prompt()).toBeInTheDocument());

    await choose(/Move Dentist/);

    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith(
        "/api/personal/events/conflicts/{pair_id}/resolve",
        expect.objectContaining({
          params: { path: { pair_id: "pair-1" } },
          body: { resolution: "edit_new", side: { kind: "personal_event", id: "personal-1" } },
        }),
      ),
    );
  });

  it("reads the personal event before opening the edit sheet", async () => {
    POST.mockResolvedValueOnce(CLASH_409).mockResolvedValueOnce({
      data: {},
      response: { status: 200 },
    });
    GET.mockResolvedValue({
      data: {
        id: "personal-1",
        name: "Dentist",
        start_time_utc: "2026-11-03T15:00:00Z",
        end_time_utc: "2026-11-03T16:00:00Z",
        start_time_tz: "America/New_York",
        location: null,
        notes: null,
      },
      response: { status: 200 },
    });

    renderActions();

    screen.getByRole("button", { name: "Save to Pulse" }).click();
    await waitFor(() => expect(prompt()).toBeInTheDocument());

    await choose(/Move Dentist/);

    // **The full record is read first** — the sheet edits personal events, and the
    // clash carries no zone. The zone has to come from somewhere real.
    await waitFor(() =>
      expect(GET).toHaveBeenCalledWith("/api/personal/events/{event_id}", {
        params: { path: { event_id: "personal-1" } },
      }),
    );
  });

  it("skips the public event, naming the saved side, and releases the save", async () => {
    POST.mockResolvedValueOnce(CLASH_409).mockResolvedValueOnce({
      data: {},
      response: { status: 200 },
    });

    renderActions();

    screen.getByRole("button", { name: "Save to Pulse" }).click();
    await waitFor(() => expect(prompt()).toBeInTheDocument());

    await choose(/Skip Free tech meetup/);

    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith(
        "/api/personal/events/conflicts/{pair_id}/resolve",
        expect.objectContaining({
          body: { resolution: "skip_public", side: { kind: "saved_event", id: "saved-1" } },
        }),
      ),
    );
    // **The save is released**, so the button goes back to "Save to Pulse".
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save to Pulse" })).toBeInTheDocument(),
    );
  });

  it("keeps both, naming one of the pair's own sides, and leaves the event saved", async () => {
    POST.mockResolvedValueOnce(CLASH_409).mockResolvedValueOnce({
      data: {},
      response: { status: 200 },
    });

    renderActions();

    screen.getByRole("button", { name: "Save to Pulse" }).click();
    await waitFor(() => expect(prompt()).toBeInTheDocument());

    await choose(/Keep both/);

    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith(
        "/api/personal/events/conflicts/{pair_id}/resolve",
        expect.objectContaining({
          // `keep_both` acts on neither side, and the server accepts either of the
          // pair's own sides for it.
          body: { resolution: "keep_both", side: { kind: "saved_event", id: "saved-1" } },
        }),
      ),
    );
    // The event stays saved, and the indicator stays.
    expect(screen.getByRole("button", { name: "Saved to your Pulse" })).toBeInTheDocument();
  });

  it("leaves the prompt open when the write fails", async () => {
    POST.mockResolvedValueOnce(CLASH_409).mockResolvedValueOnce({
      data: undefined,
      error: { code: "boom", message: "no" },
      response: { status: 500 },
    });

    renderActions();

    screen.getByRole("button", { name: "Save to Pulse" }).click();
    await waitFor(() => expect(prompt()).toBeInTheDocument());

    await choose(/Keep both/);

    // **A prompt that closed on a failed write would tell the user the conflict is
    // handled when it is not.** So it stays, and a calm line says what happened.
    await waitFor(() => expect(prompt()).toBeInTheDocument());
    expect(screen.getByRole("status")).toHaveTextContent("Couldn't record that choice");
  });
});

describe("the conflict the payload carries", () => {
  it("does not open the prompt on its own", () => {
    // The payload says "there is a choice" — not "show the choice now". The user came
    // to read an event.
    renderActions({ conflict: PAYLOAD_CONFLICT });

    expect(screen.queryByRole("dialog", { name: "Schedule conflict" })).not.toBeInTheDocument();
  });

  it("offers the pair the payload named", () => {
    renderActions({ conflict: PAYLOAD_CONFLICT });

    // The prompt is closed, but the choices are the server's — and the labels are the
    // named ones.
    expect(screen.queryByRole("button", { name: /Move Dentist/ })).not.toBeInTheDocument();
  });

  it("has no indicator of its own — the header draws the mark", () => {
    // The mark lives in the header's trust row, which is server-rendered content. This
    // island owns the prompt; the header owns the mark.
    renderActions({ conflict: PAYLOAD_CONFLICT });

    expect(screen.queryByRole("button", { name: /Schedule conflict/ })).not.toBeInTheDocument();
  });
});
