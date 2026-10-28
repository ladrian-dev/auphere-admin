import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { overflowOffenders } from "./audit";

/**
 * Spec 047, historias 8 y 9 (T089 y T094) — probar y guardar un agente en un
 * navegador de verdad: el probador (burbujas, «Lo que habría hecho», la hora y
 * la agenda simuladas), ejecutar las pruebas con su «Por qué falló» y «No
 * aplica», la revisión, «Guardar cambios» con el diff, la puerta que un owner
 * salta con el motivo, «Deshacer» y «Restaurar». axe y 390 px sin desbordar.
 *
 *   pnpm exec playwright test -c e2e/agent-quality.config.ts
 *
 * Contra `agent-quality-mock.mjs`: los trabajos terminan a la segunda consulta.
 */

const API = "http://127.0.0.1:8715";
const PAGE = "/clients/barberia-cultor/agents/00000000-0000-4000-8000-0000000000b1";

async function expectNoSeriousAxe(page: Page) {
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
    .exclude("iframe")
    .analyze();
  const blocking = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}

async function open(page: Page) {
  const res = await page.goto(PAGE);
  expect(res?.status(), `${PAGE} respondió ${res?.status()}`).toBeLessThan(400);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await expect(page.getByRole("heading", { level: 2, name: "Recepción" })).toBeVisible();
}

const section = (page: Page, name: string) => page.locator("section").filter({ has: page.getByRole("heading", { level: 3, name, exact: true }) });

