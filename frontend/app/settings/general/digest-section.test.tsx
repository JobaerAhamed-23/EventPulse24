/**
 * `/settings/digest` — the Pulse Digest's own screen.
 *
 * **The screen holds one control**, and the route's job is to put it there honestly:
 * the server's stored value on first paint, the schedule it will have to round-trip,
 * and the failure surface when neither could be read.
 *
 * **The route is the only place that knows how to turn the read into a schedule.** The
 * read hands back two independent nullable fields; the control takes one value — a
 * half-schedule is not a state the server produces. So the tests below pin that join,
 * because a route that passed one half would show a control that could only fail.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsGeneralPage from "@/app/settings/general/page";
import { redirect } from "next/navigation";

const readNotificationSettings = vi.fn();

vi.mock("@/lib/notification-settings-read", () => ({
  readNotificationSettings: () => readNotificationSettings(),
}));

const readIsPro = vi.fn();

vi.mock("@/lib/entitlement-read", () => ({
  readIsPro: () => readIsPro(),
}));

/** The notification settings, as the server sends them. */
function settings(overrides: Record<string, unknown> = {}) {
  return {
    default_reminder_slots: ["1d", "1hr"],
    quiet_hours: { start: "22:00:00", end: "08:00:00" },
    digest: { delivery_time: "09:00:00", timezone: "America/New_York" },
    ...overrides,
  };
}

const readDigestPreference = vi.fn();
const getSession = vi.fn();
const PUT = vi.fn();

vi.mock("@/lib/backend-client", () => ({
  api: { PUT: (...args: unknown[]) => PUT(...args) },
}));

vi.mock("@/lib/digest-preference-read", () => ({
  readDigestPreference: () => readDigestPreference(),
}));

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings/general",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
  /**
   * **The real `redirect` throws, and so does this one.**
   *
   * **A mock that only recorded the call would let the route keep going** — the
   * redirect would be "asserted" while the page went on to render the whole thing
   * anyway. Throwing is what makes the assertion mean what it says: the route
   * stopped at the redirect, and nothing was served.
   */
  redirect: vi.fn(() => {
    throw new Error("NEXT_REDIRECT");
  }),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  name: "",
  onboarding: { completed: true, current_step: null },
};

/** The preference, as the server sends it. */
function preference(overrides: Record<string, unknown> = {}) {
  return {
    delivery_time: "09:00:00",
    timezone: "America/New_York",
    include_personal_events: true,
    ...overrides,
  };
}

beforeEach(() => {
  readNotificationSettings.mockReset();
  readIsPro.mockReset();
  readNotificationSettings.mockResolvedValue({ kind: "found", settings: settings() });
  readIsPro.mockResolvedValue(false);
  readDigestPreference.mockReset();
  getSession.mockReset();
  PUT.mockReset();
  vi.mocked(redirect).mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
  readDigestPreference.mockResolvedValue({ kind: "found", preference: preference() });
  PUT.mockResolvedValue({
    data: { digest: { include_personal_events: false } },
    error: null,
  });
});

/** The sidenav's rail — scoped, because the page has two navigation landmarks. */
function sidenav(): HTMLElement {
  return screen.getByRole("complementary", { name: "Primary" });
}

/** The toggle — the page's one control. */
function toggle(): HTMLElement {
  return screen.getByRole("button", { name: "Personal events in the Pulse Digest" });
}

/**
 * The sidenav's account name.
 *
 * **The only thing that tells the two failure branches apart.** Both render the same
 * `SettingsStates`; what differs is whether the session was answered — and so whether
 * the account row has a name.
 *
 * **The empty name is a real value, so it is read from the attribute rather than from
 * the accessible name** — the accessible-name computation trims the trailing space
 * `"Account: "` carries, so an unnamed account's name would read as `"Account:"`.
 */
function sidenavAccountName(): string {
  const account = within(sidenav()).getByRole("button", { name: /^Account:/ });
  return (account.getAttribute("aria-label") ?? "").replace(/^Account:\s*/, "");
}

