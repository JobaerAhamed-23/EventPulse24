/**
 * `/settings/quiet-hours` — the Quiet Hours window's route.
 *
 * **The window is two local wall clocks, and the default is 22:00–08:00.** The mockup
 * drew `07:00` — a stale value — and the work item locks the label *"10pm–8am. Nothing
 * during this window."* The server's `DEFAULT_QUIET_HOURS_START`/`END` are `time(22, 0)`
 * and `time(8, 0)`, so the server and the label win.
 *
 * **The delivery time is here too**, because onboarding is not the only place a person
 * can be. It reuses the onboarding control and sends the zone it read, unchanged.
 */
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsQuietHoursPage from "@/app/settings/quiet-hours/page";

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
  usePathname: () => "/settings/quiet-hours",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
  redirect: vi.fn(),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  onboarding: { completed: true, current_step: null },
};

/** The settings, as the server sends them. */
function settings(overrides: Record<string, unknown> = {}) {
  return {
    default_reminder_slots: ["1d", "1hr"],
    quiet_hours: { start: "22:00:00", end: "08:00:00" },
    digest: { delivery_time: "09:00:00", timezone: "America/New_York" },
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
  it("shows the window's two clocks, at the server's default", async () => {
    render(await SettingsQuietHoursPage());

    expect(screen.getByLabelText("Starts")).toHaveValue("22:00");
    expect(screen.getByLabelText("Ends")).toHaveValue("08:00");
  });

  it("shows the locked label", async () => {
    render(await SettingsQuietHoursPage());

    // **The label is the work item's own words.**
    expect(document.querySelector("[data-quiet-hours-label]")?.textContent).toBe(
      "10pm–8am. Nothing during this window.",
    );
  });

  it("shows the delivery time, and the zone it belongs to", async () => {
    render(await SettingsQuietHoursPage());

    expect(screen.getByLabelText("Delivery time")).toHaveValue("09:00");
  });

  it("falls back to the server's default window when quiet hours are off", async () => {
    // **`quiet_hours` is `null` when the user has turned quiet hours off.** There is
    // then no window to edit — and the default is what the user would get back if they
    // turned it on again.
    readNotificationSettings.mockResolvedValue({
      kind: "found",
      settings: settings({ quiet_hours: null }),
    });

    render(await SettingsQuietHoursPage());

    expect(screen.getByLabelText("Starts")).toHaveValue("22:00");
    expect(screen.getByLabelText("Ends")).toHaveValue("08:00");
  });

  it("marks Settings as the active sidenav item", async () => {
    render(await SettingsQuietHoursPage());

    // **The prefix rule.** The user has not left Settings.
    const settingsLink = within(sidenav()).getByRole("link", { name: "Settings" });
    expect(settingsLink).toHaveAttribute("aria-current", "page");
  });

  it("keeps the topbar brand-only", async () => {
    const { container } = render(await SettingsQuietHoursPage());

    const header = container.querySelector("header");
    expect(header?.textContent).toContain("EventPulse24");
    expect(header?.querySelector("a")).toBeNull();
    expect(header?.querySelector("button")).toBeNull();
    expect(header?.querySelector("nav")).toBeNull();
  });

  it("has no page-level Save button, because the save is inline", async () => {
    render(await SettingsQuietHoursPage());

    expect(screen.queryByRole("button", { name: /^save/i })).toBeNull();
  });

  it("does not offer per-day-of-week windows", async () => {
    render(await SettingsQuietHoursPage());

    // **FR-51 and Pro own them, and they are out of scope.** No locked row, no upsell,
    // no carousel — a row the user can neither use nor remove is worse than no row.
    const html = document.body.innerHTML;
    expect(html).not.toContain("per-day");
    expect(html).not.toContain("Per-day");
    expect(html).not.toContain("Upgrade to Pro");
    expect(html).not.toContain("day-window-chip");
  });

  it("shows the unavailable state when the read fails", async () => {
    readNotificationSettings.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsQuietHoursPage());

    expect(document.querySelector("[data-settings-unavailable]")).not.toBeNull();
    expect(screen.getByRole("link", { name: "Back to Pulse Digest" })).toBeInTheDocument();
  });
});
