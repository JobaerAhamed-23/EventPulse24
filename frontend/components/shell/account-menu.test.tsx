/**
 * The account sheet — **one link, and Sign out.**
 *
 * **The panel is rendered in two places**, and one change has to fix both: the rail
 * opens it in a `Sheet`, and the bottom bar's More sheet renders it *inline*, because a
 * sheet opened from inside a sheet is a second overlay level. **Both are tested here**,
 * because "it works in the rail" is not a claim about the phone. **The second test
 * renders the bar**, not `MoreMenu` alone — the bar is what carries the More slot.
 *
 * **What the panel used to carry, and why it does not any more.** The `Settings` link
 * was a second way to the settings index — the rail already has a Settings row that
 * goes there — and the `Pricing` link was an upsell in a panel about the account. What
 * is left is **the one thing that can be changed**: the name.
 *
 * **The assertions are about hrefs, not about labels.** A label is the thing that
 * drifts: a link to `/settings` labelled "Account settings" re-opens exactly the door
 * this item closed, and a name check would not see it. The href is the invariant.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AccountMenu, AccountPanel } from "@/components/shell/account-menu";
import { BottomTabNav } from "@/components/shell/bottom-tab-nav";

/**
 * **The router is mocked because `SignOutButton` uses it** — it calls
 * `router.replace("/signin")` after the sign-out POST. The panel's own links are
 * plain `<Link>`s, so nothing else in this file needs the router.
 */
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/",
}));

const NAME = "Maya Ahmed";
const EMAIL = "maya@example.test";

describe("the account panel", () => {
  it("shows the name and the email", () => {
    render(<AccountPanel name={NAME} email={EMAIL} avatarUrl="" />);

    expect(screen.getByText(NAME)).toBeTruthy();
    expect(screen.getByText(EMAIL)).toBeTruthy();
  });

  it("offers 'Edit your name'", () => {
    render(<AccountPanel name={NAME} email={EMAIL} avatarUrl="" />);

    expect(screen.getByRole("link", { name: "Edit your name" })).toBeTruthy();
  });

  it("points 'Edit your name' at the profile screen, which exists", () => {
    render(<AccountPanel name={NAME} email={EMAIL} avatarUrl="" />);

    const link = screen.getByRole("link", { name: "Edit your name" });
    expect(link.getAttribute("href")).toBe("/settings/profile");
  });

  it("does not offer a Settings row", () => {
    // **The rail already has a Settings row** that goes to the same index, so the
    // sheet's copy was a second way to one place.
    render(<AccountPanel name={NAME} email={EMAIL} avatarUrl="" />);

    expect(screen.queryByRole("link", { name: "Settings" })).toBeNull();
  });

  it("does not offer a Pricing row", () => {
    // **The sheet is about the account, not about the upsell.** The account's plan has
    // a home: `/settings/account`.
    render(<AccountPanel name={NAME} email={EMAIL} avatarUrl="" />);

    expect(screen.queryByRole("link", { name: "Pricing" })).toBeNull();
  });

  it("links to one route, and it is the profile screen", () => {
    // **This is the real assertion about the removed doors.**
    //
    // **A name check is not enough.** The two assertions above pin the *labels*, and
    // a label is the thing that drifts: a link to `/settings` labelled "Account
    // settings" re-opens exactly the door this item closed, and a name check would not
    // see it. **The href is the invariant** — which is how the repo pins link
    // destinations elsewhere (`tests/settings-routes.test.ts` asserts on
    // `href="/settings`, not on the label beside it).
    //
    // **So the panel's whole set of destinations is asserted**, not one of them by
    // name. A new link to anywhere — `/pricing`, `/settings`, anywhere else — fails
    // this.
    render(<AccountPanel name={NAME} email={EMAIL} avatarUrl="" />);

    const hrefs = Array.from(document.querySelectorAll("a")).map((anchor) =>
      anchor.getAttribute("href"),
    );
    expect(hrefs).toEqual(["/settings/profile"]);
  });

  it("still offers Sign out, and it is the last thing in the panel", () => {
    render(<AccountPanel name={NAME} email={EMAIL} avatarUrl="" />);

    const signOut = screen.getByRole("button", { name: /sign out/i });
    expect(signOut).toBeTruthy();

    // **The order is the rule.** The panel is who you are, then what you can do about
    // it, then the way out — and Sign out is the way out.
    //
    // **The assertion is made against the panel's own children, not against the
    // button's wrapper.** `signOut.closest("div")` is `SignOutButton`'s *own* root
    // div, which has exactly one child — so an assertion built on it is true by
    // construction and passes whether Sign out is first, last or in the middle. The
    // panel root is found by its hook instead.
    const panel = document.querySelector("[data-account-panel]");
    expect(panel).not.toBeNull();

    const children = Array.from(panel?.children ?? []);
    // **A floor, so the assertion cannot pass vacuously.** The panel has three
    // children — the identity, the link, and the sign-out — and a refactor that
    // flattened the markup would otherwise make this an assertion about nothing.
    expect(children.length).toBeGreaterThanOrEqual(3);

    const last = children[children.length - 1];
    expect(last?.contains(signOut)).toBe(true);
  });
});

describe("the rail's account row", () => {
  it("opens the sheet, and the sheet carries the same panel", () => {
    render(<AccountMenu name={NAME} email={EMAIL} avatarUrl="" />);

    // **The sheet is closed until the row is pressed.**
    expect(screen.queryByRole("link", { name: "Edit your name" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: `Account: ${NAME}` }));

    expect(screen.getByRole("link", { name: "Edit your name" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Pricing" })).toBeNull();
  });

  it("addresses the row by the name it was given", () => {
    // **The row's accessible name carries the name**, so the sheet's trigger says who
    // it belongs to.
    render(<AccountMenu name={NAME} email={EMAIL} avatarUrl="" />);

    expect(screen.getByRole("button", { name: `Account: ${NAME}` })).toBeTruthy();
  });
});

describe("the bottom bar's More sheet", () => {
  it("renders the same panel inline, with the same link", async () => {
    // **One panel, two shapes.** The bottom bar renders `AccountPanel` *inline* rather
    // than opening a sheet inside a sheet — and the change to the panel has to reach
    // this rendering too.
    //
    // **The bar is rendered, not `MoreMenu` alone.** The work item says *"the bottom
    // bar's More sheet"*, and the bar is what carries the More slot — so this renders
    // `BottomTabNav` and opens the More sheet through it, the way `nav-routes.test.tsx`
    // does. Rendering `MoreMenu` directly would test the component without the bar
    // that mounts it.
    render(<BottomTabNav name={NAME} email={EMAIL} avatarUrl="" />);

    fireEvent.click(screen.getByRole("button", { name: "More" }));

    const sheet = await screen.findByRole("dialog", { name: "More" });

    // **The panel is inline in the sheet, not a sheet inside it** — so the link is in
    // the dialog, and there is no second dialog nested inside it.
    const link = screen.getByRole("link", { name: "Edit your name" });
    expect(sheet.contains(link)).toBe(true);
    expect(link.getAttribute("href")).toBe("/settings/profile");
    expect(screen.queryByRole("link", { name: "Pricing" })).toBeNull();
    expect(screen.getByRole("button", { name: /sign out/i })).toBeTruthy();
  });
});
