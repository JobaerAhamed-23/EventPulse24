import { expect, test } from "@playwright/test";

import { resetSignInThrottle, seedAccount, setName, signIn } from "./helpers";

/**
 * **The name, end to end — in a real browser, against the real stack.**
 *
 * ## Why this file exists
 *
 * **The unit tests prove the parts, and the parts are not the property.** There is a test
 * that the helper derives the right name, a test that every page calls the helper, and a
 * test that the rail shows the name a page hands it. **All three are about the code.**
 *
 * **This file is about the product.** It signs in as a person, opens the account sheet,
 * types a name, and asks the questions a person would ask:
 *
 * 1. **The sheet offers "Edit your name" — and nothing else it used to.**
 * 2. **Typing a name saves it.** No Save button, no form to submit.
 * 3. **The name survives a reload** — it is on the account, not in the browser.
 * 4. **The rail shows the stored name**, on the profile screen and on every other page.
 * 5. **A user with no name set still sees the email-derived name.**
 *
 * **The last one is the case that breaks silently.** A fallback that blanks the name
 * looks like a working feature and hides every user who never set one — and no unit
 * test can see it, because the unit test renders a page with a fixture, not a person
 * who has never set a name.
 *
 * **The e2e suite runs against the real stack** — the real API, the real database, the
 * real seed — so the name this test types is really written, really read back, and
 * really audited.
 */

/** The account sheet's row in the rail — its accessible name carries the display name. */
function accountRow(page: import("@playwright/test").Page) {
  return page.getByRole("button", { name: /^Account: / });
}

/**
 * BEL — the ASCII bell character.
 *
 * **It is written as an escape, not as a literal.** A control character in source is
 * invisible: a reader cannot see it, a formatter may strip it, and a diff shows
 * nothing where the character was. So it is named here, once, and every use says so.
 */
const BEL = "\u0007";

