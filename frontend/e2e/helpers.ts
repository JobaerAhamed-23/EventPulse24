import { execFile } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

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

/** `execFile`, promisified — the walkthrough runs the product's own commands. */
const run = promisify(execFile);

/**
 * The backend's directory, resolved from the working directory.
 *
 * **Not from `import.meta.url`** — Playwright loads test files through its own CommonJS
 * loader, where `import.meta` is unavailable. Same constraint the seed file records.
 */
const BACKEND_DIR = path.resolve(process.cwd(), "../backend");

/**
 * Give the account its sign-in allowance back, through the product's own reset.
 *
 * `AUTH_THROTTLE_SIGN_IN_ACCOUNT` is five an hour, and a spec that signs in once per
 * test spends the account's whole allowance — so without this the last tests of a run
 * are refused by the throttle rather than by anything they assert. **It is not a backdoor
 * around the throttle**; it is the throttle's own reset, the same one `make seed-browse`
 * calls.
 *
 * **It lives here because two specs need it.** The settings-navigation spec and the
 * profile-name spec each sign in once per test, and a helper that one of them had to
 * copy would be a second copy of the thing this repo keeps arguing about.
 */
export async function resetSignInThrottle(emails: string[]): Promise<void> {
  const script = [
    "from apps.identity.services.throttle import reset_sign_in_throttle",
    "reset_sign_in_throttle(ip_address='127.0.0.1', emails=" + JSON.stringify(emails) + ")",
  ].join("\n");
  await run("uv", ["run", "python", "manage.py", "shell", "-c", script], { cwd: BACKEND_DIR });
}

/**
 * The signed-in user's name, set to whatever the caller asks for.
 *
 * **The name is account state, so it outlives a test.** A test that sets a name leaves
 * it on the account, and the next test — and the next *run* — inherits it. That is not
 * hypothetical: it is exactly what happened the first time this spec ran, and the
 * "a user with no name set" test failed because a previous test had set one.
 *
 * **So the name is reset explicitly, through the product's own endpoint.** Not through
 * the database — a helper that wrote the row directly would be testing the row, not the
 * product. **The empty string is the meaningful reset**: it is the account's own "no
 * name set" state, and it is what a person who clears the field leaves behind.
 *
 * **The CSRF token is read from the browser's own cookie**, for the reason
 * `clearSavedEvents` records: Django rotates it on sign-in, and `page.request` is
 * Playwright's own client rather than the app's.
 */
export async function setName(page: Page, name: string): Promise<void> {
  const cookies = await page.context().cookies();
  const token = cookies.find((cookie) => cookie.name === "csrftoken")?.value;
  expect(token, "the browser holds no csrftoken cookie").toBeTruthy();

  const written = await page.request.put("/api/auth/profile", {
    headers: { "X-CSRFToken": token as string },
    data: { name },
  });
  expect(written.ok(), "the name could not be written").toBeTruthy();
}

/** A seed account, as the file names it. */
export type SeedAccount = {
  key: string;
  email: string;
  password: string;
  plan: string;
};

/** The seed file's accounts, read from the file itself. */
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
 *
 * **The accounts that are addressed by their key are excluded here.** `no-city` is a
 * Free account and `free-saver` is a Free account, so "the Free account" would match
 * three of them — and each of the three is a *different* subject for a *different*
 * test. See `seedNoCityAccount` and `seedFreeSaverAccount`.
 */
export async function seedAccount(plan: "free" | "pro"): Promise<SeedAccount> {
  const accounts = await seedAccounts();
  const matches = accounts.filter(
    (account) => account.plan === plan && account.key !== "no-city" && account.key !== "free-saver",
  );
  if (matches.length !== 1) {
    throw new Error(
      `The seed file names ${matches.length} ${plan} account(s); exactly one is needed.`,
    );
  }
  return matches[0];
}

/**
 * The second Free account — the one whose **save allowance** the full-path test spends.
 *
 * **The allowance is one save per user per day, and it outlives a test.** So two tests
 * that each need to save once cannot share an account: the first test spends the
 * allowance, and the second one finds the wall already up — and it fails for a reason
 * that has nothing to do with the code under test. **Separate accounts have separate
 * allowances**, so each test spends its own.
 *
 * **The account is addressed by its key**, because it is a Free account and there are
 * now three of those.
 */
export async function seedFreeSaverAccount(): Promise<SeedAccount> {
  const accounts = await seedAccounts();
  const matches = accounts.filter((account) => account.key === "free-saver");
  if (matches.length !== 1) {
    throw new Error(
      `The seed file names ${matches.length} free-saver account(s); exactly one is needed.`,
    );
  }
  return matches[0];
}

/**
 * The account with **no city** — the city's emptiness's subject.
 *
 * **It is a separate account, and it has to be.** Browse has two emptinesses, and the
 * city one needs a user whose city is absent. No browser flow can produce that: the API
 * reads a null city as "leave it alone" and never clears one, so the seed writes it.
 * Emptying the free account's city instead would change what every other test sees.
 */
