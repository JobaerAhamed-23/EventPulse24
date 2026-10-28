import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import prettier from "eslint-config-prettier/flat";
import tseslint from "typescript-eslint";

// AD-19: frontend code reaches the backend only through the generated client.
const BACKEND_ACCESS = "Reach the backend through `api` from @/lib/backend-client (AD-19).";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // coding-standards: @typescript-eslint/strict on top of Next's TypeScript rules.
  ...tseslint.configs.strict,
  {
    files: ["app/**/*.{ts,tsx}", "components/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-globals": ["error", { name: "fetch", message: BACKEND_ACCESS }],
      "no-restricted-properties": [
        "error",
        { object: "window", property: "fetch", message: BACKEND_ACCESS },
        { object: "globalThis", property: "fetch", message: BACKEND_ACCESS },
        { object: "self", property: "fetch", message: BACKEND_ACCESS },
      ],
    },
  },
  {
    files: ["**/*.{ts,tsx,mts,mjs}"],
    ignores: ["lib/backend-client.ts"],
    rules: {
      "no-restricted-imports": [
        "error",
        { paths: [{ name: "openapi-fetch", message: BACKEND_ACCESS }] },
      ],
    },
  },
  // Last: turn off rules that would fight Prettier's formatting.
  prettier,
  globalIgnores([".next/**", "out/**", "build/**", "coverage/**", "next-env.d.ts", "lib/api/**"]),
]);

export default eslintConfig;
