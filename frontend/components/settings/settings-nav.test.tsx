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
import { SETTINGS_DEFAULT_HREF, SETTINGS_SECTIONS } from "@/lib/settings-sections";

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

  it("marks the section the index forwards to, because that is what it renders", () => {
    /**
     * `/settings` is not a section — it redirects to `SETTINGS_DEFAULT_HREF`. But the
     * redirect is a *server* redirect, and during the forward the browser's pathname is
     * still `/settings` while the server has already rendered the default section's
     * markup.
     *
     * So the server marks the default section and the client — reading `/settings` —
     * would mark nothing, and the two disagree. That disagreement is a hydration
     * mismatch, and React reports it: the differing `aria-current` and the differing
     * `className` on the row.
     *
     * It was found by a browser probe that simulated the Dark Reader extension, because
     * the extension's DOM rewrite shifts the hydration timing enough to surface the
     * race — but nothing about it is about the extension, and it would surface for any
     * reader whose hydration is disturbed.
     *
     * So the index marks the section it is forwarding to. The row the reader sees as
     * current is the row they are about to arrive at, and the server and the client
     * agree.
     */
    pathname.mockReturnValue("/settings");

    render(<SettingsNav />);

    const current = [...nav().querySelectorAll("[aria-current='page']")];
    expect(current).toHaveLength(1);
    expect(current[0]?.getAttribute("href")).toBe(SETTINGS_DEFAULT_HREF);
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
