import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CalendarConnections } from "@/components/settings/calendar-connections";

/**
 * Calendar sync (FR-50) — the two endpoints that had no caller.
 *
 * Onboarding promised "disconnect any time in Settings" while
 * `DELETE /api/personal/calendars/{id}` was unreachable, and `calendar-step.tsx` already
 * detected `needs_reconnect` with no way to offer the fix. These tests hold both.
 *
 * **The address is a credential.** The reconnect form holds one, so a test asserts it is
 * gone from the DOM after the request — the only place in this component where a secret
 * exists at all, since `CalendarConnectionOut` carries no address by design.
 */
const GET = vi.fn();
const POST = vi.fn();
const DELETE = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    GET: (...args: unknown[]) => GET(...args),
    POST: (...args: unknown[]) => POST(...args),
    DELETE: (...args: unknown[]) => DELETE(...args),
  },
}));

const ACTIVE = {
  id: "cal-1",
  provider: "google",
  status: "active",
  display_label: "Google Calendar",
  last_synced_at: "2026-11-12T08:00:00+00:00",
  next_sync_at: null,
  sync_in_progress: false,
  last_error_kind: null,
};

const REVOKED = {
  ...ACTIVE,
  id: "cal-2",
  display_label: "Work calendar",
  status: "needs_reconnect",
  last_error_kind: "revoked",
};

const SECRET = "https://calendar.example.com/private-1234abcd/basic.ics";

beforeEach(() => {
  GET.mockReset();
  POST.mockReset();
  DELETE.mockReset();
  GET.mockResolvedValue({ data: { items: [ACTIVE] } });
  POST.mockResolvedValue({ data: undefined });
  DELETE.mockResolvedValue({ data: undefined });
});

describe("disconnecting", () => {
  it("asks first — no request leaves on the first press", () => {
    render(<CalendarConnections initial={[ACTIVE]} />);

    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));

    expect(DELETE).not.toHaveBeenCalled();
  });

  it("says the imported events go, and that the user's own events stay", () => {
    render(<CalendarConnections initial={[ACTIVE]} />);

    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));

    expect(screen.getByText(/imported events are removed/)).toBeTruthy();
    expect(screen.getByText(/Events you added yourself stay/)).toBeTruthy();
  });

  it("disconnects the connection it was pressed on", async () => {
    render(<CalendarConnections initial={[ACTIVE, REVOKED]} />);

    // The second row's Disconnect — the id in the request is what proves which row.
    const second = screen.getAllByRole("button", { name: "Disconnect" })[1];
    if (!second) throw new Error("expected two Disconnect buttons");
    fireEvent.click(second);
    fireEvent.click(screen.getByRole("button", { name: "Disconnect it" }));

    await waitFor(() =>
      expect(DELETE).toHaveBeenCalledWith("/api/personal/calendars/{connection_id}", {
        params: { path: { connection_id: "cal-2" } },
      }),
    );
  });

  it("keeps the row and the confirmation when the disconnect is refused", async () => {
    DELETE.mockResolvedValue({ error: { code: "server_error", message: "nope" } });
    render(<CalendarConnections initial={[ACTIVE]} />);

    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    fireEvent.click(screen.getByRole("button", { name: "Disconnect it" }));

    await waitFor(() => expect(DELETE).toHaveBeenCalled());
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Disconnect it" })).toBeTruthy();
  });

  it("does nothing when the confirmation is declined", () => {
    render(<CalendarConnections initial={[ACTIVE]} />);

    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    fireEvent.click(screen.getByRole("button", { name: "Keep it" }));

    expect(DELETE).not.toHaveBeenCalled();
    expect(screen.queryByText(/imported events are removed/)).toBeNull();
  });
});

