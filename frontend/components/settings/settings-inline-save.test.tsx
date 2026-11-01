/**
 * The settings islands' inline save.
 *
 * **Three things are worth proving here, and they are the ones a screenshot cannot
 * show.**
 *
 * 1. **The save is inline.** There is no Save button; the control the user pressed is
 *    the thing that saves.
 * 2. **The patch is narrow.** Each island sends **only the field it owns**. The patch's
 *    `quiet_hours` field is the one where `null` is a value — it turns quiet hours off
 *    — so a payload that re-sent the window on every chip change could turn quiet
 *    hours off by accident. The test asserts the **absence** of the other fields, not
 *    just the presence of the right one.
 * 3. **The chosen state is kept when the save fails.** Reverting it would throw away
 *    the user's work over a transient failure, and the copy promises a retry.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DefaultReminderSlots } from "@/components/settings/default-reminder-slots";
import { DigestDeliveryTime } from "@/components/settings/digest-delivery-time";
import { QuietHoursWindow } from "@/components/settings/quiet-hours-window";

const PUT = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { PUT: (...args: unknown[]) => PUT(...args) },
}));

/** The server's settings, as the `PUT` answers with them. */
function answer(overrides: Record<string, unknown> = {}) {
  return {
    data: {
      default_reminder_slots: ["1d", "1hr"],
      quiet_hours: { start: "22:00:00", end: "08:00:00" },
      digest: { delivery_time: "09:00:00", timezone: "UTC" },
      ...overrides,
    },
    response: { status: 200 },
  };
}

beforeEach(() => {
  PUT.mockReset();
  PUT.mockResolvedValue(answer());
});

/**
 * The API's refusal, as the server sends it.
 *
 * **This is the shape `backend/config/errors.py` writes.** A `DomainError` becomes
 * `{ code, message, details }` with the status the error's class maps to — and the
 * message is written for the user, which is the whole point of it being there.
 */
function refusal(code: string, message: string, status = 422) {
  return {
    data: undefined,
    error: { code, message },
    response: { status },
  };
}

/* ── the default plan ────────────────────────────────────────────────────────── */

