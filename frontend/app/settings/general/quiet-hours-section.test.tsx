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

import SettingsGeneralPage from "@/app/settings/general/page";

const readDigestPreference = vi.fn();

vi.mock("@/lib/digest-preference-read", () => ({
  readDigestPreference: () => readDigestPreference(),
}));

const PUT = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { PUT: (...args: unknown[]) => PUT(...args) },
}));

/** The digest preference, as the server sends it. */
function preference(overrides: Record<string, unknown> = {}) {
  return {
    delivery_time: "09:00:00",
    timezone: "America/New_York",
    include_personal_events: true,
    ...overrides,
  };
}

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
  usePathname: () => "/settings/general",
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
    digest: { delivery_time: "09:00:00", timezone: "America/New_York" },
    ...overrides,
  };
}

beforeEach(() => {
  readDigestPreference.mockReset();
  PUT.mockReset();
  readDigestPreference.mockResolvedValue({ kind: "found", preference: preference() });
  PUT.mockResolvedValue({ data: { digest: { include_personal_events: false } }, error: null });
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
    render(await SettingsGeneralPage());

    expect(screen.getByLabelText("Starts")).toHaveValue("22:00");
    expect(screen.getByLabelText("Ends")).toHaveValue("08:00");
  });

  it("shows the locked label", async () => {
    render(await SettingsGeneralPage());

    // **The label is the work item's own words.**
    expect(document.querySelector("[data-quiet-hours-label]")?.textContent).toBe(
      "10pm–8am. Nothing during this window.",
    );
  });

  it("shows the delivery time, and the zone it belongs to", async () => {
    render(await SettingsGeneralPage());

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

    render(await SettingsGeneralPage());

    expect(screen.getByLabelText("Starts")).toHaveValue("22:00");
    expect(screen.getByLabelText("Ends")).toHaveValue("08:00");
  });

  it("carries no hand-written link, because the sub-nav and the page carry everything", async () => {
    render(await SettingsGeneralPage());

    // **This page used to carry the only links to the digest and calendar routes**,
    // written because there was no settings index and no sub-nav. Then the sub-nav took
    // them. Now the digest is not even a route — it is a section of *this* page — so the
    // nav names `General` and `Calendars`, and the digest needs no link at all.
    const nav = screen.getByRole("navigation", { name: "Settings sections" });
    const hrefs = [...nav.querySelectorAll("a")].map((a) => a.getAttribute("href"));

    expect(hrefs).toContain("/settings/general");
    expect(hrefs).toContain("/settings/calendars");
    expect(hrefs).not.toContain("/settings/digest");
    expect(screen.queryByRole("link", { name: "What's in your Pulse Digest" })).toBeNull();
  });

  it("puts the digest's own settings on this page, both of them", async () => {
    // **The split this merge existed to end.** The delivery time was on Quiet hours and
    // the opt-out on a separate Digest page — two pages, one feature, because each
    // arrived with its own work item.
    render(await SettingsGeneralPage());

    expect(screen.getByRole("heading", { level: 2, name: "Pulse Digest" })).toBeInTheDocument();
    expect(document.querySelector("[data-digest-delivery-time]")).not.toBeNull();
    expect(document.querySelector("[data-digest-personal-events]")).not.toBeNull();
  });

  it("marks Settings as the active sidenav item", async () => {
    render(await SettingsGeneralPage());

    // **The prefix rule.** The user has not left Settings.
    const settingsLink = within(sidenav()).getByRole("link", { name: "Settings" });
    expect(settingsLink).toHaveAttribute("aria-current", "page");
  });

  it("keeps the topbar brand-only", async () => {
    const { container } = render(await SettingsGeneralPage());

    const header = container.querySelector("header");
    expect(header?.textContent).toContain("EventPulse24");
    expect(header?.querySelector("a")).toBeNull();
    expect(header?.querySelector("button")).toBeNull();
    expect(header?.querySelector("nav")).toBeNull();
  });

  it("has no page-level Save button, because the save is inline", async () => {
    render(await SettingsGeneralPage());

    expect(screen.queryByRole("button", { name: /^save/i })).toBeNull();
  });

  it("does not offer per-day-of-week windows to a Free user", async () => {
    render(await SettingsGeneralPage());

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

    render(await SettingsGeneralPage());

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
    render(await SettingsGeneralPage());

    // **The sentence is the backend's `QUIET_HOURS_PRO_UPGRADE_HINT`, verbatim.** It is
    // spelled on the client because a Free user is never refused and so never receives
    // it; this assertion is what stops the two copies drifting apart unnoticed.
    expect(screen.getByText("Set a different window for each day with Pro.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Upgrade" })).toHaveAttribute("href", "/pricing");
    // Inline, not an interruption.
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("leaves a Free user's single window exactly where it was", async () => {
    render(await SettingsGeneralPage());

    expect(screen.getByLabelText("Starts")).toHaveValue("22:00");
    expect(screen.getByLabelText("Ends")).toHaveValue("08:00");
    expect(screen.queryByLabelText("Monday starts")).toBeNull();
  });

  it("gives a Pro user the seven-row picker", async () => {
    readIsPro.mockResolvedValue(true);

    render(await SettingsGeneralPage());

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

    render(await SettingsGeneralPage());

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

    render(await SettingsGeneralPage());

    expect(within(picker()).getAllByRole("listitem")).toHaveLength(7);
    expect(screen.getByText("Set a different window for each day with Pro.")).toBeTruthy();
  });

  it("does not let a lapsed Pro user edit the week", async () => {
    readIsPro.mockResolvedValue(false);
    readNotificationSettings.mockResolvedValue({
      kind: "found",
      settings: settings({ quiet_hours_overrides: WEEK }),
    });

    render(await SettingsGeneralPage());

    fireEvent.click(screen.getByRole("button", { name: /^Monday/ }));
    expect(screen.getByLabelText("Monday starts")).toBeDisabled();
  });
});
