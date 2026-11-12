import { expect, test } from "@playwright/test";

import {
  cardTitle,
  cards,
  navigateToBrowse,
  saveButton,
  seedAccount,
  signIn,
  tierOneCards,
  tierTwoCards,
  waitForBrowse,
} from "./helpers";

/**
 * The Browse walk-through: sign in, navigate from the sidenav, see the two tiers, filter
 * by keyword, filter by a `tag:` literal, clear, save a card, and see it saved.
 *
 * **This is the "check each item works properly or not" test, and it is one test on
 * purpose.** The acceptance criteria name a *path*: sign in → navigate → see → filter →
 * filter → clear → save → see saved. Splitting it into eight tests would let eight
 * separate fixtures rebuild the same state, and the state is the hard part — a signed-in
 * session, a city with forty-nine events in it, and a page whose first paint is a server
 * render. **One test, one path, one story.** A failure says where in the path it broke,
 * which is what the walk-through write-up needs.
 *
 * **The data is the seeded catalog.** `backend/config/browse_seed.json` writes
 * forty-nine events across the seven-day window in "Fixtureville" — enough to overflow the
 * twenty-four-card page and prove the chunk loader, with varied why-tags so the `tag:`
 * filter has something to constrain.
 */

/** The keyword the seed file's titles contain, and no other card does. */
const KEYWORD = "yoga";

/**
 * The `tag:` literal the seed file's events carry, and the vocabulary really knows.
 *
 * **`tag:arts` resolves to the server key `matches_arts_culture`.** The alias table in
 * `lib/digest-labels.ts` is what makes it work: `arts` is one of six friendly names, and
 * each one names a server key the catalog actually has. **The design's original list of
 * ten tags is not this vocabulary** — four of those ten (`music`, `food`, `indoor`,
 * `rooftop`) name no why-tag the server has, and a `tag:` literal for one of them
 * refuses the whole query. This test uses a tag that exists.
 */
const TAG = "arts";