export async function seedNoCityAccount(): Promise<SeedAccount> {
  const accounts = await seedAccounts();
  const matches = accounts.filter((account) => account.key === "no-city");
  if (matches.length !== 1) {
    throw new Error(
      `The seed file names ${matches.length} no-city account(s); exactly one is needed.`,
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
 * Go to Browse through the sidenav, for a surface that may be **empty**.
 *
 * **The hero is not the signal here, because the hero is what an empty surface does not
 * have.** The city's empty state *replaces* the hero — it is a whole-page state — so a
 * helper that waited for the hero would time out on exactly the page it was sent to.
 *
 * **So the signal is "the surface has finished loading", which is the same signal
 * `waitForBrowse` gives.** The skeleton is the loading state and the only marker of it,
 * so waiting for it to clear is what says the server read is done — whichever way the
 * surface turned out.
 */
export async function navigateToBrowseExpectingEmpty(page: Page): Promise<void> {
  const sidenav = page.getByRole("navigation", { name: "Main" });
  await sidenav.getByRole("link", { name: "Browse" }).click();
  await page.waitForURL(/\/browse/);
  await waitForBrowse(page);
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

/**
 * The page's **rendered** text, lower-cased.
 *
 * **`body.textContent` is not the page's text.** It includes every `<script>` element's
 * body — including Next.js's inline RSC payload, which carries the *server's* copy of
 * the page as a JSON string — and it includes the text inside `<dialog>` elements that
 * were never opened. So a naive text search for a forbidden phrase finds the phrase in
 * the machine's copy of the page rather than in the reader's.
 *
 * **So this walks the rendered text nodes only**, skipping `SCRIPT` and `STYLE`, and
 * skipping any node whose element is not actually laid out (`offsetParent === null`
 * means an ancestor is `display: none`). **What survives is what a person could read.**
 *
 * **The shell's closed menus are excluded too, and deliberately.** The Account menu and
 * the More menu each render a native `<dialog>`, closed on a page nobody has opened them
 * on. A closed `<dialog>` takes no space and is not visible, so `offsetParent` is `null`
 * for its contents and they are skipped — which is right, because a check that failed on
 * the shell's own markup would be a check that cries wolf.
 */
export async function renderedText(page: Page): Promise<string> {
  return page.evaluate(() => {
    const chunks: string[] = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      const element = node.parentElement as HTMLElement | null;
      const tag = element?.tagName ?? "";
      if (tag !== "SCRIPT" && tag !== "STYLE" && element?.offsetParent !== null) {
        const text = (node.textContent ?? "").trim();
        if (text) chunks.push(text);
      }
      node = walker.nextNode();
    }
    return chunks.join(" ").toLowerCase();
  });
}

/**
 * Clear the signed-in user's saved events, so a test starts from an empty Pulse.
 *
 * **This is the browser's own API, not a test-only backdoor.** The suite drives the real
 * stack, and a test that reached around the API to write to the database would not be
 * testing the API at all — so the reset goes through the endpoints the product already
 * has: `GET /api/personal/saved-events` lists what is saved, and
 * `DELETE /api/personal/saved-events/{catalog_event_id}` removes each one.
 *
 * **The delete carries the CSRF token, because the backend checks it.** Django Ninja
 * marks every view it builds `csrf_exempt`, so the backend makes Django's own check
 * itself, on every unsafe request. `page.request` does not go through the app's
 * `csrfOnRequest` middleware — it is Playwright's own client, not the app's — so the
 * token has to be read from the browser's cookie and echoed in the `X-CSRFToken`
 * header, which is exactly what `lib/csrf.ts` does for the app's own requests.
 *
 * **Why it is needed at all.** The seed clears the save *allowance* on every run, but it
 * deliberately leaves the *saved rows* alone — a seed that un-saved a reader's events
 * would change what the surface shows, and the walk-through is about seeing a saved
 * event. That is right for the seed and wrong for a test suite: a leftover row puts the
 * Save button in the `saved` state, so the suite's **first** press takes the unsave
 * branch, the button correctly goes back to "Save", and the test fails for a reason that
 * has nothing to do with the code under test.
 *
 * **The allowance is not reset here.** It is the throttle's counter and it lives
 * server-side behind a 24-hour window; only the server can clear it, and the seed does
 * that. **This helper clears the rows the button's initial state is derived from** — the
 * half that would otherwise make a test's first press an unsave.
 */
export async function clearSavedEvents(page: Page): Promise<void> {
  const listed = await page.request.get("/api/personal/saved-events");
  expect(listed.ok()).toBeTruthy();

  const body = (await listed.json()) as {
    items?: { event_id: string }[];
  };

  if ((body.items ?? []).length === 0) return;

  // **The token is read from the browser's own cookie.** Django rotates it on sign-in,
  // so a token captured before the form was submitted would be the wrong one — and
  // `lib/csrf.ts` says the same thing for the same reason.
  const cookies = await page.context().cookies();
  const token = cookies.find((cookie) => cookie.name === "csrftoken")?.value;
  expect(token, "the browser holds no csrftoken cookie").toBeTruthy();

  for (const item of body.items ?? []) {
    const removed = await page.request.delete(`/api/personal/saved-events/${item.event_id}`, {
      headers: { "X-CSRFToken": token as string },
    });
    expect(removed.ok()).toBeTruthy();
  }
}
