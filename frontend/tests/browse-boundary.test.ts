// @vitest-environment node
/**
 * Browse's structural rules, asserted against the source rather than the DOM.
 *
 * **Amendment A-12 is a set of absences, and a rendering test cannot fully see them.**
 * `tests/browse-rendering.test.tsx` can see that the rendered page has no Sign-up link;
 * it cannot see that a discovery stripe was written into a *second* file and never
 * reached this branch, or that the persona copy is sitting in a comment, or that a third
 * stripe colour exists in a helper that has not been wired up yet. Those are properties
 * of the source, so they are asserted on the source — the same house pattern as
 * `tests/digest-home-boundary.test.ts` and `tests/pulse-card-boundary.test.ts`.
 *
 * The rules come from `DESIGN.md` §"Browse surface (Amendment A-10 + A-12 merge)" and
 * Amendment A-12's own lock:
 *
 * - **no pre-auth conversion scaffolding** — no Sign-up row, no How-it-works CTA, no
 *   SEO neighbour-cities footer;
 * - **no filter chip rail** (A-11's lock, reinforced by A-12);
 * - **no discovery stripe** — the stripe cap is two colours, and A-12 drops the third;
 * - **no persona-prefixed copy** — "Maya-fit" is the pre-auth surface's voice.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

/**
 * The files the Browse surface is made of.
 *
 * **The surface's own markup, and the libraries it reads.** The two groups are kept
 * apart because they answer to different rules: the markup is what the reader sees and
 * what Amendment A-11 and A-12 forbid *there*, while the libraries are vocabularies
 * and grammars that legitimately talk about things the surface must not render — the
 * tag vocabulary names `discovery` because the server sends it, and the label table
 * names chips because the server sends chip tags.
 */
const SURFACE_FILES = [
  "app/browse/page.tsx",
  "app/browse/loading.tsx",
  "components/browse/browse-hero.tsx",
  "components/browse/browse-card.tsx",
  "components/browse/browse-grid.tsx",
  "components/browse/browse-more.tsx",
  "components/browse/browse-quota-note.tsx",
  "components/browse/browse-quota-provider.tsx",
  "components/browse/browse-save.tsx",
  "components/browse/browse-search.tsx",
  "components/browse/browse-states.tsx",
];

/** The libraries the surface reads. */
const LIBRARY_FILES = [
  "lib/browse-read.ts",
  "lib/browse-labels.ts",
  "lib/browse-search.ts",
  "lib/digest-labels.ts",
];

const FILES = [...SURFACE_FILES, ...LIBRARY_FILES];

const sources = new Map(FILES.map((file) => [file, readFileSync(path.join(ROOT, file), "utf8")]));

/**
 * The source with its comments removed.
 *
 * **A comment is not code.** These files' docstrings quote the spec — they name the
 * Sign-up row, the SEO footer, the discovery stripe and the "Maya-fit" copy, because
 * explaining *why* each is forbidden is the point of the comments. A source-text
 * assertion that read them would be asserting on prose, and would fail on a file that
 * only mentions the thing in order to forbid it.
 */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

const code = new Map([...sources].map(([file, source]) => [file, withoutComments(source)]));

/** Every file's comment-stripped source, joined. */
function allCode(): string {
  return [...code.values()].join("\n");
}

/**
 * The surface's **own markup**, comment-stripped and joined.
 *
 * **Some rules are about what the reader sees, and only the markup can answer them.**
 * The tag vocabulary in `lib/digest-labels.ts` names `discovery` and the chip slugs
 * because the server sends them — that is the vocabulary working, not a stripe on the
 * page. A rule that read the libraries would cry wolf, and a rule that cries wolf is a
 * rule that gets disabled.
 */
function surfaceCode(): string {
  return SURFACE_FILES.map((file) => code.get(file) ?? "").join("\n");
}

