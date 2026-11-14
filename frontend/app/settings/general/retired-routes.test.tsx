/**
 * The three retired preferences routes.
 *
 * `/settings/reminders`, `/settings/quiet-hours` and `/settings/digest` were screens of
 * their own until the preferences were merged into `/settings/general`. They still exist,
 * because their URLs are in people's history and in onboarding copy — *"You can change
 * these later in Settings"* pointed at one of them — and a 404 to save three files is a
 * poor trade.
 *
 * What is asserted here is that each one forwards, renders nothing on the way, and lands
 * on **its own section** rather than at the top of a page that is now three times longer.
 */
import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsDigestRedirectPage from "@/app/settings/digest/page";
import SettingsQuietHoursRedirectPage from "@/app/settings/quiet-hours/page";
import SettingsRemindersRedirectPage from "@/app/settings/reminders/page";
import { SETTINGS_GENERAL_ANCHORS } from "@/lib/settings-sections";

const redirect = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings/general",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
  redirect: (destination: string) => redirect(destination),
}));

beforeEach(() => {
  redirect.mockReset();
});

const ROUTES = [
  {
    name: "/settings/reminders",
    page: SettingsRemindersRedirectPage,
    target: SETTINGS_GENERAL_ANCHORS.reminders,
    anchor: "reminders",
  },
  {
    name: "/settings/quiet-hours",
    page: SettingsQuietHoursRedirectPage,
    target: SETTINGS_GENERAL_ANCHORS["quiet-hours"],
    anchor: "quiet-hours",
  },
  {
    name: "/settings/digest",
    page: SettingsDigestRedirectPage,
    target: SETTINGS_GENERAL_ANCHORS.digest,
    anchor: "digest",
  },
];

describe("the retired preferences routes", () => {
  for (const route of ROUTES) {
    it(`${route.name} forwards to its section of /settings/general`, async () => {
      await route.page();

      expect(redirect).toHaveBeenCalledWith(route.target);
    });

    it(`${route.name} lands on an anchor, not the top of the page`, async () => {
      // **The page is three times longer than any of these screens was.** Forwarding to
      // the top would make the visitor hunt for the setting they clicked a link for.
      await route.page();

      expect(redirect).toHaveBeenCalledWith(expect.stringContaining(`#${route.anchor}`));
    });

    it(`${route.name} renders nothing of its own`, async () => {
      // `redirect` is mocked, so the component returns instead of throwing — and what it
      // returns must be nothing. A redirect that also rendered would flash a screen the
      // visitor is about to be moved off, and would fail the route invariant that
      // exempts it from needing a nav row.
      const { container } = render(await route.page());

      expect(container.textContent).toBe("");
    });
  }

  it("sends each route somewhere different", () => {
    // Three routes collapsing onto one anchor would mean two of the three links in the
    // wild quietly stopped meaning what they said.
    const targets = ROUTES.map((route) => route.target);

    expect(new Set(targets).size).toBe(targets.length);
  });
});
