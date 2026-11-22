import { expect, test, type Page } from "@playwright/test";

import { expectLongGermanFits, expectNoOverflow, expectNoSeriousAxe, expectReachableByTab, expectSolidFloatingLayer, preferLessGlassAndMotion } from "./fabrica-audit";

/**
 * Spec 047 (T168, T176 y T162) — la consola lite de Marta, del negocio, en un
 * navegador de verdad: «Agentes» (pausar con la cifra de conversaciones,
 * reanudar, la pausa del sistema explicada), «Negocio» (precio sin nombre,
 * horario con `If-Match` e `Idempotency-Key`, «Deshacer») y «Corregir esta
 * respuesta» en la Bandeja (el tipo antes de enviar, los datos personales que
 * bloquean, deshacer un dato). Cada pantalla: axe, 390 px, 200 %, teclado,
 * «Reducir transparencia/movimiento», sus estados y textos largos en alemán.
 *
 * Spec 056 (requisito 2, decisión D2 del owner) sacó Agentes y Negocio de la
 * consola del cliente: pausar agentes y números y editar la ficha pasaron a ser
 * del partner (lo cubren `agent-life.e2e.ts` y las suites de la ficha). Desde la
 * spec 074 (4.1) esta suite comprueba lo nuevo: la barra no los trae aunque la
 * API los mande, y `/agentes` o `/negocio` dan la 404 dentro de su consola, que
 * lleva a su primer módulo (2.1, 2.4 y 14).
 *
 *   pnpm exec playwright test -c e2e/fabrica.config.ts --project=lite
 *
 * Contra `fabrica-mock.mjs`.
 */

const API = "http://127.0.0.1:8719";
const RECEPCION = "00000000-0000-4000-8000-0000000000a1";
const CONV = "00000000-0000-4000-8000-000000000c01";

async function mode(page: Page, parts: Record<string, string>) {
  await page.request.post(`${API}/__test/mode`, { data: parts });
}

async function state(page: Page) {
  return (await (await page.request.get(`${API}/__test/state`)).json()) as {
    pauses: { agent: string; confirm: boolean }[];
    keys: { section: string; key: string | null }[];
    corrections: { kind: string; status: string; lesson: string; scope: string }[];
  };
}

async function open(page: Page, path: string, heading: string | RegExp) {
  const res = await page.goto(path);
  expect(res?.status(), `${path} respondió ${res?.status()}`).toBeLessThan(400);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
}

