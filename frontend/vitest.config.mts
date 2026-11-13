import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    tsconfigPaths: true, // the "@/*" alias from tsconfig.json
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["**/*.test.{ts,tsx}"],
    // **The `e2e/` directory is excluded explicitly, even though its files are `*.spec.ts`
    // and the include pattern does not match them.** The two suites have different
    // requirements — Playwright needs a running stack and a seeded database, and Vitest
    // needs neither — and a file renamed to `*.test.ts` would otherwise be picked up by
    // the wrong runner and fail for reasons that have nothing to do with the test.
    exclude: ["node_modules/**", ".next/**", "e2e/**"],
  },
});
