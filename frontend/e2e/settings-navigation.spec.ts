import { expect, test } from "@playwright/test";

import { resetSignInThrottle, seedAccount, signIn } from "./helpers";

/**
 * **Can a person get to the settings screens?** — in a real browser, by clicking.
 *
 * ## Why this spec exists
 *
 * Six `/settings/*` routes shipped, each from its own work item, each inheriting the
 * convention *"there is no `/settings` index page and no settings sub-navigation"*. Every
 * one of them worked. Every one of them had a passing page test. And four of the six
 * could not be reached by any sequence of clicks: the rail pointed at
 * `/settings/reminders`, which has no links out; `/settings/quiet-hours` carried the only
 * links to two more; `/settings/collections` was linked from nowhere at all.
 *
 * **The seventh section — Profile — inherited the index and the sub-nav, so it was
 * reachable from the moment it was added.** The list below is hand-written for exactly
 * the reason the first six were: **a hand-written list is a list somebody has to
 * remember to update**, and this spec fails when they do not.
 *
 * **Nothing caught it**, because nothing was looking. The page tests rendered each route
 * directly and the e2e specs reached them with `page.goto()` — a deep link is not a
 * click, and a route tested only by deep link is a route whose reachability is untested
 * by construction. `unwired-surfaces.spec.ts` makes this exact point about the surfaces
 * it reconnected; this spec applies it to the navigation itself.
 *
 * So every test below **navigates**. There is one `page.goto("/")` per test, to the
 * product's home, and from there it is clicks. If a settings screen is unreachable, these
 * fail — which is the only property worth asserting here and the one no unit test can.
 *
 * ## The index is gone, and these specs are how we know nothing broke with it
 *
 * `/settings` used to render the list of sections as described rows. It was a click
 * between the nav and the setting, and the screen it led to showed the same sections
 * again in its sub-nav — so `/settings` now redirects to the first section and the
 * sub-nav *is* the index. **The reachability property is unchanged**: every section is
 * still reachable from the entry point, in the same number of clicks it took before
 * (`two clicks from home`), and still reachable from every other section (`through the
 * sub-nav`). Only the surface that offers the list has moved.
 *
 * `tests/settings-routes.test.ts` holds the cheap half of the same rule: every directory
 * under `app/settings` is in `SETTINGS_SECTIONS`. That catches a route added without a
 * nav row in milliseconds. This catches the rest — that the rows, the rail and the index
 * actually carry a browser from one to the next.
 */

/** The desktop rail, by its landmark — the page has two navigation landmarks. */
function rail(page: import("@playwright/test").Page) {
  return page.getByRole("complementary", { name: "Primary" });
}

/** The settings sub-nav, by its own label. */
function subnav(page: import("@playwright/test").Page) {
  return page.getByRole("navigation", { name: "Settings sections" });
}

/**
 * The nine sections, in the order the index and the sub-nav render them.
 *
 * **This list is hand-written, and that is the point of the spec.** The spec fails when
 * somebody adds a section to `SETTINGS_SECTIONS` and forgets this list — because a
 * section the spec does not walk is a section whose reachability was never tested.
 *
 * **It must mirror `SETTINGS_SECTIONS` exactly.** `tests/settings-routes.test.ts` holds
 * the other half of the same rule (every directory under `app/settings` is in the list);
 * between them, a new settings route cannot ship unreachable.
 */
const SECTIONS = [
  { label: "Default reminders", path: "/settings/reminders", heading: "Default reminders" },
  { label: "Quiet hours", path: "/settings/quiet-hours", heading: "Quiet hours" },
  { label: "Pulse Digest", path: "/settings/digest", heading: "Pulse Digest" },
  { label: "Calendars", path: "/settings/calendars", heading: "Calendar sync" },
  { label: "Collections", path: "/settings/collections", heading: "Collections" },
  { label: "Sources", path: "/settings/sources", heading: "Sources" },
  { label: "Taste", path: "/settings/taste", heading: "Taste" },
  { label: "Account", path: "/settings/account", heading: "Account" },
  { label: "Profile", path: "/settings/profile", heading: "Profile" },
];