test.describe("Spec 047 — la consola lite: su barra, sin Agentes ni Negocio (056), y corregir respuestas", () => {
  test.beforeEach(async ({ page }) => {
    await page.request.post(`${API}/__test/reset`);
    await page.setViewportSize({ width: 1280, height: 900 });
  });

  // Spec 056 (requisito 2): Agentes y Negocio salen de la consola del cliente.
  // La simulada sigue mandando `agents` y `business` en `modules`, como un
  // acceso que los tenía guardados: la consola no los pinta ni los abre (2.1).
  test("la barra lateral trae los módulos del cliente en el orden de la API, sin Agentes ni Negocio", async ({ page }) => {
    await open(page, "/inbox", /Bandeja/);
    const links = page.getByRole("link", { name: /^(Panel|Bandeja de entrada|Agentes|Negocio|Consumo)$/ });
    await expect(links.first()).toBeVisible();
    const names = (await links.allTextContents()).map((s) => s.trim()).filter(Boolean);
    expect(names).toEqual(["Panel", "Bandeja de entrada", "Consumo"]);
  });

  for (const [what, paths] of [
    ["Agentes", ["/agentes", `/agentes/${RECEPCION}`]],
    ["Negocio", ["/negocio"]],
  ] as const) {
    test(`${what} ya no es del cliente: su dirección da la 404 dentro de su consola y lleva a su primer módulo`, async ({ page }) => {
      for (const path of paths) {
        const res = await page.goto(path);
        expect(res?.status(), `${path} respondió ${res?.status()}`).toBe(404);
        await expect(page.getByRole("heading", { level: 1, name: "Esta página no está" })).toBeVisible();
        // No dice si lo pedido existe, y sale con su menú (el marco del cliente).
        await expect(page.getByText("No existe o no es tuya.")).toBeVisible();
        await expect(page.getByRole("link", { name: "Bandeja de entrada", exact: true })).toBeVisible();
        await expect(page.getByRole("link", { name: what, exact: true })).toHaveCount(0);
        // Nada de lo que era de Agentes o Negocio, ni de lo que es del partner (50.3).
        await expect(page.getByRole("button", { name: /Pausar|Reanudar|Archivar|Publicar|Nuevo agente|Pedir saldo|Guardar horario|Deshacer/ })).toHaveCount(0);
        await expect(page.getByRole("link", { name: "Ir al inicio" })).toHaveAttribute("href", "/");
      }
      await expectNoSeriousAxe(page, `${what} · 404`);
      await expectNoOverflow(page, `${what} · 404`);

      // Con el teclado, «Ir al inicio» lleva a su primer módulo.
      await expectReachableByTab(page, page.getByRole("link", { name: "Ir al inicio" }));
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(/\/$/);
      await expect(page.getByRole("link", { name: "Panel", exact: true })).toHaveAttribute("aria-current", "page");
      // La consola del cliente no pidió nada de Agentes ni Negocio, ni pausó nada.
      expect((await state(page)).pauses).toEqual([]);
      expect((await state(page)).keys).toEqual([]);

      await page.goto(paths[0]);
      await expect(page.getByRole("heading", { level: 1, name: "Esta página no está" })).toBeVisible();
      await expectLongGermanFits(page, `${what} · 404`);
    });
  }

  test("Bandeja: «Corregir esta respuesta» — comportamiento con datos personales que bloquean, y un dato que se deshace", async ({ page }) => {
    await page.goto(`/inbox?c=${CONV}`);
    await expect(page.getByRole("log").getByText("No tenemos aparcamiento, lo siento.")).toBeVisible();
    const correct = page.getByRole("button", { name: "Corregir esta respuesta" });
    await expect(correct).toHaveCount(1);
    await correct.click();
    let dialog = page.getByRole("dialog", { name: "Corregir esta respuesta" });
    await expect(dialog).toBeVisible();
    await expectNoSeriousAxe(page, "corregir · escribir");
    await dialog.getByRole("textbox", { name: /Cómo debió responder/ }).fill("No des citas los festivos, llama a Ana al +34 600 11 22 33");
    await dialog.getByRole("radio", { name: /Solo este agente/ }).check();
    await dialog.getByRole("button", { name: "Continuar" }).click();
    await expect(dialog.getByText("Es un comportamiento")).toBeVisible();
    const pii = dialog.locator("[data-slot=correction-pii]");
    await expect(pii.getByText("Un teléfono en tu corrección: «+34 600 11 22 33»")).toBeVisible();
    await expect(pii.getByText("Un nombre en tu corrección: «Ana»")).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Enviar la propuesta" })).toBeDisabled();
    await expectNoSeriousAxe(page, "corregir · datos personales");
    await dialog.getByRole("textbox", { name: "Tu corrección" }).fill("No des citas los festivos");
    await dialog.getByRole("button", { name: "Enviar la propuesta" }).click();
    await expect(dialog.getByText(/Quien gestiona tus agentes lo verá en las mejoras del agente/)).toBeVisible();
    await dialog.locator("[data-slot=correction-done]").getByRole("button", { name: "Cerrar" }).click();
    await expect(dialog).toBeHidden();

    await correct.click();
    dialog = page.getByRole("dialog", { name: "Corregir esta respuesta" });
    await dialog.getByRole("textbox", { name: /Cómo debió responder/ }).fill("El aparcamiento más cercano está en la calle de atrás");
    await dialog.getByRole("radio", { name: /Todo el negocio/ }).check();
    await dialog.getByRole("button", { name: "Continuar" }).click();
    await expect(dialog.getByText("Es un dato")).toBeVisible();
    await expect(dialog.getByRole("textbox", { name: /Lo que preguntó el cliente/ })).toHaveValue("¿Hay aparcamiento cerca del local?");
    await dialog.getByRole("button", { name: "Guardar el dato" }).click();
    await expect(dialog.getByText("Hecho. Recepción lo sabe desde el siguiente mensaje.")).toBeVisible();
    await dialog.getByRole("button", { name: "Deshacer" }).click();
    await expect(dialog.getByText("Deshecho. El agente vuelve a responder como antes.")).toBeVisible();
    // Escape cierra el modal (47.5).
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();

    const sent = (await state(page)).corrections.map((c) => [c.kind, c.status, c.scope, c.lesson]);
    expect(sent).toEqual([
      ["behavior", "proposed", "agent", "No des citas los festivos"],
      ["data", "undone", "business", "El aparcamiento más cercano está en la calle de atrás"],
    ]);
  });

  test("Bandeja: la vista en vivo dice «Reconectando…» si se cae el directo", async ({ page }) => {
    await mode(page, { stream: "down" });
    await page.goto(`/inbox?c=${CONV}`);
    await expect(page.getByText("Reconectando…")).toBeVisible();
    await expect(page.getByRole("log").getByText("No tenemos aparcamiento, lo siento.")).toBeVisible();
  });

  test("«Reducir transparencia» y «Reducir movimiento»: el menú flotante pasa a sólido y sin animación", async ({ page }) => {
    await preferLessGlassAndMotion(page);
    await open(page, "/inbox", /Bandeja/);
    await expectSolidFloatingLayer(page, () => page.getByRole("button", { name: "marta@cultor.example" }).click());
    await expectNoSeriousAxe(page, "/inbox sin vidrio");
  });
});