describe("the route", () => {
  it("renders the toggle with the server's stored value", async () => {
    render(await SettingsGeneralPage());

    // **The server's answer, not a local default.** The server says personal events are
    // in, so the control reads pressed.
    //
    // The sentence is the row's description now rather than the control's own text —
    // the control is a switch — so it is asserted on the page, which is where a reader
    // finds it.
    expect(toggle()).toHaveAttribute("aria-pressed", "true");
    expect(toggle()).toHaveAttribute("data-state", "on");
    expect(screen.getByText("Personal events are in your Pulse Digest")).toBeInTheDocument();
  });

  it("renders the server's stored opt-out, when the user turned it off", async () => {
    readDigestPreference.mockResolvedValue({
      kind: "found",
      preference: preference({ include_personal_events: false }),
    });

    render(await SettingsGeneralPage());

    expect(toggle()).toHaveAttribute("aria-pressed", "false");
    expect(toggle()).toHaveAttribute("data-state", "off");
    expect(screen.getByText("Personal events are not in your Pulse Digest")).toBeInTheDocument();
  });

  it("gives the toggle the stored schedule, so it can be sent back unchanged", async () => {
    readDigestPreference.mockResolvedValue({
      kind: "found",
      preference: preference(),
    });

    render(await SettingsGeneralPage());

    // **The toggle is enabled, because the schedule is complete.** A control that is
    // disabled on a user who *has* a delivery time would be a control that could never
    // be used.
    expect(toggle()).not.toBeDisabled();

    // **And the schedule's *values* reach the control, not merely the fact of one.**
    //
    // **"Not disabled" is the weakest form this could take** — a route that passed
    // `timezone: "UTC"` and `deliveryTime: "00:00:00"` would satisfy it, and the user
    // would have their digest time rewritten. So the route's schedule is observed the
    // only way it can be: by pressing the control and reading the body it sends.
    fireEvent.click(toggle());

    await waitFor(() => expect(PUT).toHaveBeenCalled());
    expect(PUT.mock.calls[0][1].body).toEqual({
      include_personal_events: false,
      delivery_time: "09:00:00",
      timezone: "America/New_York",
    });
  });

  it("disables the toggle and says why when there is no schedule at all", async () => {
    readDigestPreference.mockResolvedValue({
      kind: "found",
      preference: preference({ delivery_time: null, timezone: null }),
    });

    render(await SettingsGeneralPage());

    // **A user with no `DigestPreference` row.** The endpoint requires the delivery
    // time and the zone, so there is nothing this control could send — and a control
    // that can only fail is worse than one that is honestly unavailable.
    expect(toggle()).toBeDisabled();
    expect(document.querySelector("[data-no-schedule]")?.textContent).toBe(
      "Set your delivery time first.",
    );
  });

  it("disables the toggle when only half the schedule is there", async () => {
    // **A time with no zone.** Not a state the server produces and not one the endpoint
    // accepts — so the route must not present it as a schedule it could round-trip.
    readDigestPreference.mockResolvedValue({
      kind: "found",
      preference: preference({ timezone: null }),
    });

    render(await SettingsGeneralPage());

    expect(toggle()).toBeDisabled();
    // **The same sentence as the no-schedule case, asserted exactly.** A
    // `not.toBeNull()` would pass against an empty element, and an empty element is
    // not an explanation.
    expect(document.querySelector("[data-no-schedule]")?.textContent).toBe(
      "Set your delivery time first.",
    );
  });

  it("disables the toggle when the zone is there but the time is not", async () => {
    // **The other half.** The join is symmetric, and a join that only checked one
    // side would let this through.
    readDigestPreference.mockResolvedValue({
      kind: "found",
      preference: preference({ delivery_time: null }),
    });

    render(await SettingsGeneralPage());

    expect(toggle()).toBeDisabled();
    expect(document.querySelector("[data-no-schedule]")?.textContent).toBe(
      "Set your delivery time first.",
    );
  });

  it("gives the digest its own heading and lede inside the page", async () => {
    render(await SettingsGeneralPage());

    // **The digest is a section now, not a screen.** The page is `General`; the digest
    // is one `<h2>` on it, carrying both of its settings — the delivery time, which used
    // to live on the quiet-hours page, and the opt-out, which had a page of its own.
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("General");
    expect(screen.getByRole("heading", { level: 2, name: "Pulse Digest" })).toBeInTheDocument();
    expect(
      screen.getByText("When your daily brief arrives, and what's in it."),
    ).toBeInTheDocument();
  });

  it("labels the digest section with its own heading, for a screen reader", async () => {
    // The sub-nav rows used to be how a screen reader moved between these settings. On
    // one page that job belongs to the headings, so each section is labelled by its own.
    render(await SettingsGeneralPage());

    const section = document.getElementById("digest");
    expect(section).not.toBeNull();
    expect(section?.getAttribute("aria-labelledby")).toBe("digest-heading");
  });

  it("marks Settings as the active sidenav item", async () => {
    render(await SettingsGeneralPage());

    // **The prefix rule.** The sidenav needs no change for this route.
    const settingsLink = within(sidenav()).getByRole("link", { name: "Settings" });
    expect(settingsLink).toHaveAttribute("aria-current", "page");
  });

  it("has no page-level Save button, because the save is inline", async () => {
    render(await SettingsGeneralPage());

    expect(screen.queryByRole("button", { name: /^save/i })).toBeNull();
  });

  it("keeps the topbar brand-only", async () => {
    const { container } = render(await SettingsGeneralPage());

    const header = container.querySelector("header");
    expect(header?.textContent).toContain("EventPulse24");
    expect(header?.querySelector("a")).toBeNull();
    expect(header?.querySelector("button")).toBeNull();
    expect(header?.querySelector("nav")).toBeNull();
  });

  it("carries exactly one status region in the digest section", async () => {
    render(await SettingsGeneralPage());

    // **One control, one status region** (`detail-mute-control.tsx:215-228`). The rule
    // used to read "one page, one region" because the page held one control. Merged, the
    // digest holds its two — the delivery time and the opt-out — so the count is two,
    // and the rule is restated at the level it was always about: **a region belongs to a
    // control, and the route adds none of its own.**
    const section = document.getElementById("digest");
    expect(section).not.toBeNull();

    for (const control of ["[data-digest-delivery-time]", "[data-digest-personal-events]"]) {
      const element = (section as HTMLElement).querySelector(control);
      expect(element, control).not.toBeNull();
      expect(within(element as HTMLElement).getAllByRole("status"), control).toHaveLength(1);
    }

    // Two controls, two regions: nothing in the section owns a region but a control.
    expect(within(section as HTMLElement).getAllByRole("status")).toHaveLength(2);
  });

  it("shows the unavailable state when the read fails", async () => {
    readDigestPreference.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsGeneralPage());

    expect(document.querySelector("[data-settings-unavailable]")).not.toBeNull();
    expect(screen.getByRole("link", { name: "Back to Pulse Digest" })).toBeInTheDocument();
    // **No toggle on a page that could not read the preference.** A control rendered
    // from a failed read would show a state the server never stated.
    expect(
      screen.queryByRole("button", { name: "Personal events in the Pulse Digest" }),
    ).toBeNull();
  });
});

