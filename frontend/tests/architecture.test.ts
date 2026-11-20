// @vitest-environment node
/**
 * "UI system: None" (DESIGN.md, EXPERIENCE.md §1) and the frontend's structural rules:
 * no UI kit or animation library, motion only through .fade-in, kebab-case files, and the
 * reserved generated-client folder.
 */
import {
  existsSync,
  readFileSync,
  readdirSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");
const SOURCE_DIRS = ["app", "components", "lib", "styles", "tests"];

// Component kits and animation libraries: none may be a dependency.
const FORBIDDEN_PACKAGES = [
  /^@mui\//,
  /^@material-ui\//,
  /^@chakra-ui\//,
  /^@radix-ui\//,
  /^@headlessui\//,
  /^@mantine\//,
  /^@nextui-org\//,
  /^@heroui\//,
  /^antd$/,
  /^@ant-design\//,
  /^react-bootstrap$/,
  /^bootstrap$/,
  /^daisyui$/,
  /^flowbite/,
  /^primereact$/,
  /^@ark-ui\//,
  /^shadcn/,
  /^framer-motion$/,
  /^motion$/,
  /^react-spring$/,
  /^@react-spring\//,
  /^gsap$/,
  /^@gsap\//,
  /^animejs$/,
  /^lottie/,
  /^@lottiefiles\//,
  /^@formkit\/auto-animate$/,
  /^react-transition-group$/,
  /^tailwindcss-animate$/,
  /^tw-animate-css$/,
];

// Tailwind still generates these (they aren't theme-driven), so markup is scanned instead.
const MOTION_CLASS =
  /(?<![\w-])(?:[\w-]+:)*(?:animate-[\w-]+|transition(?:-[\w-]+)?|duration-[\w-]+|delay-[\w-]+|ease-[\w-]+)(?![\w-])/;

function sourceFiles(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).flatMap((entry) => {
    const full = path.join(dir, entry);
    return statSync(full).isDirectory() ? sourceFiles(full) : [full];
  });
}

/** Class-name strings in a .tsx file: className="…", className={`…`} and className={"…"}. */
function classStrings(source: string): string[] {
  return [...source.matchAll(/className=(?:"([^"]*)"|\{`([^`]*)`\}|\{"([^"]*)"\})/g)].map(
    (m) => m[1] ?? m[2] ?? m[3],
  );
}

function motionClasses(source: string): string[] {
  return classStrings(source).flatMap((value) =>
    value.split(/\s+/).filter((token) => MOTION_CLASS.test(token)),
  );
}

describe("dependencies", () => {
  it("include no UI kit or animation library", () => {
    const pkg = JSON.parse(readFileSync(path.join(ROOT, "package.json"), "utf8"));
    const names = Object.keys({ ...pkg.dependencies, ...pkg.devDependencies });
    expect(names.length).toBeGreaterThan(0);
    const forbidden = names.filter((name) => FORBIDDEN_PACKAGES.some((re) => re.test(name)));
    expect(forbidden).toEqual([]);
  });
});

describe("motion classes in markup", () => {
  const tsx = SOURCE_DIRS.flatMap((dir) => sourceFiles(path.join(ROOT, dir))).filter(
    (file) => file.endsWith(".tsx") && !file.endsWith(".test.tsx"),
  );

  it("scans real files", () => {
    expect(tsx.length).toBeGreaterThan(0);
  });

  it("use no Tailwind animation or transition classes (motion goes through .fade-in)", () => {
    for (const file of tsx) {
      expect(motionClasses(readFileSync(file, "utf8")), path.relative(ROOT, file)).toEqual([]);
    }
  });

  it.each([
    ['<div className="animate-spin" />', ["animate-spin"]],
    ['<div className="p-4 transition" />', ["transition"]],
    ['<div className="transition-all duration-300" />', ["transition-all", "duration-300"]],
    ["<div className={`md:transition-opacity ${x}`} />", ["md:transition-opacity"]],
    ['<div className={"hover:delay-150 ease-out"} />', ["hover:delay-150", "ease-out"]],
  ])("catches planted %s", (source, expected) => {
    expect(motionClasses(source)).toEqual(expected);
  });

  it.each([
    '<div className="fade-in px-6" />',
    '<div className="text-ink-muted [font:var(--type-scale-body-md)]" />',
    '<p className="mt-4">transition</p>',
  ])("allows %s", (source) => {
    expect(motionClasses(source)).toEqual([]);
  });
});

