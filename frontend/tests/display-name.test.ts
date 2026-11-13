// @vitest-environment node
/**
 * **The name is derived in one place, and every page uses that place.**
 *
 * ## The rule
 *
 * The account has a name now. The rail, the bottom bar and every page show it — and
 * the rule for *which* name is shown is one rule: **the stored name when there is one,
 * the email-derived name when there is not.**
 *
 * ## Why this file exists
 *
 * **The rule was copy-pasted into fifteen files.** Each copy was the same five lines:
 * take the email's local part, split it on `.`, `_` and `-`, capitalise each word, join
 * them with spaces. When the account gained a name, the rule had to grow a half — and
 * **a rule with two branches that is pasted fifteen times is a rule that can differ from
 * itself in fifteen places, silently.** No single test could see that, because each
 * copy looked right on its own.
 *
 * **These assertions are filesystem-level because that is where the property lives.**
 * "Every page derives the name the same way" is a fact about the *set* of files under
 * `app/`, and no render of any one page can see it.
 *
 * **The per-page behaviour is proved elsewhere.** `lib/display-name.test.ts` pins what
 * the helper does; this file pins that **every page goes through it** — that no page
 * carries a copy of its own.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

/** Every `page.tsx` under `app/` — the routes that render a shell. */
function pageFiles(): string[] {
  const out: string[] = [];
  const walk = (directory: string): void => {
    for (const entry of readdirSync(directory)) {
      const full = path.join(directory, entry);
      if (statSync(full).isDirectory()) {
        walk(full);
        continue;
      }
      if (entry === "page.tsx") out.push(path.relative(ROOT, full).split(path.sep).join("/"));
    }
  };
  walk(path.join(ROOT, "app"));
  return out.sort();
}

/** The source of a page, with its comments removed. */
function code(relative: string): string {
  return readFileSync(path.join(ROOT, relative), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/[^\n]*/g, "");
}

