import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CalendarStep } from "@/components/onboarding/calendar-step";

/**
 * Step 1 — the providers, the credential, and the import that happens elsewhere.
 *
 * Two properties carry the weight here. The address is a **credential**: it is masked, it
 * is cleared once it has been sent, and it is never written to browser storage. And the
 * import is **not** part of the request — the worker's tick picks it up — so the step
 * polls, with a bound, and says so plainly when the bound is reached.
 */

const POST = vi.fn();
const GET = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: {
    POST: (...args: unknown[]) => POST(...args),
    GET: (...args: unknown[]) => GET(...args),
  },
}));

const CONNECTION = {
  id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  provider: "google",
  status: "active",
  display_label: "Google Calendar",
  last_error_kind: null,
  last_synced_at: null,
  next_sync_at: null,
  sync_in_progress: true,
};

const SYNCED = { ...CONNECTION, sync_in_progress: false, last_synced_at: "2026-10-30T06:00:00Z" };

const IMPORTED_EVENT = {
  id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
  name: "Standup",
  start_time_utc: "2026-11-02T13:00:00Z",
  start_time_tz: "UTC",
  end_time_utc: null,
  location: null,
  notes: null,
  version: 1,
  calendar_connection_id: CONNECTION.id,
};

const OWN_EVENT = {
  ...IMPORTED_EVENT,
  id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
  name: "Dinner",
  calendar_connection_id: null,
};

const ADDRESS = "https://calendar.google.com/calendar/ical/secret/basic.ics";

beforeEach(() => {
  POST.mockReset();
  GET.mockReset();
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

function chooseGoogle() {
  fireEvent.click(screen.getByRole("button", { name: /Google Calendar/ }));
}

function typeAddress(value = ADDRESS) {
  fireEvent.change(screen.getByLabelText("Google Calendar address"), {
    target: { value },
  });
}

function connect() {
  fireEvent.click(screen.getByRole("button", { name: "Connect" }));
}

describe("choosing a provider", () => {
  it("offers all three, with no OAuth promise", () => {
    render(<CalendarStep />);

    for (const name of ["Google Calendar", "Apple Calendar", "Outlook Calendar"]) {
      expect(screen.getByRole("button", { name: new RegExp(name) })).toBeInTheDocument();
    }
    // The mockup's "1-click OAuth" sub-labels describe a handshake this MVP does not have
    // (Amendment A-9, AD-18): the mechanism is a pasted secret address.
    expect(document.body.textContent).not.toContain("OAuth");
  });

  it("reveals that provider's guidance, and switches when another is chosen", () => {
    render(<CalendarStep />);

    chooseGoogle();
    expect(screen.getByText(/Secret address in iCal format/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Apple Calendar/ }));
    expect(screen.queryByText(/Secret address in iCal format/)).toBeNull();
    expect(screen.getByText(/tick Public Calendar/)).toBeInTheDocument();
  });

  it("shows no address field until a provider is chosen", () => {
    render(<CalendarStep />);

    expect(screen.queryByLabelText(/address/)).toBeNull();
  });
});

describe("the address is a credential", () => {
  it("is masked", () => {
    render(<CalendarStep />);
    chooseGoogle();

    expect(screen.getByLabelText("Google Calendar address")).toHaveAttribute("type", "password");
  });

  it("warns what the address is, and never offers to reveal it", () => {
    render(<CalendarStep />);
    chooseGoogle();

    expect(screen.getByText(/key to your calendar/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Show|Reveal/ })).toBeNull();
  });

  it("is not written to browser storage", async () => {
    POST.mockResolvedValue({ data: CONNECTION, error: undefined });
    GET.mockResolvedValue({ data: CONNECTION, error: undefined });
    render(<CalendarStep />);

    chooseGoogle();
    typeAddress();
    connect();

    await screen.findByRole("status");
    const stored = [
      ...Object.keys(localStorage).map((key) => localStorage.getItem(key)),
      ...Object.keys(sessionStorage).map((key) => sessionStorage.getItem(key)),
    ].join(" ");
    expect(stored).not.toContain("basic.ics");
    expect(stored).not.toContain(ADDRESS);
  });

  it("is gone from the DOM once it has been sent", async () => {
    POST.mockResolvedValue({ data: CONNECTION, error: undefined });
    GET.mockResolvedValue({ data: CONNECTION, error: undefined });
    render(<CalendarStep />);

    chooseGoogle();
    typeAddress();
    connect();

    await screen.findByRole("status");
    expect(document.body.innerHTML).not.toContain(ADDRESS);
  });

  it("is gone from the field if the user is ever sent back to it", async () => {
    // There is a real way back: the connect succeeds, the first poll reports the feed
    // revoked, and "Try again" returns to the form. If the address were still in state it
    // would be sitting in the field — a credential the user has already handed over,
    // re-rendered into a page they may well be screen-sharing.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    POST.mockResolvedValue({ data: CONNECTION, error: undefined });
    GET.mockResolvedValue({
      data: { ...CONNECTION, status: "needs_reconnect", last_error_kind: "revoked" },
      error: undefined,
    });
    render(<CalendarStep />);

    chooseGoogle();
    typeAddress();
    connect();
    await vi.advanceTimersByTimeAsync(3000);
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    chooseGoogle();

    expect(screen.getByLabelText("Google Calendar address")).toHaveValue("");
  });

  it("is kept after a refusal, so the user can correct it", async () => {
    // The opposite case, and it matters as much: a rejected address is still the user's
    // best attempt. Clearing it would make them paste it again to fix a typo.
    POST.mockResolvedValue({
      data: undefined,
      error: {
        code: "invalid_calendar_credential",
        message: "That calendar address doesn't look right.",
      },
    });
    render(<CalendarStep />);

    chooseGoogle();
    typeAddress("https://example.test/typo.ics");
    connect();

    await screen.findByRole("alert");
    expect(screen.getByLabelText("Google Calendar address")).toHaveValue(
      "https://example.test/typo.ics",
    );
  });

  it("cannot be submitted empty", () => {
    render(<CalendarStep />);
    chooseGoogle();

    expect(screen.getByRole("button", { name: "Connect" })).toBeDisabled();
  });
});