describe("who gets to be here", () => {
  /**
   * The route up to the point it redirected.
   *
   * **`redirect` throws, so the render rejects.** Catching that rejection is how the
   * test sees what the route did *instead of* serving the page.
   */
  async function renderUntilRedirect(): Promise<void> {
    await expect(SettingsGeneralPage()).rejects.toThrow("NEXT_REDIRECT");
  }

  it("redirects an anonymous visitor to the preview instead of serving the page", async () => {
    getSession.mockResolvedValue({ kind: "anonymous" });

    await renderUntilRedirect();

    // **Asserted as a redirect, not as an absence.** A page that merely failed to render
    // would pass an "is not on the screen" assertion; this one passes only if the route
    // said where to go.
    expect(redirect).toHaveBeenCalledWith("/preview");
    // **And the page was not served.** The read never ran, so no control was rendered.
    expect(readDigestPreference).not.toHaveBeenCalled();
  });

  it("redirects a half-onboarded visitor to onboarding", async () => {
    getSession.mockResolvedValue({
      kind: "signed-in",
      user: { ...USER, onboarding: { completed: false, current_step: "digest" } },
    });

    await renderUntilRedirect();

    expect(redirect).toHaveBeenCalledWith("/onboarding");
    // **And the page was not served.** A half-onboarded user must not see a control
    // that could write a preference before the onboarding they are in the middle of.
    expect(readDigestPreference).not.toHaveBeenCalled();
  });

  it("shows the not-signed-in state when the session could not be answered", async () => {
    // **`homeRoute` sends an unknown session to the home**, not to the preview — a
    // signed-in user is not anonymous because a request failed. So the route renders.
    getSession.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsGeneralPage());

    expect(redirect).not.toHaveBeenCalled();
    expect(document.querySelector("[data-settings-unavailable]")).not.toBeNull();
    // **The account row is nameless here.** This is the step-3 branch, and the only
    // thing that tells it apart from step 4 is the name: the session was never
    // answered, so there is no name to show.
    expect(sidenavAccountName()).toBe("");
  });

  it("shows the account name when the read fails but the session is known", async () => {
    // **Step 4, not step 3.** The session *was* answered, so the account row is named —
    // and that is the only difference between the two failure branches, which render
    // the same `SettingsStates`.
    readDigestPreference.mockResolvedValue({ kind: "unavailable" });

    render(await SettingsGeneralPage());

    expect(document.querySelector("[data-settings-unavailable]")).not.toBeNull();
    expect(sidenavAccountName()).toBe("Maya");
  });
});
