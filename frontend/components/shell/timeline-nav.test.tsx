import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BottomTabNav } from "@/components/shell/bottom-tab-nav";
import { Sidenav } from "@/components/shell/sidenav";

/**
 * The Timeline's place in the navigation.
 *
 * **The Timeline is a real route now.** It was a "Coming soon" span when it was a
 * design; it is a link now that the screen exists. **A link to a 404 is a lie about
 * where the label goes**, and an inert row is a `<span>` with `aria-disabled` rather
 * than an anchor — so this pins both halves: Timeline is a link, and the three routes
 * that still do not exist are not.
 *
 * **The two rails carry the same route in different geometry.** The sidenav is a
 * vertical list; the bottom tab is a five-slot bar. Both must offer Timeline as a
 * link, and both must mark the current route with `aria-current="page"`.
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

describe("the sidenav", () => {
  it("links Timeline to the screen", () => {
    render(<Sidenav name="Maya" email="maya@example.test" />);

    const item = [...sidenavRail().querySelectorAll("li")].find((li) =>
      [...li.querySelectorAll("span")].some((span) => span.textContent?.trim() === "Timeline"),
    );
    expect(item).not.toBeUndefined();
    expect(item?.querySelector("a")?.getAttribute("href")).toBe("/timeline");
    expect(item?.textContent).not.toContain("Coming soon");
  });

  it("marks Timeline as the current route when it is", () => {
    render(<Sidenav name="Maya" email="maya@example.test" />);

    const link = [...sidenavRail().querySelectorAll("a")].find(
      (anchor) => anchor.getAttribute("href") === "/timeline",
    );
    expect(link?.getAttribute("aria-current")).toBe("page");
  });

  it("does not mark Timeline as the current route on another page", () => {
    pathname.mockReturnValue("/");

    render(<Sidenav name="Maya" email="maya@example.test" />);

    const link = [...sidenavRail().querySelectorAll("a")].find(
      (anchor) => anchor.getAttribute("href") === "/timeline",
    );
    expect(link?.getAttribute("aria-current")).toBeNull();
  });

  it("leaves the three routes that do not exist inert", () => {
    render(<Sidenav name="Maya" email="maya@example.test" />);

    for (const label of ["Browse", "Conflicts", "Settings"]) {
      const item = [...sidenavRail().querySelectorAll("li")].find((li) =>
        [...li.querySelectorAll("span")].some((span) => span.textContent?.trim() === label),
      );
      expect(item?.querySelector("a"), label).toBeNull();
      expect(item?.querySelector("[aria-disabled='true']"), label).not.toBeNull();
    }
  });
});

describe("the bottom tab", () => {
  it("links Timeline to the screen", () => {
    render(<BottomTabNav name="Maya" email="maya@example.test" />);

    const link = screen.getByRole("link", { name: "Timeline" });
    expect(link).toHaveAttribute("href", "/timeline");
  });

  it("marks Timeline as the current route when it is", () => {
    render(<BottomTabNav name="Maya" email="maya@example.test" />);

    expect(screen.getByRole("link", { name: "Timeline" }).getAttribute("aria-current")).toBe(
      "page",
    );
  });

  it("keeps the three routes that do not exist inert", () => {
    render(<BottomTabNav name="Maya" email="maya@example.test" />);

    for (const label of ["Conflicts", "Settings"]) {
      expect(screen.queryByRole("link", { name: label }), label).toBeNull();
      const slot = bottomBar().querySelector(`[aria-disabled="true"]`);
      expect(slot, label).not.toBeNull();
    }
  });

  it("keeps Add a control, because it opens the create sheet rather than routing", () => {
    render(<BottomTabNav name="Maya" email="maya@example.test" />);

    const add = screen.getByRole("button", { name: "Add personal event" });
    expect(add).toHaveAttribute("aria-haspopup", "dialog");
  });
});
