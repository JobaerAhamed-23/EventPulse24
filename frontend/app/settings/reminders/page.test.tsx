/**
 * `/settings/reminders` — the Default Reminder Plan editor's route.
 *
 * **The product's first `/settings/*` route.** The sidenav's Settings entry said
 * "Coming soon" since the shell was built, and the onboarding flow tells the user
 * *"You can change these later in Settings."* This route makes that true.
 *
 * **The three things that matter here.** The route renders the **four chips** (reused
 * from the per-event picker, not copied); it says **plainly** that the default does not
 * change plans already set; and it **saves inline** — there is no Save button.
 */
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsRemindersPage from "@/app/settings/reminders/page";

const readNotificationSettings = vi.fn();
const getSession = vi.fn();

vi.mock("@/lib/notification-settings-read", () => ({
  readNotificationSettings: () => readNotificationSettings(),
}));

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings/reminders",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
  redirect: vi.fn(),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  name: "",
  onboarding: { completed: true, current_step: null },
};

/** The settings, as the server sends them. */
function settings(overrides: Record<string, unknown> = {}) {
  return {
    default_reminder_slots: ["1d", "1hr"],
    quiet_hours: { start: "22:00:00", end: "08:00:00" },
    digest: { delivery_time: "09:00:00", timezone: "UTC" },
    ...overrides,
  };
}

beforeEach(() => {
  readNotificationSettings.mockReset();
  getSession.mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  readNotificationSettings.mockResolvedValue({ kind: "found", settings: settings() });
});

/** The sidenav's rail — scoped, because the page has two navigation landmarks. */
function sidenav(): HTMLElement {
  return screen.getByRole("complementary", { name: "Primary" });
}

describe("the route", () => {
  it("renders the four chips, and only the four", async () => {
    render(await SettingsRemindersPage());

    const chips = document.querySelectorAll("[data-reminder-chip]");
    expect(chips).toHaveLength(4);
    for (const slot of ["5d", "2d", "1d", "1hr"]) {
      expect(document.querySelector(`[data-slot="${slot}"]`)).not.toBeNull();
    }
  });

  it("shows the server's default plan as the selection", async () => {
    render(await SettingsRemindersPage());

    // **The server's answer, not a local default.** The server's default plan is
    // `["1d", "1hr"]`, and those two chips are pressed.
    expect(screen.getByRole("button", { name: /1 day before/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /1 hour before/i })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: /5 days before/i })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("says plainly that it does not change plans already set", async () => {
    render(await SettingsRemindersPage());

    // **The opposite is the natural assumption**, and getting it wrong silently
    // rewrites the user's choices — so the page says which way it goes.
    const note = document.querySelector("[data-default-slots-nonretroactive]");
    expect(note).not.toBeNull();
    expect(note?.textContent).toContain("newly saved events");
    expect(note?.textContent).toContain("does not change");
  });

  it("marks Settings as the active sidenav item", async () => {
    render(await SettingsRemindersPage());

    const settingsLink = within(sidenav()).getByRole("link", { name: "Settings" });
    expect(settingsLink).toHaveAttribute("aria-current", "page");
  });

  it("keeps the topbar brand-only", async () => {
    const { container } = render(await SettingsRemindersPage());

    // **The topbar-quiet rule (ASSUM-11).** The brand mark and the tagline, and
    // nothing else — an action affordance in the topbar is an inversion.
    const header = container.querySelector("header");
    expect(header?.textContent).toContain("EventPulse24");
    expect(header?.querySelector("a")).toBeNull();
    expect(header?.querySelector("button")).toBeNull();
    expect(header?.querySelector("nav")).toBeNull();
  });

  it("has no page-level Save button, because the save is inline", async () => {
    render(await SettingsRemindersPage());

    // **The work item rules one out.** A settings screen that asks for a confirmation
    // of a control the user just pressed is asking for something it does not need.
    expect(screen.queryByRole("button", { name: /^save/i })).toBeNull();
  });

  it("shows the unavailable state when the read fails", async () => {
    readNotificationSettings.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsRemindersPage());

    expect(document.querySelector("[data-settings-unavailable]")).not.toBeNull();
    expect(screen.getByRole("link", { name: "Back to Pulse Digest" })).toBeInTheDocument();
    // **No chips on a page that could not read the plan.**
    expect(document.querySelectorAll("[data-reminder-chip]")).toHaveLength(0);
  });
});
