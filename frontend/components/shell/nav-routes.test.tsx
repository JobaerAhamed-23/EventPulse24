import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BottomTabNav } from "@/components/shell/bottom-tab-nav";
import { Sidenav } from "@/components/shell/sidenav";

/**
 * The navigation's real routes.
 *
 * **A route that exists is a link; a route that does not is a `<span>`.** Timeline and
 * Conflicts are real screens now, so both are links in both rails. **A link to a 404 is
 * a lie about where the label goes**, and an inert row is a `<span>` with
 * `aria-disabled` rather than an anchor — so this pins both halves: Timeline and
 * Conflicts are links, and the two routes that still do not exist (Browse, Settings)
 * are not.
 *
 * **The two rails carry the same routes in different geometry.** The sidenav is a
 * vertical list; the bottom tab is a five-slot bar. Both must offer the real routes as
 * links, and both must mark the current route with `aria-current="page"`.
 */

const pathname = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => pathname(),
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/components/personal-events-panel", () => ({
  PersonalEventsPanel: () => null,
}));

beforeEach(() => {
  pathname.mockReset();
  pathname.mockReturnValue("/timeline");
});

afterEach(() => {
  cleanup();
});

/** The sidenav's route list. */
function sidenavRail(): HTMLElement {
  return screen.getByRole("complementary", { name: "Primary" });
}

/** The bottom tab's bar. */
function bottomBar(): HTMLElement {
  return screen.getByRole("navigation", { name: "Main" });
}

/** The sidenav row carrying a label. */
function sidenavItem(label: string): HTMLElement | undefined {
  return [...sidenavRail().querySelectorAll("li")].find((li) =>
    [...li.querySelectorAll("span")].some((span) => span.textContent?.trim() === label),
  );
}

describe("the sidenav", () => {
  it("links Timeline to the screen", () => {
    render(<Sidenav name="Maya" email="maya@example.test" />);

    const item = sidenavItem("Timeline");
    expect(item).not.toBeUndefined();
    expect(item?.querySelector("a")?.getAttribute("href")).toBe("/timeline");
    expect(item?.textContent).not.toContain("Coming soon");
  });

  it("links Conflicts to the screen", () => {
    render(<Sidenav name="Maya" email="maya@example.test" />);

    const item = sidenavItem("Conflicts");
    expect(item).not.toBeUndefined();
    expect(item?.querySelector("a")?.getAttribute("href")).toBe("/conflicts");
    // "Coming soon" goes — the screen exists.
    expect(item?.textContent).not.toContain("Coming soon");
  });

  it("marks Timeline as the current route when it is", () => {
    render(<Sidenav name="Maya" email="maya@example.test" />);

    const link = [...sidenavRail().querySelectorAll("a")].find(
      (anchor) => anchor.getAttribute("href") === "/timeline",
    );
    expect(link?.getAttribute("aria-current")).toBe("page");
  });

  it("marks Conflicts as the current route when it is", () => {
    pathname.mockReturnValue("/conflicts");

    render(<Sidenav name="Maya" email="maya@example.test" />);

    const link = [...sidenavRail().querySelectorAll("a")].find(
      (anchor) => anchor.getAttribute("href") === "/conflicts",
    );
    expect(link?.getAttribute("aria-current")).toBe("page");
  });

  it("does not mark Conflicts as the current route on another page", () => {
    pathname.mockReturnValue("/");

    render(<Sidenav name="Maya" email="maya@example.test" />);

    const link = [...sidenavRail().querySelectorAll("a")].find(
      (anchor) => anchor.getAttribute("href") === "/conflicts",
    );
    expect(link?.getAttribute("aria-current")).toBeNull();
  });

  it("leaves the routes that do not exist inert", () => {
    render(<Sidenav name="Maya" email="maya@example.test" />);

    // **Browse is the only route left that does not exist.** Settings has one now —
    // the Default Reminder Plan and the Quiet Hours window.
    for (const label of ["Browse"]) {
      const item = sidenavItem(label);
      expect(item?.querySelector("a"), label).toBeNull();
      expect(item?.querySelector("[aria-disabled='true']"), label).not.toBeNull();
    }
  });

  it("makes Settings a real route, because the settings screens exist", () => {
    render(<Sidenav name="Maya" email="maya@example.test" />);

    const item = sidenavItem("Settings");
    const link = item?.querySelector("a");
    expect(link).not.toBeNull();
    expect(link?.getAttribute("href")).toBe("/settings/reminders");
    expect(item?.querySelector("[aria-disabled='true']")).toBeNull();
  });

  it("marks Settings active on both settings routes", () => {
    // **The prefix rule, like Digest's.** The user has not left Settings on
    // `/settings/quiet-hours`, and a rail that marks nothing active on half of
    // Settings reads as "you have left Settings".
    for (const path of ["/settings/reminders", "/settings/quiet-hours"]) {
      pathname.mockReturnValue(path);

      render(<Sidenav name="Maya" email="maya@example.test" />);

      const link = [...sidenavRail().querySelectorAll("a")].find(
        (anchor) => anchor.getAttribute("href") === "/settings/reminders",
      );
      expect(link?.getAttribute("aria-current"), path).toBe("page");
      cleanup();
    }
  });

  it("does not mark Settings active on another page", () => {
    pathname.mockReturnValue("/");

    render(<Sidenav name="Maya" email="maya@example.test" />);

    const link = [...sidenavRail().querySelectorAll("a")].find(
      (anchor) => anchor.getAttribute("href") === "/settings/reminders",
    );
    expect(link?.getAttribute("aria-current")).toBeNull();
  });
});