test.describe("Spec 047 — probar y guardar un agente", () => {
  test.beforeEach(async ({ request, page }) => {
    await request.post(`${API}/__test/reset`);
    await page.setViewportSize({ width: 1280, height: 900 });
  });

  test("el probador: burbujas, «Lo que habría hecho», la agenda que cambia y la hora", async ({ page }) => {
    await open(page);
    const tester = page.locator("[data-slot=agent-playground]");
    await tester.getByRole("button", { name: "Empezar una conversación" }).click();
    await expect(tester.getByText("Probando el borrador v2")).toBeVisible();
    await tester.getByRole("textbox", { name: "Mensaje del cliente" }).fill("quiero reservar mañana a las 11");
    await tester.getByRole("button", { name: "Enviar" }).click();
    const chat = tester.getByRole("list", { name: "Conversación de prueba" });
    await expect(chat.getByText("¡Claro! Mañana a las 11 tengo hueco para un corte.")).toBeVisible();
    await expect(chat.getByText("Respondió en 2 mensajes seguidos")).toBeVisible();
    await expect(chat.getByText("Lo que habría hecho: crear cita de Corte el 28/10/2026 a las 11:00")).toBeVisible();
    await expect(tester.getByText("Corte · 28/10/2026 a las 11:00")).toBeVisible();
    await expect(tester.locator("[data-slot=playground-now]")).toContainText("11:20");

    await tester.getByRole("button", { name: "Cambiar la hora" }).click();
    await tester.getByLabel("Nueva hora simulada").fill("2026-11-01T20:30");
    await tester.getByRole("button", { name: "Usar esta hora" }).click();
    await expect(tester.locator("[data-slot=playground-now]")).toContainText("20:30");
    await expect(page.getByText("Hora simulada cambiada.")).toHaveCount(0, { timeout: 15_000 });
    await expectNoSeriousAxe(page);
  });

  test("las pruebas y la revisión: ejecutar, «Por qué falló», «No aplica» y los hallazgos", async ({ page, request }) => {
    await open(page);
    const tests = section(page, "Pruebas");
    await expect(tests.getByText("El juez aún no decide: solo cuenta el estado final.")).toBeVisible();
    await tests.getByRole("button", { name: "Ejecutar todas" }).click();
    const failing = tests.getByRole("listitem", { name: "Reserva una cita" });
    await expect(failing.getByText("Falla")).toBeVisible({ timeout: 20_000 });
    await expect(tests.getByRole("listitem", { name: "Pide un descuento" }).getByText("Inestable")).toBeVisible();
    await failing.getByText("Por qué falló").click();
    await expect(failing.getByText(/La cita no existe en la agenda al terminar/)).toBeVisible();

    const parking = tests.getByRole("listitem", { name: "Pregunta por aparcamiento" });
    await parking.getByRole("button", { name: "Marcar Pregunta por aparcamiento como «No aplica»" }).click();
    await parking.getByRole("textbox", { name: /Por qué no aplica/ }).fill("Es una barbería a domicilio");
    await parking.getByRole("button", { name: "Guardar la razón" }).click();
    await expect(parking.getByText("No aplica: Es una barbería a domicilio")).toBeVisible();
    const sent = await (await request.get(`${API}/__test/state`)).json();
    expect(Object.values(sent.notApplicable)).toEqual(["Es una barbería a domicilio"]);

    // «Arreglar» abre las instrucciones del borrador.
    await failing.getByRole("button", { name: "Arreglar Reserva una cita en las instrucciones" }).click();
    await expect(page.getByRole("form", { name: "Editar «Instrucciones»" })).toBeVisible();
    await page.getByRole("form", { name: "Editar «Instrucciones»" }).getByRole("button", { name: "Cancelar" }).click();

    const review = section(page, "Revisión");
    await expect(review.getByText("Contradice la ficha: horario del domingo.")).toBeVisible();
    await expect(review.getByRole("link", { name: "Ir a Conectores" })).toHaveAttribute("href", "/clients/barberia-cultor/integrations");
    await expect(review.locator("[data-slot=review-check][data-ok=true]")).toHaveCount(6);
    await page.waitForTimeout(500);
    await expect(page.locator("[data-sonner-toast]")).toHaveCount(0, { timeout: 15_000 });
    await expectNoSeriousAxe(page);
  });

  test("«Guardar cambios»: el diff, la puerta saltada con el motivo, «Deshacer» y «Restaurar»", async ({ page, request }) => {
    await open(page);
    await page.getByRole("button", { name: "Guardar cambios" }).click();
    const sheet = page.getByRole("dialog", { name: "Qué cambia al guardar" });
    await expect(sheet.getByText("+ Reglas")).toBeVisible();
    await expect(sheet.getByText("~ Instrucciones")).toBeVisible();
    await sheet.getByRole("textbox", { name: /Nota del cambio/ }).fill("Lista de espera");
    await sheet.getByRole("button", { name: "Guardar cambios" }).click();

    const gate = page.locator("[data-slot=publish-gate]");
    await expect(page.getByText("No se guardó: no pasa la puerta")).toBeVisible({ timeout: 20_000 });
    await expect(gate.getByText("La prueba crítica «Reserva una cita» no pasa 3 de 3.")).toBeVisible();
    await expectNoSeriousAxe(page);
    await page.getByRole("button", { name: "Guardar igualmente…" }).click();
    const dialog = page.getByRole("dialog", { name: "Guardar saltando la puerta" });
    await dialog.getByRole("textbox", { name: /Motivo/ }).fill("AgendaPro se conecta mañana a primera hora");
    await dialog.getByRole("button", { name: "Guardar con este motivo" }).click();

    const toast = page.locator("[data-sonner-toast]").filter({ hasText: "Guardado como v2" });
    await expect(toast).toBeVisible({ timeout: 20_000 });
    const sent = await (await request.get(`${API}/__test/state`)).json();
    expect(sent.publishes).toEqual([
      { note: "Lista de espera" },
      { note: "Lista de espera", override_reason: "AgendaPro se conecta mañana a primera hora", accept_normal_failures: true },
    ]);
    await expect(page.getByText("No hay cambios sin guardar.")).toBeVisible();
    const history = section(page, "Historial");
    await expect(history.getByRole("listitem", { name: "v2" }).getByText(/Guardada saltando la puerta/)).toBeVisible();

    await toast.getByRole("button", { name: "Deshacer" }).click();
    await expect(page.getByText("Deshecho: vuelve a atender la v1.")).toBeVisible();
    await expect(history.getByRole("listitem", { name: "v1" }).getByText("Atiende ahora")).toBeVisible();

    await history.getByRole("listitem", { name: "v2" }).getByRole("button", { name: "Restaurar la v2" }).click();
    const confirm = page.getByRole("dialog", { name: "¿Restaurar la v2?" });
    await confirm.getByRole("button", { name: "Restaurar" }).click();
    await expect(page.getByText("Borrador nuevo con la v2. Guárdalo para que atienda.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Guardar cambios" })).toBeVisible();
    expect((await (await request.get(`${API}/__test/state`)).json()).restored).toEqual([2]);
  });

  test("a 390 px nada se desborda y pasa axe", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await open(page);
    const tester = page.locator("[data-slot=agent-playground]");
    await tester.getByRole("button", { name: "Empezar una conversación" }).click();
    await tester.getByRole("textbox", { name: "Mensaje del cliente" }).fill("quiero reservar mañana a las 11");
    await tester.getByRole("button", { name: "Enviar" }).click();
    await expect(tester.getByText("Respondió en 2 mensajes seguidos")).toBeVisible();
    await section(page, "Pruebas").getByRole("button", { name: "Ejecutar todas" }).click();
    await expect(section(page, "Pruebas").getByRole("listitem", { name: "Reserva una cita" }).getByText("Falla")).toBeVisible({ timeout: 20_000 });
    await page.waitForTimeout(300);
    expect(await overflowOffenders(page), "@390px se desborda").toEqual([]);
    await expect(page.locator("[data-sonner-toast]")).toHaveCount(0, { timeout: 15_000 });
    await expectNoSeriousAxe(page);
  });
});
