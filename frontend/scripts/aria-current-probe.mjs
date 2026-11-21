/**
 * The `aria-current` probe.
 *
 * **What it compares.** The server's markup for the settings sub-nav against the
 * browser's, on the same URL, after hydration. The settings sub-nav marks its current
 * section with `aria-current="page"`, and the client component's `usePathname()` and
 * the server's render of it have to agree — a difference between them is a hydration
 * mismatch, and the browser's diff names it.
 *
 * **The server's markup is read from the raw response**, before React touches it, so
 * the comparison is between the two things React itself compares.
 */

import { chromium } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3000";
const SEED_FILE = join(process.cwd(), "..", "backend", "config", "browse_seed.json");

const seed = JSON.parse(await readFile(SEED_FILE, "utf8"));
const account = seed.users.find((u) => u.plan === "pro");

const browser = await chromium.launch();
const context = await browser.newContext();
const page = await context.newPage();

await page.goto(`${BASE}/signin`, { waitUntil: "load" });
await page.waitForTimeout(3000);
await page.locator("#signin-email").fill(account.email);
await page.locator("#signin-password").fill(account.password);
await page.getByRole("button", { name: "Sign in" }).click();
await page.waitForURL((url) => !url.pathname.startsWith("/signin"), { timeout: 20_000 });

for (const path of ["/settings", "/settings/general", "/settings/profile"]) {
  /** The server's own markup, read before React touches it. */
  const serverHtml = await page.evaluate(
    async ({ base, target }) => {
      const response = await fetch(base + target, { credentials: "include" });
      return response.text();
    },
    { base: BASE, target: path },
  );

  /**
   * The rows the server rendered, parsed out of that markup.
   *
   * **Only the settings sub-nav's rows count.** The page carries `aria-current` in
   * other places too — the pre-auth footer, the reminders breadcrumb — and those are
   * not what this compares.
   */
  const navMarkup = serverHtml.match(/<nav aria-label="Settings sections"[\s\S]*?<\/nav>/)?.[0];
  const serverRows = navMarkup
    ? [...navMarkup.matchAll(/aria-current="page"[^>]*>([^<]*)</g)].map((m) => m[1].trim())
    : [];
  const serverAnyCurrent = navMarkup
    ? [...navMarkup.matchAll(/aria-current="([^"]*)"/g)].map((m) => m[1])
    : [];

  await page.goto(`${BASE}${path}`, { waitUntil: "load" });
  await page.waitForTimeout(2500);

  const clientRows = await page.evaluate(() =>
    Array.from(document.querySelectorAll('[aria-label="Settings sections"] a'))
      .filter((a) => a.getAttribute("aria-current") === "page")
      .map((a) => a.textContent.trim()),
  );

  console.log(path);
  console.log(
    "  server:",
    JSON.stringify(serverRows),
    "all aria-current:",
    JSON.stringify(serverAnyCurrent),
  );
  console.log("  client:", JSON.stringify(clientRows));
  console.log(
    "  match:",
    JSON.stringify(serverRows) === JSON.stringify(clientRows) ? "YES" : "NO — a hydration mismatch",
  );
}

await browser.close();
