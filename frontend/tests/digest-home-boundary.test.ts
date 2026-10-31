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
import { readFileSync } from "node:fs";
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
    // And the row it opens is inert, because Browse is not built: a link to a 404 is
    // a lie.
    expect(more).toContain('aria-disabled="true"');
    expect(more).not.toContain("<Link");
  });

  it("links nowhere that does not exist — the account row included", () => {
    // The sidenav's own rule: "a link to a 404 is a lie about where the label goes."
    // The account row broke it by linking to `/settings`, which has no route. It is a
    // button onto the account sheet now, and this pins it: no shell file may link to a
    // route that is not built, and `/settings` is the one that was.
    for (const [file, source] of code) {
      expect(source, file).not.toContain('href="/settings"');
    }
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

  it("constrains the content, so a wide screen does not reflow the digest", () => {
    // §10: "Desktop adds whitespace and hover affordances — never features, screens,
    // actions or copy." A wide viewport stretches a card; a wide *card* changes how the
    // card reads.
    const shell = code.get("components/shell/app-shell.tsx") ?? "";
    expect(shell).toContain("max-w-(--layout-container-max)");
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

  it("gives the empty state one link and no button", () => {
    const empty = code.get("components/digest/digest-empty.tsx") ?? "";

    expect([...empty.matchAll(/<Link/g)]).toHaveLength(1);
    expect(empty).not.toContain("<button");
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