describe("the pages", () => {
  it("there are some to check", () => {
    // **The guard on the guard.** If the walk found nothing, every assertion below
    // would pass vacuously — and "no page carries its own copy" would be true of a
    // codebase with no pages at all.
    expect(pageFiles().length).toBeGreaterThan(10);
  });

  it("no page carries its own copy of the display-name rule", () => {
    // **This is the assertion the whole item exists for.**
    //
    // **A local copy is a `function displayName` in a page's own source.** The old
    // copies were five lines each, in fifteen files, and every one of them looked
    // correct — which is exactly why the rule could drift without anything failing.
    //
    // **A page that defines one is a page whose rail can disagree with every other
    // page's rail**, and nothing would say so.
    //
    // **The name is not the only shape a copy can take.** A copy called `localName`
    // or `greetingName` is the same copy under another hat, and matching only on the
    // identifier lets it through. **So the rule is about the *rule*, not the name**:
    // a page that derives a name from an email — by splitting it, capitalising it,
    // or otherwise — is carrying a copy, whatever it called the function.
    const carriers: string[] = [];

    for (const file of pageFiles()) {
      const source = code(file);
      // **The rule, spelled out.** The helper's fallback is exactly this: take the
      // local part, split it on the separators, capitalise each word.
      if (/\.split\s*\(\s*["'`]@/.test(source)) carriers.push(file);
      if (/\.split\s*\(\s*\/\s*\[?\._-/.test(source)) carriers.push(file);
      // **A function named after the rule, whatever it is called.**
      if (/function\s+\w*[dD]isplay[Nn]ame\w*\s*\(/.test(source)) carriers.push(file);
    }

    expect(
      [...new Set(carriers)],
      "These pages carry their own copy of the display-name rule. Delete the local " +
        "copy and use the shared helper in @/lib/display-name:\n  " +
        [...new Set(carriers)].join("\n  "),
    ).toEqual([]);
  });

  it("every page that names somebody calls the shared helper with the whole user", () => {
    // **The argument is the point.** `displayName(session.user.email)` is the old
    // call — it passes only the address, so **the stored name can never be shown**,
    // and the call compiles and looks right. The helper takes the user, so the
    // stored name travels with it.
    //
    // **The rule is "the argument is not the whole user", not "the argument is
    // literally `session.user.email`".** A whitelist of wrong spellings would let
    // through `displayName(session.user.email as never)`, `displayName(user.email)`,
    // `displayName(session.user.email.toLowerCase())` — every one of which is the
    // same bug wearing a different hat. **So the assertion is inverted: anything that
    // is not exactly `session.user` is wrong.**
    const wrong: string[] = [];
    const right: string[] = [];

    for (const file of pageFiles()) {
      const source = code(file);
      if (!/\bdisplayName\s*\(/.test(source)) continue;
      // **Every call in the file, whatever the argument is.**
      const calls = source.match(/\bdisplayName\s*\(([^)]*)\)/g) ?? [];
      for (const call of calls) {
        if (/^\s*displayName\s*\(\s*session\.user\s*\)$/.test(call)) right.push(file);
        else wrong.push(file);
      }
    }

    expect(
      wrong,
      "These pages call displayName with something other than the whole user, so " +
        "they can never show the stored name. Pass the whole user:\n  " +
        [...new Set(wrong)].join("\n  "),
    ).toEqual([]);
    expect(right.length, "no page calls the shared helper at all").toBeGreaterThan(0);
  });

  it("no page passes a hand-built name to the shell", () => {
    // **The shell's `name` prop is what the rail shows.** A page that assembles a name
    // itself — `"Maya "` + something, or a literal — is a page whose rail can say
    // something no other page's rail says.
    //
    // **The empty string is allowed**, because three routes serve anonymous visitors
    // and must pass `""` for them. That is the one exception, and it is a literal.
    //
    // ## The hole this assertion had, and why it is closed
    //
    // **Six pages bind the name to a local `const name` and pass that.** So an earlier
    // version of this test allowed the bare identifier `name` — and that let a page
    // write `const name = "Maya " + session.user.email.split("@")[0]` and pass **all
    // seven** tests in this file green. **The review proved it.**
    //
    // **The lesson is the repo's own: an assertion that cannot fail.** The allow-list
    // said "the identifier `name` is fine" without ever asking *where `name` came
    // from*.
    //
    // **So the rule is now "the name is traceable to the helper".** A prop is legal
    // if it is the helper's call, the empty string, or a local binding whose
    // definition is *exactly* the helper's call. **Anything else is a hand-built
    // name**, including a binding that the helper's call only partly feeds.
    const offenders: string[] = [];

    for (const file of pageFiles()) {
      const source = code(file);
      const calls = source.match(/<AppShell\s+name=\{([^}]*)\}/g) ?? [];
      if (calls.length === 0) continue;

      // **The local bindings, and what each is defined as.**
      const bindings = new Map<string, string>();
      for (const definition of source.matchAll(
        /const\s+(\w+)\s*=\s*([^;]+);/g,
      )) {
        bindings.set(definition[1], definition[2].trim());
      }

      for (const call of calls) {
        const prop = call.replace(/^<AppShell\s+name=\{/, "").replace(/\}$/, "").trim();

        // **The three legal forms.**
        if (prop === '""') continue;
        if (/^displayName\s*\(\s*session\.user\s*\)$/.test(prop)) continue;
        if (bindings.has(prop)) {
          const definition = bindings.get(prop) ?? "";
          // **A binding is legal only if it *is* the helper's call.** A ternary
          // around it — `session.kind === "signed-in" ? displayName(session.user) : ""`
          // — is legal too, because both arms are the helper or the empty string.
          const arms = definition.includes("?")
            ? definition.split("?").slice(1).join("?").split(":")
            : [definition];
          const allLegal = arms.every((arm) =>
            /^\s*(""|displayName\s*\(\s*session\.user\s*\))\s*$/.test(arm),
          );
          if (allLegal) continue;

          offenders.push(
            `${file} — name is bound to \`${prop}\`, which is defined as \`${definition}\``,
          );
          continue;
        }

        offenders.push(`${file} — name is \`${prop}\``);
      }
    }

    expect(
      offenders,
      "These pages build the shell's name themselves, so their rail can disagree " +
        "with every other page's rail. Use displayName(session.user):\n  " +
        offenders.join("\n  "),
    ).toEqual([]);
  });
});

describe("the helper", () => {
  it("is a server-safe module — no client banner and no imports", () => {
    // **It is imported by server components, client components and tests alike**, so
    // it must not carry `"use client"` and must not import anything that only exists
    // on one side of the boundary.
    //
    // **The comments are stripped first, and that is not a detail.** The module's own
    // docstring *names* `"use client"` — it explains why the module must not carry it
    // — so an assertion over the raw file would find the phrase in the prose and
    // fail. **A comment is not code, and an assertion that reads one is asserting on
    // prose.** The repo makes this point in `tests/endpoint-coverage.test.ts` for the
    // same reason.
    const source = code("lib/display-name.ts");

    expect(source).not.toContain('"use client"');
    expect(source).not.toMatch(/^import\s/m);
  });

  it("takes the whole user, not two positional arguments", () => {
    // **`displayName(name, email)` would invite the two in the wrong order**, and the
    // rule is "the stored name if there is one, otherwise the address" — one object
    // makes that impossible to get backwards.
    const source = readFileSync(path.join(ROOT, "lib/display-name.ts"), "utf8");

    expect(source).toMatch(/export function displayName\(user:\s*\{\s*name:\s*string;\s*email:\s*string\s*\}\)/);
  });

  it("is the one the pages import, not a copy of it", () => {
    // **Every page that names somebody imports it from `@/lib/display-name`.** A page
    // that imported it from somewhere else — or from a file that re-exported it — would
    // be a second place for the rule to live.
    for (const file of pageFiles()) {
      const source = code(file);
      if (!/\bdisplayName\s*\(/.test(source)) continue;
      expect(source, `${file} must import the shared helper`).toMatch(
        /import\s*\{\s*displayName\s*\}\s*from\s*["']@\/lib\/display-name["']/,
      );
    }
  });
});
