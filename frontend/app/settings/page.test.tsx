/**
 * `/settings` — the settings index.
 *
 * **The route that did not exist**, and whose absence made four of six settings screens
 * unreachable by clicking. These assert the two things the index is for: it lists every
 * section, and each row goes to the section it names.
 */
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsIndexPage from "@/app/settings/page";
import { SETTINGS_SECTIONS } from "@/lib/settings-sections";

const getSession = vi.fn();
const redirect = vi.fn();

vi.mock("@/lib/session", async () => {
  const actual = await vi.importActual<typeof import("@/lib/session")>("@/lib/session");
  return { ...actual, getSession: () => getSession() };
});

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
  redirect: (destination: string) => redirect(destination),
}));

const USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "maya@example.test",
  onboarding: { completed: true, current_step: null },
};

beforeEach(() => {
  getSession.mockReset();
  redirect.mockReset();
  getSession.mockResolvedValue({ kind: "signed-in", user: USER });
});

describe("the index", () => {
  it("lists every settings section", async () => {
    render(await SettingsIndexPage());

    for (const section of SETTINGS_SECTIONS) {
      const link = screen.getAllByRole("link").find((a) => a.getAttribute("href") === section.href);
      expect(link, section.href).toBeDefined();
      expect(link?.textContent, section.href).toContain(section.label);
      expect(link?.textContent, section.href).toContain(section.description);
    }
  });

  it("lists the sections in the order the list declares", async () => {
    render(await SettingsIndexPage());

    const hrefs = screen
      .getAllByRole("link")
      .map((a) => a.getAttribute("href") ?? "")
      .filter((href) => href.startsWith("/settings/"));

    expect(hrefs).toEqual(SETTINGS_SECTIONS.map((section) => section.href));
  });

  it("renders no section twice", async () => {
    render(await SettingsIndexPage());

    // The index and the sub-nav render the same list, and mounting both here would put
    // every destination on the screen twice. The index renders the long form only.
    const hrefs = screen
      .getAllByRole("link")
      .map((a) => a.getAttribute("href") ?? "")
      .filter((href) => href.startsWith("/settings/"));

    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it("does not mount the sub-nav, which would be the same six links again", async () => {
    render(await SettingsIndexPage());

    expect(screen.queryByRole("navigation", { name: "Settings sections" })).toBeNull();
  });

  it("names itself Settings", async () => {
    render(await SettingsIndexPage());

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Settings");
  });

  it("sends a visitor who is not signed in away, rather than listing an account", async () => {
    getSession.mockResolvedValue({ kind: "anonymous" });

    await SettingsIndexPage();

    expect(redirect).toHaveBeenCalled();
  });
});

describe("the section list", () => {
  it("is a list, so a screen reader can count it", async () => {
    render(await SettingsIndexPage());

    const items = screen
      .getAllByRole("listitem")
      .filter((item) => item.querySelector('a[href^="/settings/"]') !== null);

    expect(items).toHaveLength(SETTINGS_SECTIONS.length);
    for (const item of items) {
      expect(within(item).getAllByRole("link")).toHaveLength(1);
    }
  });
});
