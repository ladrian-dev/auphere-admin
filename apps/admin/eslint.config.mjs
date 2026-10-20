import nexusUi from "@nexus/ui/eslint";
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

// Spec 031: the same rules as the console — no raw colours, no values off the
// spacing scale, only the radii the tokens define.
export default defineConfig([
  ...nextVitals,
  ...nextTs,
  nexusUi.configs.recommended,
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // The ucm-* packages have their own setup; CI builds them before typecheck.
    "packages/**",
  ]),
]);
