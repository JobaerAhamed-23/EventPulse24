// @vitest-environment node
/**
 * The Pulse Digest home's structural rules, asserted against the source rather than the
 * DOM.
 *
 * **These are the rules a rendering test cannot catch.** `app/page.test.tsx` can see
 * that the empty state carries one link; it cannot see that a literal hex has crept
 * into a *second* file, or that a motion class has been added to the markup, or that a
 * terracotta fill has been introduced on a nav row. Those are properties of the source,
 * so they are asserted on the source — the same house pattern as
 * `tests/pulse-card-boundary.test.ts`.
 *
 * The rules come from `DESIGN.md` and `EXPERIENCE.md`, and they are the ones whose
 * violation would be silent: a literal hex would look right in one theme and wrong in
 * the other; a second animation would be a second motion in a product that has one; a
 * terracotta fill on a nav row would spend an accent that is rationed to four uses.
 */
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

/** The files the home surface is made of. */
const FILES = [
  "app/page.tsx",
  "components/add-event-button.tsx",
  "components/digest/digest-header.tsx",
  "components/digest/digest-empty.tsx",
  "components/digest/digest-preparing.tsx",
  "components/digest/digest-error.tsx",
  "components/digest/digest-skeleton.tsx",
  "components/shell/app-shell.tsx",
  "components/shell/sidenav.tsx",
  "components/shell/bottom-tab-nav.tsx",
  "components/shell/more-menu.tsx",
  "components/shell/account-menu.tsx",
  "components/shell/nav-glyphs.tsx",
  "lib/digest-attempt.ts",
  "lib/digest-read.ts",
];

const sources = new Map(FILES.map((file) => [file, readFileSync(path.join(ROOT, file), "utf8")]));

/**
 * The source with its comments removed.
 *
 * **A comment is not code.** These files' docstrings quote the spec — they mention the
 * middle dot, the terracotta ration and the 1800ms pulse — and a source-text assertion
 * that read them would be asserting on prose. So the comments come out first.
 */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

const code = new Map([...sources].map(([file, source]) => [file, withoutComments(source)]));

/** The class-name strings in a .tsx file. */
function classStrings(source: string): string[] {
  return [...source.matchAll(/className=(?:"([^"]*)"|\{`([^`]*)`\}|\{"([^"]*)"\})/g)].map(
    (match) => match[1] ?? match[2] ?? match[3] ?? "",
  );
}

/** Every class-name token across the surface. */
function allTokens(): string[] {
  return [...code.values()].flatMap((source) =>
    classStrings(source).flatMap((value) => value.split(/\s+/)),
  );
}