/**
 * The server/client boundary.
 *
 * **A `"use client"` module may not reach `next/headers`.** The App Router's
 * `cookies()` and `headers()` are server-only, and a client bundle that imports them
 * fails to build:
 *
 * > You're importing a module that depends on "next/headers". This API is only
 * > available in Server Components in the App Router.
 *
 * **The unit tests do not catch it** — jsdom resolves `next/headers` to a stub, so the
 * island renders happily and every test passes. The **build** is what knows the
 * difference between a server module and a client one, and this rule makes the suite
 * know it too, so the defect is caught by `pnpm test` rather than by CI's build step.
 *
 * **The rule is about the module graph, not the file.** A client component may import
 * a helper that happens to live in `lib/`; what it may not do is import a module that
 * *transitively* reaches `next/headers`. So the check follows the imports.
 *
 * **Three things are deliberately not followed**, because following them would make the
 * rule cry wolf:
 *
 * - **Type-only imports.** `import type { ConflictPair } from "@/lib/conflict-list-read"`
 *   names a server module but imports no code from it — TypeScript erases the whole
 *   statement, so the client bundle never reaches it. Only the *values* cross the
 *   boundary.
 * - **The directive's position.** A module is a client module when `"use client"` is
 *   its **first statement**. A file that merely mentions the phrase — in a docstring,
 *   or in this test's own planted source — is not a client module.
 * - **The test files.** They are run by Vitest, not bundled by Next, and they mock
 *   `next/headers` away.
 */
