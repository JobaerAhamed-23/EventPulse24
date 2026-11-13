// @vitest-environment node
/**
 * **The settings surface is navigable** — asserted against the app directory, not the
 * DOM.
 *
 * ## The bug these rules exist for
 *
 * Six `/settings/*` routes shipped, one per work item, each inheriting the convention
 * *"there is no `/settings` index page and no settings sub-navigation"*. Reachability was
 * therefore hand-written: the rail pointed at `/settings/reminders`, which has no links
 * out; `/settings/quiet-hours` carried the only links to `/settings/digest` and
 * `/settings/calendars`; `/settings/collections` was linked from nowhere at all. Four of
 * six working screens could not be reached by clicking, and **every test passed** — the
 * route tests rendered each page directly and the e2e specs navigated with
 * `page.goto()`, so nothing anywhere asserted that a user could *get* to them.
 *
 * These are the assertions that close that gap, and they are source- and
 * filesystem-level because that is where the property lives: "every settings route is in
 * the nav" is a fact about the set of directories under `app/settings`, and no render of
 * any one page can see it.
 */
import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { SETTINGS_SECTIONS, isSettingsPath } from "@/lib/settings-sections";

const ROOT = path.resolve(__dirname, "..");
const SETTINGS_DIR = path.join(ROOT, "app", "settings");

/** The route segments that have a page under `app/settings/` — the built screens. */
function builtSections(): string[] {
  return readdirSync(SETTINGS_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .filter((entry) => existsSync(path.join(SETTINGS_DIR, entry.name, "page.tsx")))
    .map((entry) => entry.name)
    .sort();
}

describe("the settings sections", () => {
  it("every section in the list is a route that exists", () => {
    // The 404-link rule, pointed at the one list two surfaces render. A row here with
    // no page behind it would be a dead link in the index *and* in the sub-nav on all
    // six screens at once.
    for (const section of SETTINGS_SECTIONS) {
      const segments = section.href.split("/").filter(Boolean);
      expect(segments[0], section.href).toBe("settings");
      expect(existsSync(path.join(ROOT, "app", ...segments, "page.tsx")), section.href).toBe(true);
    }
  });

  it("every route that exists is in the list", () => {
    // **This is the assertion that was missing.** The other direction — a screen that
    // is built, works, and is in no navigation — is exactly what shipped four times.
    // A seventh settings route added without a row here fails this, at the moment it is
    // added rather than whenever somebody notices.
    const listed = SETTINGS_SECTIONS.map((section) =>
      section.href.replace("/settings/", ""),
    ).sort();
    expect(listed).toEqual(builtSections());
  });

  it("has an index page, which is what the nav points at", () => {
    expect(existsSync(path.join(SETTINGS_DIR, "page.tsx"))).toBe(true);
  });

  it("lists no section twice, and no two sections under one label", () => {
    const hrefs = SETTINGS_SECTIONS.map((section) => section.href);
    const labels = SETTINGS_SECTIONS.map((section) => section.label);
    expect(new Set(hrefs).size).toBe(hrefs.length);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it("gives every section a description, because the index renders one", () => {
    for (const section of SETTINGS_SECTIONS) {
      expect(section.description.length, section.href).toBeGreaterThan(0);
    }
  });
});

describe("isSettingsPath", () => {
  it("is true on the index", () => {
    // The whole reason the helper exists: `"/settings".startsWith("/settings/")` is
    // `false`, so the bare prefix both navs used would go quiet on the index.
    expect(isSettingsPath("/settings")).toBe(true);
  });

  it("is true on every section", () => {
    for (const section of SETTINGS_SECTIONS) {
      expect(isSettingsPath(section.href), section.href).toBe(true);
    }
  });

  it("is false elsewhere", () => {
    for (const route of ["/", "/timeline", "/browse", "/conflicts", "/pricing", "/settingsfoo"]) {
      expect(isSettingsPath(route), route).toBe(false);
    }
  });
});

describe("the settings screens", () => {
  it("mount the sub-nav in every signed-in branch, so none is a dead end", () => {
    // `/settings/reminders` was the rail's destination and had no links out at all.
    //
    // **Per branch, not per file.** A settings page renders `AppShell` two or three
    // times — the signed-out shell, the `unavailable` shell, and the page itself — and
    // a `toContain("<SettingsNav />")` over the whole file passes while a branch that
    // lost its nav still ships. A mutation probe that deleted one of the two from
    // `/settings/reminders` left that weaker assertion green, which is how this one
    // came to be written: every `AppShell` opened with the signed-in user's name must
    // be followed immediately by the sub-nav.
    const missing: string[] = [];

    for (const section of builtSections()) {
      const source = readFileSync(path.join(SETTINGS_DIR, section, "page.tsx"), "utf8");
      const lines = source.split("\n");

      lines.forEach((line, index) => {
        // The signed-out branch is `name="" email=""` and is deliberately bare: a
        // section rail for somebody who is not signed in is a rail into six redirects.
        if (!/<AppShell name=\{.*email=\{session\.user\.email\}>/.test(line)) return;

        const next = lines.slice(index + 1).find((candidate) => candidate.trim() !== "");
        if (next?.trim() !== "<SettingsNav />") {
          missing.push(`${section}/page.tsx:${index + 1}`);
        }
      });
    }

    expect(missing).toEqual([]);
  });

  it("open at least one signed-in branch each, which is what the rule above walks", () => {
    // The guard on the guard. If the `<AppShell name={…} email={session.user.email}>`
    // pattern above ever stops matching — a rename, a refactor to a layout — the loop
    // would find nothing and pass vacuously, which is the failure mode of every
    // source-text assertion.
    //
    // **The floor is one, not two, and that is deliberate.** Most settings pages have
    // two: a named `unavailable` shell and the page itself, because most of them read
    // their own data and that read can fail. **`/settings/profile` reads nothing of its
    // own** — the name it edits is carried by the session — so it has one signed-in
    // branch and no `unavailable` shell to go with it.
    //
    // **One branch is still enough for the rule above to have teeth.** The loop walks
    // *every* branch it finds and demands the sub-nav after each, so a single branch is
    // walked once — not vacuously, but exactly once. The floor exists so the loop finds
    // something at all; it does not require a second copy of the same assertion.
    for (const section of builtSections()) {
      const source = readFileSync(path.join(SETTINGS_DIR, section, "page.tsx"), "utf8");
      const branches = source.match(/<AppShell name=\{.*email=\{session\.user\.email\}>/g) ?? [];
      expect(branches.length, section).toBeGreaterThanOrEqual(1);
    }
  });

  it("carries no hand-written link to another settings screen", () => {
    // **One list, not a web of one-off links.** The two links that used to sit on
    // `/settings/quiet-hours` were written because there was no sub-nav; with one, a
    // second copy of a destination is a second place to keep in sync. The index is
    // exempt — rendering the list in long form is its whole job.
    for (const section of builtSections()) {
      const source = readFileSync(path.join(SETTINGS_DIR, section, "page.tsx"), "utf8");
      const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
      expect(code.match(/href="\/settings/g) ?? [], section).toEqual([]);
    }
  });
});
