import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PersonalEventRemindersPage from "@/app/personal-events/[id]/reminders/page";

/**
 * FR-20's screen — reminders on a **personal** event.
 *
 * The endpoint accepted `personal_event` from the day it was written and nothing ever
 * sent it: `ReminderPicker` was mounted once, hard-coded to `saved_event`. These tests
 * hold the kind that is sent, because that single string is the whole gap.
 */
const readReminderPlan = vi.fn();
const readDefaultReminderSlots = vi.fn();
const readPersonalEvent = vi.fn();
const getSession = vi.fn();
const homeRoute = vi.fn();

vi.mock("@/lib/reminder-plan-read", () => ({
  readReminderPlan: (...args: unknown[]) => readReminderPlan(...args),
  readDefaultReminderSlots: (...args: unknown[]) => readDefaultReminderSlots(...args),
}));
vi.mock("@/lib/personal-event-read", () => ({
  readPersonalEvent: (...args: unknown[]) => readPersonalEvent(...args),
}));
vi.mock("@/lib/session", () => ({
  getSession: (...args: unknown[]) => getSession(...args),
  homeRoute: (...args: unknown[]) => homeRoute(...args),
}));
vi.mock("@/lib/detail-time", () => ({ browserTimeZone: () => "Europe/London" }));
vi.mock("@/components/shell/app-shell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock("@/components/reminders/reminder-picker", () => ({
  ReminderPicker: (props: { targetId: string; targetKind: string }) => (
    <div data-picker-stub data-target-kind={props.targetKind} data-target-id={props.targetId} />
  ),
}));
vi.mock("@/components/reminders/reminder-states", () => ({
  ReminderStates: (props: { kind: string }) => <div data-reminder-states={props.kind} />,
}));

const EVENT_ID = "6b9f0000-0000-7000-8000-00000000beef";

async function renderPage() {
  const ui = await PersonalEventRemindersPage({ params: Promise.resolve({ id: EVENT_ID }) });
  render(ui);
}

beforeEach(() => {
  readReminderPlan.mockReset();
  readDefaultReminderSlots.mockReset();
  readPersonalEvent.mockReset();
  getSession.mockReset();
  homeRoute.mockReset();

  getSession.mockResolvedValue({ kind: "signed-in", user: { email: "mara.k@example.com" } });
  homeRoute.mockReturnValue(null);
  readReminderPlan.mockResolvedValue({
    kind: "found",
    plan: { slots: ["1d"], deliveries: [] },
  });
  readDefaultReminderSlots.mockResolvedValue(["1d", "1h"]);
  readPersonalEvent.mockResolvedValue({
    kind: "found",
    event: { id: EVENT_ID, name: "Dinner with Rahul" },
  });
});

describe("the personal-event reminder screen", () => {
  it("reads the plan as a personal event, not a saved one", async () => {
    // **The whole gap in one assertion.** The endpoint takes both kinds; the UI only
    // ever sent `saved_event`.
    await renderPage();

    expect(readReminderPlan).toHaveBeenCalledWith("personal_event", EVENT_ID);
  });

  it("gives the picker the personal kind and the event's id", async () => {
    await renderPage();

    const picker = document.querySelector("[data-picker-stub]");
    expect(picker?.getAttribute("data-target-kind")).toBe("personal_event");
    expect(picker?.getAttribute("data-target-id")).toBe(EVENT_ID);
  });

  it("names the event in the crumb and the lede", async () => {
    await renderPage();

    expect(screen.getAllByText(/Dinner with Rahul/).length).toBeGreaterThan(0);
  });

  it("falls back to a neutral name when the event cannot be read", async () => {
    // The plan is still the user's and still editable; only the name is unknown. A
    // screen that refused to render would lose the plan over a missing title.
    readPersonalEvent.mockResolvedValue({ kind: "unavailable" });
    await renderPage();

    expect(screen.getByText(/Reminders for this event/)).toBeInTheDocument();
    expect(document.querySelector("[data-picker-stub]")).not.toBeNull();
  });

  it("shows the plan's own failure state rather than the picker", async () => {
    readReminderPlan.mockResolvedValue({ kind: "missing" });
    await renderPage();

    expect(document.querySelector("[data-reminder-states]")?.getAttribute("data-reminder-states")).toBe(
      "missing",
    );
    expect(document.querySelector("[data-picker-stub]")).toBeNull();
  });

  it("points the crumb at the Timeline, where personal events live", async () => {
    // Not the Digest: the mockup is explicit that a personal event is reached from the
    // Timeline / Add surfaces.
    await renderPage();

    expect(screen.getByRole("link", { name: "Timeline" })).toHaveAttribute("href", "/timeline");
  });
});