describe("the home's tokens", () => {
  it("uses no literal hex colour", () => {
    for (const [file, source] of code) {
      expect(source.match(/#[0-9a-fA-F]{3,8}\b/g) ?? [], file).toEqual([]);
    }
  });

  it("uses no raw rgb() or hsl() colour", () => {
    for (const [file, source] of code) {
      expect(source.match(/\b(?:rgb|rgba|hsl|hsla)\(/g) ?? [], file).toEqual([]);
    }
  });

  it("takes every colour from a token utility", () => {
    // `text-` is ambiguous in Tailwind: `text-left` is an alignment, `text-ink-primary`
    // is a colour. So the alignment utilities are excluded before the colour check.
    const alignments = new Set([
      "text-left",
      "text-center",
      "text-right",
      "text-justify",
      "text-start",
      "text-end",
    ]);

    const colours = allTokens().filter(
      (token) =>
        /^(?:bg|text|border|ring|outline|fill|stroke)-/.test(token) && !alignments.has(token),
    );

    expect(colours.length).toBeGreaterThan(0);
    for (const token of colours) {
      // `ring-1` is a *width*, not a colour. `border-t-2` and `border-b` are widths
      // too — the *colour* is the separate `border-accent-terracotta` utility.
      if (/^(?:ring|border)-?\d/.test(token)) continue;
      if (/^border-[trblxy]?$/.test(token)) continue;
      expect(
        /^(?:bg|text|border|ring|outline|fill|stroke)-(?:surface|ink|accent|warm|warn|signal|border)/.test(
          token,
        ),
        token,
      ).toBe(true);
    }
  });

  it("names no font family outside the type scale", () => {
    const families = allTokens().filter((token) => token.includes("[font:"));

    expect(families.length).toBeGreaterThan(0);
    for (const token of families) {
      expect(token, token).toMatch(/\[font:var\(--type-scale-/);
    }
  });
});

describe("the home's motion", () => {
  it("adds no transition, duration, delay or animation class to the markup", () => {
    // `styles/motion.test.ts` proves the *stylesheets* carry one animation and one
    // transition. This proves the *markup* adds none — a Tailwind `transition-opacity`
    // would pass that test and would be a second motion in the product.
    const motion = allTokens().filter((token) =>
      /^(?:[\w-]+:)*(?:animate-[\w-]+|transition(?:-[\w-]+)?|duration-[\w-]+|delay-[\w-]+|ease-[\w-]+)$/.test(
        token,
      ),
    );

    expect(motion).toEqual([]);
  });

  it("uses the one skeleton pulse, and only on the skeleton", () => {
    // §5 requires the 1800ms pulse. `styles/motion.test.ts` allows exactly that one
    // animation. Here the assertion is about *where* it lands: only the loading
    // skeleton may pulse, because a pulsing digest would be a motion on content.
    const pulsing = [...code].filter(([, source]) => source.includes("skeleton-pulse"));

    expect(pulsing.map(([file]) => file)).toEqual(["components/digest/digest-skeleton.tsx"]);
  });
});

describe("the home's terracotta ration", () => {
  it("spends terracotta only on the sanctioned uses", () => {
    // The five sanctioned uses are the today dot, the primary CTA, the verified
    // source badge, the focus ring and the header's quick-add outline (DESIGN.md
    // §Color usage rules). On this surface four are reachable: the `Indicator.Today`
    // dot, the error state's primary retry, the brand mark's glyph and the quick-add —
    // whose outline, label and hover tint are the only tinted terracotta tokens allowed.
    // Nothing else may carry it.
    const terracotta = allTokens().filter((token) => token.includes("terracotta"));

    expect(terracotta.length).toBeGreaterThan(0);
    for (const token of terracotta) {
      expect(token, token).toMatch(
        /^(?:bg-accent-terracotta|text-accent-terracotta|border-accent-terracotta|border-t-accent-terracotta|focus-visible:outline-accent-terracotta|border-accent-terracotta\/45|hover:border-accent-terracotta|hover:bg-accent-terracotta\/10)$/,
      );
    }
  });

  it("gives the active sidenav route an ink pill, never a terracotta fill", () => {
    const sidenav = code.get("components/shell/sidenav.tsx") ?? "";

    // The active route's class string carries `bg-surface-subtle` and must not carry
    // any terracotta utility.
    const activeBranch = /active\s*\?\s*"([^"]+)"/.exec(sidenav)?.[1] ?? "";
    expect(activeBranch).toContain("bg-surface-subtle");
    expect(activeBranch).not.toContain("terracotta");
  });

  it("gives the active bottom-tab slot an ink inversion, not a terracotta fill", () => {
    const bottom = code.get("components/shell/bottom-tab-nav.tsx") ?? "";

    const activeBranch = /active \? "([^"]+)"/.exec(bottom)?.[1] ?? "";
    expect(activeBranch).toContain("bg-ink-primary");
    expect(activeBranch).not.toContain("terracotta");
  });

  it("marks no nav row's fill with terracotta", () => {
    // A terracotta fill on a control used many times per day burns the accent.
    const navFiles = ["components/shell/sidenav.tsx", "components/shell/bottom-tab-nav.tsx"];
    for (const file of navFiles) {
      const fills = classStrings(code.get(file) ?? "")
        .flatMap((value) => value.split(/\s+/))
        .filter((token) => token.startsWith("bg-") && token.includes("terracotta"));

      expect(fills, file).toEqual([]);
    }
  });
});

describe("the home's separators", () => {
  it("uses no CSS pseudo-element for visible helper text", () => {
    // `EXPERIENCE.md` §8: visible helper text must be in the DOM. A `::after` would be
    // visible to a sighted user and silent to a screen reader.
    for (const [file, source] of code) {
      expect(source.includes("::after"), file).toBe(false);
      expect(source.includes("::before"), file).toBe(false);
      expect(source.includes("content-["), file).toBe(false);
    }
  });
});

describe("the home's shell", () => {
  it("carries the six routes in the locked order", () => {
    const sidenav = code.get("components/shell/sidenav.tsx") ?? "";

    const order = [...sidenav.matchAll(/<SidenavItem[\s\S]*?label="([^"]+)"/g)].map(
      (match) => match[1],
    );
    expect(order).toEqual(["Digest", "Timeline", "Add", "Browse", "Conflicts", "Settings"]);
  });

  it("does not render an inert route as an anchor", () => {
    // An `<a href>` to a route that does not exist is a lie, and `<a aria-disabled>`
    // still navigates — the attribute is a hint, not a mechanism.
    const sidenav = code.get("components/shell/sidenav.tsx") ?? "";

    // The inert branch returns a `<span>` carrying `aria-disabled`, and the `<Link>` is
    // rendered only in the branch that has an `href`. So the inert branch must contain
    // no anchor *after* the `aria-disabled` marker.
    const inertBranch = /if \(!href\) \{[\s\S]*?\n  \}/.exec(sidenav)?.[0] ?? "";
    expect(inertBranch).not.toBe("");
    expect(inertBranch).toContain('aria-disabled="true"');
    expect(inertBranch).not.toContain("<Link");
    expect(inertBranch).not.toContain("<a");
  });

  it("keeps the topbar brand-only", () => {
    const shell = code.get("components/shell/app-shell.tsx") ?? "";

    // The topbar-quiet rule: the topbar carries the wordmark and nothing else. No
    // link, no button, no nav.
    const header = /<header[\s\S]*?<\/header>/.exec(shell)?.[0] ?? "";
    expect(header).not.toContain("<Link");
    expect(header).not.toContain("<button");
    expect(header).not.toContain("<nav");
  });

  it("mounts the create sheet outside the route list", () => {
    // The create sheet is a whole panel of markup. Inside the `<li>` it would be a form
    // nested in a navigation list — and its "Name" field would be a descendant of the
    // route list, which is structurally nonsense.
    const sidenav = code.get("components/shell/sidenav.tsx") ?? "";
    const bottom = code.get("components/shell/bottom-tab-nav.tsx") ?? "";

    for (const [file, source] of [
      ["sidenav", sidenav],
      ["bottom", bottom],
    ] as const) {
      const list = /<ul[\s\S]*?<\/ul>/.exec(source)?.[0] ?? "";
      expect(list.includes("PersonalEventsPanel"), file).toBe(false);
      expect(source.includes("PersonalEventsPanel"), file).toBe(true);
    }
  });

  it("draws the Add glyph once, with no duplicate plus mark", () => {
    // Each Add affordance draws the 16×16 stroke-only `+` glyph and nothing else: a
    // literal "+" beside it would put two plus signs on one control.
    const button = code.get("components/add-event-button.tsx") ?? "";
    expect([...button.matchAll(/<AddGlyph \/>/g)]).toHaveLength(1);
    expect(button).not.toMatch(/>\s*\+/);

    for (const file of ["components/shell/sidenav.tsx", "components/shell/bottom-tab-nav.tsx"]) {
      const source = code.get(file) ?? "";
      const glyphs = [...source.matchAll(/label="Add"[\s\S]*?glyph=\{<AddGlyph \/>\}/g)];
      expect(glyphs.length, file).toBe(1);
    }
  });

  it("gives the More slot a working sheet, not a dead control", () => {
    // The More slot is a control, not a route: it opens the overflow sheet. A slot
    // that renders a `<div>` and does nothing is a control that lies.
    const bottom = code.get("components/shell/bottom-tab-nav.tsx") ?? "";
    // Not the exact `<MoreMenu />`: the sheet now also carries the account panel, so it
    // takes props. What is pinned is that the slot mounts the component at all.
    expect(bottom).toContain("<MoreMenu ");

    const more = code.get("components/shell/more-menu.tsx") ?? "";
    expect(more).toContain("<Sheet");
    expect(more).toContain("onClick");
    // And the row it opens is a **link**, because the Browse surface shipped: a link
    // to a 404 would be a lie, and so would a "Coming soon" label next to a city full
    // of events.
    expect(more).toContain('href="/browse"');
    expect(more).not.toContain('aria-disabled="true"');
  });

  it("leaves no aria-disabled Browse row anywhere in the shell", () => {
    // **Browse was the last "Coming soon" the product said out loud.** It appeared in
    // three places — the sidenav's rail, the More sheet's row, and (as the bottom
    // tab's Digest slot, which had never been a link) the bar itself — and all three
    // are links now.
    //
    // **This is asserted on the source rather than the DOM**, because the three places
    // live in three different files and only one of them is reachable from any single
    // render. A source-level sweep of the shell's own files is the only assertion that
    // sees all three at once.
    const shellFiles = [
      "components/shell/sidenav.tsx",
      "components/shell/bottom-tab-nav.tsx",
      "components/shell/more-menu.tsx",
    ];

    for (const file of shellFiles) {
      const source = code.get(file) ?? "";

      // **The inert branch is kept** — it is the rule the next deferred route inherits
      // — so the sweep cannot be "this file contains no `aria-disabled`". It is
      // narrower and truer: *no inert branch mentions Browse*.
      //
      // The inert branch is the one that renders the disabled `<span>`, so the label
      // inside it is the label that is on the way but not here.
      const inertBranch = /if \(!href\) \{[\s\S]*?\n  \}/.exec(source)?.[0] ?? "";
      expect(inertBranch.includes('label="Browse"'), file).toBe(false);
    }

    // **The More sheet has no inert branch at all.** Its only row is Browse, and
    // Browse is a route — so there was never a reason for the sheet to carry a
    // disabled `<span>`, and the branch was removed rather than left behind empty.
    const more = code.get("components/shell/more-menu.tsx") ?? "";
    expect(more).not.toContain("aria-disabled");
    expect(more).not.toContain("Coming soon");

    // **And the Browse rows are links.** The sidenav's rail and the More sheet's row
    // both point at the same route, so a phone and a desktop land on the same place.
    const sidenav = code.get("components/shell/sidenav.tsx") ?? "";
    expect(sidenav).toContain('href="/browse"');
    expect(more).toContain('href="/browse"');

    // **And the bar's Digest slot is a link**, because the digest home shipped — it
    // had no `href` at all, so the bar's first tab rendered the inert branch while
    // also carrying `active={pathname === "/"}`.
    const bottom = code.get("components/shell/bottom-tab-nav.tsx") ?? "";
    const digestSlot = /<TabSlot[\s\S]*?label="Digest"[\s\S]*?\/>/.exec(bottom)?.[0] ?? "";
    expect(digestSlot).not.toBe("");
    expect(digestSlot).toContain('href="/"');
  });

  it("links nowhere that does not exist — resolved against the app directory", () => {
    // The sidenav's own rule: "a link to a 404 is a lie about where the label goes."
    //
    // **This used to be a deny-list of one string.** It asserted that no shell file
    // contained `href="/settings"`, because the account row had linked there and
    // `/settings` had no route. A deny-list only ever catches the 404 somebody already
    // found: `/settings/billing` sat in the dev billing panel and in three backend
    // config defaults for weeks, so every completed checkout returned the payer to a
    // 404, and this test was green throughout.
    //
    // So the rule is now resolved rather than listed — every literal internal `href` in
    // these files must have a `page.tsx` behind it. `/settings` passes today because
    // the settings index exists; delete that route and this fails.
    // **The exception is gone, and so is the link it fenced.** `/suggest` sat in an
    // `UNBUILT` set here, with a reverse assertion that would fail if the route were
    // ever built — an honest fence around a link `digest-empty.tsx` shipped knowingly
    // ahead of its route. Amendment A-26 (2026-11-20) withdrew the link instead of
    // building the route, after a user hit the 404. There is nothing left to allow.
    //
    // **The general rule now lives in `tests/internal-links.test.ts`**, which runs this
    // same resolution over `app/**` and `components/**` rather than the fifteen files
    // this suite names. That widening is why `/terms` and `/privacy` are no longer
    // invisible: both shipped in the auth surfaces, outside this file's reach, under a
    // sentence asking the user to agree to them. This assertion stays as the home
    // surface's own guard.

    const missing: string[] = [];

    for (const [file, source] of code) {
      for (const match of source.matchAll(/href="(\/[^"#?]*)/g)) {
        const route = match[1];
        // A dynamic segment is a template, not a destination: these files hold none,
        // and one would need the params to resolve.
        if (route.includes("[")) continue;

        const segments = route.split("/").filter(Boolean);
        const candidates = [
          path.join(ROOT, "app", ...segments, "page.tsx"),
          path.join(ROOT, "app", ...segments, "route.ts"),
        ];
        if (!candidates.some((candidate) => existsSync(candidate))) {
          missing.push(`${file} → ${route}`);
        }
      }
    }

    expect(missing).toEqual([]);
  });

  it("keeps sign out reachable at both breakpoints", () => {
    // The rail is `hidden md:flex`. Mounting the only sign-out in its footer is how the
    // control went missing once already — the Pulse Digest replaced the home page that
    // held it, the endpoint kept working, and nothing rendered the button. So both the
    // desktop surface and the mobile one must mount the account panel.
    const sidenav = code.get("components/shell/sidenav.tsx") ?? "";
    const more = code.get("components/shell/more-menu.tsx") ?? "";
    const account = code.get("components/shell/account-menu.tsx") ?? "";

    expect(sidenav).toContain("<AccountMenu ");
    expect(more).toContain("<AccountPanel ");
    expect(account).toContain("<SignOutButton />");
  });

  it("lets the content fill the window, with no container cap on <main>", () => {
    // §10 — "Desktop adds whitespace and hover affordances — never features, screens,
    // actions or copy" — used to be read here as a hard container: `<main>` capped at
    // `--layout-container-max` and centred. In the authed shell that cap could not
    // compose. The rail is a flex sibling, so `mx-auto` centred the content inside the
    // *leftover* column: half a rail right of the screen's centre, with the surplus
    // opening as a dead band between the rail and the content — 570px of it at 2560px.
    // Capping the shell instead made the gutters equal, and equal gutters are still
    // 570px of nothing at each edge.
    //
    // The rule itself is intact: a wider viewport still adds no features, screens,
    // actions or copy. It just no longer buys that with margins that read as emptiness.
    //
    // **The <main> tag is read, not the whole file**, because the file's comments name
    // the token to explain why it is gone — a whole-file `toContain` would pass on the
    // prose alone and assert nothing.
    const shell = code.get("components/shell/app-shell.tsx") ?? "";
    const main = /<main className="([^"]*)"/.exec(shell)?.[1];

    expect(main, "app-shell.tsx has no <main className=...>").toBeDefined();
    expect(main).not.toContain("max-w-(--layout-container-max)");
    expect(main).toContain("w-full");
  });
});

