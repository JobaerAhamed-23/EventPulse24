import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BottomTabNav } from "@/components/shell/bottom-tab-nav";
import { Sidenav } from "@/components/shell/sidenav";
import { SETTINGS_SECTIONS } from "@/lib/settings-sections";

/**
 * The navigation's real routes.
 *
 * **A route that exists is a link; a route that does not is a `<span>`.** Every route
 * the product has shipped is a link now — Digest, Timeline, Browse, Conflicts and
 * Settings are all real screens. **A link to a 404 is a lie about where the label
 * goes**, and an inert row is a `<span>` with `aria-disabled` rather than an anchor.
 *
 * **Browse was the last one standing.** It was a `<span aria-disabled="true">` reading
 * "Coming soon" in the sidenav, in the More sheet, and — as the *bottom tab's* Digest
 * slot, which had never been a link since the digest home shipped — in the bar. All
 * three are links now, and the "Coming soon" note is gone from the product.
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

  it("links Browse to the screen, because the Browse surface shipped", () => {
    render(<Sidenav name="Maya" email="maya@example.test" />);

    // **Browse was the last inert row in the rail.** The surface shipped with the
    // Browse read API, so the row is a link to the same `/browse` the mobile More
    // sheet points at — one route, two rails, one destination.
    const item = sidenavItem("Browse");
    expect(item).not.toBeUndefined();
    expect(item?.querySelector("a")?.getAttribute("href")).toBe("/browse");
    expect(item?.querySelector("[aria-disabled='true']")).toBeNull();
    expect(item?.textContent).not.toContain("Coming soon");
  });

  it("marks Browse as the current route when it is", () => {
    pathname.mockReturnValue("/browse");

    render(<Sidenav name="Maya" email="maya@example.test" />);

    const link = [...sidenavRail().querySelectorAll("a")].find(
      (anchor) => anchor.getAttribute("href") === "/browse",
    );
    expect(link?.getAttribute("aria-current")).toBe("page");
  });

  it("does not mark Browse as the current route on another page", () => {
    pathname.mockReturnValue("/");

    render(<Sidenav name="Maya" email="maya@example.test" />);

    const link = [...sidenavRail().querySelectorAll("a")].find(
      (anchor) => anchor.getAttribute("href") === "/browse",
    );
    expect(link?.getAttribute("aria-current")).toBeNull();
  });

  it("points Settings at the index, not at one of the six screens", () => {
    // It pointed at `/settings/reminders` until the index existed, and that screen has
    // no links out — so the rail's Settings row landed the user on one of six settings
    // screens with no way to reach the other five.
    render(<Sidenav name="Maya" email="maya@example.test" />);

    const item = sidenavItem("Settings");
    const link = item?.querySelector("a");
    expect(link).not.toBeNull();
    expect(link?.getAttribute("href")).toBe("/settings");
    expect(item?.querySelector("[aria-disabled='true']")).toBeNull();
  });

  it("marks Settings active on the index and on every section", () => {
    // **The prefix rule, like Digest's** — plus the equality the prefix cannot cover.
    // `"/settings".startsWith("/settings/")` is false, so a bare prefix would drop the
    // highlight on the index: the rail going quiet on the screen it just navigated to.
    for (const path of ["/settings", ...SETTINGS_SECTIONS.map((section) => section.href)]) {
      pathname.mockReturnValue(path);

      render(<Sidenav name="Maya" email="maya@example.test" />);

      const link = [...sidenavRail().querySelectorAll("a")].find(
        (anchor) => anchor.getAttribute("href") === "/settings",
      );
      expect(link?.getAttribute("aria-current"), path).toBe("page");
      cleanup();
    }
  });

  it("does not mark Settings active on another page", () => {
    pathname.mockReturnValue("/");

    render(<Sidenav name="Maya" email="maya@example.test" />);

    const link = [...sidenavRail().querySelectorAll("a")].find(
      (anchor) => anchor.getAttribute("href") === "/settings",
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
    // **Every route the bar carries is a real one now.** Browse lives behind the More
    // sheet, and Settings points at `/settings` — the index, the same destination the
    // desktop rail uses — so the bar's `aria-disabled` slots are gone, and this says so.
    const link = screen.getByRole("link", { name: "Settings" });
    expect(link).toHaveAttribute("href", "/settings");

    const settingsSlot = [...bottomBar().querySelectorAll("a, [aria-disabled]")].find(
      (slot) => slot.textContent?.trim() === "Settings",
    );
    expect(settingsSlot?.getAttribute("aria-disabled")).toBeNull();
  });

  it("links Digest to the home, because the digest home shipped", () => {
    render(<BottomTabNav name="Maya" email="maya@example.test" />);

    // **The first tab was the one inert slot nobody noticed.** It has had no `href`
    // since the digest home shipped, so on a phone the Digest tab rendered the inert
    // branch — a disabled `<span>` carrying a visually-hidden "Coming soon" — while
    // also carrying `active={pathname === "/"}`. The home route's own tab did nothing
    // and said it was not coming soon.
    const link = screen.getByRole("link", { name: "Digest" });
    expect(link).toHaveAttribute("href", "/");
  });

  it("marks Digest active on the detail screens that hang off it", () => {
    // **The prefix rule, like the sidenav's.** The Detail Screen is reached by tapping
    // a Digest card, so a reader on `/events/...` has not left the Digest — and a bar
    // that marks nothing active there while the rail marks Digest reads as a bug.
    pathname.mockReturnValue("/events/folk-pub-quiz");

    render(<BottomTabNav name="Maya" email="maya@example.test" />);

    expect(screen.getByRole("link", { name: "Digest" }).getAttribute("aria-current")).toBe("page");
  });

  it("marks Settings as the current route on the index and every section", () => {
    for (const path of ["/settings", ...SETTINGS_SECTIONS.map((section) => section.href)]) {
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

describe("the More sheet", () => {
  /**
   * Open the sheet and return it.
   *
   * **The sheet is a dialog, and it only exists once it is opened.** The More slot is
   * mounted in the bar with `open={false}`, so the rows inside it are not in the DOM
   * until the user taps More — which is the correct behaviour for a dialog, and the
   * reason these assertions have to open it first.
   */
  async function openMore(): Promise<HTMLElement> {
    render(<BottomTabNav name="Maya" email="maya@example.test" />);

    const more = screen.getByRole("button", { name: "More" });
    fireEvent.click(more);

    return await screen.findByRole("dialog", { name: "More" });
  }

  it("links Browse to the screen, because the Browse surface shipped", async () => {
    const sheet = await openMore();

    const row = [...sheet.querySelectorAll("a")].find(
      (anchor) => anchor.textContent?.trim() === "Browse",
    );
    expect(row).not.toBeUndefined();
    expect(row?.getAttribute("href")).toBe("/browse");
    expect(row?.getAttribute("aria-disabled")).toBeNull();
    expect(sheet.textContent).not.toContain("Coming soon");
  });

  it("marks the Browse row as the current route when it is", async () => {
    pathname.mockReturnValue("/browse");

    const sheet = await openMore();

    const row = [...sheet.querySelectorAll("a")].find(
      (anchor) => anchor.getAttribute("href") === "/browse",
    );
    expect(row?.getAttribute("aria-current")).toBe("page");
  });

  it("keeps More a control, so it carries no current-route marker", async () => {
    pathname.mockReturnValue("/browse");

    render(<BottomTabNav name="Maya" email="maya@example.test" />);

    const more = screen.getByRole("button", { name: "More" });
    expect(more.getAttribute("aria-current")).toBeNull();
    expect(more.getAttribute("aria-haspopup")).toBe("dialog");
  });
});