describe("connecting", () => {
  it("sends the provider and the address", async () => {
    POST.mockResolvedValue({ data: CONNECTION, error: undefined });
    GET.mockResolvedValue({ data: CONNECTION, error: undefined });
    render(<CalendarStep />);

    chooseGoogle();
    typeAddress();
    connect();

    await vi.waitFor(() => {
      expect(POST).toHaveBeenCalledWith("/api/personal/calendars", {
        body: { provider: "google", address: ADDRESS, display_label: "Google Calendar" },
      });
    });
  });

  it("shows the sync state while the import runs", async () => {
    POST.mockResolvedValue({ data: CONNECTION, error: undefined });
    GET.mockResolvedValue({ data: CONNECTION, error: undefined });
    render(<CalendarStep />);

    chooseGoogle();
    typeAddress();
    connect();

    expect(await screen.findByRole("status")).toHaveTextContent(/Importing your events/);
  });

  it("shows this connection's imported events once the sync lands", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    POST.mockResolvedValue({ data: CONNECTION, error: undefined });
    GET.mockImplementation((path: string) => {
      if (path === "/api/personal/calendars/{connection_id}") {
        return Promise.resolve({ data: SYNCED, error: undefined });
      }
      // The user's own event is in the list too, and must not be claimed as imported.
      return Promise.resolve({ data: { items: [IMPORTED_EVENT, OWN_EVENT] }, error: undefined });
    });
    render(<CalendarStep />);

    chooseGoogle();
    typeAddress();
    connect();
    await vi.advanceTimersByTimeAsync(3000);

    expect(await screen.findByText("Standup")).toBeInTheDocument();
    expect(screen.queryByText("Dinner")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("1 event is on your Pulse.");
  });

  it("pairs the Personal tone with the word, so colour is never the only signal", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    POST.mockResolvedValue({ data: CONNECTION, error: undefined });
    GET.mockImplementation((path: string) =>
      path === "/api/personal/calendars/{connection_id}"
        ? Promise.resolve({ data: SYNCED, error: undefined })
        : Promise.resolve({ data: { items: [IMPORTED_EVENT] }, error: undefined }),
    );
    render(<CalendarStep />);

    chooseGoogle();
    typeAddress();
    connect();
    await vi.advanceTimersByTimeAsync(3000);

    await screen.findByText("Standup");
    expect(screen.getByText("Personal")).toBeInTheDocument();
  });

  it("says the import is still running when the wait runs out", async () => {
    // The dispatcher is a 60-second tick, and with no worker running it never arrives at
    // all. The step must settle into a calm sentence rather than poll forever.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    POST.mockResolvedValue({ data: CONNECTION, error: undefined });
    GET.mockResolvedValue({ data: CONNECTION, error: undefined });
    render(<CalendarStep />);

    chooseGoogle();
    typeAddress();
    connect();
    await vi.advanceTimersByTimeAsync(80000);

    expect(await screen.findByRole("status")).toHaveTextContent(/still importing/);
  });
});

