/**
 * The truth test: does React 19 warn about a mutated `<html>` element or `<svg>`?
 *
 * **Why this exists.** The application's own hydration path turned out to be very hard
 * to instrument from the outside, and two rounds of browser probes disagreed with the
 * unit tests. The disagreement has to be settled by something authoritative, and the
 * authoritative thing is React itself, driven directly.
 *
 * **So this renders a page with React's own `hydrateRoot` — no Next.js in the loop.**
 * The server markup is produced by `renderToString`, the DOM is then mutated the way
 * Dark Reader mutates it, and React hydrates the result. Whatever React says is the
 * answer, and it answers the question the app's own probe could not.
 *
 * **Four cases are run**, because they are different questions:
 *
 * - `none` — neither flag. This is the baseline: it must warn, or the whole probe is
 *   not measuring anything.
 * - `html` — only the `<html>` flag. Does guarding the root layout silence the
 *   document element's mutation?
 * - `svg` — only the `<svg>` flag. Does guarding a glyph silence the stroke rewrite?
 * - `both` — both flags. The application's actual configuration.
 *
 * **A case that warns without the flag and stays quiet with it is the proof.**
 *
 * **The React bundles are served as files, not pasted into a script tag.**
 * They are CommonJS and they contain template literals, so embedding them in a string
 * means escaping backslashes, backticks and `${` — and an escaping mistake corrupts
 * the bundle in ways that look like React misbehaving. A local HTTP server sidesteps
 * the whole problem: the browser fetches the real files, byte for byte.
 */

import { chromium } from "@playwright/test";
import { createRequire } from "node:module";
import { createServer } from "node:http";
import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";

const require = createRequire(import.meta.url);
/**
 * `react-dom/server` is the only React module needed on this side of the script.
 *
 * `react` itself is **not** imported: the element tree is built as a *source string*
 * and evaluated inside the browser, where the served bundles provide `React`. The
 * server-side `renderToString` call is what turns that same string into the markup
 * the browser then mutates.
 */
const ReactDOMServer = require("react-dom/server");

const base = join(process.cwd(), "node_modules", ".pnpm");

/** The React packages, resolved from the installed tree. */
async function packagePath(globPrefix, tail) {
  const entries = (await readdir(base)).filter((d) => d.startsWith(globPrefix));
  return join(base, entries[0], "node_modules", tail);
}

const schedulerPath = await packagePath("scheduler@", "scheduler/cjs/scheduler.development.js");
const reactPath = await packagePath("react@19", "react/cjs/react.development.js");
const domPath = await packagePath("react-dom@19", "react-dom/cjs/react-dom.development.js");
const clientPath = await packagePath(
  "react-dom@19",
  "react-dom/cjs/react-dom-client.development.js",
);

/**
 * The loader for each bundle.
 *
 * **Each one is an IIFE**, because a classic script's `var` is global: four bundles in
 * four script tags would otherwise each reset the *previous* bundle's `module` and
 * `exports`, and the last one to load would leave every earlier bundle pointing at
 * the wrong exports object.
 *
 * **The `require` shim resolves React's own dependencies** from the globals the other
 * bundles put on `window`. The real `react-dom` is loaded rather than a hand-written
 * stand-in, because the client runtime reads
 * `ReactDOM.__DOM_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE` and that
 * object holds the event system's shared state.
 */
const LOADERS = {
  "/scheduler.js": `
(function () {
  var module = { exports: {} };
  var exports = module.exports;
  var process = { env: { NODE_ENV: "development" } };
  __SCHEDULER__
  window.Scheduler = module.exports;
})();
`,
  "/react.js": `
(function () {
  var module = { exports: {} };
  var exports = module.exports;
  var process = { env: { NODE_ENV: "development" } };
  __REACT__
  window.React = module.exports;
})();
`,
  "/react-dom.js": `
(function () {
  var module = { exports: {} };
  var exports = module.exports;
  var process = { env: { NODE_ENV: "development" } };
  function require(name) {
    if (name === "react") return window.React;
    if (name === "scheduler") return window.Scheduler;
    if (name === "react-dom") return window.ReactDOM;
    throw new Error("unhandled require: " + name);
  }
  __REACT_DOM__
  window.ReactDOM = module.exports;
})();
`,
  "/react-dom-client.js": `
(function () {
  var module = { exports: {} };
  var exports = module.exports;
  var process = { env: { NODE_ENV: "development" } };
  function require(name) {
    if (name === "react") return window.React;
    if (name === "scheduler") return window.Scheduler;
    if (name === "react-dom") return window.ReactDOM;
    throw new Error("unhandled require: " + name);
  }
  __REACT_DOM_CLIENT__
  window.ReactDOMClient = module.exports;
})();
`,
};