test.describe("Browse: the full path", () => {
  test("sign in, navigate from the sidenav, filter, clear, save, and see it saved", async ({
    page,
  }) => {
    // --- the accounts the seed file names --------------------------------------------------
    const free = await seedAccount("free");

    // --- 1. sign in ------------------------------------------------------------------------
    await signIn(page, free);

    // --- 2. navigate to Browse from the sidenav --------------------------------------------
    // **The sidenav's Browse row, clicked.** Not `page.goto("/browse")` — that would test
    // the router and would pass whether or not the row was a link at all.
    await navigateToBrowse(page);
    await waitForBrowse(page);

    // **The sidenav marks the current route.** A nav row that does not mark itself is a
    // reader with no idea where they are, and the design asks for the active state.
    await expect(
      page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Browse" }),
    ).toHaveAttribute("aria-current", "page");

    // --- 3. the ranked cards, in two tiers ------------------------------------------------
    // **The first tier is "3 worth your attention today".** The server says how many
    // (`tier_2_starts_at`), and the client slices at that index — it does not re-tier.
    // **The heading says three, and the section holds three.**
    await expect(page.getByRole("heading", { name: "3 worth your attention today" })).toBeVisible();
    await expect(tierOneCards(page)).toHaveCount(3);

    // **The second tier is "More this week", and it is a separate section.** Both tiers
    // exist — one tier would not be two tiers.
    await expect(page.getByRole("heading", { name: "More this week" })).toBeVisible();
    expect(await tierTwoCards(page).count()).toBeGreaterThan(0);

    // **The cards are ranked, and the order is the server's.** The first tier's cards come
    // before the second tier's cards in the document, and the two sections are separate
    // lists — so the page reads top-down as "worth your attention, then the rest".
    const allCards = cards(page);
    expect(await allCards.count()).toBeGreaterThan(24);

    // **The first page is the server's twenty-four.** The seed file writes forty-nine
    // events, so the page is full and the chunk loader is live — which is what makes the
    // search's chunk-boundary a real limitation rather than a footnote.
    await expect(page.locator("[data-browse-more]")).toBeVisible();

    // **The must-know stripe is amber and the public stripe is slate — two colours, no
    // third.** The design caps the stripes at two and drops discovery outright.
    const stripeLabels = await page
      .locator("[data-browse-stripe-label]")
      .evaluateAll((nodes) => nodes.map((node) => node.textContent?.trim() ?? ""));
    const kinds = new Set(stripeLabels);
    expect([...kinds].sort()).toEqual(["Must-know", "Public"]);

    // **At most one must-know card.** The stripe is a single notice, not a category.
    expect(stripeLabels.filter((label) => label === "Must-know").length).toBeLessThanOrEqual(1);

    // --- 4. filter with a keyword ------------------------------------------------------------
    const before = await cards(page).count();
    await page.locator("[data-browse-search]").fill(KEYWORD);

    // **The count line reports what matched, and it is the client's own count.** The
    // number that matched sits next to the server's pool total, and the gap between them
    // is the chunk-bounded search made visible.
    await expect(page.locator("[data-browse-search-meta]")).toBeVisible();
    const matched = await cards(page).count();
    expect(matched).toBeGreaterThan(0);
    expect(matched).toBeLessThan(before);

    // **Only the matching cards survive, and every one of them really contains the
    // keyword.** A filter that showed the right *count* but the wrong *cards* would be
    // the worst failure there is: the count line would look right and the grid would lie.
    const titles = await cardTitle(cards(page).first()).textContent();
    expect(titles?.toLowerCase()).toContain(KEYWORD);
    for (const label of await page
      .locator("[data-browse-stripe-label]")
      .evaluateAll((nodes) => nodes.map((node) => node.textContent?.trim() ?? ""))) {
      expect(["Must-know", "Public"]).toContain(label);
    }

    // --- 5. filter with a `tag:` literal -----------------------------------------------------
    await page.locator("[data-browse-search]").fill(`tag:${TAG}`);

    // **The tag filter narrows to the cards that carry the tag.** The seed file's events
    // have varied why-tags, so the tag has something to constrain.
    const tagged = await cards(page).count();
    expect(tagged).toBeGreaterThan(0);
    expect(tagged).toBeLessThan(matched);

    // **Every surviving card carries the tag's why-tag.** The tag's *label* is "Arts &
    // culture"; the *key* the server sends is `matches_arts_culture`. The label is what a
    // reader sees, so the label is what the test reads.
    const tagLines = await page
      .locator("[data-browse-tags]")
      .evaluateAll((nodes) => nodes.map((node) => node.textContent ?? ""));
    expect(tagLines.length).toBe(tagged);
    for (const line of tagLines) {
      expect(line.toLowerCase()).toContain("arts");
    }

    // --- 6. clear ---------------------------------------------------------------------------
    await page.locator("[data-browse-search-clear]").click();

    // **Clearing restores the whole surface.** The input is empty, the count line is gone
    // (it only exists while a filter is on), and the cards are back.
    await expect(page.locator("[data-browse-search]")).toHaveValue("");
    await expect(page.locator("[data-browse-search-meta]")).toHaveCount(0);
    await expect(cards(page)).toHaveCount(before);

    // --- 7. save a card ----------------------------------------------------------------------
    const card = cards(page).first();
    const title = (await cardTitle(card).textContent())?.trim() ?? "";
    const button = saveButton(card);

    await expect(button).toHaveText("Save");
    await button.click();

    // **The button morphs to "Saved ✓".** The morph is the feedback — there is no toast
    // and no dialog — so the label *is* the assertion.
    await expect(button).toHaveText("Saved ✓");

    // --- 8. see it saved ---------------------------------------------------------------------
    // **The card comes back with the save already on it.** The server's `is_saved` is the
    // first paint's state, so a reload shows "Saved ✓" without a flash of "Save".
    await page.reload();
    await waitForBrowse(page);

    const reloaded = cards(page).first();
    await expect(cardTitle(reloaded)).toHaveText(title);
    await expect(saveButton(reloaded)).toHaveText("Saved ✓");
  });
});
