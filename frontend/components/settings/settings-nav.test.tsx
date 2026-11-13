/**
 * `SettingsNav` — the sub-nav every settings screen carries.
 *
 * **It is the component that makes the settings surface navigable**, so what is asserted
 * here is reachability: every section is a link, the current one is marked, and the
 * marking is an ink pill rather than a terracotta fill.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsNav } from "@/components/settings/settings-nav";
import { SETTINGS_SECTIONS } from "@/lib/settings-sections";

const pathname = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => pathname(),
}));

beforeEach(() => {
  pathname.mockReset();
  pathname.mockReturnValue("/settings/reminders");
});

afterEach(cleanup);

/** The sub-nav landmark, by its own label. */
function nav(): HTMLElement {
  return screen.getByRole("navigation", { name: "Settings sections" });
}

describe("the sub-nav", () => {
  it("links to every settings section", () => {
    render(<SettingsNav />);

    const hrefs = [...nav().querySelectorAll("a")].map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual(SETTINGS_SECTIONS.map((section) => section.href));
  });

  it("labels each link with the name of the screen it opens", () => {
    render(<SettingsNav />);

    for (const section of SETTINGS_SECTIONS) {
      const link = screen.getByRole("link", { name: section.label });
      expect(link.getAttribute("href"), section.label).toBe(section.href);
    }
  });

  it("marks the current section, and only it", () => {
    for (const section of SETTINGS_SECTIONS) {
      pathname.mockReturnValue(section.href);

      render(<SettingsNav />);

      const current = [...nav().querySelectorAll("a")].filter(
        (a) => a.getAttribute("aria-current") === "page",
      );
      expect(current, section.href).toHaveLength(1);
      expect(current[0]?.getAttribute("href"), section.href).toBe(section.href);
      cleanup();
    }
  });

  it("marks nothing on the index, which is not a section", () => {
    // The index renders the long-form list and does not mount this component — but the
    // rule is the component's, not the page's: `/settings` is not one of the six, and
    // an equality rather than a prefix is what keeps it from lighting one up.
    pathname.mockReturnValue("/settings");

    render(<SettingsNav />);

    expect(nav().querySelectorAll("[aria-current='page']")).toHaveLength(0);
  });

  it("does not mark a section on a route that merely starts like it", () => {
    pathname.mockReturnValue("/settings/reminders/extra");

    render(<SettingsNav />);

    expect(nav().querySelectorAll("[aria-current='page']")).toHaveLength(0);
  });

  it("spends no terracotta on the active pill", () => {
    // `DESIGN.md`: "no terracotta fill on the active route" — "terracotta on a
    // small-control toggle burns the accent on a control used many times per day", and
    // this is such a control six times over. The same rule the sidenav's rail follows.
    render(<SettingsNav />);

    for (const link of nav().querySelectorAll("a")) {
      expect(link.className).not.toContain("terracotta");
    }
  });

  it("is a list, so a screen reader can count the sections", () => {
    render(<SettingsNav />);

    expect(nav().querySelectorAll("li")).toHaveLength(SETTINGS_SECTIONS.length);
  });
});
