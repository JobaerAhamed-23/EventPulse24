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