describe("reconnecting", () => {
  it("is offered for a revoked connection", () => {
    render(<CalendarConnections initial={[REVOKED]} />);

    expect(screen.getByRole("button", { name: "Reconnect" })).toBeTruthy();
  });

  it("is not offered for a healthy connection", () => {
    render(<CalendarConnections initial={[ACTIVE]} />);

    expect(screen.queryByRole("button", { name: "Reconnect" })).toBeNull();
  });

  it("posts the pasted address to the revoked connection", async () => {
    render(<CalendarConnections initial={[REVOKED]} />);

    fireEvent.click(screen.getByRole("button", { name: "Reconnect" }));
    fireEvent.change(screen.getByLabelText("New address"), { target: { value: SECRET } });
    fireEvent.click(screen.getByRole("button", { name: "Reconnect" }));

    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith("/api/personal/calendars/{connection_id}/reconnect", {
        params: { path: { connection_id: "cal-2" } },
        body: { address: SECRET, display_label: "" },
      }),
    );
  });

  it("leaves no trace of the address in the DOM afterwards", async () => {
    // The address is the credential. It must not survive the request in a field, a
    // value attribute or anywhere else on the page.
    //
    // **The refresh returns the connection still revoked**, and that is what makes this
    // test able to fail. With the default mock the re-read answers with an *active*
    // connection, so the form unmounts because the connection stopped needing a
    // reconnect — and the assertion would pass even if the address were never cleared.
    // A mutation probe found exactly that: removing `setReconnecting(null)` left all
    // thirteen tests green.
    GET.mockResolvedValue({ data: { items: [REVOKED] } });
    render(<CalendarConnections initial={[REVOKED]} />);

    fireEvent.click(screen.getByRole("button", { name: "Reconnect" }));
    fireEvent.change(screen.getByLabelText("New address"), { target: { value: SECRET } });
    fireEvent.click(screen.getByRole("button", { name: "Reconnect" }));

    await waitFor(() => expect(POST).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByLabelText("New address")).toBeNull());
    expect(document.body.innerHTML).not.toContain(SECRET);
    expect(document.body.innerHTML).not.toContain("private-1234abcd");
  });

  it("does not post an empty address", () => {
    render(<CalendarConnections initial={[REVOKED]} />);

    fireEvent.click(screen.getByRole("button", { name: "Reconnect" }));
    fireEvent.change(screen.getByLabelText("New address"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Reconnect" }));

    expect(POST).not.toHaveBeenCalled();
  });

  it("turns the error slug into a sentence rather than printing the slug", () => {
    render(<CalendarConnections initial={[REVOKED]} />);

    expect(screen.getByText(/The provider revoked this address/)).toBeTruthy();
    expect(screen.queryByText("revoked")).toBeNull();
  });

  it("falls back to a neutral line for a slug it does not know", () => {
    render(<CalendarConnections initial={[{ ...REVOKED, last_error_kind: "teapot" }]} />);

    expect(screen.getByText("The last sync didn't go through.")).toBeTruthy();
    expect(screen.queryByText("teapot")).toBeNull();
  });
});

