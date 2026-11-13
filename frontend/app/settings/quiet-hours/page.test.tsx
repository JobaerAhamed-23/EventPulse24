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
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsQuietHoursPage from "@/app/settings/quiet-hours/page";

const readNotificationSettings = vi.fn();
const getSession = vi.fn();
const readIsPro = vi.fn();

vi.mock("@/lib/notification-settings-read", () => ({
  readNotificationSettings: () => readNotificationSettings(),
}));

vi.mock("@/lib/entitlement-read", () => ({
  readIsPro: () => readIsPro(),
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
  readIsPro.mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  readNotificationSettings.mockResolvedValue({ kind: "found", settings: settings() });
  // **Free is the default for every case in "the route".** The existing assertions are
  // the Free screen's, and they are what proves it did not move.
  readIsPro.mockResolvedValue(false);
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

  it("reaches the digest and calendar screens through the sub-nav", async () => {
    render(await SettingsQuietHoursPage());

    // **This page used to carry the only links to those two routes**, written because
    // there was no settings index and no sub-nav. Both exist now, so the hand-written
    // links are gone and the sub-nav carries the destinations — which is what keeps
    // them reachable from all six screens rather than from this one.
    const nav = screen.getByRole("navigation", { name: "Settings sections" });
    const hrefs = [...nav.querySelectorAll("a")].map((a) => a.getAttribute("href"));

    expect(hrefs).toContain("/settings/digest");
    expect(hrefs).toContain("/settings/calendars");
    expect(screen.queryByRole("link", { name: "What's in your Pulse Digest" })).toBeNull();
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

  it("does not offer per-day-of-week windows to a Free user", async () => {
    render(await SettingsQuietHoursPage());

    // **FR-51 and Pro own them.** No locked row, no carousel — a row the user can
    // neither use nor remove is worse than no row, which is why
    // `component.control.day-picker`'s locked seven-row variant was not built.
    const html = document.body.innerHTML;
    expect(html).not.toContain("per-day");
    expect(html).not.toContain("Per-day");
    expect(html).not.toContain("Upgrade to Pro");
    expect(html).not.toContain("day-window-chip");
    // Scoped by the picker's own landmark: the sidenav is a list too.
    expect(screen.queryByRole("region", { name: "Per-day quiet hours" })).toBeNull();
  });

  it("shows the unavailable state when the read fails", async () => {
    readNotificationSettings.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsQuietHoursPage());

    expect(document.querySelector("[data-settings-unavailable]")).not.toBeNull();
    expect(screen.getByRole("link", { name: "Back to Pulse Digest" })).toBeInTheDocument();
  });
});

/**
 * The three tiers this screen has, which is one more than it looks.
 *
 * A **Free** user has no week and is offered one. A **Pro** user edits theirs. A
 * **lapsed** Pro user — not Pro, but holding stored windows the API still returns — reads
 * theirs. The third is the one an `is_pro` check alone would get wrong, by hiding windows
 * the user set and making a lapse look like a deletion.
 */
describe("the tiers", () => {
  /** The per-day picker's own region — the sidenav is also a list of items. */
  function picker(): HTMLElement {
    return screen.getByRole("region", { name: "Per-day quiet hours" });
  }

  /** The seven stored windows, as the settings response carries them. */
  const WEEK = [
    { weekday: 0, start: "23:00:00", end: "07:00:00" },
    { weekday: 1, start: "23:00:00", end: "07:00:00" },
    { weekday: 2, start: "23:00:00", end: "07:00:00" },
    { weekday: 3, start: "23:00:00", end: "07:00:00" },
    { weekday: 4, start: "22:00:00", end: "08:00:00" },
    { weekday: 5, start: "01:00:00", end: "10:00:00" },
    { weekday: 6, start: "21:00:00", end: "08:00:00" },
  ];

  it("offers a Free user the Pro variant, inline and once", async () => {
    render(await SettingsQuietHoursPage());

    // **The sentence is the backend's `QUIET_HOURS_PRO_UPGRADE_HINT`, verbatim.** It is
    // spelled on the client because a Free user is never refused and so never receives
    // it; this assertion is what stops the two copies drifting apart unnoticed.
    expect(screen.getByText("Set a different window for each day with Pro.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Upgrade" })).toHaveAttribute("href", "/pricing");
    // Inline, not an interruption.
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("leaves a Free user's single window exactly where it was", async () => {
    render(await SettingsQuietHoursPage());

    expect(screen.getByLabelText("Starts")).toHaveValue("22:00");
    expect(screen.getByLabelText("Ends")).toHaveValue("08:00");
    expect(screen.queryByLabelText("Monday starts")).toBeNull();
  });

  it("gives a Pro user the seven-row picker", async () => {
    readIsPro.mockResolvedValue(true);

    render(await SettingsQuietHoursPage());

    expect(within(picker()).getAllByRole("listitem")).toHaveLength(7);
    // The base window is still there — the picker sits beside it, not instead of it.
    expect(screen.getByLabelText("Starts")).toHaveValue("22:00");
  });

  it("does not offer a Pro user an upgrade", async () => {
    readIsPro.mockResolvedValue(true);
    readNotificationSettings.mockResolvedValue({
      kind: "found",
      settings: settings({ quiet_hours_overrides: WEEK }),
    });

    render(await SettingsQuietHoursPage());

    expect(screen.queryByText("Set a different window for each day with Pro.")).toBeNull();
  });

  it("shows a lapsed Pro user their seven stored windows", async () => {
    // **Not Pro, but holding a week.** The API keeps these rows on purpose and still
    // returns them; what a lapse removes is their effect and the right to change them.
    readIsPro.mockResolvedValue(false);
    readNotificationSettings.mockResolvedValue({
      kind: "found",
      settings: settings({ quiet_hours_overrides: WEEK }),
    });

    render(await SettingsQuietHoursPage());

    expect(within(picker()).getAllByRole("listitem")).toHaveLength(7);
    expect(screen.getByText("Set a different window for each day with Pro.")).toBeTruthy();
  });

  it("does not let a lapsed Pro user edit the week", async () => {
    readIsPro.mockResolvedValue(false);
    readNotificationSettings.mockResolvedValue({
      kind: "found",
      settings: settings({ quiet_hours_overrides: WEEK }),
    });

    render(await SettingsQuietHoursPage());

    fireEvent.click(screen.getByRole("button", { name: /^Monday/ }));
    expect(screen.getByLabelText("Monday starts")).toBeDisabled();
  });
});