/**
 * Every Tailwind colour utility the surface names, wherever it names it.
 *
 * **Not just the ones in a `className` attribute.** A stripe's colour is chosen by a
 * *helper* — `stripeColour()` returns `"bg-accent-slate"` as a plain string — and a
 * scan that only read `className="…"` would miss it entirely. A rule that cannot see
 * the thing it forbids is a rule that proves nothing, so the scan reads every quoted
 * string in the file and looks for the utility names there.
 */
function allTokens(): string[] {
  const utilities = [...code.values()].flatMap((source) =>
    [...source.matchAll(/"([^"]*)"/g)].map((match) => match[1]),
  );
  return utilities.flatMap((value) => value.split(/\s+/)).filter(Boolean);
}

describe("Amendment A-12 — the conversion scaffolding is absent", () => {
  it.each([
    ["a Sign-up call to action", /sign[\s-]?up/i],
    ["a How-it-works call to action", /how[\s-]?it[\s-]?works/i],
    ["a sign-in call to action", /sign[\s-]?in/i],
    ["a conversion CTA row", /hero[\s-_-]?ctas?/i],
  ])("has no %s", (_name, pattern) => {
    expect(allCode()).not.toMatch(pattern);
  });

  it("has no SEO neighbour-cities footer", () => {
    const source = allCode();
    // The rail's own vocabulary: the footer element, and the links it carries.
    expect(source).not.toMatch(/seo[\s-]?foot/i);
    expect(source).not.toMatch(/neighbou?r[\s-]?cit/i);
    expect(source).not.toMatch(/nearby[\s-]?cit/i);
    // A `<footer>` inside the Browse surface would be the SEO footer's element.
    expect(source).not.toMatch(/<footer/);
  });

  it("has no filter chip rail", () => {
    // **The surface's markup, not the vocabularies.** The server's why-tag vocabulary
    // names chips — that is the server's vocabulary, and the card translating a chip
    // tag into words is the card doing its job. What A-11 forbids is a chip rail
    // *rendered on this page*.
    const source = surfaceCode();
    // A-11's lock: the city page's `When:`/`Category:` chips do not migrate.
    expect(source).not.toMatch(/\bchips?\b/i);
    // The mockup's own chip labels.
    expect(source).not.toMatch(/this weekend/i);
    expect(source).not.toMatch(/by category/i);
  });

  it("has no persona-prefixed copy", () => {
    // The city page's "Maya-fit" section head is the pre-auth surface's voice: a
    // stranger does not know who Maya is. The Browse surface's head is "3 worth your
    // attention today".
    expect(allCode()).not.toMatch(/maya/i);
  });
});

/**
 * Amendment A-11's lock: the inline keyword search is the **only** filter surface.
 *
 * **The city page's filter vocabulary does not migrate.** Its chip rail — `When: This
 * week / Weekend / Tonight / Free` and `Category: All / Music / Tech / Community /
 * Arts / Family / Food & drink / Sports` — is forbidden, along with date pickers and
 * preset toggles. The design's own words: *"the calm contract requires self-contained,
 * learnable-in-5-seconds grammar taught by placeholder + the microcopy line below the
 * input."*
 *
 * **A lock needs enforcement.** The rule is asserted here on the source and, in
 * `tests/browse-rendering.test.tsx`, on the rendered DOM — because a source scan cannot
 * see a chip rail written into a component this branch never renders, and a rendering
 * test cannot see a category button that is present but hidden.
 */
