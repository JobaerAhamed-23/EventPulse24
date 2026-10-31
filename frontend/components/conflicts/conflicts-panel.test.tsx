import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConflictsPanel } from "@/components/conflicts/conflicts-panel";
import type { ConflictPair } from "@/lib/conflict-list-read";

/**
 * The Conflict Review screen's decisions.
 *
 * **The request has to name the side.** The pair row stores its two sides sorted, so
 * the row cannot say which side the user is acting on — the request has to
 * (`ConflictResolutionIn.side`). So the tests here pin *both* halves of every post: the
 * resolution, and the side it acts on. A post with the right resolution and the wrong
 * side would delete a personal event when the user meant to release a save.
 *
 * **A failed choice leaves the pair where it was.** The pair stays Active, its buttons
 * come back, and a calm line says what happened. A pair that vanished on a failed write
 * would be a lie about the user's schedule.
 */

const POST = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, replace: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/lib/backend-client", () => ({
  api: { POST: (...args: unknown[]) => POST(...args) },
}));

const PERSONAL_ID = "11111111-1111-1111-1111-111111111111";
const SAVED_ID = "22222222-2222-2222-2222-222222222222";
const PAIR_ID = "44444444-4444-4444-4444-444444444444";

function personalSide(overrides: Record<string, unknown> = {}) {
  return {
    available: true,
    end_time_utc: null,
    id: PERSONAL_ID,
    kind: "personal_event",
    name: "Work standup",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-09-08T13:00:00Z",
    ...overrides,
  };
}

function savedSide(overrides: Record<string, unknown> = {}) {
  return {
    available: true,
    end_time_utc: null,
    id: SAVED_ID,
    kind: "saved_event",
    name: "Designers coffee chat",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-09-08T13:15:00Z",
    ...overrides,
  };
}

function pair(overrides: Partial<ConflictPair> = {}): ConflictPair {
  return {
    actions: ["keep_both", "edit_new", "skip_public"],
    kind: "time",
    left: personalSide(),
    pair_id: PAIR_ID,
    right: savedSide(),
    status: "active",
    ...overrides,
  } as ConflictPair;
}

function resolvedPair(overrides: Partial<ConflictPair> = {}): ConflictPair {
  return {
    actions: [],
    kind: "time",
    left: personalSide(),
    pair_id: "55555555-5555-5555-5555-555555555555",
    resolution: "skip_public",
    resolved_at: "2026-09-11T23:00:00Z",
    right: savedSide(),
    status: "resolved",
    ...overrides,
  } as ConflictPair;
}

/** The body of the one POST the panel made. */
function posted(): { resolution: string; side: { kind: string; id: string } } {
  const [, options] = POST.mock.calls[0] as [
    string,
    {
      params: { path: { pair_id: string } };
      body: { resolution: string; side: { kind: string; id: string } };
    },
  ];
  return options.body;
}

/** The pair id the one POST named. */
function postedPairId(): string {
  const [, options] = POST.mock.calls[0] as [string, { params: { path: { pair_id: string } } }];
  return options.params.path.pair_id;
}

beforeEach(() => {
  POST.mockReset();
  refresh.mockReset();
  POST.mockResolvedValue({ data: {}, error: undefined, response: new Response(null) });
});

afterEach(() => {
  cleanup();
});

describe("the active section", () => {
  it("shows both sides, each with its name and its own kind label", () => {
    render(<ConflictsPanel active={[pair()]} resolved={[]} />);

    const article = screen.getByRole("article");
    expect(within(article).getByText("Work standup")).toBeInTheDocument();
    expect(within(article).getByText("Designers coffee chat")).toBeInTheDocument();
    expect(within(article).getByText("Personal")).toBeInTheDocument();
    expect(within(article).getByText("Public event")).toBeInTheDocument();
  });

  it("offers exactly the actions the API allowed", () => {
    render(
      <ConflictsPanel active={[pair({ actions: ["keep_both", "skip_public"] })]} resolved={[]} />,
    );

    const group = screen.getByRole("group", { name: /Choices for the conflict/ });
    const buttons = within(group).getAllByRole("button");
    expect(buttons).toHaveLength(2);
    // The API did not allow a move, so none is offered.
    expect(within(group).queryByText(/^Move /)).toBeNull();
  });

  it("words the actions the way FR-33 does", () => {
    render(<ConflictsPanel active={[pair()]} resolved={[]} />);

    expect(screen.getByText("Move Work standup")).toBeInTheDocument();
    expect(screen.getByText("Skip Designers coffee chat")).toBeInTheDocument();
    expect(screen.getByText("Keep both — I'll manage")).toBeInTheDocument();
  });
});