describe("the server/client boundary", () => {
  /** Every `.ts`/`.tsx` source file, by its path relative to the frontend root. */
  const allSource = SOURCE_DIRS.flatMap((dir) => sourceFiles(path.join(ROOT, dir))).filter(
    (file) => file.endsWith(".ts") || file.endsWith(".tsx"),
  );

  /**
   * Whether a file's **first statement** is the `"use client"` directive.
   *
   * **The directive has to come first.** That is the App Router's own rule, and it is
   * what makes the check a statement about the file's *role* rather than a search for
   * a phrase anywhere in it. A docstring that quotes `"use client"` — as this very
   * test's and the server-only read module's do — must not turn those files into
   * client modules.
   */
  function isClientModule(file: string): boolean {
    const source = readFileSync(file, "utf8");
    // A directive prologue is a run of string-literal statements before any real code.
    const first = source.match(/^\s*(?:\/\*[\s\S]*?\*\/\s*|\/\/[^\n]*\n\s*)*"([^"]+)"\s*;?/);
    return first?.[1] === "use client";
  }

  /**
   * The import specifiers a file names **as values**, from `import … from "…"` and
   * `import("…")`.
   *
   * **Type-only imports are skipped.** `import type { X } from "…"` is erased by
   * TypeScript before the bundler ever sees it, so it creates no edge in the client
   * bundle. Following it would flag every island that borrows a *type* from a
   * server-side read module — which is safe, and common, and not the defect.
   */
  function importsOf(file: string): string[] {
    const source = readFileSync(file, "utf8");
    const valueImports = [
      ...source.matchAll(/(?:^|\n)\s*import\s(?!type\s)[^;]*?from\s+["']([^"']+)["']/g),
    ];
    const dynamicImports = [...source.matchAll(/import\(\s*["']([^"']+)["']\s*\)/g)];
    return [...valueImports, ...dynamicImports].map((m) => m[1]);
  }

  /** The `@/lib/...` module a specifier names, or null if it names something else. */
  function localModule(specifier: string): string | null {
    if (!specifier.startsWith("@/")) return null;
    return path.join(ROOT, specifier.slice(2));
  }

  /** The file a module specifier resolves to, trying the extensions a module may have. */
  function resolveModule(specifier: string): string | null {
    const base = localModule(specifier);
    if (base === null) return null;
    for (const candidate of [base, `${base}.ts`, `${base}.tsx`, path.join(base, "index.ts")]) {
      if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
    }
    return null;
  }

  /**
   * Whether a file reaches `next/headers` — directly, or through what it imports.
   *
   * **The walk is bounded by the files it has already seen**, so an import cycle is a
   * loop that terminates rather than a stack overflow.
   */
  function reachesServerOnly(file: string, seen = new Set<string>()): boolean {
    if (seen.has(file)) return false;
    seen.add(file);
    const source = readFileSync(file, "utf8");
    if (/from\s+["']next\/headers["']/.test(source)) return true;
    for (const specifier of importsOf(file)) {
      const resolved = resolveModule(specifier);
      if (resolved !== null && reachesServerOnly(resolved, seen)) return true;
    }
    return false;
  }

  it("keeps every client module off the server-only API", () => {
    // **Only the client modules.** A server component may import `next/headers` — that
    // is what it is for.
    const clients = allSource.filter(
      (file) => !file.endsWith(".test.tsx") && !file.endsWith(".test.ts") && isClientModule(file),
    );
    expect(clients.length).toBeGreaterThan(0);

    const offenders = clients
      .filter((file) => reachesServerOnly(file))
      .map((file) => path.relative(ROOT, file));
    expect(offenders).toEqual([]);
  });

  it("catches a client module that imports next/headers", () => {
    // **The rule has to be able to fail**, or it is a rule that proves nothing.
    const planted = path.join(ROOT, "components", "planted-server-import.tsx");
    try {
      writeFileSync(
        planted,
        [
          '"use client";',
          'import { cookies } from "next/headers";',
          "export const c = cookies;",
        ].join("\n"),
      );
      expect(isClientModule(planted)).toBe(true);
      expect(reachesServerOnly(planted)).toBe(true);
    } finally {
      if (existsSync(planted)) unlinkSync(planted);
    }
  });

  it("does not follow a type-only import", () => {
    // **A type is not a dependency.** `import type { ConflictPair } from
    // "@/lib/conflict-list-read"` names a server module but imports no code from it —
    // TypeScript erases the statement, so the client bundle never reaches it. The
    // islands that borrow those types are not defects, and this rule must not say
    // they are.
    const planted = path.join(ROOT, "components", "planted-type-import.tsx");
    try {
      writeFileSync(
        planted,
        [
          '"use client";',
          'import type { ConflictPair } from "@/lib/conflict-list-read";',
          "export type P = ConflictPair;",
        ].join("\n"),
      );
      expect(reachesServerOnly(planted)).toBe(false);
    } finally {
      if (existsSync(planted)) unlinkSync(planted);
    }
  });

  it("does not mistake a docstring for the client directive", () => {
    // **The directive has to be the first statement.** A module whose docstring
    // *quotes* `"use client"` — as `lib/notification-settings-read.ts` does, to warn
    // readers off it — is a server module, and this rule must leave it alone.
    const planted = path.join(ROOT, "components", "planted-mention.tsx");
    try {
      writeFileSync(
        planted,
        [
          "/**",
          ' * A docstring that mentions "use client" without being one.',
          " */",
          'import { cookies } from "next/headers";',
          "export const c = cookies;",
        ].join("\n"),
      );
      expect(isClientModule(planted)).toBe(false);
    } finally {
      if (existsSync(planted)) unlinkSync(planted);
    }
  });
});

describe("files", () => {
  const KEBAB = /^[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z0-9]+)*$/;

  /**
   * Next.js's own dynamic-route segment.
   *
   * **`[id]` is the framework's name for a parameterised segment, not a name we
   * chose.** The App Router reads the brackets; a route directory called `event-id`
   * would be a *literal* segment named `event-id`, and there would be no way to
   * parameterise it. So the segment is exempt from the kebab-case rule — and only the
   * segment: `app/events/[id]/page.tsx` is fine, `app/events/[id]/SomeFile.tsx` is not.
   */
  const DYNAMIC_SEGMENT = /^\[[a-z0-9]+\]$/;

  it("are kebab-case in every source folder", () => {
    const files = SOURCE_DIRS.flatMap((dir) => sourceFiles(path.join(ROOT, dir)));
    expect(files.length).toBeGreaterThan(0);
    const offenders = files
      .map((file) => path.relative(ROOT, file))
      .filter((rel) => rel !== path.join("lib", "api", "README.md"))
      .filter(
        (rel) =>
          !rel.split(path.sep).every((part) => KEBAB.test(part) || DYNAMIC_SEGMENT.test(part)),
      );
    expect(offenders).toEqual([]);
  });

  it("reserve lib/api for the generated client, with its README", () => {
    expect(readFileSync(path.join(ROOT, "lib/api/README.md"), "utf8")).toMatch(
      /generated[\s\S]*never edited by hand/i,
    );
  });
});