describe("the default reminder plan", () => {
  it("saves on change, with no Save button", async () => {
    render(<DefaultReminderSlots initialSlots={["1d", "1hr"]} />);

    expect(screen.queryByRole("button", { name: /^save/i })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /5 days before/i }));

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    expect(PUT.mock.calls[0]?.[0]).toBe("/api/settings/notifications");
  });

  it("sends the chosen slots, and only the slots", async () => {
    render(<DefaultReminderSlots initialSlots={["1d", "1hr"]} />);

    fireEvent.click(screen.getByRole("button", { name: /5 days before/i }));

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    const body = PUT.mock.calls[0]?.[1]?.body;
    expect(body).toEqual({ default_reminder_slots: ["1d", "1hr", "5d"] });
    // **The quiet window and the digest schedule are omitted.** An omitted field is
    // left alone — and `quiet_hours: null` would turn quiet hours OFF.
    expect(body).not.toHaveProperty("quiet_hours");
    expect(body).not.toHaveProperty("digest");
  });

  it("says 'Saved.' quietly, and announces it", async () => {
    render(<DefaultReminderSlots initialSlots={["1d", "1hr"]} />);

    fireEvent.click(screen.getByRole("button", { name: /5 days before/i }));

    await waitFor(() => expect(screen.getByText("Saved.")).toBeInTheDocument());
    // **A `role="status"` region**, so a screen reader announces it without the focus
    // moving. No emoji, no celebration.
    const status = document.querySelector('[role="status"]');
    expect(status).not.toBeNull();
    expect(status?.textContent).toBe("Saved.");
  });

  it("keeps the chosen state when the save fails", async () => {
    PUT.mockRejectedValue(new Error("offline"));

    render(<DefaultReminderSlots initialSlots={["1d", "1hr"]} />);

    fireEvent.click(screen.getByRole("button", { name: /5 days before/i }));

    await waitFor(() =>
      expect(
        screen.getByText("Couldn't save. We'll try again on your next change."),
      ).toBeInTheDocument(),
    );
    // **The chip is still chosen.** The copy promises a retry on the next change, and
    // that promise is only true if the state survived.
    expect(screen.getByRole("button", { name: /5 days before/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("shows the failure line verbatim, and not the quiet-hours one", async () => {
    PUT.mockResolvedValue({ data: undefined, response: { status: 500 } });

    render(<DefaultReminderSlots initialSlots={["1d", "1hr"]} />);

    fireEvent.click(screen.getByRole("button", { name: /5 days before/i }));

    await waitFor(() =>
      expect(
        screen.getByText("Couldn't save. We'll try again on your next change."),
      ).toBeInTheDocument(),
    );
    // **The two routes say different things**, and this route says the longer one.
    expect(screen.queryByText("Couldn't save.")).toBeNull();
  });
});

/* ── the quiet hours window ──────────────────────────────────────────────────── */

describe("the quiet hours window", () => {
  it("saves the window on change, and sends only the window", async () => {
    render(<QuietHoursWindow initialStart="22:00:00" initialEnd="08:00:00" />);

    fireEvent.change(screen.getByLabelText("Starts"), { target: { value: "21:00" } });

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    const body = PUT.mock.calls[0]?.[1]?.body;
    expect(body).toEqual({ quiet_hours: { start: "21:00", end: "08:00" } });
    // **The default plan and the digest schedule are omitted** — a payload that
    // re-sent the slots on every window change would be a payload that could rewrite
    // the user's default plan by accident.
    expect(body).not.toHaveProperty("default_reminder_slots");
    expect(body).not.toHaveProperty("digest");
  });

  it("does not save a half-changed window", async () => {
    render(<QuietHoursWindow initialStart="22:00:00" initialEnd="08:00:00" />);

    // **A window with one end missing is not a window.** The server would refuse it, so
    // the client does not send it.
    fireEvent.change(screen.getByLabelText("Starts"), { target: { value: "" } });

    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(PUT).not.toHaveBeenCalled();
  });

  it("keeps the chosen window when the save fails", async () => {
    PUT.mockRejectedValue(new Error("offline"));

    render(<QuietHoursWindow initialStart="22:00:00" initialEnd="08:00:00" />);

    fireEvent.change(screen.getByLabelText("Starts"), { target: { value: "21:00" } });

    await waitFor(() => expect(screen.getByText("Couldn't save.")).toBeInTheDocument());
    // **The user's own clock is still there.**
    expect(screen.getByLabelText("Starts")).toHaveValue("21:00");
  });

  it("shows the shorter failure line, verbatim", async () => {
    PUT.mockRejectedValue(new Error("offline"));

    render(<QuietHoursWindow initialStart="22:00:00" initialEnd="08:00:00" />);

    fireEvent.change(screen.getByLabelText("Starts"), { target: { value: "21:00" } });

    await waitFor(() => expect(screen.getByText("Couldn't save.")).toBeInTheDocument());
    // **The reminders route's longer line does not belong here.**
    expect(screen.queryByText("Couldn't save. We'll try again on your next change.")).toBeNull();
  });

  it("shows the saved window, quiet", async () => {
    render(<QuietHoursWindow initialStart="22:00:00" initialEnd="08:00:00" />);

    fireEvent.change(screen.getByLabelText("Starts"), { target: { value: "21:00" } });

    await waitFor(() => expect(screen.getByText("Saved.")).toBeInTheDocument());
  });
});

/* ── the delivery time ───────────────────────────────────────────────────────── */

describe("the digest delivery time", () => {
  it("saves the time with the zone, and sends only the schedule", async () => {
    render(
      <DigestDeliveryTime initialDeliveryTime="09:00:00" initialTimezone="America/New_York" />,
    );

    fireEvent.change(screen.getByLabelText("Delivery time"), { target: { value: "08:00" } });

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    const body = PUT.mock.calls[0]?.[1]?.body;
    // **The zone travels with the time.** `DigestScheduleIn` says it plainly: "Both or
    // neither. A wall clock without its zone is not a schedule."
    expect(body).toEqual({
      digest: { delivery_time: "08:00", timezone: "America/New_York" },
    });
    expect(body).not.toHaveProperty("quiet_hours");
    expect(body).not.toHaveProperty("default_reminder_slots");
  });

  it("keeps the chosen time when the save fails", async () => {
    PUT.mockRejectedValue(new Error("offline"));

    render(
      <DigestDeliveryTime initialDeliveryTime="09:00:00" initialTimezone="America/New_York" />,
    );

    fireEvent.change(screen.getByLabelText("Delivery time"), { target: { value: "08:00" } });

    await waitFor(() => expect(screen.getByText("Couldn't save.")).toBeInTheDocument());
    expect(screen.getByLabelText("Delivery time")).toHaveValue("08:00");
  });

  it("does not save an emptied input", async () => {
    render(
      <DigestDeliveryTime initialDeliveryTime="09:00:00" initialTimezone="America/New_York" />,
    );

    fireEvent.change(screen.getByLabelText("Delivery time"), { target: { value: "" } });

    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(PUT).not.toHaveBeenCalled();
  });
});

/* ── the API's own verdict ──────────────────────────────────────────────────── */

describe("the API's own verdict", () => {
  it("shows the server's refusal, verbatim, on the quiet window", async () => {
    // **The full-day window is the server's refusal.** `start == end` is the absence
    // of a window, not a window, and the server says so in a message written for the
    // user: *"A quiet window needs a start and an end that differ."*
    //
    // **The generic line would throw that away**, and the user would be left with
    // "Couldn't save." and no idea what to change — on a screen whose only two
    // controls are two clocks.
    PUT.mockResolvedValue(
      refusal("invalid_quiet_hours_window", "A quiet window needs a start and an end that differ."),
    );

    render(<QuietHoursWindow initialStart="22:00:00" initialEnd="08:00:00" />);

    // **The end is moved onto the start**, which is the full-day window: the same clock
    // twice. (A time input only fires a change when its value actually changes, so this
    // is the end clock that moves — and it is the realistic way to reach the refusal.)
    fireEvent.change(screen.getByLabelText("Ends"), { target: { value: "22:00" } });

    await waitFor(() =>
      expect(
        screen.getByText("A quiet window needs a start and an end that differ."),
      ).toBeInTheDocument(),
    );
    // **The generic line is not shown as well** — the API's verdict replaces it, rather
    // than joining it.
    expect(screen.queryByText("Couldn't save.")).toBeNull();
  });

  it("shows the server's refusal, verbatim, on the delivery time", async () => {
    PUT.mockResolvedValue(
      refusal("invalid_digest_schedule", "That schedule is not a time in that zone."),
    );

    render(
      <DigestDeliveryTime initialDeliveryTime="09:00:00" initialTimezone="America/New_York" />,
    );

    fireEvent.change(screen.getByLabelText("Delivery time"), { target: { value: "08:00" } });

    await waitFor(() =>
      expect(screen.getByText("That schedule is not a time in that zone.")).toBeInTheDocument(),
    );
    expect(screen.queryByText("Couldn't save.")).toBeNull();
  });

  it("shows the server's refusal, verbatim, on the default plan", async () => {
    PUT.mockResolvedValue(refusal("invalid_reminder_plan", "That plan has too many reminders."));

    render(<DefaultReminderSlots initialSlots={["1d", "1hr"]} />);

    fireEvent.click(screen.getByRole("button", { name: /5 days before/i }));

    await waitFor(() =>
      expect(screen.getByText("That plan has too many reminders.")).toBeInTheDocument(),
    );
    // **The reminders route's own line does not appear** — the API's verdict replaced
    // it.
    expect(screen.queryByText("Couldn't save. We'll try again on your next change.")).toBeNull();
  });

  it("keeps the user's own clock when the server refuses the window", async () => {
    PUT.mockResolvedValue(
      refusal("invalid_quiet_hours_window", "A quiet window needs a start and an end that differ."),
    );

    render(<QuietHoursWindow initialStart="22:00:00" initialEnd="08:00:00" />);

    fireEvent.change(screen.getByLabelText("Ends"), { target: { value: "22:00" } });

    await waitFor(() =>
      expect(
        screen.getByText("A quiet window needs a start and an end that differ."),
      ).toBeInTheDocument(),
    );
    // **The user's clock is still theirs.** A refusal does not undo what they typed.
    expect(screen.getByLabelText("Ends")).toHaveValue("22:00");
  });

  it("falls back to the route's own line when the API says nothing", async () => {
    // **The request never reached the API**, so there is nothing to quote — and the
    // route's own line is the honest one, because nothing was refused.
    PUT.mockRejectedValue(new Error("offline"));

    render(<QuietHoursWindow initialStart="22:00:00" initialEnd="08:00:00" />);

    fireEvent.change(screen.getByLabelText("Starts"), { target: { value: "21:00" } });

    await waitFor(() => expect(screen.getByText("Couldn't save.")).toBeInTheDocument());
  });
});

/* ── the in-flight affordance ────────────────────────────────────────────────── */

describe("the in-flight affordance", () => {
  it("shows a static dot, never a spinner", async () => {
    // **The product bans spinners.** `EXPERIENCE.md`: "No spinners, anywhere. A
    // spinner is a visual urgency badge." The architecture test plants `animate-spin`
    // as a must-fail fixture. So the in-flight state is the form the spec itself
    // specifies for reduced motion: a static dot.
    let resolvePut: (value: unknown) => void = () => {};
    PUT.mockReturnValue(
      new Promise((resolve) => {
        resolvePut = resolve;
      }),
    );

    render(<DefaultReminderSlots initialSlots={["1d"]} />);
    fireEvent.click(screen.getByRole("button", { name: /5 days before/i }));

    await waitFor(() => expect(document.querySelector("[data-saving-dot]")).not.toBeNull());
    const dot = document.querySelector("[data-saving-dot]");
    expect(dot?.className).toContain("rounded-full");
    // **A static dot.** Nothing animates.
    expect(dot?.className).not.toContain("animate-");
    expect(dot?.getAttribute("aria-hidden")).toBe("true");

    resolvePut(answer());
    await waitFor(() => expect(document.querySelector("[data-saving-dot]")).toBeNull());
  });
});