describe("choosing an action", () => {
  it("posts a move against the personal side", async () => {
    render(<ConflictsPanel active={[pair()]} resolved={[]} />);

    fireEvent.click(screen.getByRole("button", { name: /Move Work standup/ }));

    await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));
    expect(posted().resolution).toBe("edit_new");
    expect(posted().side).toEqual({ kind: "personal_event", id: PERSONAL_ID });
    expect(postedPairId()).toBe(PAIR_ID);
  });

  it("posts a skip against the saved side", async () => {
    // The whole point of the side: a skip releases a *save*, and it must not be able to
    // delete the user's own event by naming it.
    render(<ConflictsPanel active={[pair()]} resolved={[]} />);

    fireEvent.click(screen.getByRole("button", { name: /Skip Designers coffee chat/ }));

    await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));
    expect(posted().resolution).toBe("skip_public");
    expect(posted().side).toEqual({ kind: "saved_event", id: SAVED_ID });
  });

  it("posts a keep-both", async () => {
    render(<ConflictsPanel active={[pair()]} resolved={[]} />);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Keep both events. The conflict indicator remains on both.",
      }),
    );

    await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));
    expect(posted().resolution).toBe("keep_both");
  });

  it("posts a keep-both against one of the pair's own sides", async () => {
    // The server accepts *either* of the pair's sides for `keep_both` — it is about
    // neither side — but it still requires a side, and the side named must be one of
    // the pair's own.
    render(<ConflictsPanel active={[pair()]} resolved={[]} />);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Keep both events. The conflict indicator remains on both.",
      }),
    );

    await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));
    expect([
      { kind: "personal_event", id: PERSONAL_ID },
      { kind: "saved_event", id: SAVED_ID },
    ]).toContainEqual(posted().side);
  });

  it("re-reads the page after a success", async () => {
    render(<ConflictsPanel active={[pair()]} resolved={[]} />);

    fireEvent.click(screen.getByRole("button", { name: /Skip Designers coffee chat/ }));

    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("does not re-read the page when the write failed", async () => {
    POST.mockResolvedValue({
      data: undefined,
      error: { code: "invalid_resolution", message: "That choice is not allowed." },
      response: new Response(null, { status: 422 }),
    });
    render(<ConflictsPanel active={[pair()]} resolved={[]} />);

    fireEvent.click(screen.getByRole("button", { name: /Skip Designers coffee chat/ }));

    await waitFor(() =>
      expect(screen.getByText("Couldn't record that choice. Try again.")).toBeInTheDocument(),
    );
    expect(refresh).not.toHaveBeenCalled();
  });
});

describe("a failed choice", () => {
  it("leaves the pair active, with its buttons still there", async () => {
    POST.mockResolvedValue({
      data: undefined,
      error: { code: "invalid_resolution", message: "That choice is not allowed." },
      response: new Response(null, { status: 422 }),
    });
    render(<ConflictsPanel active={[pair()]} resolved={[]} />);

    fireEvent.click(screen.getByRole("button", { name: /Skip Designers coffee chat/ }));

    await waitFor(() =>
      expect(screen.getByText("Couldn't record that choice. Try again.")).toBeInTheDocument(),
    );
    // The pair is still there, and its actions are still offered.
    expect(screen.getByRole("article")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Move Work standup/ })).toBeEnabled();
  });
});