describe("the initials rule", () => {
  /**
   * The rule, in one module.
   *
   * **The disc is drawn in three places** — the sidenav's account row, the bottom bar's
   * More sheet and the account sheet — and **the fallback is what the account looks
   * like** to somebody who has not set a picture. So a fallback that differs between
   * them is visible.
   *
   * **The rule therefore lives in `lib/avatar.ts` and nowhere else.** This test is what
   * stops a second copy appearing: someone writes `name.slice(0, 2).toUpperCase()` in a
   * component because it is one line, and the rail's initials quietly stop matching the
   * sheet's.
   *
   * **The patterns are deliberately narrow.** `slice(0, 2)` is the naive rule and is
   * exactly what must not come back; a bare `.toUpperCase()` or `.split(" ")` is
   * innocent on its own and is not worth a false positive.
   */
  const NAIVE_INITIALS = /(?:name|displayName|live)\s*\.\s*slice\s*\(\s*0\s*,\s*2\s*\)/;

  it("is written once, in lib/avatar.ts", () => {
    const offenders: string[] = [];

    for (const dir of SOURCE_DIRS) {
      for (const file of sourceFiles(path.join(ROOT, dir))) {
        if (!file.endsWith(".tsx") && !file.endsWith(".ts")) continue;
        const rel = path.relative(ROOT, file);
        // **The rule's own module is the one place it is allowed.** And this file may
        // name the pattern — that is what makes the rule checkable — so it is exempt
        // too.
        if (rel === path.join("lib", "avatar.ts")) continue;
        if (rel === path.join("tests", "architecture.test.ts")) continue;
        if (rel === path.join("tests", "avatar-in-the-shell.test.tsx")) continue;

        const source = readFileSync(file, "utf8");
        if (NAIVE_INITIALS.test(source)) offenders.push(rel);
      }
    }

    expect(offenders).toEqual([]);
  });

  it("is reached through the shared helper, not through a second implementation", () => {
    // **The helper is the only way to get the initials.** The disc imports it, and the
    // helper is a pure function in a module that imports nothing — so a server
    // component may use it too.
    const disc = readFileSync(path.join(ROOT, "components/shell/avatar-disc.tsx"), "utf8");
    expect(disc).toMatch(/import\s*\{\s*initials\s*\}\s*from\s*"@\/lib\/avatar"/);

    // **And the helper is the whole rule** — one function, no dependencies, so there is
    // nothing to keep in step with.
    const helper = readFileSync(path.join(ROOT, "lib/avatar.ts"), "utf8");
    expect(helper).toMatch(/export function initials\(/);
    expect(helper.match(/export function /g) ?? []).toHaveLength(1);
  });
});
