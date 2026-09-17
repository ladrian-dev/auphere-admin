/**
 * Requisitos 2.1 y 2.7 — el humo de la pantalla construida.
 *
 * Lo que este test comprueba **sólo se puede ver con el código compilado y
 * servido desde disco**, que es donde han aparecido los fallos que más han
 * dolido en esta aplicación: el actualizador que nunca arrancaba y el paquete
 * que se tragaba su propia salida no se reproducían en desarrollo.
 *
 * Tres afirmaciones:
 *
 * 1. la pantalla monta y pinta algo;
 * 2. la política de contenido **no bloquea nada de lo que la pantalla
 *    necesita** — si bloqueara las fuentes o el script, Chromium lo diría en
 *    consola y aquí se ve;
 * 3. las fuentes de marca **cargan desde el paquete**, sin red.
 *
 * El recorrido de la aplicación entera, empaquetada y firmada, es otro (T140).
 */
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test } from "@playwright/test";
import type { ElectronApplication, Page } from "@playwright/test";

const HERE = dirname(fileURLToPath(import.meta.url));
const HARNESS = join(HERE, "harness.cjs");
const BUILT = join(HERE, "..", "..", "dist", "app", "index.html");

let app: ElectronApplication;
let window: Page;
const consoleLines: string[] = [];

test.beforeAll(async () => {
  // Sin `pnpm build` no hay nada que ahumar, y decirlo es más útil que un
  // error de Playwright sobre un fichero que no existe.
  expect(existsSync(BUILT), `falta ${BUILT}: ejecuta \`pnpm --filter @nexus/desktop build\``).toBe(true);

  app = await electron.launch({ args: [HARNESS] });
  window = await app.firstWindow();
  window.on("console", (message) => consoleLines.push(`${message.type()} ${message.text()}`));
  await window.waitForLoadState("domcontentloaded");
});

test.afterAll(async () => {
  await app?.close();
});

test("la pantalla monta y pinta", async () => {
  await expect(window.locator("#root")).not.toBeEmpty();
});

test("la política de contenido no bloquea nada de lo que la pantalla usa", async () => {
  // Chromium escribe en consola una línea por recurso bloqueado. Si aparece
  // una sola, la política está mal puesta y la pantalla se ve rota.
  const bloqueado = consoleLines.filter((line) => /Content Security Policy/i.test(line));
  expect(bloqueado, `la política bloqueó:\n${bloqueado.join("\n")}`).toHaveLength(0);
});

test("las fuentes de marca cargan desde el paquete", async () => {
  const cargadas = await window.evaluate(async () => {
    await document.fonts.ready;
    // `check()` sólo dice que sí cuando la cara ya está cargada, y las fuentes
    // web se cargan cuando algo las usa. La monoespaciada puede no haberse
    // usado todavía en esta pantalla, así que se pide explícitamente: lo que
    // se comprueba es que **se puede** cargar desde el paquete.
    const [inter, mono] = await Promise.all([
      document.fonts.load('16px "Inter Tight Variable"'),
      document.fonts.load('16px "JetBrains Mono Variable"'),
    ]);
    return {
      interTight: inter.length > 0,
      mono: mono.length > 0,
      familiaDelCuerpo: getComputedStyle(document.body).fontFamily,
    };
  });

  expect(cargadas.interTight).toBe(true);
  expect(cargadas.mono).toBe(true);
  // Y la que de verdad se usa al pintar, que es lo que se veía mal: la misma
  // voz tipográfica que la consola, no la del sistema.
  expect(cargadas.familiaDelCuerpo).toContain("Inter Tight Variable");
});

test("no se pide nada a la red", async () => {
  const peticiones: string[] = [];
  window.on("request", (request) => peticiones.push(request.url()));
  await window.reload();
  await window.waitForLoadState("domcontentloaded");

  const remotas = peticiones.filter((url) => /^https?:/i.test(url));
  expect(remotas, `la pantalla pidió:\n${remotas.join("\n")}`).toHaveLength(0);
});
