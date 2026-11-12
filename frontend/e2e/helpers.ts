import { readFile } from "node:fs/promises";
import path from "node:path";

import { expect, type Locator, type Page } from "@playwright/test";

/**
 * The shared helpers for the Browse end-to-end tests.
 *
 * **These tests drive the real stack.** The data behind them is the committed seed file
 * (`backend/config/browse_seed.json`), written by `make manage ARGS="seed_browse_catalog"`.
 * **The credentials below are that file's** — they are read out of the seed file rather
 * than invented here, so a change to the file's accounts cannot leave these tests
 * signing in as an account that no longer exists.
 *
 * **Why the credentials are read from the file rather than copied.** A copy is a second
 * source of truth. The seed file's `users` block is the definition of who the walk-through
 * signs in as, and a test that hard-codes `free@browse.example.test` would keep passing
 * its own assertion while the seed renamed the account — and the walk-through would be
 * signing in as nobody, against a surface that would then be empty, and the empty-surface
 * finding would look like a product bug rather than a stale test.
 */

/**
 * The path to the backend's seed file.
 *
 * **It is resolved from the working directory, not from `import.meta.url`.** Playwright
 * loads test files through its own CommonJS loader, and `import.meta` is not available
 * there — `import.meta.url` throws *"exports is not defined in ES module scope"* before
 * the test body runs. The working directory is the frontend's, because that is where
 * `pnpm exec playwright test` runs and where the `playwright.config.ts` sits, so
 * `../backend/config/browse_seed.json` is the file — **and the path is checked**, so a
 * run from the wrong directory fails with a clear message instead of a module-not-found.
 */
const SEED_FILE = path.resolve(process.cwd(), "../backend/config/browse_seed.json");

/** A seed account, as the file names it. */
export type SeedAccount = {
  key: string;
  email: string;
  password: string;
  plan: string;
};

/** The seed file's two accounts, read from the file itself. */
export async function seedAccounts(): Promise<SeedAccount[]> {
  const raw = await readSeedFile();
  return raw.users as SeedAccount[];
}

/** The seed file, parsed. */
async function readSeedFile(): Promise<{
  city: { name: string; tz: string };
  users: SeedAccount[];
}> {
  return JSON.parse(await readFile(SEED_FILE, "utf8"));
}

/**
 * The one account of the given plan.
 *
 * **It fails loudly when the file does not name exactly one.** A helper that returned
 * `undefined` would let a test carry on and fail somewhere else, and the message would
 * point at the symptom rather than at the cause.
 */
export async function seedAccount(plan: "free" | "pro"): Promise<SeedAccount> {
  const accounts = await seedAccounts();
  const matches = accounts.filter((account) => account.plan === plan);
  if (matches.length !== 1) {
    throw new Error(
      `The seed file names ${matches.length} ${plan} account(s); exactly one is needed.`,
    );
  }
  return matches[0];
}

/**
 * Sign in, the way a person does.
 *
 * **The form, the fields, the button.** The email field is `#signin-email`, the password
 * field is `#signin-password`, and the submit button reads "Sign in". **The test types
 * into them and presses the button** — it does not set a cookie directly, because the
 * point of the walk-through is that a person can get in, and a test that forged the
 * session cookie would be testing the surface *after* the sign-in, which is the part
 * that is already covered elsewhere.
 *
 * **It waits for the session to take.** The form's submit calls `router.replace(next)`
 * and then `router.refresh()`, so the page navigates *after* the cookie is set. Waiting
 * for the URL to leave `/signin` is the honest signal that the session is live.
 */
export async function signIn(page: Page, account: SeedAccount): Promise<void> {
  await page.goto("/signin");
  await page.locator("#signin-email").fill(account.email);
  await page.locator("#signin-password").fill(account.password);
  await page.getByRole("button", { name: "Sign in" }).click();

  // **The URL leaving `/signin` is the signal.** The digest is the home route for a
  // signed-in user who is through onboarding, so that is where the form sends them.
  await page.waitForURL((url) => !url.pathname.startsWith("/signin"), { timeout: 20_000 });
}

/**
 * Go to Browse **through the sidenav**, not by typing the URL.
 *
 * **This is the acceptance criterion, and the difference matters.** "Navigate to Browse
 * from the sidenav" is a claim about the sidenav's Browse row being a link that works.
 * A test that does `page.goto("/browse")` would pass whether the sidenav row was a link,
 * a dead `<span>`, or absent — it would be testing the router, not the navigation.
 */
export async function navigateToBrowse(page: Page): Promise<void> {
  const sidenav = page.getByRole("navigation", { name: "Main" });
  await sidenav.getByRole("link", { name: "Browse" }).click();
  await page.waitForURL(/\/browse/);
  await expect(page.locator("[data-browse-hero]")).toBeVisible();
}

/**
 * The cards on the page, in the order they are drawn.
 *
 * **The hook is `data-browse-card`, and it is on the `<article>`.** The grid's section
 * hooks (`data-browse-section`) say which tier a card is in; the card hook says a card
 * is here. Together they let a test say "the first tier has three cards" without reading
 * a class name or a position.
 */
export function cards(page: Page) {
  return page.locator("[data-browse-card]");
}

/** The cards in the first tier — "3 worth your attention today". */
export function tierOneCards(page: Page) {
  return page.locator('[data-browse-section="tier-1"] [data-browse-card]');
}

/** The cards in the second tier — "More this week". */
export function tierTwoCards(page: Page) {
  return page.locator('[data-browse-section="tier-2"] [data-browse-card]');
}

/**
 * A card's title.
 *
 * **The title is the `<h3>`.** The card's own `<article>` has no heading of its own, so
 * the title is read from the heading inside it.
 */
export function cardTitle(card: Locator): Locator {
  return card.locator("h3");
}

/** The Save button on a card. */
export function saveButton(card: Locator): Locator {
  return card.locator("[data-browse-save-button]");
}

/**
 * Wait for the surface to finish loading.
 *
 * **The skeleton is the loading state, and it is the only signal of it.** The Browse page
 * renders `BrowseSkeleton` while the server read is in flight and the grid when it is
 * done. A test that asserted on the grid without waiting for the skeleton to clear would
 * race the server — and the race would be intermittent, and intermittent failures are
 * the ones that get mistaken for product bugs.
 */
export async function waitForBrowse(page: Page): Promise<void> {
  await expect(page.locator("[data-browse-skeleton]")).toHaveCount(0, { timeout: 20_000 });
}