describe("the refusals", () => {
  it("shows the Free cap through the shared prompt, in the server's own words", async () => {
    // **The same component the save cap renders.** There is one spelling of this UI,
    // and the assertions below are the shared component's contract, not this file's.
    POST.mockResolvedValue({
      data: undefined,
      error: {
        code: "calendar_cap_reached",
        message: "You've connected the calendars your plan allows.",
        details: { cap: 1, upgrade_hint: "Save more with Pro." },
      },
    });
    render(<CalendarStep />);

    chooseGoogle();
    typeAddress();
    connect();

    // `upgrade_hint`, not `message`: the server owns the upgrade copy, so changing it
    // backend-side needs no change here.
    //
    // Waited on by its text, not by its role: the `connecting` phase renders its own
    // `role="status"` line, so a role query would resolve on that one first.
    const prompt = await screen.findByText("Save more with Pro.");
    expect(prompt.closest("[role='status']")).not.toBeNull();
    expect(screen.queryByText("You've connected the calendars your plan allows.")).toBeNull();
    expect(screen.getByRole("link", { name: "Upgrade" })).toHaveAttribute("href", "/pricing");
    // The API's payload carries no modal semantics, and this surface invents none.
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("renders a reworded cap hint without a frontend change", async () => {
    POST.mockResolvedValue({
      data: undefined,
      error: {
        code: "calendar_cap_reached",
        message: "You've connected the calendars your plan allows.",
        details: { cap: 3, upgrade_hint: "Three calendars is the free plan. Pro has more." },
      },
    });
    render(<CalendarStep />);

    chooseGoogle();
    typeAddress();
    connect();

    expect(await screen.findByText("Three calendars is the free plan. Pro has more."))
      .toBeInTheDocument();
  });

  it("shows a refused address on the field, in the API's words", async () => {
    POST.mockResolvedValue({
      data: undefined,
      error: {
        code: "invalid_calendar_credential",
        message: "That calendar address doesn't look right.",
        details: { field: "url" },
      },
    });
    render(<CalendarStep />);

    chooseGoogle();
    typeAddress("not-an-address");
    connect();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That calendar address doesn't look right.",
    );
    expect(screen.getByLabelText("Google Calendar address")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("uses the locked failure copy for anything else", async () => {
    POST.mockResolvedValue({
      data: undefined,
      error: { code: "request_failed", message: "Something went wrong." },
    });
    render(<CalendarStep />);

    chooseGoogle();
    typeAddress();
    connect();

    expect(await screen.findByRole("alert")).toHaveTextContent("Connection failed. Skip for now?");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("treats a connection that needs reconnecting as a failure, not a slow import", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    POST.mockResolvedValue({ data: CONNECTION, error: undefined });
    GET.mockResolvedValue({
      data: { ...CONNECTION, status: "needs_reconnect", last_error_kind: "revoked" },
      error: undefined,
    });
    render(<CalendarStep />);

    chooseGoogle();
    typeAddress();
    connect();
    await vi.advanceTimersByTimeAsync(3000);

    expect(await screen.findByRole("alert")).toHaveTextContent("Connection failed. Skip for now?");
  });

  it("shows the failure state when the connect never reaches the API", async () => {
    POST.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<CalendarStep />);

    chooseGoogle();
    typeAddress();
    connect();

    expect(await screen.findByRole("alert")).toHaveTextContent("Connection failed. Skip for now?");
  });

  it("keeps watching when a single poll fails to go out", async () => {
    // One failed poll is not a failed import — the connection is made and the worker is
    // working. Giving up here would tell the user their calendar failed when it did not.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    POST.mockResolvedValue({ data: CONNECTION, error: undefined });
    GET.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    GET.mockImplementation((path: string) =>
      path === "/api/personal/calendars/{connection_id}"
        ? Promise.resolve({ data: SYNCED, error: undefined })
        : Promise.resolve({ data: { items: [IMPORTED_EVENT] }, error: undefined }),
    );
    render(<CalendarStep />);

    chooseGoogle();
    typeAddress();
    connect();
    await vi.advanceTimersByTimeAsync(9000);

    expect(await screen.findByText("Standup")).toBeInTheDocument();
  });

  it("lets the user try again after a failure", async () => {
    POST.mockResolvedValue({
      data: undefined,
      error: { code: "request_failed", message: "Something went wrong." },
    });
    render(<CalendarStep />);

    chooseGoogle();
    typeAddress();
    connect();
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));

    expect(screen.getByRole("button", { name: /Google Calendar/ })).toBeInTheDocument();
  });
});

describe("a calendar that is already connected", () => {
  it("is shown as connected rather than as an empty form", () => {
    GET.mockResolvedValue({ data: { items: [] }, error: undefined });
    render(<CalendarStep existing={SYNCED} />);

    expect(screen.getByRole("status")).toHaveTextContent(/Connected/);
    expect(screen.queryByLabelText(/address/)).toBeNull();
  });

  it("says what it has already imported, rather than claiming it found nothing", async () => {
    // The page hands the step a connection, not its events. Without reading them, a
    // returning user is told their full calendar is empty.
    GET.mockResolvedValue({ data: { items: [IMPORTED_EVENT, OWN_EVENT] }, error: undefined });
    render(<CalendarStep existing={SYNCED} />);

    expect(await screen.findByText("Standup")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("1 event is on your Pulse.");
    expect(screen.queryByText("Dinner")).toBeNull();
  });

  it("says so plainly when the connected calendar really is empty", async () => {
    GET.mockResolvedValue({ data: { items: [OWN_EVENT] }, error: undefined });
    render(<CalendarStep existing={SYNCED} />);

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Nothing upcoming in that calendar yet.",
    );
  });
});