/** The element tree, built the same way on both sides. */
function elementSource(flags) {
  const htmlFlag = flags.suppressHtml ? ", suppressHydrationWarning: true" : "";
  const svgFlag = flags.suppressSvg ? ", suppressHydrationWarning: true" : "";
  return `React.createElement(
  "html",
  { lang: "en"${htmlFlag} },
  React.createElement(
    "body",
    null,
    React.createElement(
      "svg",
      { "aria-hidden": "true", viewBox: "0 0 16 16", fill: "none", stroke: "currentColor"${svgFlag} },
      React.createElement("path", { d: "M1 8h2.5" })
    )
  )
)`;
}

const markupFor = (flags) => ReactDOMServer.renderToString(eval(elementSource(flags)));

/** The mutation, run in the browser before hydration. */
const MUTATOR = `<script>
(function () {
  var root = document.documentElement;
  root.setAttribute("data-darkreader-mode", "dynamic");
  root.setAttribute("data-darkreader-scheme", "dark");
  root.setAttribute("data-darkreader-proxy-injected", "true");
  var svgs = document.querySelectorAll("svg");
  for (var i = 0; i < svgs.length; i++) {
    svgs[i].setAttribute("data-darkreader-inline-stroke", "");
    svgs[i].setAttribute("style", "--darkreader-inline-stroke:currentColor");
  }
  window.__mutated = { html: true, svgs: svgs.length };
})();
</script>`;

const bundles = {
  "/scheduler.js": await readFile(schedulerPath, "utf8"),
  "/react.js": await readFile(reactPath, "utf8"),
  "/react-dom.js": await readFile(domPath, "utf8"),
  "/react-dom-client.js": await readFile(clientPath, "utf8"),
};

const server = createServer((request, response) => {
  const url = new URL(request.url, "http://localhost");

  if (url.pathname === "/") {
    const flags = JSON.parse(url.searchParams.get("flags") ?? "{}");
    const markup = markupFor({
      suppressHtml: Boolean(flags.html),
      suppressSvg: Boolean(flags.svg),
    });
    const element = elementSource({
      suppressHtml: Boolean(flags.html),
      suppressSvg: Boolean(flags.svg),
    });
    const html = `<!DOCTYPE html>${markup}${MUTATOR}
<script src="/scheduler.js"></script>
<script src="/react.js"></script>
<script src="/react-dom.js"></script>
<script src="/react-dom-client.js"></script>
<script>
(function () {
  try {
    ReactDOMClient.hydrateRoot(document, ${element});
  } catch (e) {
    console.error("HYDRATE_THREW", e && e.message);
  }
})();
</script>`;
    response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    response.end(html);
    return;
  }

  const template = LOADERS[url.pathname];
  const source = bundles[url.pathname];
  if (!template || !source) {
    response.writeHead(404);
    response.end("not found");
    return;
  }
  const body = template
    .replace("__SCHEDULER__", source)
    .replace("__REACT__", source)
    .replace("__REACT_DOM__", source)
    .replace("__REACT_DOM_CLIENT__", source);
  response.writeHead(200, { "content-type": "application/javascript; charset=utf-8" });
  response.end(body);
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const origin = `http://127.0.0.1:${server.address().port}`;

const browser = await chromium.launch();
const context = await browser.newContext();

const results = {};

for (const [label, flags] of Object.entries({
  none: { html: false, svg: false },
  html: { html: true, svg: false },
  svg: { html: false, svg: true },
  both: { html: true, svg: true },
})) {
  const tab = await context.newPage();
  const errors = [];
  tab.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  tab.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));

  await tab.goto(`${origin}/?flags=${JSON.stringify(flags)}`, { waitUntil: "domcontentloaded" });
  await tab.waitForTimeout(900);

  const mutated = await tab.evaluate(() => window.__mutated ?? null);
  const warnings = errors.filter((e) => /hydrat|did not match|mismatch/i.test(e));
  results[label] = {
    mutated,
    hydrationWarnings: warnings.length,
    firstWarning: (warnings[0] ?? "").slice(0, 1200),
    otherErrors: errors
      .filter((e) => !/hydrat|did not match|mismatch/i.test(e))
      .slice(0, 3)
      .map((e) => e.split("\n")[0].slice(0, 140)),
  };
  await tab.close();
}

console.log(JSON.stringify(results, null, 2));
await browser.close();
server.close();
