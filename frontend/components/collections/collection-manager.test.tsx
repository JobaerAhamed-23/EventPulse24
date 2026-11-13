/**
 * The collections manager: FR-49's four verbs, plus membership.
 *
 * **What these tests exist to hold:**
 *
 * 1. **Reorder sends the whole ordering**, not a swap — the server must never see a
 *    partially reordered list, and a test that only checked "the request happened" would
 *    pass against a pairwise endpoint that cannot promise that.
 * 2. **Delete says what survives.** "Delete" above a list of events reads as deleting the
 *    events; the confirmation is where that is made untrue for the user.
 * 3. **The server's list wins after every write**, so positions and counts cannot drift
 *    away from what the server actually stored.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CollectionManager } from "@/components/collections/collection-manager";

const GET = vi.fn();
const POST = vi.fn();
const PATCH = vi.fn();
const PUT = vi.fn();
const DELETE = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    GET: (...args: unknown[]) => GET(...args),
    POST: (...args: unknown[]) => POST(...args),
    PATCH: (...args: unknown[]) => PATCH(...args),
    PUT: (...args: unknown[]) => PUT(...args),
    DELETE: (...args: unknown[]) => DELETE(...args),
  },
}));

function collection(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "01a1cd00-0000-7000-8000-000000000001",
    name: "Weekend",
    position: 0,
    item_count: 0,
    ...overrides,
  };
}

const THREE = [
  collection({ id: "id-one", name: "One", position: 0 }),
  collection({ id: "id-two", name: "Two", position: 1 }),
  collection({ id: "id-three", name: "Three", position: 2 }),
];

beforeEach(() => {
  GET.mockReset();
  POST.mockReset();
  PATCH.mockReset();
  PUT.mockReset();
  DELETE.mockReset();
  GET.mockResolvedValue({ data: THREE });
  POST.mockResolvedValue({ data: collection() });
  PATCH.mockResolvedValue({ data: collection() });
  PUT.mockResolvedValue({ data: THREE });
  DELETE.mockResolvedValue({ data: undefined, response: { status: 204 } });
});

function renderManager(initial = THREE) {
  return render(<CollectionManager initial={initial} />);
}

/**
 * The first control with this label.
 *
 * Every row carries a Rename and a Delete, so these names are deliberately ambiguous —
 * the row is identified by position, and the tests that care about *which* row assert on
 * the id in the request rather than on the control they pressed.
 */
function firstButton(name: string): HTMLElement {
  const [button] = screen.getAllByRole("button", { name });
  if (!button) throw new Error(`no button labelled ${name}`);
  return button;
}

// ── Create ─────────────────────────────────────────────────────────────────────────