describe("the empty state", () => {
  it("is honest rather than an error when no calendar is connected", () => {
    render(<CalendarConnections initial={[]} />);

    expect(screen.getByText(/No calendar connected/)).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

/**
 * "Sync now" (FR-50) — the button that asks, rather than fetches.
 *
 * The endpoint marks the connection due and the 60-second dispatcher picks it up, so what
 * is asserted here is the *asking* and the *waiting*: the row says "Syncing…" until the
 * server reports a new `last_synced_at`, and says so out loud instead of spinning forever
 * when the sync never lands.
 */
describe("syncing now", () => {
  it("asks the server to sync this calendar", async () => {
    render(<CalendarConnections initial={[ACTIVE]} />);

    fireEvent.click(screen.getByRole("button", { name: "Sync now" }));

    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith("/api/personal/calendars/{connection_id}/sync", {
        params: { path: { connection_id: "cal-1" } },
      }),
    );
  });

  it("says Syncing… while it waits", async () => {
    render(<CalendarConnections initial={[ACTIVE]} />);

    fireEvent.click(screen.getByRole("button", { name: "Sync now" }));

    expect(await screen.findByRole("button", { name: "Syncing…" })).toBeDisabled();
  });

  it("stops waiting once the server reports a newer sync", async () => {
    // The list the poll re-reads has moved on: a different `last_synced_at` is how a
    // queued sync is known to have landed.
    GET.mockResolvedValue({
      data: { items: [{ ...ACTIVE, last_synced_at: "2026-11-12T09:30:00+00:00" }] },
    });
    render(<CalendarConnections initial={[ACTIVE]} />);

    fireEvent.click(screen.getByRole("button", { name: "Sync now" }));

    // `waitFor` on the enabled state, not `findByRole` on the label: the button reads
    // "Sync now" while the request is still in flight too, so a name-only match would
    // resolve against the busy phase and prove nothing.
    await waitFor(() => expect(screen.getByRole("button", { name: "Sync now" })).toBeEnabled());
  });

  it("is not offered for a connection that cannot be synced", () => {
    // The endpoint answers 409 for a revoked connection, and a button whose only outcome
    // is a refusal is not a button. The remedy on this row is Reconnect.
    render(<CalendarConnections initial={[REVOKED]} />);

    expect(screen.queryByRole("button", { name: "Sync now" })).toBeNull();
  });

  it("shows the server's own refusal when the cooldown refuses", async () => {
    // The API owns this sentence; the component must not replace it with a generic one.
    POST.mockResolvedValue({
      error: {
        code: "rate_limited",
        message: "That calendar was just refreshed. Give it a moment.",
        details: { retry_after_seconds: 42 },
      },
    });
    render(<CalendarConnections initial={[ACTIVE]} />);

    fireEvent.click(screen.getByRole("button", { name: "Sync now" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That calendar was just refreshed. Give it a moment.",
    );
  });

  it("does not claim to be syncing after a refusal", async () => {
    POST.mockResolvedValue({ error: { code: "rate_limited", message: "Give it a moment." } });
    render(<CalendarConnections initial={[ACTIVE]} />);

    fireEvent.click(screen.getByRole("button", { name: "Sync now" }));

    // **The row must not contradict the line beside it.** A "Syncing…" label under a
    // message saying the request was refused tells the user two different things.
    await screen.findByRole("alert");
    expect(screen.getByRole("button", { name: "Sync now" })).toBeEnabled();
  });
});

/**
 * Connecting a calendar from Settings (FR-50).
 *
 * `POST /api/personal/calendars` had one caller — onboarding step 1 — so a user who
 * skipped it, or who wanted a second calendar later, could not add one at all.
 */
describe("connecting", () => {
  it("offers all three providers, with no ranking between them", () => {
    render(<CalendarConnections initial={[]} />);

    for (const name of ["Google Calendar", "Apple Calendar", "Outlook Calendar"]) {
      expect(screen.getByRole("button", { name })).toBeEnabled();
    }
  });

  it("sends the pasted address to the chosen provider", async () => {
    render(<CalendarConnections initial={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "Apple Calendar" }));

    fireEvent.change(screen.getByLabelText("Apple Calendar address"), {
      target: { value: SECRET },
    });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith("/api/personal/calendars", {
        body: { provider: "apple", address: SECRET, display_label: "Apple Calendar" },
      }),
    );
  });

  it("warns that the address is a key to the calendar", () => {
    render(<CalendarConnections initial={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "Google Calendar" }));

    expect(screen.getByText(/key to your calendar/i)).toBeInTheDocument();
  });

  it("keeps no copy of the address once the request has gone", async () => {
    // **It is a credential.** The same rule the reconnect form follows: it lives in state
    // for as long as one keystroke needs, and no longer.
    render(<CalendarConnections initial={[]} />);
    fireEvent.click(screen.getByRole("button", { name: "Google Calendar" }));
    fireEvent.change(screen.getByLabelText("Google Calendar address"), {
      target: { value: SECRET },
    });

    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    await waitFor(() => expect(POST).toHaveBeenCalled());
    expect(document.body.innerHTML).not.toContain(SECRET);
  });

  it("renders the server's upgrade sentence when the plan is full", async () => {
    // The cap is the server's, and so is its copy: a backend wording change must not need
    // a frontend change.
    POST.mockResolvedValue({
      error: {
        code: "calendar_cap_reached",
        message: "You've connected the calendars your plan allows.",
        details: { cap: 1, upgrade_hint: "Save more with Pro." },
      },
    });
    render(<CalendarConnections initial={[ACTIVE]} />);
    fireEvent.click(screen.getByRole("button", { name: "Google Calendar" }));
    fireEvent.change(screen.getByLabelText("Google Calendar address"), {
      target: { value: SECRET },
    });

    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    expect(await screen.findByText("Save more with Pro.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upgrade" })).toHaveAttribute("href", "/pricing");
  });

  it("offers the form even when the user already holds a calendar", () => {
    // **The cap is not predicted here.** A form hidden by a client-side count would be
    // hidden wrongly for a user whose tier changed in another tab, and would read as the
    // feature being missing rather than the plan being full.
    render(<CalendarConnections initial={[ACTIVE]} />);

    expect(screen.getByRole("button", { name: "Google Calendar" })).toBeEnabled();
  });

  it("tells a user with no calendar that they can connect one here", () => {
    render(<CalendarConnections initial={[]} />);

    // The old copy sent them back to onboarding, which they cannot re-enter.
    expect(screen.getByText(/Connect one below/i)).toBeInTheDocument();
  });
});
