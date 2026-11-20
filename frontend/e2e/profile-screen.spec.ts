import path from "node:path";

import { expect, test } from "@playwright/test";

import {
  accountRow,
  clearAvatar,
  goToSettingsSection,
  railDisc,
  resetEmailChangeThrottle,
  resetSignInThrottle,
  seedAccount,
  setName,
  sheetDisc,
  signIn,
  subnav,
} from "./helpers";

/**
 * **The profile screen, end to end — in a real browser, against the real stack.**
 *
 * ## Why this file exists
 *
 * **`profile-name.spec.ts` proves the name.** This file proves the *screen* — the four
 * controls on it, the order they are in, and the fact that a person can reach all of
 * it by clicking.
 *
 * **The unit tests prove the parts, and the parts are not the property.** There is a
 * test that the island publishes the picture, a test that the disc falls back to the
 * initials, and a test that the city section is absent when the read fails. **All three
 * are about the code.** This file is about the product: it signs in as a person, walks
 * to the screen through the settings sub-nav, and uses each control the way a person
 * would.
 *
 * ## The one rule this file obeys: **reach the screen by clicking**
 *
 * **A deep link is not a click, and a route tested only by deep link is a route whose
 * reachability is untested by construction.** That is the argument
 * `settings-navigation.spec.ts` makes about the whole settings surface — four of the
 * first six screens could not be reached by any sequence of clicks, every one of them
 * had a passing page test, and nothing caught it because nothing was looking.
 *
 * **So this file never types the profile screen's URL.** It clicks the rail's Settings
 * row and then the sub-nav's Profile row, and the navigation helper
 * (`goToSettingsSection`) is the same helper the settings spec would use — **a helper
 * that one spec had to copy would be a second copy of the thing this repo keeps
 * arguing about.**
 *
 * ## What is proved here
 *
 * 1. **The screen is reachable by clicking**, and it carries all four controls.
 * 2. **The name saves, and the rail shows it — without a reload.** The shell is a
 *    server render, so this is the one property a page test cannot see.
 * 3. **A picture uploads, and the rail's face changes — without a reload.**
 * 4. **A picture removes, and the rail's face falls back to the initials.**
 * 5. **An address change can be asked for, and cancelled.**
 * 6. **The place controls are both there and both real** — the city and the zone, which
 *    arrived from `/settings/account` and `/settings/general` respectively.
 *
 * ## The picture's bytes are real
 *
 * **The server identifies the format from the bytes**, not from the filename — "a
 * payload whose bytes are not an image is refused however it is named". **So the fixture
 * is a real PNG**, a one-pixel file committed to the repository, and not a file with the
 * right extension and the wrong contents. A file with the wrong bytes would be refused,
 * and the refusal would be the test asserting the wrong thing.
 */

/**
 * The picture fixture, resolved from the working directory.
 *
 * **Not from `import.meta.url`** — Playwright loads test files through its own
 * CommonJS loader, where `import.meta` is unavailable. The same constraint
 * `helpers.ts` records for the seed file.
 */
const PICTURE = path.resolve(process.cwd(), "e2e/fixtures/avatar.png");

/**
 * The address the change is requested to.
 *
 * **It is not an address anybody holds.** The endpoint answers 202 for a free address
 * and for one another account already holds, so a real address would prove nothing
 * about availability — and would leave a pending change on the shared seed account.
 */
const NEW_EMAIL = "maya.new@example.test";