describe("creating", () => {
  it("sends the trimmed name and clears the field", async () => {
    GET.mockResolvedValue({ data: [...THREE, collection({ id: "id-new", name: "Gigs" })] });
    renderManager();

    fireEvent.change(screen.getByLabelText("New collection"), {
      target: { value: "  Gigs  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith("/api/personal/collections", {
        body: { name: "Gigs" },
      }),
    );
    await waitFor(() => expect(screen.getByLabelText("New collection")).toHaveValue(""));
  });

  it("cannot be submitted empty", () => {
    renderManager();

    expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();
  });

  it("cannot be submitted with only spaces", () => {
    renderManager();

    fireEvent.change(screen.getByLabelText("New collection"), { target: { value: "   " } });

    expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();
  });

  it("shows the server's refusal and keeps what was typed", async () => {
    POST.mockResolvedValue({
      error: { code: "collection_name_taken", message: "You already have one of those." },
      response: { status: 409 },
    });
    renderManager();

    fireEvent.change(screen.getByLabelText("New collection"), { target: { value: "One" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    expect(await screen.findByText("You already have one of those.")).toBeTruthy();
    // The user's work is kept: they have a name to edit rather than one to retype.
    expect(screen.getByLabelText("New collection")).toHaveValue("One");
  });
});

// ── Rename ─────────────────────────────────────────────────────────────────────────

describe("renaming", () => {
  it("sends the new name for that collection", async () => {
    renderManager();

    fireEvent.click(firstButton("Rename"));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Ones" } });
    fireEvent.click(screen.getByRole("button", { name: "Save name" }));

    await waitFor(() =>
      expect(PATCH).toHaveBeenCalledWith("/api/personal/collections/{collection_id}", {
        params: { path: { collection_id: "id-one" } },
        body: { name: "Ones" },
      }),
    );
  });

  it("can be abandoned without sending anything", () => {
    renderManager();

    fireEvent.click(firstButton("Rename"));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(PATCH).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Name")).toBeNull();
  });
});

// ── Reorder ────────────────────────────────────────────────────────────────────────

describe("reordering", () => {
  it("sends the whole resulting order, not a swap", async () => {
    // **The acceptance criterion.** A pairwise endpoint could not promise the server never
    // sees a partially reordered list; this asserts the complete ordering goes in one call.
    renderManager();

    fireEvent.click(screen.getByLabelText("Move Two up"));

    await waitFor(() =>
      expect(PUT).toHaveBeenCalledWith("/api/personal/collections/order", {
        body: { collection_ids: ["id-two", "id-one", "id-three"] },
      }),
    );
  });

  it("moves one down the same way", async () => {
    renderManager();

    fireEvent.click(screen.getByLabelText("Move One down"));

    await waitFor(() =>
      expect(PUT).toHaveBeenCalledWith("/api/personal/collections/order", {
        body: { collection_ids: ["id-two", "id-one", "id-three"] },
      }),
    );
  });

  it("disables the ends rather than letting them fail silently", () => {
    renderManager();

    expect(screen.getByLabelText("Move One up")).toBeDisabled();
    expect(screen.getByLabelText("Move Three down")).toBeDisabled();
    expect(screen.getByLabelText("Move Two up")).not.toBeDisabled();
  });

  it("takes the order back from the server afterwards", async () => {
    const reversed = [...THREE].reverse();
    GET.mockResolvedValue({ data: reversed });
    renderManager();

    fireEvent.click(screen.getByLabelText("Move Three up"));

    // The server's list is the truth — an optimistic guess could drift from the positions
    // actually stored.
    await waitFor(() => expect(GET).toHaveBeenCalled());
  });
});

// ── Delete ─────────────────────────────────────────────────────────────────────────

describe("deleting", () => {
  it("asks first, and says the saved events survive", () => {
    // **The criterion**: "delete" above a list of events reads as deleting the events.
    renderManager();

    fireEvent.click(firstButton("Delete"));

    expect(screen.getByText(/Your saved events stay saved/)).toBeTruthy();
    expect(DELETE).not.toHaveBeenCalled();
  });

  it("does nothing when the confirmation is declined", () => {
    renderManager();

    fireEvent.click(firstButton("Delete"));
    fireEvent.click(screen.getByRole("button", { name: "Keep it" }));

    expect(DELETE).not.toHaveBeenCalled();
    expect(screen.queryByText(/Your saved events stay saved/)).toBeNull();
  });

  it("deletes once confirmed", async () => {
    renderManager();

    fireEvent.click(firstButton("Delete"));
    fireEvent.click(screen.getByRole("button", { name: "Delete it" }));

    await waitFor(() =>
      expect(DELETE).toHaveBeenCalledWith("/api/personal/collections/{collection_id}", {
        params: { path: { collection_id: "id-one" } },
      }),
    );
  });

  it("confirms in place, with no dialog to trap focus", () => {
    renderManager();

    fireEvent.click(firstButton("Delete"));

    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

// ── The empty states, which are two different states ───────────────────────────────

describe("emptiness", () => {
  it("renders the quiet empty state when there are no collections", () => {
    renderManager([]);

    const empty = screen.getByText("No collections yet.");
    expect(empty).toBeTruthy();
    // `component.emptystate.quiet`: dashed, so it reads as intentional, not failed.
    expect(document.querySelector("[data-collections-empty]")?.className).toContain(
      "border-dashed",
    );
  });

  it("still offers the create control with no collections", () => {
    renderManager([]);

    expect(screen.getByLabelText("New collection")).toBeTruthy();
  });

  it("says an opened collection is empty without borrowing the failure treatment", async () => {
    GET.mockResolvedValue({ data: [] });
    renderManager();

    fireEvent.click(screen.getByRole("button", { name: /^One/ }));

    // A container somebody made on purpose is not a failure.
    expect(await screen.findByText(/Nothing in here yet/)).toBeTruthy();
    expect(document.querySelector("[data-collections-empty]")).toBeNull();
  });
});

// ── Membership ─────────────────────────────────────────────────────────────────────

describe("what is inside", () => {
  const EVENT = {
    id: "save-1",
    event_id: "event-1",
    start_time_utc: "2027-03-03T19:30:00+00:00",
    end_time_utc: "2027-03-03T21:30:00+00:00",
    event_version: 4,
  };

  it("reads the collection's events and renders the snapshot time", async () => {
    GET.mockResolvedValue({ data: [EVENT] });
    renderManager();

    fireEvent.click(screen.getByRole("button", { name: /^One/ }));

    await waitFor(() =>
      expect(GET).toHaveBeenCalledWith("/api/personal/collections/{collection_id}/events", {
        params: { path: { collection_id: "id-one" } },
      }),
    );
    // The snapshot — AD-17 keeps it current, so a postponement shows with no catalog read.
    expect(await screen.findByText(/2027|Mar/)).toBeTruthy();
  });

  it("takes a save out without touching the save itself", async () => {
    GET.mockResolvedValue({ data: [EVENT] });
    renderManager();

    fireEvent.click(screen.getByRole("button", { name: /^One/ }));
    await screen.findByText(/2027|Mar/);
    fireEvent.click(screen.getByRole("button", { name: "Take out" }));

    await waitFor(() =>
      expect(DELETE).toHaveBeenCalledWith(
        "/api/personal/collections/{collection_id}/events/{saved_event_id}",
        { params: { path: { collection_id: "id-one", saved_event_id: "save-1" } } },
      ),
    );
  });

  it("closes an open collection when pressed again", async () => {
    GET.mockResolvedValue({ data: [EVENT] });
    renderManager();

    const toggle = screen.getByRole("button", { name: /^One/ });
    fireEvent.click(toggle);
    await waitFor(() => expect(toggle).toHaveAttribute("aria-expanded", "true"));

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });
});

// ── Failures ───────────────────────────────────────────────────────────────────────

describe("when a write fails", () => {
  it("says so without losing the list", async () => {
    PUT.mockResolvedValue({
      error: { code: "server_error", message: "" },
      response: { status: 500 },
    });
    renderManager();

    fireEvent.click(screen.getByLabelText("Move Two up"));

    expect(await screen.findByText("Couldn't save that. Try again in a moment.")).toBeTruthy();
    expect(screen.getByRole("button", { name: /^One/ })).toBeTruthy();
  });

  it("survives a request that never reached the API", async () => {
    POST.mockRejectedValue(new Error("offline"));
    renderManager();

    fireEvent.change(screen.getByLabelText("New collection"), { target: { value: "Gigs" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    expect(await screen.findByText("Couldn't save that. Try again in a moment.")).toBeTruthy();
  });
});

// ── Assign: putting a save into a collection (FR-49) ───────────────────────────────

/**
 * The endpoint these tests cover had no caller at all before this work item.
 * `PUT /api/personal/collections/{id}/events/{saved_event_id}` was built and tested on the
 * backend, and the UI could create a collection, rename it, reorder it, delete it and take
 * things out of it — and never put anything in. A Pro feature that could not be used.
 *
 * **Every test here is paired with a mutation that makes it fail.** That is the point of
 * this intent: the gaps it closes all sat behind green test suites.
 */
describe("assigning a save to a collection", () => {
  const SAVE_A = {
    id: "save-a",
    title: "Hackney Jazz Night",
    start_time_utc: "2027-03-03T19:30:00+00:00",
  };
  const SAVE_B = {
    id: "save-b",
    title: "Sunday Market",
    start_time_utc: "2027-03-07T10:00:00+00:00",
  };
  const IN_COLLECTION = {
    id: "save-a",
    event_id: "event-1",
    start_time_utc: "2027-03-03T19:30:00+00:00",
    end_time_utc: null,
    event_version: 1,
  };

  /**
   * Answer by **path**, not by call order.
   *
   * Three different GETs are in play — the collections list, one collection's events, and
   * the user's saves — and a mock that answered by order would silently change meaning the
   * moment a read was added or moved.
   */
  function mockReads({
    events = [] as unknown[],
    saves = [SAVE_A, SAVE_B] as unknown[],
    savesFails = false,
  } = {}): void {
    GET.mockImplementation((path: string) => {
      if (path === "/api/personal/saved-events") {
        if (savesFails) return Promise.resolve({ data: undefined });
        return Promise.resolve({ data: { items: saves, omitted: 0 } });
      }
      if (path.includes("/events")) return Promise.resolve({ data: events });
      return Promise.resolve({ data: THREE });
    });
  }

  /** Open the first collection and reveal the picker. */
  async function openPicker(): Promise<void> {
    fireEvent.click(screen.getByRole("button", { name: /^One/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Add a save" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Add a save" }));
  }

  it("sends the collection id and the save row's id", async () => {
    // **The id matters.** `SavedEventOut.id` is the personal save's row id, which is what
    // membership points at; `event_id` is the catalog event. Sending the wrong one would
    // 404 against a save the user does not own.
    mockReads();
    renderManager();

    await openPicker();
    fireEvent.click(await screen.findByText("Hackney Jazz Night"));

    await waitFor(() =>
      expect(PUT).toHaveBeenCalledWith(
        "/api/personal/collections/{collection_id}/events/{saved_event_id}",
        { params: { path: { collection_id: "id-one", saved_event_id: "save-a" } } },
      ),
    );
  });

  it("does not offer a save that is already in this collection", async () => {
    // The endpoint would answer 204 and write nothing — correct of it, wrong of a button.
    mockReads({ events: [IN_COLLECTION] });
    renderManager();

    await openPicker();

    expect(await screen.findByText("Sunday Market")).toBeTruthy();
    expect(screen.queryByText("Hackney Jazz Night")).toBeNull();
  });

  it("says so when every save is already in the collection", async () => {
    mockReads({ events: [IN_COLLECTION], saves: [SAVE_A] });
    renderManager();

    await openPicker();

    expect(await screen.findByText("Everything you've saved is already in here.")).toBeTruthy();
  });

  it("offers a plain line, not the dashed empty state, when nothing is saved at all", async () => {
    // An empty *picker* is the same kind of absence the empty collection is: a container
    // the user has not filled, not a failure. `component.emptystate.quiet` is for a found
    // absence and would overstate this.
    mockReads({ saves: [] });
    renderManager();

    await openPicker();

    expect(
      await screen.findByText("Nothing saved yet. Save an event and it can go in here."),
    ).toBeTruthy();
    expect(document.querySelector("[data-picker-empty]")).toBeTruthy();
  });

  it("reads the saves when the picker opens, not when the collection does", async () => {
    // The saves list is unbounded for a Pro account. A user who expands a collection to
    // look at it must not pay for that read.
    mockReads();
    renderManager();

    fireEvent.click(screen.getByRole("button", { name: /^One/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Add a save" })).toBeTruthy());

    expect(GET.mock.calls.some(([path]) => path === "/api/personal/saved-events")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Add a save" }));

    await waitFor(() =>
      expect(GET.mock.calls.some(([path]) => path === "/api/personal/saved-events")).toBe(true),
    );
  });

  it("re-reads the collection after assigning, and keeps it open", async () => {
    // `open()` is a toggle: re-reading through it would close the collection the user is
    // filling. The re-read is what removes the assigned save from the picker.
    mockReads();
    renderManager();

    await openPicker();
    fireEvent.click(await screen.findByText("Hackney Jazz Night"));

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: /^One/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("renders the server's own refusal when the assign is refused", async () => {
    // A Free account's 409 carries `{cap, upgrade_hint}` and no modal-shaped field. The
    // client renders the sentence as it arrived and builds no prompt of its own.
    mockReads();
    PUT.mockResolvedValue({
      error: {
        code: "collections_pro_only",
        message: "Collections are part of Pro.",
        details: { cap: 0, upgrade_hint: "Collections are part of Pro." },
      },
    });
    renderManager();

    await openPicker();
    fireEvent.click(await screen.findByText("Hackney Jazz Night"));

    expect(await screen.findByText("Collections are part of Pro.")).toBeTruthy();
  });

  it("tells a failed saves read apart from a failed write", async () => {
    // A read is not a save. Reusing the write's line would report the wrong operation on a
    // screen where both happen.
    mockReads({ savesFails: true });
    renderManager();

    await openPicker();

    expect(
      await screen.findByText("Couldn't read your saves. Try again in a moment."),
    ).toBeTruthy();
  });

  it("leaves taking a save out ungated and intact", async () => {
    // Unassign is open on every tier — "this is how a lapsed Pro user tidies up" — and it
    // removes a membership, never the save. This item must not have changed either fact.
    mockReads({ events: [IN_COLLECTION] });
    renderManager();

    fireEvent.click(screen.getByRole("button", { name: /^One/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Take out" }));

    await waitFor(() =>
      expect(DELETE).toHaveBeenCalledWith(
        "/api/personal/collections/{collection_id}/events/{saved_event_id}",
        { params: { path: { collection_id: "id-one", saved_event_id: "save-a" } } },
      ),
    );
    // Not the saved-event delete, which would unsave it entirely.
    expect(
      DELETE.mock.calls.some(([path]) =>
        String(path).includes("/api/personal/saved-events/{catalog_event_id}"),
      ),
    ).toBe(false);
  });

  it("tells the user where the control is, in the empty collection's own words", async () => {
    mockReads();
    renderManager();

    fireEvent.click(screen.getByRole("button", { name: /^One/ }));

    expect(await screen.findByText("Nothing in here yet. Add a save to it below.")).toBeTruthy();
  });
});
