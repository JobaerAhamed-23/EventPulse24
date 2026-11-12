import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright's configuration for the Browse end-to-end tests.
 *
 * **These tests run against the real stack, not a mock.** The Browse surface is a
 * server-rendered page that reads a ranked pool from the API, filters it in the browser
 * and saves events through an endpoint with a server-side quota gate. **None of that
 * exists in a mock** — a mocked API would be asserting that the mock behaves, which is
 * the one thing a mock is guaranteed to do. So these tests drive the real frontend
 * against the real backend against the real database, and the data in that database comes
 * from the committed seed file via `make manage ARGS="seed_browse_catalog"`.
 *
 * **That is why they are not part of `make test-web`.** The Vitest suite is fast,
 * hermetic and runs on every commit; these tests need a stack up and a seeded database,
 * so they are a separate target (`make test-e2e`) that the walk-through item runs
 * deliberately. The Vitest `include` pattern is `**\/*.test.{ts,tsx}` and these files are
 * `*.spec.ts` under `e2e/`, so the two suites cannot pick up each other's files.
 *
 * **The web server is started by Playwright, the API is not.** The API is the backend's
 * own process (`make dev` runs it), and a Playwright-managed API would need the same
 * migrations, the same role grants and the same environment the backend has, so the
 * backend's own `make dev` is the honest thing to point at. The frontend, by contrast,
 * is a plain `next dev` with no state worth managing, so Playwright starts it — and
 * `reuseExistingServer` means a stack the developer already has running is used rather
 * than fought with.
 *
 * **The base URL comes from the environment, exactly as the app does.** `API_BASE_URL`
 * and `WEB_PORT` are the same variables `.env` sets for `make dev`, so the e2e run
 * talks to the same backend the developer is looking at, and a mismatch is a visible
 * environment error rather than a mysterious failure.
 */

/** The frontend's origin. `WEB_PORT` is the same variable `.env` sets. */
const WEB_PORT = Number(process.env.WEB_PORT ?? "3000");

/** The frontend's origin, as a URL. */
const BASE_URL = process.env.E2E_BASE_URL ?? `http://127.0.0.1:${WEB_PORT}`;

export default defineConfig({
  /**
   * **The test directory is `e2e/`, and it has to be.**
   *
   * Playwright's default `testDir` is the whole project, and its default match pattern
   * is the same shape as the Vitest suite's own — `*.spec.ts` *or* `*.test.ts`. So
   * without this line, `playwright test` would try to run every Vitest file, and each
   * one would die with *"Vitest cannot be imported in a CommonJS module"* — Playwright
   * loads the file through its own CommonJS loader, and Vitest's ESM-only entry point
   * refuses.
   *
   * **The two suites must not find each other's files.** They have incompatible
   * requirements — Vitest needs a jsdom environment and no stack; Playwright needs a
   * running stack and a seeded database — and a file picked up by the wrong runner
   * fails for reasons that have nothing to do with the test itself.
   */
  testDir: "./e2e",

  /**
   * **One worker, and the reason is the save quota.**
   *
   * The Free account's allowance is **one save a day**, and it lives in Redis under a
   * key naming the user. Two workers running the Free test at once would spend the same
   * allowance between them — one of them would see the wall where the test expects a
   * save, or the other would see a save where the test expects the wall — and **the
   * failure would be intermittent and would look like a product bug.** The quota is a
   * real gate and the tests have to own it serially.
   */
  workers: 1,
  fullyParallel: false,

  /**
   * **The reporter is the list reporter, and the output is plain.**
   *
   * The CI runner reads the exit code; a developer reads the lines. Neither needs a
   * browser to be opened, and `--reporter=list` prints the failure's message and the
   * call that caused it, which is what a failing walk-through needs to say.
   */
  reporter: [["list"]],

  /**
   * **The timeout is generous, and the reason is the stack.**
   *
   * The first page of Browse is a server render that waits on the API, which waits on
   * the database. On a cold stack — the first request after `make dev` compiles a
   * route — that can take several seconds, and a timeout that fires mid-compile would
   * be a false failure. Thirty seconds is long enough for the slow case and short
   * enough that a genuinely hung test still fails rather than blocking the run.
   */
  timeout: 30_000,
  expect: {
    /**
     * **Ten seconds for an assertion to become true.**
     *
     * The client-side parts — the filter, the save button's morph, the quota line — are
     * near-instant. But the search's *first* paint is a server render, and the save
     * button's label changes after a round trip to the API, so the wait has to cover a
     * request that has left the browser.
     */
    timeout: 10_000,
  },

  /**
   * **The traces are kept on failure.**
   *
   * A failed walk-through is evidence, and the evidence is what the write-up is made
   * of. `trace: "retain-on-failure"` keeps the trace only when a test fails, so a green
   * run leaves nothing behind and a red one leaves a DOM snapshot, a network log and a
   * timeline of what the browser did.
   */
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },

  /**
   * **Chromium only, and only at the desktop size.**
   *
   * The design's locks are stated for the desktop surface — a three-column grid, a
   * sidenav, two tiers — and the walk-through is of that surface. The sidenav is
   * `hidden` below `md`, so a phone-sized run would not have the navigation the
   * acceptance criteria name.
   */
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } },
    },
  ],

  /**
   * **The web server.**
   *
   * `reuseExistingServer` is `!process.env.CI`, so a developer with `make dev` already
   * running uses that stack, and CI starts a fresh one. The command is `pnpm dev` from
   * the frontend directory, which is what `make dev` runs too.
   */
  webServer: {
    command: "pnpm dev",
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
