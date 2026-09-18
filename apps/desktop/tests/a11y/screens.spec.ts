/**
 * Criterio de éxito CE-005 — **cero incidencias graves o críticas** en la
 * revisión automática de accesibilidad de cada pantalla.
 *
 * Se pasa sobre la pantalla **ya construida**, dentro de Electron, con el mismo
 * `preload` y la misma política de contenido que en producción. Hacerlo sobre
 * componentes sueltos en jsdom mediría otra cosa: el contraste real depende de
 * los tokens resueltos, y el orden de foco, del árbol entero.
 *
 * Qué se exige y qué no, dicho a las claras: `serious` y `critical` bloquean.
 * `moderate` y `minor` se registran y no bloquean — axe los emite también para
 * patrones discutibles, y un umbral que nadie puede mantener se acaba apagando
 * entero, que es peor que uno estricto en lo que importa.
 *
 * Los dos temas, porque el contraste cambia con cada uno y la aplicación sigue
 * al del sistema. `packages/ui` ya comprueba los pares declarados con su propio
 * test; esto comprueba lo que de verdad se pinta.
 */
import { existsSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test } from "@playwright/test";
import type { ElectronApplication, Page } from "@playwright/test";
import type { AxeResults } from "axe-core";

const HERE = dirname(fileURLToPath(import.meta.url));
const HARNESS = join(HERE, "..", "smoke", "harness.cjs");
/**
 * La fuente de axe, que se **inyecta en la página**.
 *
 * `@axe-core/playwright` no sirve aquí: para manejar marcos abre una pestaña
 * nueva, y Electron responde «Target.createTarget: Not supported». Inyectar el
 * script y llamarlo es lo que la propia documentación de axe recomienda para
 * entornos que no son un navegador normal — y de paso evita el envoltorio que
 * arrastra un par de `playwright-core`, que ya rompió el typecheck de la
 * consola una vez.
 */
const AXE = createRequire(import.meta.url).resolve("axe-core/axe.min.js");
const BUILT = join(HERE, "..", "..", "dist", "app", "index.html");

let app: ElectronApplication;
let window: Page;

test.beforeAll(async () => {
  expect(existsSync(BUILT), `falta ${BUILT}: ejecuta \`pnpm --filter @nexus/desktop build\``).toBe(true);
  app = await electron.launch({ args: [HARNESS] });
  window = await app.firstWindow();
  await window.waitForLoadState("domcontentloaded");
  await window.waitForSelector("#root *");
});

test.afterAll(async () => {
  await app?.close();
});

/** Lo que bloquea. Lo demás se registra para poder mirarlo. */
const BLOQUEAN = new Set(["serious", "critical"]);

async function revisar(tema: "light" | "dark") {
  await window.emulateMedia({ colorScheme: tema });
  // Que el tema haya llegado a pintarse antes de medir el contraste.
  await window.waitForTimeout(150);
  await window.evaluate(readFileSync(AXE, "utf8"));
  const results = (await window.evaluate(async () =>
    // @ts-expect-error `axe` lo acaba de inyectar la línea de arriba.
    (await window.axe.run(document, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
    })) as unknown,
  )) as AxeResults;
  return results.violations;
}

for (const tema of ["light", "dark"] as const) {
  test(`sin incidencias graves ni críticas en tema ${tema}`, async () => {
    const violations = await revisar(tema);
    const graves = violations.filter((v) => BLOQUEAN.has(v.impact ?? ""));
    const detalle = graves
      .map((v) => `${v.impact} · ${v.id}: ${v.help}\n  ${v.nodes.map((n) => n.target.join(" ")).join("\n  ")}`)
      .join("\n");
    expect(graves, `incidencias que bloquean en tema ${tema}:\n${detalle}`).toHaveLength(0);
  });

  test(`y lo leve queda anotado, no escondido, en tema ${tema}`, async () => {
    const violations = await revisar(tema);
    const leves = violations.filter((v) => !BLOQUEAN.has(v.impact ?? ""));
    // No bloquea: se imprime para que exista y se pueda decidir sobre ello.
    if (leves.length > 0) {
      console.log(`[a11y ${tema}] ${leves.length} leve(s):`);
      for (const v of leves) console.log(`  ${v.impact} · ${v.id}: ${v.help}`);
    }
    expect(Array.isArray(leves)).toBe(true);
  });
}
