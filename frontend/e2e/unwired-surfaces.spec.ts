import { execFile } from "node:child_process";
import path from "node:path";
import { promisify } from "node:util";

import { expect, test } from "@playwright/test";

import {
  cards,
  clearSavedEvents,
  navigateToBrowse,
  saveButton,
  seedAccount,
  signIn,
  waitForBrowse,
} from "./helpers";

/** `execFile`, promisified — the walkthrough runs the product's own commands. */
const run = promisify(execFile);

/**
 * The backend's directory, resolved from the working directory.
 *
 * **Not from `import.meta.url`** — Playwright loads test files through its own CommonJS
 * loader, where `import.meta` is unavailable. Same constraint `helpers.ts` records.
 */
const BACKEND_DIR = path.resolve(process.cwd(), "../backend");

/**
 * The walkthrough for `unwired-surfaces`, in a real browser.
 *
 * **This intent is the one place where a unit test is structurally the wrong instrument.**
 * Every gap it closed sat behind a green suite: four endpoints were built, tested and
 * documented while nothing called them, and two components had full coverage while nothing
 * rendered them. A test that mounts a component proves the component works. It cannot prove
 * **a person can get to it**, and that is the only thing this intent was ever about.
 *
 * So each test below starts from a signed-in browser and navigates — no deep links into
 * components, no mocked client. If a control is unreachable, these fail.
 *
 * **The sign-in throttle is real and will bite on the second run.**
 * `AUTH_THROTTLE_SIGN_IN_IP` is ten an hour per IP and `AUTH_THROTTLE_SIGN_IN_ACCOUNT` is
 * five per account (`shared/constants.py:466-468`), so a walkthrough that signs in once per
 * test burns the account's five on its second run. The allowance is given back through the
 * product's own `reset_sign_in_throttle` — the same function `make seed-browse` calls. It is
 * not a backdoor around the throttle; it is the throttle's own reset.
 */
async function resetSignInThrottle(emails: string[]): Promise<void> {
  const script = [
    "from apps.identity.services.throttle import reset_sign_in_throttle",
    "reset_sign_in_throttle(ip_address='127.0.0.1', emails=" + JSON.stringify(emails) + ")",
  ].join("\n");
  await run("uv", ["run", "python", "manage.py", "shell", "-c", script], { cwd: BACKEND_DIR });
}

/** Read one fact out of the database, through the product's own models. */
async function backendFact(script: string): Promise<string> {
  const { stdout } = await run("uv", ["run", "python", "manage.py", "shell", "-c", script], {
    cwd: BACKEND_DIR,
  });
  const marker = stdout.indexOf("@@FACT@@");
  expect(marker, `the script printed no @@FACT@@ marker:\n${stdout}`).toBeGreaterThanOrEqual(0);
  return stdout.slice(marker + "@@FACT@@".length).trim();
}

