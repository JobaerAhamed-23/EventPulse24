/**
 * `/settings` — the redirect to the first section.
 *
 * **It used to be an index**, and the index was a click between the nav and the setting:
 * a list of sections, leading to a screen whose sub-nav lists the same sections again.
 * These assert what replaced it — that `/settings` renders nothing and forwards to the
 * first section — and, because the destination is derived rather than typed, that it
 * cannot drift away from the list.
 */
import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsIndexPage from "@/app/settings/page";
import { SETTINGS_DEFAULT_HREF, SETTINGS_SECTIONS } from "@/lib/settings-sections";

const redirect = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
  redirect: (destination: string) => redirect(destination),
}));

beforeEach(() => {
  redirect.mockReset();
});

describe("the settings index", () => {
  it("redirects to the first section", async () => {
    await SettingsIndexPage();

    expect(redirect).toHaveBeenCalledWith(SETTINGS_SECTIONS[0].href);
  });

  it("redirects to the section the list names as the default", async () => {
    // The destination is derived from the list, so reordering the list moves it. A
    // hard-coded route here would pass while the real page pointed somewhere else.
    await SettingsIndexPage();

    expect(redirect).toHaveBeenCalledWith(SETTINGS_DEFAULT_HREF);
  });

  it("redirects whoever asks, signed in or not", async () => {
    // It reads no session: the section it forwards to runs `homeRoute` itself, so an
    // anonymous visitor lands on `/preview` by way of one extra hop rather than by a
    // second copy of the same rule here.
    await SettingsIndexPage();

    expect(redirect).toHaveBeenCalledTimes(1);
  });

  it("renders no index of its own", async () => {
    // The sub-nav on the destination *is* the index now. A list here as well would be
    // the same sections on the screen twice, one click apart.
    //
    // `redirect` is mocked, so the component returns instead of throwing, and what it
    // returns must be nothing.
    const { container } = render(await SettingsIndexPage());

    expect(container.textContent).toBe("");
    expect(container.querySelector("a")).toBeNull();
  });
});

describe("the default section", () => {
  it("is the first in the list", () => {
    expect(SETTINGS_DEFAULT_HREF).toBe(SETTINGS_SECTIONS[0].href);
  });

  it("is a section, not a route invented for the redirect", () => {
    expect(SETTINGS_SECTIONS.map((section) => section.href)).toContain(SETTINGS_DEFAULT_HREF);
  });
});
