import nexusUi from "@nexus/ui/eslint";
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  nexusUi.configs.recommended,
  // Lo que deja Playwright al correr: el informe HTML trae su propio bundle
  // minificado y son 3 000 avisos que tapan los de verdad. Están en
  // `.gitignore` desde siempre; faltaba decírselo también al linter, y solo
  // se nota cuando alguien corre el e2e antes que el lint.
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "drizzle/**",
    "e2e/.report/**",
    "test-results/**",
  ]),
]);
