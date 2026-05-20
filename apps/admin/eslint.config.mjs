import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Workspace packages have their own lint setup (or none). The
    // admin's eslint config doesn't apply to them — keep concerns
    // separate. CI builds them via ``pnpm build:packages`` before
    // typecheck, so any TS errors still surface there.
    "packages/**",
  ]),
]);

export default eslintConfig;
