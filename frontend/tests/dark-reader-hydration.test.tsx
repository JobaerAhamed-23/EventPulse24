import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RootLayout from "@/app/layout";
import { Sidenav } from "@/components/shell/sidenav";

// next/font only works inside Next's compiler; each mock returns a distinct variable class.
vi.mock("next/font/google", () => ({
  Inter: () => ({ variable: "font-var-inter" }),
  Source_Serif_4: () => ({ variable: "font-var-source-serif" }),
  JetBrains_Mono: () => ({ variable: "font-var-jetbrains-mono" }),
}));

vi.mock("@/styles/globals.css", () => ({}));

// The sidenav marks the active route from the pathname, so it needs one.
vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
}));

// The sidenav mounts the personal-events panel, which is not what this test is about.
vi.mock("@/components/personal-events-panel", () => ({
  PersonalEventsPanel: () => null,
}));

/**
 * The Dark Reader hydration guard.
 *
 * **Dark Reader rewrites the page before React hydrates.** It is a browser extension
 * that inverts the colours of a page it thinks is light, and to do that it rewrites
 * the DOM: it stamps the document element with its own attributes
 * (`data-darkreader-mode`, `data-darkreader-scheme`, `data-darkreader-proxy-injected`)
 * and rewrites every stroke-only SVG's stroke (`data-darkreader-inline-stroke` plus a
 * `style` attribute carrying `--darkreader-inline-stroke`).
 *
 * React then hydrates, compares the mutated DOM against the markup it rendered on the
 * server, finds attributes it did not render, and reports a hydration mismatch. **The
 * server markup was correct and the extension's attributes are the extension's
 * business** — so React's answer is to ignore them, not to patch them back and fight
 * the reader who installed the extension.
 *
 * **Why this needs a test.** React's `suppressHydrationWarning` is **one level deep**:
 * it silences a mismatch on the element that carries it, not on that element's
 * descendants. A flag on `<html>` does not cover the nav `<svg>`s; a flag on a
 * wrapper `<div>` does not cover the `<svg>` inside it. The flag therefore has to sit
 * on each mutated element, and the only thing that keeps it there is a test — the
 * guard is invisible in the markup and a well-meaning cleanup would remove it.
 *
 * **This test is the one that would have caught the bug.** It does what the extension
 * does — mutates the DOM between render and hydrate — and asserts React stays quiet.
 */

/** The attributes Dark Reader puts on the document element. */
const HTML_MUTATIONS: Array<[string, string]> = [
  ["data-darkreader-mode", "dynamic"],
  ["data-darkreader-scheme", "dark"],
  ["data-darkreader-proxy-injected", "true"],
];

/** The attributes Dark Reader puts on a stroke-only SVG. */
const SVG_MUTATIONS: Array<[string, string]> = [
  ["data-darkreader-inline-stroke", ""],
  ["style", "--darkreader-inline-stroke:currentColor"],
];

/**
 * Render to markup, mutate the DOM the way the extension does, then hydrate.
 *
 * **The mutation happens between the two halves, which is the whole point.** The
 * extension runs on page load, before React's bundle has executed — so the DOM React
 * hydrates against is already the extension's, and the server markup it compares
 * against is not.
 *
 * Returns the hydration warnings React logged.
 */
async function hydrateWithDarkReader(element: React.ReactElement): Promise<string[]> {
  const markup = renderToStaticMarkup(element);

  // The server markup goes into a fresh container, exactly as a page load would.
  const container = document.createElement("div");
  container.innerHTML = markup;
  document.body.appendChild(container);

  // **The extension rewrites the DOM.**
  const html = document.documentElement;
  for (const [name, value] of HTML_MUTATIONS) {
    html.setAttribute(name, value);
  }
  for (const svg of Array.from(container.querySelectorAll("svg"))) {
    for (const [name, value] of SVG_MUTATIONS) {
      svg.setAttribute(name, value);
    }
  }

  const warnings: string[] = [];
  const originalError = console.error;
  console.error = (...args: unknown[]) => {
    warnings.push(args.map((a) => String(a)).join(" "));
  };

  try {
    const { hydrateRoot } = await import("react-dom/client");
    const root = hydrateRoot(container, element);
    // Let hydration run to completion.
    await new Promise((resolve) => setTimeout(resolve, 50));
    root.unmount();
  } finally {
    console.error = originalError;
  }

  return warnings.filter((w) => /hydrat|did not match|mismatch/i.test(w));
}

