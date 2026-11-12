import { expect, test } from "@playwright/test";

import { cards, navigateToBrowse, saveButton, seedAccount, signIn, waitForBrowse } from "./helpers";

/**
 * The Free quota wall, and the Pro account's absence of one.
 *
 * **The Free account's allowance is one save a day, and the refusal is inline.** The
 * design says it plainly: *"A cap that interrupts with a modal is a cap that trains
 * people to dismiss prompts."* So the second Save is refused **in place**, under the
 * button, as a `role="status"` line with the upgrade copy — **and no modal appears.**
 *
 * **The "no modal" half is the half that is easy to get wrong and is therefore
 * asserted explicitly.** A test that only checked the refusal line would pass even if a
 * modal appeared *as well*. So this test checks both: the inline line is there, **and**
 * the page has no dialog, no `aria-modal`, and no overlay. A refusal that interrupts is
 * the failure this test exists to catch.
 *
 * **The Pro account has no cap at all.** `cap` is `null` for Pro — not a large number —
 * so there is nothing to hit. The Pro test saves repeatedly and every save lands.
 */

/**
 * The modal that must never appear.
 *
 * **It is checked as a set of selectors, because a modal has several shapes.** A
 * `role="dialog"`, an `aria-modal="true"`, a `<dialog>` element, a Next.js route
 * announcement — any of them would be an interruption. And an overlay is a modal's
 * visual half: a fixed, full-screen element over the page.
 */
async function assertNoModal(page: import("@playwright/test").Page): Promise<void> {
  await expect(page.locator('[role="dialog"]')).toHaveCount(0);
  await expect(page.locator('[aria-modal="true"]')).toHaveCount(0);
  await expect(page.locator("dialog")).toHaveCount(0);
  // **The overlay.** A fixed, inset-0 element covering the viewport. The upgrade sheet
  // and the add-event sheet both use one, so this is the shape an interruption takes.
  await expect(page.locator('div[class*="fixed"][class*="inset-0"]:visible')).toHaveCount(0);
}

test.describe("Browse: the save quota", () => {
  test("the Free account's second save is refused inline, with the upgrade copy and no modal", async ({
    page,
  }) => {
    const free = await seedAccount("free");

    await signIn(page, free);
    await navigateToBrowse(page);
    await waitForBrowse(page);

    // **The first save lands.** One save is the Free allowance, so this is the one that
    // works — and it has to work, or the second save would be refused for the wrong
    // reason.
    const first = cards(page).first();
    await saveButton(first).click();
    await expect(saveButton(first)).toHaveText("Saved ✓");

    // **The hero says the allowance is spent.** The number is the payload's: "1 of 1
    // save used today".
    await expect(page.locator("[data-browse-quota]")).toContainText("1 of 1 save");

    // --- the second save, on a different card ------------------------------------------------
    const second = cards(page).nth(1);
    const secondTitle = (await second.locator("h3").textContent())?.trim() ?? "";

    // **The second card's button reads the wall, not "Save".** The button's label is the
    // allowance as the payload states it — "1 of 1 save used today" — so the reader can
    // see the wall before pressing.
    await expect(saveButton(second)).toHaveText("1 of 1 save used today");

    // **And it is disabled.** A wall that still accepted the press and then refused it
    // would be a button that invites the click it will reject.
    await expect(saveButton(second)).toBeDisabled();

    // **Pressing it anyway must not produce a save.** A disabled button does not fire
    // the handler, so this is belt-and-braces against a `disabled` that is not honoured.
    await saveButton(second).click({ force: true });
    await expect(saveButton(second)).toHaveText("1 of 1 save used today");

    // **The refusal is inline, with the upgrade copy.** It is a `role="status"` line
    // under the button — the API's own words plus the upgrade link.
    const refusal = page.locator("[data-browse-save-cap]");
    await expect(refusal).toBeVisible();
    await expect(refusal).toContainText("used your 1 free save today");
    await expect(page.locator("[data-browse-save-upgrade]")).toBeVisible();

    // **And no modal appeared.** The refusal is a line in the page's normal flow.
    await assertNoModal(page);

    // **Nothing was saved.** The second card's button still reads the wall, and the card
    // is not in the saved set.
    await expect(saveButton(second)).not.toHaveText("Saved ✓");

    // **The refusal survived a reload.** The server's gate is the gate — the client does
    // not remember a refusal, and the page does not either.
    await page.reload();
    await waitForBrowse(page);
    await expect(page.locator("[data-browse-quota]")).toContainText("1 of 1 save");
    await expect(page.locator("[data-browse-save-cap]")).toHaveCount(0);
    await expect(saveButton(cards(page).nth(1))).toHaveText("1 of 1 save used today");

    // **The first card is still saved**, so the reload did not lose the save either.
    await expect(saveButton(cards(page).first())).toHaveText("Saved ✓");
    expect(secondTitle.length).toBeGreaterThan(0);
  });

  test("the Pro account saves repeatedly, with no cap", async ({ page }) => {
    const pro = await seedAccount("pro");

    await signIn(page, pro);
    await navigateToBrowse(page);
    await waitForBrowse(page);

    // **The hero says there is no limit.** `cap` is `null` for Pro, so the note says
    // "Pro plan · no save limit" — and there is no number to hit.
    await expect(page.locator("[data-browse-quota]")).toContainText("no save limit");

    // **Five saves, five successes.** The Free allowance is one, so five is four past it.
    // **Each card's button morphs to "Saved ✓"** and no card is refused.
    for (let index = 0; index < 5; index += 1) {
      const card = cards(page).nth(index);
      const button = saveButton(card);

      // **The button reads "Save", not the wall's label.** A Pro account's card never
      // shows the spent-allowance label.
      await expect(button).toHaveText("Save");
      await button.click();
      await expect(button).toHaveText("Saved ✓");
    }

    // **No refusal line anywhere.** The cap line is a Free-only state.
    await expect(page.locator("[data-browse-save-cap]")).toHaveCount(0);

    // **And no modal, either.** The Pro path has no interruption to interrupt with, and
    // the check is the same one the Free test makes.
    await assertNoModal(page);

    // **The saves survive a reload**, which is the server's state and not the client's.
    await page.reload();
    await waitForBrowse(page);
    for (let index = 0; index < 5; index += 1) {
      await expect(saveButton(cards(page).nth(index))).toHaveText("Saved ✓");
    }
  });
});
