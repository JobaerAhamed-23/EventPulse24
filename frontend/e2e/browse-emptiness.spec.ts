import { expect, test } from "@playwright/test";

import {
  cards,
  navigateToBrowse,
  navigateToBrowseExpectingEmpty,
  seedAccount,
  seedNoCityAccount,
  signIn,
  waitForBrowse,
} from "./helpers";

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
 * **The city-emptiness half needs a user whose city is absent, and the seed provides
 * one.** The accounts the other specs use are in "Fixtureville", which the seed file
 * fills with forty-nine events — so none of them can show the city's emptiness. The
 * seed therefore writes an account of its own, `no-city`, whose city is absent.
 *
 * **A third account, not an emptied one.** Clearing the free account's city would
 * change what every other test sees — the free account's cards *are* the other tests'
 * subject — and the API will not do it anyway: `PUT /onboarding/digest-preference` reads
 * a null city as "leave it alone", so no browser flow can produce the state. The seed
 * writes it, and `make test-e2e`'s seed is repeatable, so the state is there every run.
 *
 * **An earlier version of this file did not test the city half at all**, on the
 * grounds that manufacturing the state would mean mutating the shared database. The
 * reasoning was sound and the conclusion was wrong: the state was reachable, and a
 * test that declines to reach it is a gap with a good excuse.
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
    //
    // **The assertion is scoped to the empty state, and it has to be.** The hook
    // `data-browse-change-city` is on the **hero's** "Change city" link as well as the
    // empty state's — the hero names the city and offers to change it on every page.
    // So "no Change city link anywhere on the page" would be asserting that the hero
    // does not exist, which is a different claim and a false one. What must be absent is
    // the *empty state's* link: the query's emptiness recovers through the search box.
    await expect(page.locator("[data-browse-empty] [data-browse-change-city]")).toHaveCount(0);

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

  test("a city with nothing on says nothing nearby — and offers Change city", async ({ page }) => {
    const noCity = await seedNoCityAccount();

    await signIn(page, noCity);

    // **The empty surface has no hero, so the navigation cannot wait for one.** The
    // city's empty state replaces the hero, and a helper that waited for the hero
    // would time out on exactly the page it was sent to.
    await navigateToBrowseExpectingEmpty(page);

    // **The city's emptiness appears.** It is a whole-page state — it replaces the
    // hero — and it says what the design says it says: *"Nothing nearby tonight. Try a
    // wider city?"*
    const cityEmpty = page.locator("[data-browse-empty]");
    await expect(cityEmpty).toBeVisible();
    await expect(cityEmpty).toContainText("Nothing nearby tonight");

    // **Its heading is the page's `<h1>`.** The city emptiness replaces the hero, so
    // it carries the page's own heading level — unlike the query's emptiness, which sits
    // *under* the hero and is an `<h2>`. A heading level that skipped would break the
    // heading order, and this is the half of the distinction a merge would break.
    await expect(cityEmpty.locator("h1")).toHaveCount(1);
    await expect(cityEmpty.locator("h1")).toHaveText("Nothing nearby tonight. Try a wider city?");

    // **And its way out is "Change city", pointing at the city's settings.** This is
    // the difference between the two emptinesses in one assertion: the city's problem
    // is the city, so the recovery is the city.
    const changeCity = cityEmpty.locator("[data-browse-change-city]");
    await expect(changeCity).toBeVisible();
    await expect(changeCity).toHaveAttribute("href", "/settings/account");

    // **The hero is gone, because the empty state took its place.** A hero saying
    // "Fixtureville" above a "nothing nearby" message would claim a city the surface
    // has nothing for.
    await expect(page.locator("[data-browse-hero]")).toHaveCount(0);

    // **And the query's emptiness is not here.** A user with no city has not run a
    // query, so the query's empty state — with its "Nothing matched." and its search
    // box — must not be on the page.
    await expect(page.locator("[data-browse-search-empty]")).toHaveCount(0);

    // **No cards are drawn.** The grid is gone, so the sections are gone with it.
    await expect(cards(page)).toHaveCount(0);
    await expect(page.locator('[data-browse-section="tier-1"]')).toHaveCount(0);
    await expect(page.locator('[data-browse-section="tier-2"]')).toHaveCount(0);

    // **There is no search box either.** A search over nothing would be a search over
    // no city — and the design's answer to "nothing nearby" is a wider city, not a
    // narrower query.
    await expect(page.locator("[data-browse-search]")).toHaveCount(0);
  });

  test("the two emptinesses are different elements with different recoveries", async ({ page }) => {
    const free = await seedAccount("free");

    await signIn(page, free);
    await navigateToBrowse(page);
    await waitForBrowse(page);

    // **They are different elements with different hooks.** A merge would leave one of
    // them with no hook at all, and this is the check that says so.
    const cityEmpty = page.locator("[data-browse-empty]");
    const searchEmpty = page.locator("[data-browse-search-empty]");

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

    // **And it carries no "Change city".** The query's problem is the query, and the
    // query's recovery is the search box — not the city's settings.
    await expect(searchEmpty.locator("[data-browse-change-city]")).toHaveCount(0);

    await page.locator("[data-browse-search-clear]").click();
  });
});
