// @vitest-environment node
/**
 * "UI system: None" (DESIGN.md, EXPERIENCE.md §1) and the frontend's structural rules:
 * no UI kit or animation library, motion only through .fade-in, kebab-case files, and the
 * reserved generated-client folder.
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
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
