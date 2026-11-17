/**
 * FR-10's **Pulse Ping switch** — the control onboarding promised.
 *
 * **What is worth proving here is what a screenshot cannot show:**
 *
 * 1. **The body is exactly one key.** The endpoint is a patch, so sending anything else
 *    would quietly rewrite settings this control does not own. The assertion is on the
 *    **exact key set**, not on the presence of `pulse_ping`.
 * 2. **The state after a save is the server's answer**, not the optimistic guess.
 * 3. **A failed save puts the switch back.** The Ping was not turned off, and a control
 *    claiming otherwise claims something that did not happen.
 * 4. **The accessible name is stable** across both states, with the state carried by the
 *    switch's own semantics rather than by colour alone (WCAG 1.4.1).
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PulsePingSwitch } from "@/components/settings/pulse-ping-switch";

const PUT = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { PUT: (...args: unknown[]) => PUT(...args) },
}));

/** The server's answer to the `PUT` — `NotificationSettingsOut`, narrowed to what this reads. */
function answer(pulse_ping: boolean) {
  return { data: { pulse_ping }, error: undefined };
}

function switchControl() {
  return screen.getByRole("button", { name: "Daily Pulse Ping" });
}

beforeEach(() => {
  PUT.mockReset();
});

describe("the switch reports the server's state", () => {
  it("is on when the server says the ping is on", () => {
    render(<PulsePingSwitch initialPulsePing={true} />);

    expect(switchControl()).toHaveAttribute("aria-pressed", "true");
  });

  it("is off when the server says the ping is off", () => {
    render(<PulsePingSwitch initialPulsePing={false} />);

    expect(switchControl()).toHaveAttribute("aria-pressed", "false");
  });

  it("keeps one accessible name in both states", () => {
    const { rerender } = render(<PulsePingSwitch initialPulsePing={true} />);
    expect(switchControl()).toBeInTheDocument();

    rerender(<PulsePingSwitch initialPulsePing={false} />);

    // A name that changed with the state would say both "press me" and "nothing to
    // press" at once.
    expect(switchControl()).toBeInTheDocument();
  });

  it("says the state in words, not only in the control", () => {
    render(<PulsePingSwitch initialPulsePing={false} />);

    expect(
      screen.getByText("No Pulse Ping — your brief is still here when you want it"),
    ).toBeInTheDocument();
  });
});

describe("the save", () => {
  it("sends exactly one key", async () => {
    PUT.mockResolvedValue(answer(false));
    render(<PulsePingSwitch initialPulsePing={true} />);

    fireEvent.click(switchControl());

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    const [path, options] = PUT.mock.calls[0] as [string, { body: Record<string, unknown> }];
    expect(path).toBe("/api/settings/notifications");
    // **The exact key set.** The endpoint is a patch: anything else here would rewrite a
    // setting the user did not touch.
    expect(Object.keys(options.body)).toEqual(["pulse_ping"]);
    expect(options.body.pulse_ping).toBe(false);
  });

  it("turns the ping back on", async () => {
    PUT.mockResolvedValue(answer(true));
    render(<PulsePingSwitch initialPulsePing={false} />);

    fireEvent.click(switchControl());

    await waitFor(() => {
      const [, options] = PUT.mock.calls[0] as [string, { body: Record<string, unknown> }];
      expect(options.body.pulse_ping).toBe(true);
    });
  });

  it("takes the server's answer over its own guess", async () => {
    // The user pressed "off" and the server resolved it as still on. The control must
    // show what the server holds.
    PUT.mockResolvedValue(answer(true));
    render(<PulsePingSwitch initialPulsePing={true} />);

    fireEvent.click(switchControl());

    await waitFor(() => expect(switchControl()).toHaveAttribute("aria-pressed", "true"));
  });

  it("says it saved", async () => {
    PUT.mockResolvedValue(answer(false));
    render(<PulsePingSwitch initialPulsePing={true} />);

    fireEvent.click(switchControl());

    await waitFor(() => expect(screen.getByText("Saved.")).toBeInTheDocument());
  });
});

describe("a save that does not take", () => {
  it("puts the switch back when the API refuses", async () => {
    PUT.mockResolvedValue({ data: undefined, error: { detail: "Nope." } });
    render(<PulsePingSwitch initialPulsePing={true} />);

    fireEvent.click(switchControl());

    await waitFor(() => expect(switchControl()).toHaveAttribute("aria-pressed", "true"));
  });

  it("puts the switch back when the request never arrives", async () => {
    PUT.mockRejectedValue(new Error("offline"));
    render(<PulsePingSwitch initialPulsePing={true} />);

    fireEvent.click(switchControl());

    await waitFor(() => expect(screen.getByText("Couldn't save.")).toBeInTheDocument());
    expect(switchControl()).toHaveAttribute("aria-pressed", "true");
  });
});
