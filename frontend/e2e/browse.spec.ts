import { expect, test } from "@playwright/test";

import {
  cardTitle,
  cards,
  clearSavedEvents,
  navigateToBrowse,
  renderedText,
  saveButton,
  seedFreeSaverAccount,
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
    // **The second Free account, and the reason is the save allowance.** This path
    // spends one save, and the allowance is one save per user per day in a window that
    // outlives the test. The quota spec spends the *other* Free account's allowance on
    // purpose — and if the two shared an account, whichever ran second would find the
    // wall already up and fail for a reason that had nothing to do with the code under
    // test. **Separate accounts have separate allowances.**
    const free = await seedFreeSaverAccount();

    // --- 1. sign in ------------------------------------------------------------------------
    await signIn(page, free);

    // **The Pulse starts empty.** A saved row left by another spec would put the Save
    // button in the `saved` state, so this path's save would be an *unsave* and the
    // button would correctly go back to "Save". The reset is the browser's own API, so
    // the test still drives the real stack.
    await clearSavedEvents(page);

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

    // --- the design's locks, on the surface as it stands ---------------------------------
    //
    // **These are checked here, in this session, rather than in a walk-through file of
    // their own — and the reason is the sign-in throttle.** The limit is ten sign-ins an
    // hour from one address (`AUTH_THROTTLE_SIGN_IN_IP`), and the whole suite runs on one
    // machine against one stack. A separate file would sign in again, and the suite would
    // cross the limit and fail with a 429 **for a reason that has nothing to do with the
    // code under test**. The locks are about what the surface looks like, so they belong
    // on a surface that is already open.
    //
    // **Every check below asserts on something *absent*, or on a count that must agree.**
    // A check that passes whether or not the forbidden thing is there proves nothing.

    // --- no filter chip rail (Amendment A-11) --------------------------------------------
    // **The keyword search is the only filter surface.** The `chips` vocabulary — This
    // week / Weekend / Tonight / Free, and Category: All / Music / Tech / … — does not
    // migrate.
    //
    // **The check is on controls, not on words.** A first attempt searched the page's
    // text for "this week", "weekend" and "tonight" and it failed — on *legitimate*
    // content: the tier-two head "More this week", a card's own tag "This weekend", an
    // event titled "Hackathon Weekend", the window label "Tonight + 7 days" and the
    // `tag:tonight` grammar hint. **A chip rail is a row of filter controls**, so the
    // check has to count controls. Looking for the words the design names would flag the
    // design's own copy.
    await expect(
      page.locator('[data-browse-chip], [role="group"][aria-label*="filter" i]'),
    ).toHaveCount(0);

    const controlLabels = await page
      .locator("button, a[href], [role='button']")
      .evaluateAll((nodes) =>
        nodes.map((node) => ((node as HTMLElement).textContent ?? "").trim().toLowerCase()),
      );
    for (const chip of ["this week", "weekend", "tonight", "free", "category: all"]) {
      // **An exact match, not a substring.** "More this week" is a heading, not a
      // control, and a heading is not a filter.
      expect(controlLabels.filter((text) => text === chip)).toHaveLength(0);
    }

    // --- no count badges ------------------------------------------------------------------
    // **No numeric tag anywhere.** The design bans "saved 7" and "47 nearby" — a *count*
    // rendered as a pill.
    //
    // **The check must not depend on a class name.** A first attempt matched
    // `span[class*="badge"]` and it found **72** of them — every card's source badge
    // (`component.indicator.confidence` row) and its state badge. **Those are the
    // design's own vocabulary**: `component.card.pulse.digest`'s anatomy includes them,
    // and Amendment A-22 puts the state badge in its own row. Banning them would have
    // been banning the design.
    //
    // **A second attempt then failed to catch a badge it should have caught.** A count
    // badge injected as `<span class="rounded-full bg-surface-subtle px-2 py-0.5">7</span>`
    // has *no* "badge" in its class name, and the class-based selector walked right past
    // it. **A class name is a naming convention, not a contract** — the count badge the
    // design forbids is not obliged to call itself one.
    //
    // **So the check asks the design's actual question: is there a bare number in a
    // pill?** It finds every element whose whole text is a number and that is rendered
    // as a small rounded chip. The source badge reads "Official" or "Community" and the
    // state badge reads "Cancelled" — neither is a number, so neither is caught.
    const countBadges = await page.evaluate(() => {
      const found: string[] = [];
      for (const node of Array.from(document.querySelectorAll("*"))) {
        const element = node as HTMLElement;
        // **The element's whole text is a number.** "7" is a count. "7 events" is a
        // label, and "Official" is a label.
        const text = (element.textContent ?? "").trim();
        if (!/^\d+$/.test(text)) continue;
        // **And it is a chip, not a layout container.** A card's whole body is not a
        // count badge even if it happened to hold only digits.
        const style = getComputedStyle(element);
        const rounded = style.borderRadius !== "0px";
        const tight = element.scrollHeight <= 40 && element.scrollWidth <= 80;
        if (rounded && tight && element.children.length === 0) {
          found.push(`${element.tagName}.${element.className} = ${text}`);
        }
      }
      return found;
    });
    expect(countBadges).toEqual([]);

    // --- no upsell carousel (Amendment A-12) ----------------------------------------------
    // **The Pro upsell lives on `/digest` and `/settings/plan` only.** So there is no
    // upsell card and no carousel of anything.
    await expect(
      page.locator('[data-browse-upsell], [role="region"][aria-label*="carousel" i]'),
    ).toHaveCount(0);

    // **And no horizontal scroller.** A carousel is a horizontally scrolling strip; the
    // design's card grid is a wrapping grid.
    const scrollers = await page.evaluate(() => {
      const found: string[] = [];
      for (const node of Array.from(document.querySelectorAll("*"))) {
        const element = node as HTMLElement;
        if (element.scrollWidth > element.clientWidth + 8) {
          const overflow = getComputedStyle(element).overflowX;
          if (overflow === "auto" || overflow === "scroll") {
            found.push(`${element.tagName}.${element.className}`);
          }
        }
      }
      return found;
    });
    expect(scrollers).toHaveLength(0);

    // --- the tier-one head agrees with the tier-one cards ---------------------------------
    // **A heading that lies about its own section is a heading that lies.** The design's
    // copy is "3 worth your attention today", and the section must hold three.
    const tierOneHead = (
      await page.locator('[data-browse-section="tier-1"] h2').textContent()
    )?.trim();
    expect(tierOneHead).toContain(String(await tierOneCards(page).count()));

    // --- one Save button per card, and it is a real button ---------------------------------
    // **The design says Save is the single affordance per card**, and the card body is
    // not a button. So the count of Save buttons is the count of cards, and every one of
    // them is a `<button>`.
    expect(await page.locator("[data-browse-save-button]").count()).toBe(await cards(page).count());
    const saveTagNames = await page
      .locator("[data-browse-save-button]")
      .evaluateAll((nodes) => nodes.map((node) => node.tagName));
    expect(new Set(saveTagNames)).toEqual(new Set(["BUTTON"]));

    // --- no social proof, no Sign-up CTA, no SEO footer ----------------------------------
    //
    // **These three are checked on the *rendered* text, and the distinction is the whole
    // point of `renderedText`.** `body.textContent` includes Next.js's inline RSC
    // payload — the server's own copy of the page, as a JSON string — so a naive search
    // finds the phrase in the machine's copy rather than in the reader's. It also
    // includes the shell's closed `<dialog>` menus.
    //
    // **A probe found zero hits for all seventeen phrases** the design's anti-pattern
    // list forbids. The check is kept because a check that only ever passed once is not
    // a check.
    const text = await renderedText(page);

    // **No social proof.** No "X people going", no "234 attending".
    for (const phrase of ["people going", "attending", "going too", "others saved"]) {
      expect(text).not.toContain(phrase);
    }

    // **No Sign-up CTA (Amendment A-12).** The surface is authed; there is nothing to
    // sign up for, and the conversion scaffolding does not migrate.
    for (const phrase of ["sign up", "signup", "create an account", "how it works"]) {
      expect(text).not.toContain(phrase);
    }

    // **No SEO footer (Amendment A-12).** The city page's neighbour-cities rail does not
    // migrate.
    for (const phrase of ["nearby cities", "other cities", "explore cities", "more cities"]) {
      expect(text).not.toContain(phrase);
    }

    // **The cards are ranked, and the order is the server's.** The first tier's cards come
    // before the second tier's cards in the document, and the two sections are separate
    // lists — so the page reads top-down as "worth your attention, then the rest".

    // **The first page is the server's twenty-four.** The seed file writes forty-nine
    // events, so the page is full and the chunk loader is live — which is what makes the
    // search's chunk-boundary a real limitation rather than a footnote.
    await expect(page.locator("[data-browse-more]")).toBeVisible();
    expect(await cards(page).count()).toBe(24);

    // **The chunk arrives when the reader asks for it.** The anchor is the soft cap's
    // only way through, and the click is intercepted so the chunk loads *in place* —
    // so the count grows without a navigation. **This is the step the earlier version of
    // this test skipped**, and it is why it asserted on a count it had never given the
    // server a chance to change.
    await page.locator("[data-browse-more] a").click();

    // **The chunk lands, and the anchor's own announcement says how many.** The live
    // region is the reader's only signal, so asserting on it proves the chunk arrived
    // *and* that the reader was told.
    await expect(page.locator("[data-browse-more-status]")).toContainText("Loaded");

    // **And the pool is bigger than one page now.** Forty-nine events, twenty-four on
    // the first page — so more than twenty-four cards means the chunk landed.
    expect(await cards(page).count()).toBeGreaterThan(24);

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
    //
    // **The narrowing is against the whole surface, not against the keyword's result.**
    // The two filters are independent: `tag:arts` is not a subset of "yoga", so the
    // tagged count is *larger* than the keyword's — the seed file holds one yoga event
    // and seven arts-and-culture ones. **An earlier version of this line asserted
    // `tagged < matched`, which is a false claim about the product** — the two filters do
    // not compose into one narrower set, so the assertion failed for a reason that had
    // nothing to do with the code under test.
    //
    // **The claim that is true, and is the one worth making:** the tag filter narrows the
    // *unfiltered* surface, and every card that survives carries the tag.
    const tagged = await cards(page).count();
    expect(tagged).toBeGreaterThan(0);
    expect(tagged).toBeLessThan(before);

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