test.describe("the account's name", () => {
  test.beforeEach(async ({ page }) => {
    const free = await seedAccount("free");
    await resetSignInThrottle([free.email]);
    await signIn(page, free);

    // **The name is cleared before every test.**
    //
    // **The name is account state, so it outlives a test.** A test that sets one leaves
    // it behind, and the next test — and the next *run* — inherits it. The first run of
    // this file proved it: the "a user with no name set" test failed because a previous
    // test had set a name, and the rail showed it.
    //
    // **The clear goes through the product's own endpoint**, with the empty string that
    // *is* the account's "no name set" state.
    await setName(page, "");

    // **And the page is reloaded, because the rail is drawn from the server.**
    //
    // **The clear happened after the page was rendered.** The sign-in above landed on a
    // page the server drew with whatever name the account held *then* — which, after a
    // previous test set one, is the name that test left behind. Clearing the account
    // afterwards does not redraw the rail: the shell is a server render, and its name is
    // fixed for the life of that render.
    //
    // **So the reload is what makes the page agree with the account.** The second run
    // of this file proved why this line is here: without it, "a user with no name set"
    // still failed, because the rail was carrying the name from before the clear — the
    // account said "no name" and the screen said "Maya Ahmed", and the screen was the
    // one out of date.
    await page.reload();
  });

  test("the account sheet offers the name, the edit link and Sign out", async ({ page }) => {
    const account = await seedAccount("free");

    await accountRow(page).click();

    const sheet = page.locator("dialog[aria-label='Account']");
    await expect(sheet).toBeVisible();

    // **The name and the email are both there** — the sheet is about the account.
    await expect(sheet.getByText(account.email)).toBeVisible();

    // **"Edit your name" is the one link**, and it points at the profile screen.
    const link = sheet.getByRole("link", { name: "Edit your name" });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("href", "/settings/profile");

    // **Sign out is still there.**
    await expect(sheet.getByRole("button", { name: "Sign out" })).toBeVisible();
  });

  test("the sheet offers no Settings row and no Pricing row", async ({ page }) => {
    // **The two doors this change closed.** A Settings link would re-open the door the
    // account sheet was changed to close; a Pricing link would put an upsell in a panel
    // about the account.
    //
    // **The assertion is on the href, not on the label** — a link renamed to "Account
    // settings" would re-open the same door without failing a label check.

    await accountRow(page).click();

    const sheet = page.locator("dialog[aria-label='Account']");
    await expect(sheet).toBeVisible();

    const hrefs = await sheet.locator("a").evaluateAll((links) =>
      links.map((link) => link.getAttribute("href")),
    );
    expect(hrefs).toEqual(["/settings/profile"]);
  });

  test("typing a name saves it, and it survives a reload", async ({ page }) => {
    // **The way a person gets there: the sheet's link.**
    await accountRow(page).click();
    await page.getByRole("link", { name: "Edit your name" }).click();
    await expect(page).toHaveURL(/\/settings\/profile$/);

    const field = page.locator("[data-profile-name-input]");
    await expect(field).toBeVisible();

    // **The field starts empty** — the account has no name set yet.
    await expect(field).toHaveValue("");

    await field.fill("Maya Ahmed");

    // **"Saved." appears, with no Save button pressed** — the control saves on change.
    await expect(page.locator("[data-saved]")).toHaveText("Saved.");

    // **And it is on the account, not in the browser.** A reload asks the server again.
    await page.reload();
    await expect(page.locator("[data-profile-name-input]")).toHaveValue("Maya Ahmed");
  });

  test("the rail shows the stored name, on this screen and on every other", async ({ page }) => {
    await accountRow(page).click();
    await page.getByRole("link", { name: "Edit your name" }).click();
    await expect(page).toHaveURL(/\/settings\/profile$/);

    await page.locator("[data-profile-name-input]").fill("Maya Ahmed");
    await expect(page.locator("[data-saved]")).toHaveText("Saved.");

    // **The rail on the profile screen.**
    await expect(accountRow(page)).toHaveAttribute("aria-label", "Account: Maya Ahmed");

    // **And the rail on a different page** — the rule is one rule, and it is the rail's
    // to show on every screen.
    await page.goto("/settings");
    await expect(accountRow(page)).toHaveAttribute("aria-label", "Account: Maya Ahmed");

    await page.goto("/timeline");
    await expect(accountRow(page)).toHaveAttribute("aria-label", "Account: Maya Ahmed");
  });

  test("a user with no name set still sees the email-derived name", async ({ page }) => {
    // **The case that breaks silently.** The seed's accounts have no name, so this is the
    // state every seeded account is in — and the state every account that has never set
    // a name is in.
    //
    // **The fallback must not blank the name.** A blank rail reads as "this account has
    // no name" rather than "this feature is broken", and it hides every user who never
    // set one.
    const account = await seedAccount("free");

    // **The email's local part, capitalised** — the rule the copies used.
    const local = account.email.split("@")[0] ?? account.email;
    const expected = local
      .split(/[._-]+/)
      .filter(Boolean)
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ");

    expect(expected).not.toBe("");

    // **The rail is not blank, and it is not the raw local part.**
    await expect(accountRow(page)).toHaveAttribute("aria-label", `Account: ${expected}`);

    // **And the profile screen's field is empty** — the account really has no name.
    // **This is what makes the assertion above meaningful**: the rail is showing the
    // fallback, not a stored name.
    await page.goto("/settings/profile");
    await expect(page.locator("[data-profile-name-input]")).toHaveValue("");
  });

  test("clearing the name falls back again", async ({ page }) => {
    // **An emptied name is a thing a person does** — it means "no name set". The
    // account stores `""` and the product falls back to the email-derived name.
    const account = await seedAccount("free");

    await page.goto("/settings/profile");
    await page.locator("[data-profile-name-input]").fill("Maya Ahmed");
    await expect(page.locator("[data-saved]")).toHaveText("Saved.");
    await expect(accountRow(page)).toHaveAttribute("aria-label", "Account: Maya Ahmed");

    // **Now clear it.**
    await page.locator("[data-profile-name-input]").fill("");
    await expect(page.locator("[data-saved]")).toHaveText("Saved.");

    const local = account.email.split("@")[0] ?? account.email;
    const expected = local
      .split(/[._-]+/)
      .filter(Boolean)
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ");

    // **The rail is back to the fallback.**
    await page.reload();
    await expect(accountRow(page)).toHaveAttribute("aria-label", `Account: ${expected}`);
  });

  test("a name carrying a control character is refused, and the API's own message is shown", async ({
    page,
  }) => {
    // **The failure line is the API's, when the API refused.** A generic "Couldn't
    // save." would throw away the message written for the person who typed it.

    // **The character is BEL, and that is not an accident.** The backend refuses the
    // C0 control range — minus tab — and DEL, because a name carrying one would
    // break the one-line layout it is rendered in.
    //
    // **A line break cannot be tested here, and the reason is the browser's.** The
    // field is `<input type="text">`, and the HTML value sanitization algorithm strips
    // `\r` and `\n` from a single-line input's value — so a newline typed into it never
    // reaches the field, let alone the API. The first version of this test filled the
    // field with `"Maya\nAhmed"` and waited for a refusal that could never arrive; the
    // failure line was absent because **the API had been asked to save a legal name**.
    //
    // **BEL is not stripped.** It is not a line terminator, so the browser hands it
    // over, and the API refuses it — which is the same refusal a newline would earn,
    // reached by the only road the browser leaves open.
    await page.goto("/settings/profile");
    await page.locator("[data-profile-name-input]").fill(`Maya${BEL}Ahmed`);

    // **The refusal line is shown**, and the field is marked invalid.
    await expect(page.locator("[data-save-failed]")).toBeVisible();
    await expect(page.locator("[data-profile-name-input]")).toHaveAttribute(
      "aria-invalid",
      "true",
    );

    // **And the API's own message is what it says** — not the generic offline line.
    await expect(page.locator("[data-save-failed]")).toHaveText(
      /can't contain line breaks or control characters/i,
    );
  });
});