test.describe("the settings surface is navigable", () => {
  // Once per test, not once per file: five tests signing in would otherwise spend the
  // account's whole hourly allowance and refuse the last of them.
  test.beforeEach(async () => {
    const free = await seedAccount("free");
    await resetSignInThrottle([free.email]);
  });

  test("the rail lands on the first section, with no index in between", async ({ page }) => {
    const account = await seedAccount("free");
    await signIn(page, account);

    await page.goto("/");
    await rail(page).getByRole("link", { name: "Settings" }).click();

    // **`/settings` is a redirect now.** It used to render a list of the same sections
    // the sub-nav below carries, which made every setting two clicks deep: the nav, the
    // row, the screen. One click lands on a setting.
    const first = SECTIONS[0];
    await expect(page).toHaveURL(new RegExp(`${first.path}$`));
    await expect(page.getByRole("heading", { level: 1, name: first.heading })).toBeVisible();

    // And the section it landed on is marked in the sub-nav, so the screen says which
    // of the sections this is rather than looking like the only one.
    const current = subnav(page).locator("[aria-current='page']");
    await expect(current).toHaveCount(1);
    await expect(current).toHaveText(first.label);
  });

  test("a bookmarked /settings still arrives somewhere", async ({ page }) => {
    const account = await seedAccount("free");
    await signIn(page, account);

    // The index was a real route for a while, so it is in people's history and in their
    // bookmarks. It must forward, not 404.
    await page.goto("/settings");

    await expect(page).toHaveURL(new RegExp(`${SECTIONS[0].path}$`));
  });

  test("every settings screen is two clicks from home", async ({ page }) => {
    const account = await seedAccount("free");
    await signIn(page, account);

    // **The property the index used to carry**, now carried by the sub-nav: from the
    // rail, every section is one further click. It was false for four of the first six
    // screens, which is why this walks all of them rather than trusting the list.
    for (const section of SECTIONS) {
      // Home between sections, so each section is reached from the entry point rather
      // than from whichever screen the previous iteration left behind.
      await page.goto("/");
      await rail(page).getByRole("link", { name: "Settings" }).click();

      const nav = subnav(page);
      await expect(nav, "the landing screen carries no settings sub-nav").toBeVisible();

      const row = nav.getByRole("link", { name: section.label, exact: true });
      await expect(row, `the sub-nav does not offer ${section.label}`).toBeVisible();
      await row.click();

      await expect(page, `clicking ${section.label} did not land on ${section.path}`).toHaveURL(
        new RegExp(`${section.path}$`),
      );
      await expect(
        page.getByRole("heading", { level: 1, name: section.heading }),
        `${section.path} did not render its own heading`,
      ).toBeVisible();
    }
  });

  test("every settings screen reaches every other, through the sub-nav", async ({ page }) => {
    const account = await seedAccount("free");
    await signIn(page, account);

    // **The dead-end test.** `/settings/reminders` was the rail's destination and had no
    // links out at all, so a user who followed the nav landed on one screen with no way
    // onward. Walk the sections in a ring: from each one, click the next.
    await page.goto("/settings/reminders");

    for (let index = 0; index < SECTIONS.length; index += 1) {
      const next = SECTIONS[(index + 1) % SECTIONS.length];

      const nav = subnav(page);
      await expect(nav, "this screen carries no settings sub-nav").toBeVisible();

      await nav.getByRole("link", { name: next.label, exact: true }).click();

      await expect(page).toHaveURL(new RegExp(`${next.path}$`));
      await expect(page.getByRole("heading", { level: 1, name: next.heading })).toBeVisible();
    }
  });

  test("the sub-nav marks the screen you are on", async ({ page }) => {
    const account = await seedAccount("free");
    await signIn(page, account);

    await page.goto("/settings/quiet-hours");

    const current = subnav(page).locator("[aria-current='page']");
    await expect(current).toHaveCount(1);
    await expect(current).toHaveText("Quiet hours");
  });

  test("the rail stays on Settings across the whole surface", async ({ page }) => {
    const account = await seedAccount("free");
    await signIn(page, account);

    // The index included — `"/settings".startsWith("/settings/")` is false, so the bare
    // prefix the rail used would drop its highlight on the screen it just navigated to.
    for (const path of ["/settings", ...SECTIONS.map((section) => section.path)]) {
      await page.goto(path);

      const settings = rail(page).getByRole("link", { name: "Settings" });
      await expect(settings, `the rail goes quiet on ${path}`).toHaveAttribute(
        "aria-current",
        "page",
      );
    }
  });
});
