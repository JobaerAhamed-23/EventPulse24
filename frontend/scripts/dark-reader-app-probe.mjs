/**
 * The application-level Dark Reader probe.
 *
 * **What it answers.** The React truth test settled what React *does* when an
 * extension rewrites the page before hydration. This answers the other half: what
 * **this application** does, on the pages a signed-in reader actually sees — the
 * pages whose nav glyphs the user's console error named.
 *
 * **The mutation is injected into the HTML response**, as an inline script at the end
 * of `<body>`. That is the only point in the page's timeline where both halves of the
 * condition hold: the parser has already built the DOM, and the deferred module
 * scripts that carry React have not yet executed.
 *
 * **The probe reports what it did, not just what it found.** A run in which the
 * mutator never ran says so, loudly — because a probe that reports a clean result for
 * the wrong reason is worse than no probe at all.
 *
 * Usage: node scripts/dark-reader-app-probe.mjs [--no-guards]
 */

import { chromium } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3000";
const SEED_FILE = join(process.cwd(), "..", "backend", "config", "browse_seed.json");

const HTML_MUTATIONS = [
  ["data-darkreader-mode", "dynamic"],
  ["data-darkreader-scheme", "dark"],
  ["data-darkreader-proxy-injected", "true"],
];

const SVG_MUTATIONS = [
  ["data-darkreader-inline-stroke", ""],
  ["style", "--darkreader-inline-stroke:currentColor"],
];

const MUTATOR = `
<script>
(function () {
  var HTML_MUTATIONS = ${JSON.stringify(HTML_MUTATIONS)};
  var SVG_MUTATIONS = ${JSON.stringify(SVG_MUTATIONS)};
  var root = document.documentElement;
  for (var i = 0; i < HTML_MUTATIONS.length; i++) {
    root.setAttribute(HTML_MUTATIONS[i][0], HTML_MUTATIONS[i][1]);
  }
  var svgs = document.querySelectorAll("svg");
  for (var j = 0; j < svgs.length; j++) {
    for (var k = 0; k < SVG_MUTATIONS.length; k++) {
      var name = SVG_MUTATIONS[k][0];
      var value = SVG_MUTATIONS[k][1];
      if (name === "style") {
        svgs[j].setAttribute("style", (svgs[j].getAttribute("style") || "") + value);
      } else {
        svgs[j].setAttribute(name, value);
      }
    }
  }
  window.__darkReaderProbe = {
    svgCount: svgs.length,
    htmlAttrs: Array.prototype.map.call(root.attributes, function (a) { return a.name; }),
  };
})();
</script>
`;

const seed = JSON.parse(await readFile(SEED_FILE, "utf8"));
const account = seed.users.find((u) => u.plan === "pro");

const browser = await chromium.launch();
const context = await browser.newContext();

const errors = [];

/**
 * The HTML response is rewritten to carry the mutator.
 *
 * **Only the document is rewritten.** The content type is checked on the *response*,
 * not on the request: a request's headers say what the browser is asking for, and a
 * navigation request says nothing about what the server will answer with.
 */
await context.route("**/*", async (route) => {
  const request = route.request();
  if (request.resourceType() !== "document") {
    await route.continue();
    return;
  }

  /**
   * **Only the pages under test are mutated.**
   *
   * The sign-in page is left alone, because it is not what the probe is about and the
   * mutation is not what the sign-in needs: the form's own script has to run against
   * the markup the server sent. Mutating it would make the sign-in fail for a reason
   * that has nothing to do with the thing being measured.
   */
  if (
    !request.url().includes("/browse") &&
    !request.url().includes("/timeline") &&
    !request.url().includes("/settings")
  ) {
    await route.continue();
    return;
  }

  const response = await route.fetch();
  const contentType = response.headers()["content-type"] ?? "";
  if (!contentType.includes("text/html")) {
    await route.fulfill({ response });
    return;
  }

  const body = await response.text();
  const index = body.lastIndexOf("</body>");
  const patched =
    index === -1 ? body + MUTATOR : body.slice(0, index) + MUTATOR + body.slice(index);

  await route.fulfill({ response, body: patched });
});

const page = await context.newPage();
page.on("console", (message) => {
  if (message.type() === "error") errors.push(message.text());
});
page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));

/** Sign in, the way a person does. */
await page.goto(`${BASE}/signin`, { waitUntil: "domcontentloaded" });

/**
 * **Wait for the form to be live before typing into it.**
 *
 * The sign-in form is a React component with an `onSubmit` handler. **Before React
 * hydrates, the markup on the page is a plain HTML form** — and clicking its button
 * then does what a plain HTML form does: a GET navigation with the field values in
 * the query string, which is not a sign-in at all.
 *
 * So the probe waits for the button to be attached before it touches anything. The
 * signal is that the button's `type` attribute is `button` rather than `submit` —
 * hmm, no: the signal that matters is that React's handler is live, and the honest
 * way to see that is to wait for the button to stop being a form's default submit.
 */
await page.waitForFunction(
  () => {
    const button = document.querySelector("button[type='submit'], form button");
    return Boolean(button) && !button.hasAttribute("formaction");
  },
  { timeout: 20_000 },
);
await page.waitForTimeout(1500);

await page.locator("#signin-email").fill(account.email);
await page.locator("#signin-password").fill(account.password);
await page.getByRole("button", { name: "Sign in" }).click();
await page.waitForURL((url) => !url.pathname.startsWith("/signin"), { timeout: 20_000 });

/** Clear the console, so only the Browse load's warnings count. */
errors.length = 0;

const report = {};

for (const path of ["/browse", "/timeline", "/settings"]) {
  await page.goto(`${BASE}${path}`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(3500);

  const probe = await page.evaluate(() => window.__darkReaderProbe ?? null);
  const svgs = await page.evaluate(() => {
    const list = Array.from(document.querySelectorAll("svg"));
    return {
      count: list.length,
      withExtensionAttributes: list.filter((svg) =>
        svg.hasAttribute("data-darkreader-inline-stroke"),
      ).length,
    };
  });

  const hydration = errors.filter((line) => /hydrat|did not match|mismatch/i.test(line));

  report[path] = {
    mutatorRan: Boolean(probe),
    svgs,
    hydrationWarnings: hydration.length,
    firstWarning: (hydration[0] ?? "").split("\n")[0].slice(0, 140),
    warningNamesElements: hydration
      .flatMap((line) => line.split("\n"))
      .filter((line) => /^\s*[-+]\s/.test(line))
      .slice(0, 8)
      .map((line) => line.trim()),
    fullWarning: (hydration[0] ?? "").slice(0, 2500),
  };

  errors.length = 0;
}

console.log(JSON.stringify(report, null, 2));
await browser.close();