describe("the bottom tab", () => {
  it("links Timeline to the screen", () => {
    render(<BottomTabNav name="Maya" email="maya@example.test" />);

    const link = screen.getByRole("link", { name: "Timeline" });
    expect(link).toHaveAttribute("href", "/timeline");
  });

  it("links Conflicts to the screen", () => {
    render(<BottomTabNav name="Maya" email="maya@example.test" />);

    const link = screen.getByRole("link", { name: "Conflicts" });
    expect(link).toHaveAttribute("href", "/conflicts");
  });

  it("marks Timeline as the current route when it is", () => {
    render(<BottomTabNav name="Maya" email="maya@example.test" />);

    expect(screen.getByRole("link", { name: "Timeline" }).getAttribute("aria-current")).toBe(
      "page",
    );
  });

  it("marks Conflicts as the current route when it is", () => {
    pathname.mockReturnValue("/conflicts");

    render(<BottomTabNav name="Maya" email="maya@example.test" />);

    expect(screen.getByRole("link", { name: "Conflicts" }).getAttribute("aria-current")).toBe(
      "page",
    );
  });

  it("keeps the routes that do not exist inert", () => {
    render(<BottomTabNav name="Maya" email="maya@example.test" />);

    // **The mobile rail gets the same treatment as the desktop one.** A route that
    // only exists on desktop is not a route, and the onboarding copy — *"You can
    // change these later in Settings"* — has to be true on a phone too.
    //
    // **Browse is still inert**, and it is the bar's one `aria-disabled` slot — so the
    // assertion is about *Settings* not being one, not about the bar having none.
    const link = screen.getByRole("link", { name: "Settings" });
    expect(link).toHaveAttribute("href", "/settings/reminders");

    const settingsSlot = [...bottomBar().querySelectorAll("a, [aria-disabled]")].find(
      (slot) => slot.textContent?.trim() === "Settings",
    );
    expect(settingsSlot?.getAttribute("aria-disabled")).toBeNull();
  });

  it("marks Settings as the current route on both settings routes", () => {
    for (const path of ["/settings/reminders", "/settings/quiet-hours"]) {
      pathname.mockReturnValue(path);

      render(<BottomTabNav name="Maya" email="maya@example.test" />);

      expect(screen.getByRole("link", { name: "Settings" }).getAttribute("aria-current")).toBe(
        "page",
      );
      cleanup();
    }
  });

  it("keeps Add a control, because it opens the create sheet rather than routing", () => {
    render(<BottomTabNav name="Maya" email="maya@example.test" />);

    const add = screen.getByRole("button", { name: "Add personal event" });
    expect(add).toHaveAttribute("aria-haspopup", "dialog");
  });
});