describe("a move", () => {
  it("opens the personal side in the edit sheet", async () => {
    render(<ConflictsPanel active={[pair()]} resolved={[]} />);

    // The sheet is a native `<dialog>` — closed it takes no space.
    expect(document.querySelector("dialog")?.open).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: /Move Work standup/ }));

    await waitFor(() => expect(document.querySelector("dialog")?.open).toBe(true));

    // The sheet opened on the **personal** side — the name field carries it, and the
    // name is an input's value, not the dialog's text.
    const nameField = within(document.querySelector("dialog") as HTMLElement).getByLabelText(
      /^Name/,
    ) as HTMLInputElement;
    expect(nameField.value).toBe("Work standup");
  });

  it("opens the sheet with the conflicting time highlighted", async () => {
    render(<ConflictsPanel active={[pair()]} resolved={[]} />);

    fireEvent.click(screen.getByRole("button", { name: /Move Work standup/ }));

    await waitFor(() => expect(document.querySelector("dialog")?.open).toBe(true));

    // The sheet says why the time is highlighted — that is what "Move" promised.
    expect(document.querySelector("dialog")).toHaveTextContent(
      "This is the time that overlaps. Shift it to fix it.",
    );
  });
});

describe("a mixed pair", () => {
  // The backend's `resolutions_for_pair` is the **union** of the two sides' allowed
  // sets, so a personal-vs-saved pair offers **four** actions — the personal side's
  // `delete_new` *and* the saved side's `skip_public`, alongside the two they share.
  // This is the case where getting a side wrong is easiest: two buttons sound like they
  // destroy something, and only one of them is allowed to.
  //
  // **A pair has one kind, so it has one middle action** — `edit_new` for a time pair,
  // `update_existing` for a duplicate. The backend's maps are keyed by kind, so the
  // server never sends both, and the review screen's labels cannot collide.
  const MIXED = pair({
    actions: ["keep_both", "edit_new", "delete_new", "skip_public"],
  });

  it("offers all four actions the server allowed", () => {
    render(<ConflictsPanel active={[MIXED]} resolved={[]} />);

    const group = screen.getByRole("group", { name: /Choices for the conflict/ });
    expect(within(group).getAllByRole("button")).toHaveLength(4);
  });

  it("labels each action with the event it is about", () => {
    render(<ConflictsPanel active={[MIXED]} resolved={[]} />);

    // The personal side, for the move and the delete.
    expect(screen.getByText("Move Work standup")).toBeInTheDocument();
    expect(screen.getByText("Delete Work standup")).toBeInTheDocument();
    // The saved side, for the skip.
    expect(screen.getByText("Skip Designers coffee chat")).toBeInTheDocument();
    expect(screen.getByText("Keep both — I'll manage")).toBeInTheDocument();
  });

  it("posts a delete against the personal side", async () => {
    render(<ConflictsPanel active={[MIXED]} resolved={[]} />);

    fireEvent.click(screen.getByRole("button", { name: /Delete Work standup/ }));

    await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));
    expect(posted().resolution).toBe("delete_new");
    expect(posted().side).toEqual({ kind: "personal_event", id: PERSONAL_ID });
  });

  it("posts a skip against the saved side", async () => {
    render(<ConflictsPanel active={[MIXED]} resolved={[]} />);

    fireEvent.click(screen.getByRole("button", { name: /Skip Designers coffee chat/ }));

    await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));
    expect(posted().resolution).toBe("skip_public");
    expect(posted().side).toEqual({ kind: "saved_event", id: SAVED_ID });
  });

  it("offers one middle action for a duplicate pair", () => {
    // A duplicate pair's middle action is `update_existing`, and it opens the personal
    // side — the *existing* event — in edit mode.
    const DUPLICATE = pair({
      actions: ["keep_both", "update_existing", "delete_new", "skip_public"],
      kind: "duplicate",
    });

    render(<ConflictsPanel active={[DUPLICATE]} resolved={[]} />);

    expect(screen.getByText("Move Work standup")).toBeInTheDocument();
    expect(screen.queryByText("Move Designers coffee chat")).toBeNull();
  });
});

describe("the resolved section", () => {
  it("shows the resolution in words, with the event and the day", () => {
    render(<ConflictsPanel active={[]} resolved={[resolvedPair()]} />);

    expect(screen.getByText(/Skipped public · Designers coffee chat ·/)).toBeInTheDocument();
  });

  it("offers no affordance at all — a decided pair is never decided again", () => {
    render(<ConflictsPanel active={[]} resolved={[resolvedPair()]} />);

    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });

  it("shows both sides", () => {
    render(<ConflictsPanel active={[]} resolved={[resolvedPair()]} />);

    expect(screen.getByText("Work standup")).toBeInTheDocument();
    expect(screen.getByText("Designers coffee chat")).toBeInTheDocument();
  });
});