describe("Amendment A-11 — the search is the only filter surface", () => {
  it("has no category buttons", () => {
    const source = allCode();
    // A category button is a control that toggles a category. The city page's own
    // category vocabulary is the clearest signal.
    expect(source).not.toMatch(/food\s*&?\s*drink/i);
    expect(source).not.toMatch(/all[\s_-]?categories?/i);
  });

  it("has no date pickers or preset toggles", () => {
    const source = allCode();
    // A date picker is a `type="date"` input; a preset is a toggle that narrows the
    // window.
    expect(source).not.toMatch(/type\s*=\s*["']date["']/);
    expect(source).not.toMatch(/date[\s_-]?picker/i);
    expect(source).not.toMatch(/preset/i);
  });

  it("has exactly one search input", () => {
    // One input, and it is a search input. A second one would be a second grammar.
    const source = allCode();
    const searchInputs = source.match(/type\s*=\s*["']search["']/g) ?? [];
    expect(searchInputs.length).toBe(1);
  });

  it("keeps the placeholder verbatim", () => {
    // The placeholder teaches the grammar in place, and the AC fixes it word for word.
    const source = code.get("components/browse/browse-search.tsx") ?? "";
    expect(source).toMatch(/Search this week — jazz, free, outdoor, tag:music/);
  });

  it("does not widen an unknown tag into a plain-word match", () => {
    // The grammar's trustworthiness rests on this: `tag:music` — a name the server
    // has no fact for — must not become a search for "music" anywhere on the card.
    const source = code.get("lib/browse-search.ts") ?? "";
    expect(source).toMatch(/resolvedTags/);
    expect(source).not.toMatch(/resolvedTags\s*\.\s*filter\s*\(/);
  });
});

describe("Amendment A-12 — the stripe cap is two colours", () => {
  it("uses only the slate and amber stripes", () => {
    const stripes = allTokens().filter((token) => token.startsWith("bg-accent-"));
    // `bg-accent-terracotta` is the brand accent, not a stripe; the stripes are the
    // category colours.
    const categoryStripes = stripes.filter(
      (token) => token !== "bg-accent-terracotta" && token !== "bg-accent-amber-settled",
    );
    for (const stripe of categoryStripes) {
      expect(["bg-accent-slate", "bg-accent-amber"]).toContain(stripe);
    }
  });

  it("has no discovery stripe", () => {
    // **The surface's markup, not the vocabularies.** `lib/digest-labels.ts` labels the
    // server's `discovery` tag, and it must — the server sends it. What A-12 forbids is
    // the discovery *stripe*: a third category colour on the card's edge.
    const source = surfaceCode();
    expect(source).not.toMatch(/discovery/i);
    // The digest's discovery treatment is the 0.85-opacity variant. If that opacity
    // class ever appears on a Browse card, the third stripe is back.
    expect(allTokens()).not.toContain("opacity-85");
  });

  it("names the stripe in words as well as in colour", () => {
    // WCAG 1.4.1: colour is never the only carrier. The kicker says which stripe it is.
    const source = code.get("lib/browse-labels.ts") ?? "";
    expect(source).toMatch(/must[\s_-]?know/i);
    expect(source).toMatch(/public/i);
  });
});

describe("the surface adds no tokens", () => {
  it("declares no new colour, spacing or CSS variable", () => {
    // `styles/tokens.css` is the only place a token may be **declared**. Browse must not
    // touch it, and must not declare one of its own.
    //
    // **A declaration, not a reference.** The markup *uses* the existing tokens —
    // `var(--type-scale-headline-sm)` is how a class names one — and that is the whole
    // point of the token system. What must not appear is a *new* token being
    // introduced, so the check is for a declaration: a `--name:` at the start of a
    // declaration.
    const source = allCode();
    expect(source).not.toMatch(/--color-[\w-]+\s*:/);
    expect(source).not.toMatch(/--spacing-[\w-]+\s*:/);
    expect(source).not.toMatch(/--breakpoint-[\w-]+\s*:/);
    expect(source).not.toMatch(/--type-scale-[\w-]+\s*:/);
    expect(source).not.toMatch(/@theme/);
  });

  it("uses no literal hex colour", () => {
    // A literal hex would look right in one theme and wrong in the other. The digest's
    // boundary test holds the same line.
    expect(allCode()).not.toMatch(/#[0-9a-f]{3,8}\b/i);
  });
});

describe("the surface reaches the backend only through the generated client", () => {
  it("does not call fetch", () => {
    // AD-19. The lint rule forbids it in `components/` and `app/`, and this test says
    // the same thing in a place that reports *why*.
    expect(allCode()).not.toMatch(/\bfetch\s*\(/);
  });

  it("does not import openapi-fetch directly", () => {
    expect(allCode()).not.toMatch(/from\s+["']openapi-fetch["']/);
  });
});

describe("the surface is a server component except for the four islands", () => {
  it("marks only the four islands as client modules", () => {
    // The route, the hero, the grid, the card and the states all render on the server.
    // Only the search island needs the browser, because Amendment A-11's filter runs
    // client-side over the loaded set — and a filter that reached only part of the
    // surface would be a filter that lied about how much it had narrowed.
    //
    // **The chunk loader is not a client module any more.** It was one when it owned the
    // fetch; now the island owns the chunk's state, because a chunk becomes part of the
    // loaded set the moment it lands and the query has to reach it. The loader is the
    // island's presentational half.
    //
    // **The Save button is the second island.** It holds a state machine and talks to
    // the API, so it cannot be a server component — but the **card** stays one, and an
    // island can be mounted inside a server component's markup.
    //
    // **The allowance is the third and fourth, and they are one thing in two files.**
    // The hero's quota note and the cards' Save buttons read the *same* number, and
    // that number moves: one save spends the Free allowance, so the note in the hero
    // and the wall on every other card have to move with it. **The hero is a server
    // component and the cards are a client island, so a prop cannot carry it** — a
    // shared number needs a shared owner, and the owner is a client context. So the
    // provider is a client module (it holds the number and asks the server again), and
    // the note that reads it is one too (it has to re-render when the number moves).
    //
    // **The count is not the point; the list is.** The rule says *which* modules reach
    // across the client/server boundary, so a new client module cannot be added
    // without this assertion being updated — which is the point: a surface that grows
    // an island should say so, in the place that says what the surface is.
    const clients = [...code.entries()]
      .filter(([, source]) => source.trimStart().startsWith('"use client"'))
      .map(([file]) => file);
    expect(clients).toEqual([
      "components/browse/browse-quota-note.tsx",
      "components/browse/browse-quota-provider.tsx",
      "components/browse/browse-save.tsx",
      "components/browse/browse-search.tsx",
    ]);
  });

  it("keeps the card a server component", () => {
    // **The Save button is an island; the card is not.** The card hands the island the
    // payload's facts — the catalog id, the title, `is_saved` and the quota — and
    // renders it in the slot the grid work item reserved. A card that became a client
    // component would put the whole grid's markup across the client/server boundary for
    // the sake of one button.
    const card = code.get("components/browse/browse-card.tsx") ?? "";
    expect(card.trimStart()).not.toMatch(/^["']use client["']/);
    // And it mounts the island rather than re-implementing the button.
    expect(card).toMatch(/<BrowseSave/);
  });

  it("does not reach next/headers from either client island", () => {
    // The architecture test enforces this across the app; this is the same rule stated
    // for the two files that could break it. A server-only import in a client module
    // **passes the unit tests** and fails the build.
    expect(code.get("components/browse/browse-search.tsx")).not.toMatch(/next\/headers/);
    expect(code.get("components/browse/browse-save.tsx")).not.toMatch(/next\/headers/);
  });
});

describe("the surface is not a fork of the shell", () => {
  it("imports AppShell rather than re-implementing it", () => {
    const source = code.get("app/browse/page.tsx") ?? "";
    expect(source).toMatch(
      /import\s+\{\s*AppShell\s*\}\s+from\s+[""]@\/components\/shell\/app-shell[""]/,
    );
    expect(source).toMatch(/<AppShell/);
  });

  it("does not re-implement the sidenav or the topbar", () => {
    const source = allCode();
    // The shell's own landmarks. A forked shell would re-declare them.
    expect(source).not.toMatch(/aria-label=["']Primary["']/);
    expect(source).not.toMatch(/aria-label=["']Brand["']/);
    expect(source).not.toMatch(/<aside/);
    expect(source).not.toMatch(/<nav/);
  });
});

describe("the surface decides nothing the server decided", () => {
  it("renders the server's order and the server's tier split", () => {
    const page = code.get("app/browse/page.tsx") ?? "";
    const grid = code.get("components/browse/browse-grid.tsx") ?? "";
    const search = code.get("components/browse/browse-search.tsx") ?? "";
    // The split comes from the server's `tier_2_starts_at`, not from a client-side
    // count of "the top three". A `slice(0, 3)` anywhere would be the client deciding
    // a tier (AD-10).
    //
    // **The chain is now four links.** The route reads the server's field; the island
    // carries it down; the island counts the pool's tier-one *survivors*; the grid
    // slices at that count. Every link is named, so the whole chain from the payload to
    // the slice is visible in the source — which is what this rule is for.
    //
    // **The count is the point.** The grid must slice at a *count of the pool's
    // tier-one survivors*, not at the server's raw index — slicing the filtered list at
    // the index would promote a tier-two card into tier one.
    expect(page).toMatch(/tier_2_starts_at/);
    expect(search).toMatch(/tierTwoStartsAt/);
    expect(search).toMatch(/survivingTierOneCount/);
    expect(grid).toMatch(/tierOneCount/);
    expect(grid).not.toMatch(/slice\(\s*0\s*,\s*3\s*\)/);
    expect(search).not.toMatch(/slice\(\s*0\s*,\s*3\s*\)/);
    // The grid must not slice at the server's index itself — that is the re-tiering.
    expect(grid).not.toMatch(/tierTwoStartsAt/);
  });

  it("does not compute a score, a bucket or a recency band", () => {
    const source = allCode();
    // `confidence` is the server's bucket. A client-side re-bucketing would be AD-10's
    // exact failure.
    expect(source).not.toMatch(/relevance_score|score_bucket|recompute/i);
    // The confidence is read from the payload, never derived from a score.
    expect(source).toMatch(/card\.confidence/);
  });

  it("does not re-sort the cards the search filtered", () => {
    // **The search removes cards; it does not rearrange them.** A `.sort()` on the
    // filtered list would be the client re-ranking the server's pool, which is AD-10's
    // exact failure wearing a search's clothes.
    const source = code.get("lib/browse-search.ts") ?? "";
    expect(source).not.toMatch(/\.sort\s*\(/);
    expect(source).not.toMatch(/\.reverse\s*\(/);
  });

  it("draws the chunk's cards in one place only", () => {
    // **The chunk's cards used to be rendered twice.** The chunk loader had a list of
    // its own below the grid; when Amendment A-11's search moved the chunk's state
    // into the island, the grid began drawing the whole loaded set *and* the loader
    // kept drawing the chunk — so every chunked event appeared twice on the page.
    //
    // **One place draws the cards.** The grid is that place, because the chunk's
    // cards belong to the grid's second section: the server's tier formula puts every
    // card past the first section in tier two.
    const grid = code.get("components/browse/browse-grid.tsx") ?? "";
    const more = code.get("components/browse/browse-more.tsx") ?? "";

    // The grid draws the cards.
    expect(grid).toMatch(/<BrowseCard/);
    // The loader draws none.
    expect(more).not.toMatch(/<BrowseCard/);
    expect(more).not.toMatch(/data-browse-appended/);
  });
});

/**
 * `EXPERIENCE.md` §`Component.Surface.Browse`, "Anti-patterns (explicitly forbidden on
 * this surface)".
 *
 * **Five of those locks had no enforcement anywhere.** The stripe cap, the chip rail,
 * the discovery stripe and the pre-auth CTA leakage each had a rule in this file — and
 * these five had none. A lock with no enforcement is a sentence in a document, and the
 * document is not the product.
 *
 * **Each rule is asserted on the surface's own markup, not on the libraries.** The
 * libraries are vocabularies that legitimately name things the surface must not render,
 * and a scan that read them would cry wolf. A rule that cries wolf gets disabled, and a
 * disabled rule is worse than no rule because it looks like coverage.
 *
 * **And each rule names a phrase, not a word.** The anti-patterns are about *copy* and
 * about *specific components* — "X people going", "saved 7", a streak popup. The word
 * "badge" is **legitimate vocabulary on this surface**: `Badge.Source` is part of
 * `component.card.pulse.digest`'s anatomy and Browse borrows it, and so is the event
 * state badge. A rule that banned the word "badge" would fail on correct markup.
 */
describe("the anti-pattern list — the five locks with no enforcement", () => {
  it("has no social proof", () => {
    // **"No 'X people going' social proof. No '234 attending' counters."**
    //
    // The phrases are what the lock names, so the phrases are what the rule matches.
    // The surface's *own* counts — "147 events this week" in the city-meta pill, "144
    // events" in the section head's meta — are the pool's own size, which the reader can
    // page to, and they are not social proof. The lock is about **other people**.
    const source = surfaceCode();
    expect(source).not.toMatch(/people\s+(going|interested|attending|joining)/i);
    expect(source).not.toMatch(/\bgoing\b/i);
    expect(source).not.toMatch(/\battending\b/i);
    expect(source).not.toMatch(/others?\s+(are\s+)?(going|interested|saved)/i);
  });

  it("has no count badges on a card", () => {
    // **"No count badges anywhere. No 'saved 7' or '47 nearby' or any numeric tag."**
    //
    // **The word "badge" is not the subject — the numeric counter is.** `Badge.Source`
    // and the event state badge are `component.card.pulse.digest`'s anatomy and Browse
    // borrows them; what the lock forbids is a *number* worn as a badge.
    //
    // **The surface's own counts are not count badges.** "147 events this week" is the
    // pool's size, and the section head's "144 events · scroll for more" is the tier's
    // size — both are the same fact the design puts there, and neither is a badge.
    const source = surfaceCode();
    expect(source).not.toMatch(/saved\s+\d+/i);
    expect(source).not.toMatch(/\d+\s+nearby/i);
    expect(source).not.toMatch(/\d+\s+(going|attending|interested|booked)/i);
    expect(source).not.toMatch(/\b\d+\s+saved\b/i);
  });

  it("has no gamification chrome", () => {
    // **"No gamification chrome. No streaks, no 'you saved 5 days in a row!', no
    // badges."**
    //
    // The Surface's own vocabulary is checked too: a component named after a streak
    // would be the chrome, whatever copy it carried.
    const source = allCode();
    expect(source).not.toMatch(/\bstreak/i);
    expect(source).not.toMatch(/days?\s+in\s+a\s+row/i);
    expect(source).not.toMatch(/you\s+saved\s+\d+/i);
    expect(source).not.toMatch(/\blevel\s*\d/i);
    expect(source).not.toMatch(/\bpoints?\s+(earned|balance)/i);
  });

  it("has no upsell carousel", () => {
    // **"No upsell carousels. The single Pro upsell (`component.card.pro.upsell`)
    // lives only on `/digest` and `/settings/plan`; it does not migrate to Browse."**
    //
    // The carousel is a component, so the rule is on the component's name — and on the
    // routes it is allowed to live on, so the rule cannot be satisfied by renaming.
    const source = allCode();
    expect(source).not.toMatch(/carousel/i);
    expect(source).not.toMatch(/pro[\s_-]?upsell/i);
    expect(source).not.toMatch(/upsell[\s_-]?card/i);
  });

  it("has no 'you might also like' rail", () => {
    // **"No 'you might also like' rails beyond the section-head grouping."**
    //
    // The surface has exactly two sections, and both are section heads — the tier
    // split, which the server decides. A third grouping would be the rail.
    const source = surfaceCode();
    expect(source).not.toMatch(/might\s+also\s+like/i);
    expect(source).not.toMatch(/you\s+might\s+like/i);
    expect(source).not.toMatch(/related\s+events/i);
    expect(source).not.toMatch(/recommended\s+for\s+you/i);

    // **And there are exactly two sections.** The grid's sections are the server's tier
    // split, and the split is two — a third section would be a rail wearing a
    // different name.
    const grid = code.get("components/browse/browse-grid.tsx") ?? "";
    const sections = grid.match(/data-browse-section/g) ?? [];
    expect(new Set(sections).size).toBeLessThanOrEqual(2);
  });
});
