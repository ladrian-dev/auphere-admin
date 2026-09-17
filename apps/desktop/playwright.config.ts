/**
 * Spec 010 — las dos suites que no son de unidad.
 *
 * `tests/smoke/` abre la pantalla ya construida dentro de Electron; `tests/a11y/`
 * pasa la revisión automática de accesibilidad. Las dos las ejecuta Playwright,
 * no vitest, y por eso `vitest.config.ts` las excluye: si se colaran en la suite
 * de unidad, el paso que corre la tubería se pondría rojo sin que nadie
 * entendiera por qué.
 */
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests",
  testMatch: ["smoke/**/*.spec.ts", "a11y/**/*.spec.ts"],
  // Electron abre una sola aplicación por fichero: en paralelo se pisan.
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  // Un fallo aquí casi siempre es un fallo de verdad, no un test inestable.
  retries: 0,
  timeout: 60_000,
});
