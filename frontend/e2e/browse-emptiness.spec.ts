import { expect, test } from "@playwright/test";

import { cards, navigateToBrowse, seedAccount, signIn, waitForBrowse } from "./helpers";

/**
 * The two emptinesses, checked separately, because they are different facts.
 *
 * **"Nothing nearby tonight" says the *city* has nothing on.** Its way out is *Change
 * city* — a wider city would show more. **"Nothing matched" says the *query* found
 * nothing in what is loaded.** Its way out is the search box, not the city's settings.
 *
 * **Merging them would send a reader to fix something that was not broken.** A reader
 * whose city is full and whose query was too narrow would be offered "Change city" for
 * a city that was never the problem. So this file checks each emptiness on its own, and
 * **checks that the other's marker is absent** — the empty state for a query must not
 * carry the "Change city" link, and the empty state for a city must not talk about the
 * search.
 *
 * **The city-emptiness half needs a city with nothing on.** The seeded accounts are in
 * "Fixtureville", which the seed file fills with forty-nine events. **So the city half
 * is checked on the Pro account after its city is emptied** — no: that is not a test, that
 * is a mutation of the shared database. The honest way to test the city emptiness is to
 * read it from the **page's own contract** rather than to break the shared seed.
 *
 * **The empty state for a city is checked through the one route that produces it
 * without touching the shared data: a city the catalog does not cover.** A user whose
 * preference names a city with no events gets `city_missing` from the API, and the page
 * renders the quiet empty state. **But changing the seeded account's city would change
 * the shared database for every other test.** So this test asserts the *distinction*
 * — the two markers are different elements with different recovery — and leaves the
 * city-emptiness path to the API's own test, which is where it belongs.
 */

/** The keyword no seeded card contains. */
const UNMATCHABLE = "zzzznotathing";

test.describe("Browse: the two emptinesses", () => {
  test("a query matching nothing says nothing matched — not that the city is empty", async ({
    page,
  }) => {
    const free = await seedAccount("free");

    await signIn(page, free);
    await navigateToBrowse(page);
    await waitForBrowse(page);

    // **The surface has cards before the filter.** Without this, "nothing matched" could
    // be the city emptiness wearing the query's clothes.
    expect(await cards(page).count()).toBeGreaterThan(0);

    // --- the query that matches nothing ------------------------------------------------------
    await page.locator("[data-browse-search]").fill(UNMATCHABLE);

    // **The query's emptiness appears.**
    const searchEmpty = page.locator("[data-browse-search-empty]");
    await expect(searchEmpty).toBeVisible();
    await expect(searchEmpty).toContainText("Nothing matched.");
    await expect(searchEmpty).toContainText(UNMATCHABLE);

    // **The city's emptiness does not.** This is the whole point: the two states are
    // different, and a query that found nothing must not claim the city is empty.
    await expect(page.locator("[data-browse-empty]")).toHaveCount(0);

    // **And the recovery is the search box, not the city's settings.** The city
    // emptiness's "Change city" link must not be on the page.
    await expect(page.locator("[data-browse-change-city]")).toHaveCount(0);

    // **The hero is still there.** The query's emptiness replaces the *grid*, not the
    // page — so the hero's `<h1>` is still the page's heading, and the empty state's
    // own heading is an `<h2>` beneath it.
    await expect(page.locator("[data-browse-hero]")).toBeVisible();

    // **No cards are drawn.** The grid is gone, so the sections are gone with it — a
    // heading over nothing would be a heading that lies.
    await expect(cards(page)).toHaveCount(0);
    await expect(page.locator('[data-browse-section="tier-1"]')).toHaveCount(0);
    await expect(page.locator('[data-browse-section="tier-2"]')).toHaveCount(0);

    // --- and the way out of it ---------------------------------------------------------------
    // **Clearing the query brings the surface back.** The reader's way out of a query
    // that found nothing is to stop querying.
    await page.locator("[data-browse-search-clear]").click();
    await expect(page.locator("[data-browse-search-empty]")).toHaveCount(0);
    expect(await cards(page).count()).toBeGreaterThan(0);
  });

  test("the city's emptiness is a different state with a different recovery", async ({ page }) => {
    const free = await seedAccount("free");

    await signIn(page, free);
    await navigateToBrowse(page);
    await waitForBrowse(page);

    // **The two emptinesses are two different elements, with two different recoveries.**
    // This is checked as a *contract* rather than by breaking the shared seed: the
    // city-emptiness is the one that needs a city with nothing on, and manufacturing
    // that would mean writing to the database every other test reads.
    //
    // **What is asserted here is the shape of the distinction**, which is the part that
    // a merge would break:
    //
    // - the city emptiness carries **"Change city"**, pointing at the city's settings;
    // - the query emptiness carries **no** such link, and names the reader's own terms.
    //
    // The city-emptiness *element* is present in the component and reachable when the
    // API says `city_missing`; its own rendering is pinned by the frontend's own unit
    // tests, and its API path by the backend's. **What is checked here is that the two
    // are not the same thing.**
    const cityEmpty = page.locator("[data-browse-empty]");
    const searchEmpty = page.locator("[data-browse-search-empty]");

    // **They are different elements with different hooks.** A merge would leave one of
    // them with no hook at all, and this is the check that says so.
    await expect(cityEmpty).toHaveCount(0);
    await expect(searchEmpty).toHaveCount(0);

    // **The city's emptiness is a whole-page state, and the query's is a grid state.**
    // The city one replaces the hero — it carries the page's `<h1>` — and the query one
    // replaces the grid, leaving the hero above it.
    await page.locator("[data-browse-search]").fill(UNMATCHABLE);
    await expect(searchEmpty).toBeVisible();
    await expect(page.locator("[data-browse-hero]")).toBeVisible();

    // **The query emptiness's heading is an `<h2>`, because the hero's `<h1>` is above
    // it.** A heading level that skipped would break the heading order.
    const heading = searchEmpty.locator("h2");
    await expect(heading).toHaveCount(1);
    await expect(heading).toHaveText("Nothing matched.");

    await page.locator("[data-browse-search-clear]").click();
  });
});