test.describe("the profile screen", () => {
  test.beforeEach(async ({ page }) => {
    const free = await seedAccount("free");
    await resetSignInThrottle([free.email]);

    // **And the email-change allowance too.** The window is five an hour per IP and
    // three an hour per account — much tighter than the sign-in's — so the spec's own
    // requests spend it, and the *second run* of the suite finds the window already up.
    // The request is then refused with a 429 and the test fails for a reason that has
    // nothing to do with the code under test.
    //
    // **It is not optional bookkeeping**: this was the last failing test in the spec,
    // and it failed for exactly this reason.
    await resetEmailChangeThrottle([free.email]);

    await signIn(page, free);

    // **The name is cleared before every test**, for the reason
    // `profile-name.spec.ts` records: the name is account state, so it outlives a test,
    // and the next test — and the next run — inherits it.
    await setName(page, "");

    // **And so is the picture.** It is account state for the same reason, and the seed
    // does not clear it — `make seed-browse-for-test` clears the saved *rows*, because
    // the Browse walk-through is about seeing a saved event. **A picture left behind by
    // one test would make the next test's "the rail has no picture yet" assertion fail
    // for a reason that has nothing to do with the code under test.**
    //
    // **A mutation probe found this**, not a reading of the code: the probe removed the
    // island's publish call, and the upload test failed at its *first* assertion — the
    // one about the state *before* the upload.
    await clearAvatar(page);

    // **And the page is reloaded**, because the rail is drawn from the server. The
    // clears happened after the page was rendered, and the shell is a server render, so
    // its name and its picture are fixed for the life of that render.
    await page.reload();
  });

  test("is reachable by clicking, and carries all four controls", async ({ page }) => {
    // **The walk is the claim.** The rail's Settings row, then the sub-nav's Profile
    // row — and the helper asserts the URL afterwards, so a sub-nav that pointed
    // somewhere else would fail here rather than pass silently.
    await goToSettingsSection(page, "Profile", "/settings/profile");

    // **The heading.**
    await expect(page.getByRole("heading", { level: 1, name: "Profile" })).toBeVisible();

    // **All four controls**, in the order the heading promises.
    await expect(page.getByRole("region", { name: "Profile picture" })).toBeVisible();
    await expect(page.getByLabel("Your name")).toBeVisible();
    await expect(page.getByLabel(/new email address/i)).toBeVisible();
    await expect(page.getByLabel("City")).toBeVisible();
  });

  test("the sub-nav offers Profile from every settings screen", async ({ page }) => {
    // **The claim is "from every screen", so this walks them.** The sub-nav is
    // rendered by each screen, and a screen that rendered it without the Profile row
    // would be a dead end for the picture and the address — which now live here.
    const sections = [
      { label: "General", path: "/settings/general" },
      { label: "Calendars", path: "/settings/calendars" },
      { label: "Collections", path: "/settings/collections" },
      { label: "Sources", path: "/settings/sources" },
      { label: "Taste", path: "/settings/taste" },
      { label: "Account", path: "/settings/account" },
      { label: "Profile", path: "/settings/profile" },
    ];

    for (const section of sections) {
      await page.goto(section.path);

      const nav = subnav(page);
      await expect(nav, `${section.path} carries no settings sub-nav`).toBeVisible();

      const row = nav.getByRole("link", { name: "Profile", exact: true });
      await expect(row, `${section.path} does not offer Profile`).toBeVisible();
      await expect(row).toHaveAttribute("href", "/settings/profile");
    }
  });

  test("the name saves, and the rail shows it without a reload", async ({ page }) => {
    await goToSettingsSection(page, "Profile", "/settings/profile");

    await page.locator("[data-profile-name-input]").fill("Maya Ahmed");
    await expect(page.locator("[data-saved]")).toHaveText("Saved.");

    // **No reload.** The shell is a server render, so the rail's name is fixed for the
    // life of it — and the island publishes the new name to the shell once the server
    // has accepted it. **A save that does not show up is a save that did not happen.**
    await expect(accountRow(page)).toHaveAttribute("aria-label", "Account: Maya Ahmed");

    // **And it is on the account, not in the browser.**
    await page.reload();
    await expect(page.locator("[data-profile-name-input]")).toHaveValue("Maya Ahmed");
  });

  test("a picture uploads, and the rail's face changes without a reload", async ({ page }) => {
    await goToSettingsSection(page, "Profile", "/settings/profile");

    // **Before: the rail shows the initials**, because the account has no picture.
    const disc = railDisc(page);
    await expect(disc).toBeVisible();
    await expect(disc.locator("img")).toHaveCount(0);

    // **The file is chosen, and the choice is the save.**
    await page.locator("[data-avatar-input]").setInputFiles(PICTURE);
    await expect(page.locator("[data-avatar-upload] [data-saved]")).toHaveText("Saved.");

    // **The rail's face is now a picture — without a reload.** The shell was rendered
    // on the server with the picture the account held *then*, which was none, so this
    // is the island's publish reaching the rail.
    await expect(disc.locator("img")).toHaveCount(1);
    await expect(disc.locator("img")).toHaveAttribute("src", /\/api\/auth\/profile\/avatar\//);

    // **And the account sheet shows the same face**, because it is the same component.
    await accountRow(page).click();
    await expect(sheetDisc(page).locator("img")).toHaveCount(1);

    // **It survives a reload**, because it is on the account.
    await page.reload();
    await expect(railDisc(page).locator("img")).toHaveCount(1);
  });

  test("a picture removes, and the rail's face falls back to the initials", async ({ page }) => {
    await goToSettingsSection(page, "Profile", "/settings/profile");

    await page.locator("[data-avatar-input]").setInputFiles(PICTURE);
    await expect(page.locator("[data-avatar-upload] [data-saved]")).toHaveText("Saved.");
    await expect(railDisc(page).locator("img")).toHaveCount(1);

    // **And the removal.** The control only exists when there is a picture — a
    // "Remove picture" button on an account with no picture is an affordance that
    // cannot work.
    await page.locator("[data-avatar-remove]").click();
    await expect(page.locator("[data-avatar-upload] [data-saved]")).toHaveText("Saved.");

    // **The rail's face is the initials again — without a reload.** The removal
    // publishes `""`, which the disc reads as "no picture".
    await expect(railDisc(page).locator("img")).toHaveCount(0);
    await expect(railDisc(page)).toHaveText(/./);

    // **And the account sheet follows it.**
    await accountRow(page).click();
    await expect(sheetDisc(page).locator("img")).toHaveCount(0);
  });

  test("an address change can be asked for, and cancelled", async ({ page }) => {
    await goToSettingsSection(page, "Profile", "/settings/profile");

    await expect(page.locator("[data-current-email]")).toBeVisible();

    // **The address is typed and the link is requested.** The endpoint sends real mail
    // — a link to the new address and a warning to the current one — and the screen
    // says what that means before the button is pressed.
    await page.locator("[data-new-email-input]").fill(NEW_EMAIL);
    await page.locator("[data-request-change]").click();

    // **The pending block names the address**, so somebody who mistyped it can see what
    // they typed.
    await expect(page.locator("[data-pending-change]")).toContainText(NEW_EMAIL);

    // **And the change is cancelled**, because a pending change on the shared seed
    // account would make the next run's screen show the pending block instead of the
    // form. The cancel is idempotent on the server, so pressing it is not an error.
    await page.locator("[data-cancel]").click();
    await expect(page.locator("[data-pending-change]")).toHaveCount(0);
    await expect(page.locator("[data-new-email-input]")).toBeVisible();
  });

  test("the place controls are both there, and both are real", async ({ page }) => {
    await goToSettingsSection(page, "Profile", "/settings/profile");

    // **The city picker is a real control with the catalog's cities in it.**
    const city = page.getByLabel("City");
    await expect(city).toBeVisible();
    const options = await city.locator("option").count();
    expect(options, "the city picker offers no cities").toBeGreaterThan(0);

    // **The zone is edited here too, not signposted.** It used to sit on
    // `/settings/general`, two screens away from the city — so a user correcting both
    // after a move had to find two settings, on two screens, to describe one fact about
    // themselves.
    const zone = page.getByLabel("Timezone");
    await expect(zone).toBeVisible();
    await expect(page.locator("[data-timezone-select] option").first()).toBeAttached();

    // **And nothing is left pointing elsewhere for it.** The line that said the zone
    // sat under General is gone with the move; a signpost to the screen you are on is
    // worse than none.
    await expect(page.locator("[data-city-zone-note]")).toHaveCount(0);
  });

  test("the zone saves, and the city picked after it does not undo the save", async ({ page }) => {
    /**
     * **The hazard the move creates.** `HomeCity` posts `timezone` back unchanged with
     * every city change, from a value the server render fixed — so on a screen that
     * also edits the zone, a city picked afterwards can send the old zone and quietly
     * revert the zone change. Both controls save with a "Saved." and the account ends
     * up on the zone it started on.
     *
     * The page test asserts the request's body; this asserts what the **server** then
     * holds, by reloading and reading the control back.
     */
    await goToSettingsSection(page, "Profile", "/settings/profile");

    const zone = page.getByLabel("Timezone");
    const city = page.getByLabel("City");

    const before = await zone.inputValue();
    const next = before === "Europe/London" ? "Asia/Dhaka" : "Europe/London";

    await zone.selectOption(next);
    await expect(page.locator("[data-digest-timezone] [data-saved]")).toBeVisible();

    // **Any city change will do — the point is the request it sends, not the city.**
    // A different one is chosen where the catalog offers one, because a `selectOption`
    // to the value already selected is a weaker trigger than a real change.
    const cityBefore = await city.inputValue();
    const cityValues = await city.locator("option").evaluateAll((options) =>
      options.map((option) => (option as HTMLOptionElement).value).filter((value) => value !== ""),
    );
    const otherCity = cityValues.find((value) => value !== cityBefore) ?? cityBefore;
    await city.selectOption(otherCity);
    await expect(page.locator("[data-home-city-select]")).toBeEnabled();

    await page.reload();
    await expect(page.getByLabel("Timezone")).toHaveValue(next);

    // Put the account back, so the next run starts where this one did.
    await page.getByLabel("City").selectOption(cityBefore);
    await page.getByLabel("Timezone").selectOption(before);
    await expect(page.getByLabel("Timezone")).toHaveValue(before);
  });
});
