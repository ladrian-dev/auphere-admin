/**
 * Spec 010, T004 — la suite de unidad de la aplicación de escritorio.
 *
 * Hasta ahora `vitest` corría sin configuración y recogía todo lo que casara con
 * el patrón por defecto. Con la spec 010 entran dos suites que **no** son de
 * unidad y que ejecuta Playwright —el humo del binario y la revisión de
 * accesibilidad—, y sus ficheros viven dentro de `tests/`. Sin esta exclusión,
 * `pnpm --filter @nexus/desktop test` intentaría correrlos como si fueran tests
 * de vitest y se pondría rojo: justo el paso que ejecuta la tubería.
 *
 * Es el mismo error que ya rompió el despliegue dos veces —algo nuevo que en
 * local nadie corre entero—, así que se ataja en la configuración y no en la
 * memoria de quien lanza los comandos.
 */
import { createRequire } from "node:module";

import { defineConfig } from "vitest/config";

/** La misma constante que inyecta `vite.app.config.ts`: sin ella, cualquier
 *  test que monte un componente que nombre la versión se rompe al importarlo. */
const { version } = createRequire(import.meta.url)("./package.json") as { version: string };

export default defineConfig({
  define: { __APP_VERSION__: JSON.stringify(version) },
  test: {
    include: ["tests/**/*.test.{ts,tsx}"],
    exclude: ["node_modules/**", "dist/**", "release/**", "tests/smoke/**", "tests/a11y/**"],
  },
});