describe("the home's digest states", () => {
  it("keeps the not-composed state distinct from the empty state", () => {
    const empty = code.get("components/digest/digest-empty.tsx") ?? "";
    const preparing = code.get("components/digest/digest-preparing.tsx") ?? "";

    // "No qualifying events in {city}." is a claim about the world. The not-composed
    // state must not say it.
    expect(empty).toContain("No qualifying events in");
    expect(preparing).not.toContain("No qualifying events");
    expect(preparing).not.toContain("Nothing on the pulse");
  });

  it("gives the empty state nothing to click (Amendment A-26)", () => {
    const empty = code.get("components/digest/digest-empty.tsx") ?? "";

    // **This asserted one link until 2026-11-20.** The link was "Suggest an event",
    // pointing at `/suggest` — a route that existed in no layer of the product — so
    // this assertion was holding a 404 in place. A-26 withdrew the link rather than
    // building the route. Zero is now the rule, and it is the stronger one: the
    // surface whose whole argument is that it offers nothing offers nothing.
    expect([...empty.matchAll(/<Link/g)]).toHaveLength(0);
    expect(empty).not.toContain("<button");
    expect(empty).not.toContain("href");
  });

  it("names both error labels", () => {
    const error = code.get("components/digest/digest-error.tsx") ?? "";

    // The apostrophe is HTML-escaped in the source (`Couldn&apos;t`), because a
    // literal `'` inside JSX text is what React escapes anyway.
    expect(error).toContain("Couldn&apos;t reach Pulse");
    expect(error).toContain("Try again");
    expect(error).toContain("Refresh page.");
  });
});

describe("the home's personal events", () => {
  it("renders no personal-events list, because the Timeline is where they live", () => {
    const page = code.get("app/page.tsx") ?? "";

    // The stopgap list is gone, and with it the page's second read. A personal-events
    // read on the digest's home would fetch a list the page does not show.
    expect(page).not.toContain("PersonalEventsPanel");
    expect(page).not.toContain("readPersonalEvents");
    expect(page).not.toContain("personal-events-section");
    expect(page).not.toContain("Your personal events");
  });

  it("confirms an add inline, never as a toast", () => {
    const button = code.get("components/add-event-button.tsx") ?? "";

    // "inline notice only" — no toast, no portal, no floating layer.
    expect(button).not.toContain("createPortal");
    expect(button).not.toContain("fixed ");
    expect(button).not.toContain("toast");
    expect(button).not.toContain("Toast");
  });

  it("points the confirmation at the Timeline, not at a route that does not exist", () => {
    const button = code.get("components/add-event-button.tsx") ?? "";

    // The Timeline exists. A link to anywhere else would be a 404 — and the sidenav's
    // own rule against linking to a page that is not built.
    expect(button).toContain("/timeline?week=");
  });
});