test.describe("unwired-surfaces: the controls are reachable in a browser", () => {
  test.beforeAll(async () => {
    const [free, pro] = await Promise.all([seedAccount("free"), seedAccount("pro")]);
    await resetSignInThrottle([free.email, pro.email]);
  });

  /**
   * FR-49. The endpoint existed and had no caller; a collection could not be filled.
   *
   * **The assertion is on the collection's contents, not on a request.** A request-level
   * assertion is what the unit suite already does; this one proves the save is *in there*
   * afterwards.
   */
  test("FR-49: a Pro user can save an event and put it into a collection", async ({ page }) => {
    const pro = await seedAccount("pro");
    await signIn(page, pro);

    // **The save is made by this test**, not assumed from the seed. A Pro account with no
    // saves is a legitimate state, and a walkthrough that skipped on it would report
    // "passed" for the one thing this intent built.
    // **Start from no saves.** The Save control toggles, so a re-run that found the
    // previous run's save would *un*-save it and then find an empty picker — which is
    // exactly how the second run of this walkthrough failed.
    await page.goto("/browse");
    await clearSavedEvents(page);
    // **Reload after clearing.** The Save control is a toggle rendered from the state the
    // page was served with; without this the button still reads "saved" and pressing it
    // *un*-saves, leaving the picker empty — how the second run failed.
    await page.reload();

    await navigateToBrowse(page);
    await waitForBrowse(page);
    const firstCard = cards(page).first();
    await expect(firstCard).toBeVisible();
    await saveButton(firstCard).click();

    await page.goto("/settings/collections");
    await expect(page.getByRole("heading", { name: "Collections" })).toBeVisible();

    // A fresh collection, so the test does not depend on what earlier runs left behind.
    const name = `Walkthrough ${Date.now()}`;
    await page.getByLabel("New collection").fill(name);
    await page.getByRole("button", { name: "Create" }).click();

    const collection = page.getByRole("button", { name: new RegExp(`^${name}`) });
    await expect(collection).toBeVisible();
    await collection.click();

    // **The control this intent built.** Before it, the empty collection pointed at a
    // saved-events screen that rendered nowhere, and the endpoint had no caller at all.
    const addSave = page.getByRole("button", { name: "Add a save" });
    await expect(addSave, "the Add a save control is not reachable").toBeVisible();
    await addSave.click();

    // **Wait for the read to land before asserting on what it found.** The picker has a
    // loading state, and a check that ran before it cleared saw neither a save nor the
    // empty state — which is how the first run of this test failed for the wrong reason.
    await expect(page.locator("[data-picker-loading]")).toHaveCount(0);

    const offered = page.locator("[data-assign-picker] button[data-assign]");
    await expect(offered.first(), "the picker offered nothing to assign").toBeVisible();
    await offered.first().click();

    // The save is in the collection now: its contents list is no longer empty.
    await expect(page.locator("[data-collection-events] [data-collection-event]")).not.toHaveCount(
      0,
    );
  });

  /**
   * FR-50. Onboarding promised disconnect twice and there was no screen.
   *
   * The walkthrough reaches it **the way a user would** — from the settings page that
   * carries the link — rather than by typing the URL, because discoverability was half the
   * gap.
   */
  test("FR-50: the calendar screen is reachable from Settings, and offers Disconnect", async ({
    page,
  }) => {
    const free = await seedAccount("free");
    await signIn(page, free);

    await page.goto("/settings/quiet-hours");
    const link = page.getByRole("link", { name: "Calendars you've connected" });
    await expect(link, "nothing in Settings links to the calendar screen").toBeVisible();
    await link.click();

    await expect(page).toHaveURL(/\/settings\/calendars$/);
    await expect(page.getByRole("heading", { name: "Calendar sync" })).toBeVisible();

    // Either a connection with a Disconnect control, or the honest empty state — never an
    // error, and never a screen with no account of itself.
    const disconnect = page.getByRole("button", { name: "Disconnect" });
    const empty = page.locator("[data-no-calendars]");
    expect(
      (await disconnect.count()) + (await empty.count()),
      "the screen rendered neither a connection nor the empty state",
    ).toBeGreaterThan(0);
  });

  /**
   * FR-20. `ReminderPicker` was mounted once, hard-coded to `saved_event`.
   *
   * Reached through the edit sheet's link, which is the only way a user finds it.
   */
  test("FR-20: a personal event's reminders are reachable from its edit sheet", async ({
    page,
  }) => {
    const free = await seedAccount("free");
    await signIn(page, free);

    // **The event is created by this test.** The seeded accounts carry no personal event,
    // and a walkthrough that skipped on that would report "passed" for the surface this
    // item built.
    await page.goto("/timeline");
    const sidenav = page.getByRole("navigation", { name: "Main" });
    await sidenav.getByRole("button", { name: "Add" }).click();

    const createSheet = page.getByRole("dialog", { name: "Add personal event" });
    await expect(createSheet).toBeVisible();
    const name = `Walkthrough dinner ${Date.now()}`;
    await createSheet.getByLabel(/Name/).fill(name);
    // Tomorrow, so it lands inside the week the Timeline shows.
    const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    await createSheet.getByLabel(/^Date/).fill(tomorrow);
    await createSheet.getByLabel(/Start time/).fill("19:30");
    await createSheet.getByRole("button", { name: "Save to my Pulse" }).click();
    await expect(createSheet).toBeHidden();

    // **A conflict is a legitimate outcome, and it opens a sheet that blocks the page.**
    // A previous run of this walkthrough leaves its own 19:30 event behind, so the second
    // run's create overlaps it and the server answers 409 — the event *is* written, and a
    // prompt is pending. The walkthrough answers it the way a user would. Without this,
    // the test times out clicking a Timeline block that an open dialog is covering, which
    // is how it failed on every run after the first.
    const conflict = page.getByRole("dialog", { name: "Schedule conflict" });
    if (await conflict.isVisible().catch(() => false)) {
      await conflict.getByRole("button", { name: /Keep both/ }).click();
      await expect(conflict).toBeHidden();
    }

    // The block the create just put on the Timeline.
    //
    // **Scoped to the desktop grid**, because the Timeline draws the week twice — the
    // grid and the mobile day view are both in the DOM, and the event appears in each.
    // An unscoped match is a strict-mode violation, and `.first()` can land on the copy
    // the viewport has hidden, which is not clickable.
    const block = page
      .locator('[aria-label="Week grid"]')
      .getByRole("button", { name: new RegExp(name) })
      .first();
    await expect(block, "the created event is not on the Timeline").toBeVisible();
    await block.click();

    const sheet = page.getByRole("dialog", { name: "Edit personal event" });
    await expect(sheet).toBeVisible();

    const remindersLink = sheet.getByRole("link", { name: /Edit reminders/ });
    await expect(remindersLink, "the edit sheet offers no way to reach reminders").toBeVisible();
    await remindersLink.click();

    await expect(page).toHaveURL(/\/personal-events\/[0-9a-f-]+\/reminders$/);
    await expect(page.getByRole("heading", { name: "When should we remind you?" })).toBeVisible();
  });

  /**
   * FR-24. The open half of "saved **or** opened" never fired.
   *
   * **The assertion is a database row**, because that is the whole point: the signal is
   * invisible in the UI by design, and a DOM assertion could not tell a working signal from
   * a missing one. Which is exactly how it went unnoticed for three intents.
   */
  test("FR-24: opening a Detail Screen records the open", async ({ page }) => {
    const free = await seedAccount("free");
    await signIn(page, free);

    // **The signal is idempotent per (user, event)** — the endpoint's own words:
    // *"opening the screen again refreshes the timestamp rather than adding a row"*. So a
    // row count cannot prove a write: a re-run of this walkthrough opens the same event
    // and the count does not move. The second run failed exactly that way.
    //
    // **So the assertion is on the row for the event this test opened**, cleared first so
    // the row that is found can only have been written by this run.
    await backendFact(
      [
        "from apps.personalization.models import EventDetailOpen",
        "from shared.db import PERSONAL",
        "EventDetailOpen.objects.using(PERSONAL).all().delete()",
        "print('@@FACT@@cleared')",
      ].join("\n"),
    );

    // **Browse, not the digest.** The digest's contents depend on composition having run
    // for this account; Browse is seeded by `make seed-browse-for-test` and always has
    // cards. The Detail Screen is the same screen either way.
    await navigateToBrowse(page);
    await waitForBrowse(page);
    const card = cards(page).first();
    await expect(card).toBeVisible();
    await card.getByRole("link").first().click();
    await expect(page).toHaveURL(/\/events\//);

    const eventId = new URL(page.url()).pathname.split("/").pop() ?? "";
    expect(eventId, "no event id in the Detail Screen's URL").toMatch(/^[0-9a-f-]{36}$/);

    // The write is fire-and-forget, so the row may land just after the navigation settles.
    await expect
      .poll(
        async () =>
          await backendFact(
            [
              "from apps.personalization.models import EventDetailOpen",
              "from shared.db import PERSONAL",
              `print('@@FACT@@' + str(EventDetailOpen.objects.using(PERSONAL).filter(event_id='${eventId}').exists()))`,
            ].join("\n"),
          ),
        { message: "no EventDetailOpen row was written for the event that was opened" },
      )
      .toBe("True");
  });

  /**
   * **The `.catch` that no unit test in this repo can cover.**
   *
   * `record-detail-open.tsx` swallows a rejected write. A probe that deleted the handler
   * left the Vitest suite green, because Vitest installs its own `unhandledRejection`
   * handler and a listener registered inside a test never fires. A browser is where that
   * failure is visible: an unhandled rejection is a console error on every detail view.
   */
  test("FR-24: opening a Detail Screen logs no unhandled rejection", async ({ page }) => {
    const free = await seedAccount("free");
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));

    await signIn(page, free);
    await navigateToBrowse(page);
    await waitForBrowse(page);
    const card = cards(page).first();
    await expect(card).toBeVisible();
    await card.getByRole("link").first().click();
    await expect(page).toHaveURL(/\/events\//);

    expect(errors, `the page raised: ${errors.join(" | ")}`).toEqual([]);
  });
});
