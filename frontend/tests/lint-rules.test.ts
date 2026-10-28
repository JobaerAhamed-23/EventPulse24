// @vitest-environment node
/** AD-19 lint rules fire: page code can't fetch the backend or use openapi-fetch directly. */
import path from "node:path";

import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");
const eslint = new ESLint({ cwd: ROOT });

async function ruleIds(code: string, file: string): Promise<string[]> {
  const [result] = await eslint.lintText(code, { filePath: path.join(ROOT, file) });
  return result.messages.map((message) => message.ruleId ?? "parse-error");
}

describe("backend access rules (AD-19)", () => {
  it.each([
    ['await fetch("/api/health");', "no-restricted-globals"],
    ['await window.fetch("/api/health");', "no-restricted-properties"],
    ['await globalThis.fetch("/api/health");', "no-restricted-properties"],
    ['await self.fetch("/api/health");', "no-restricted-properties"],
    [
      'import createClient from "openapi-fetch";\nexport const c = createClient;',
      "no-restricted-imports",
    ],
  ])(
    "rejects %s in app/",
    async (statement, rule) => {
      const code = statement.startsWith("import")
        ? statement
        : `export async function load() {\n  ${statement}\n}\n`;

      expect(await ruleIds(code, "app/planted.tsx")).toContain(rule);
    },
    30_000,
  );

  it("allows openapi-fetch in lib/backend-client.ts", async () => {
    const code = 'import createClient from "openapi-fetch";\nexport const c = createClient;\n';

    expect(await ruleIds(code, "lib/backend-client.ts")).not.toContain("no-restricted-imports");
  }, 30_000);

  it("allows the generated client in page code", async () => {
    const code =
      'import { api } from "@/lib/backend-client";\n' +
      'export async function load() {\n  return api.GET("/api/health");\n}\n';

    expect(await ruleIds(code, "app/planted.tsx")).toEqual([]);
  }, 30_000);
});