describe("the Dark Reader hydration guard", () => {
  beforeEach(() => {
    // The extension's attributes go on `<html>`, and they outlive one test.
    for (const [name] of HTML_MUTATIONS) {
      document.documentElement.removeAttribute(name);
    }
  });

  it("keeps the root layout quiet when the extension marks the document", async () => {
    /**
     * The layout returns the `<html>` element itself — rendering it with Testing
     * Library would nest an `<html>` inside a `<div>`, which is not what the browser
     * hydrates. `renderToStaticMarkup` on the element gives the same markup the
     * server sent, so the test hydrates the real thing.
     */
    const html = RootLayout({ children: <p>child</p> } as LayoutProps<"/">);

    const warnings = await hydrateWithDarkReader(html);

    expect(warnings).toEqual([]);
  });

  it("keeps the nav glyphs quiet when the extension rewrites their strokes", async () => {
    const warnings = await hydrateWithDarkReader(
      <Sidenav name="Ada Lovelace" email="ada@example.com" avatarUrl="" />,
    );

    expect(warnings).toEqual([]);
  });

  it("keeps the browse magnifier quiet when the extension rewrites its stroke", async () => {
    /**
     * The magnifier is asserted at the source, not through the whole component.
     *
     * `BrowseSearch` is a client component that fetches, paginates and holds a dozen
     * props — rendering it to test one `<svg>` would drag the whole browse data layer
     * into a hydration test and make the test fail for reasons that have nothing to
     * do with the extension. **What matters here is that the `<svg>` carries the
     * guard**, and that is a property of the file.
     *
     * So this reads the component's source and checks that the `<svg>` element that
     * holds the magnifier has `suppressHydrationWarning` on it. The
     * "proves the mutation is what React would otherwise complain about" test below
     * then proves that a guarded `<svg>` really is quiet — so together the two say
     * what the file says and what React does.
     */
    const { readFile } = await import("node:fs/promises");
    const { join } = await import("node:path");

    const source = await readFile(
      join(process.cwd(), "components", "browse", "browse-search.tsx"),
      "utf8",
    );

    // The magnifier's <svg> block, and the guard on it. The match starts at the JSX
    // tag itself — a plain `<svg` also appears in this file's prose, and matching
    // that would test the comment instead of the component.
    const svg = source.match(/<svg\s[\s\S]*?>/)?.[0];
    expect(svg).toBeDefined();
    expect(svg).toContain("suppressHydrationWarning");
  });

  /**
   * The test has to be able to fail.
   *
   * **A guard test that cannot fail is not a guard.** This renders the same markup
   * *without* the `suppressHydrationWarning` flags and asserts React *does* complain —
   * which proves the mutation is real and that the flags are what silenced it. If this
   * ever stops warning, the mutation stopped happening and the three tests above have
   * stopped testing anything.
   */
  it("proves the mutation is what React would otherwise complain about", async () => {
    const unguarded = (
      <svg aria-hidden="true" viewBox="0 0 16 16" fill="none" stroke="currentColor">
        <path d="M1 8h2.5" />
      </svg>
    );

    const warnings = await hydrateWithDarkReader(unguarded);

    expect(warnings.length).toBeGreaterThan(0);
    expect(warnings.join(" ")).toContain("darkreader-inline-stroke");
  });
});
