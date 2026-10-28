import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { overflowOffenders } from "./audit";

/**
 * Spec 047, historia 7 (T081) — crear un agente describiéndolo, en un navegador
 * de verdad: la pestaña Agentes vacía, «Nuevo agente», un ejemplo, «Generar
 * borrador», los bloques que llegan en orden, una pregunta respondida (con
 * dónde se guarda) y la pantalla del agente, donde editar un bloque deja las
 * pruebas sin ejecutar. axe en cada pantalla y 390 px sin desbordar.
 *
 *   pnpm exec playwright test -c e2e/builder.config.ts
 *
 * Contra `builder-mock.mjs`: el trabajo suelta tres bloques por consulta.
 */

const API = "http://127.0.0.1:8714";
const REF = "barberia-cultor";
const AGENT = "00000000-0000-4000-8000-0000000000b1";

async function expectNoSeriousAxe(page: Page) {
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
    .exclude("iframe")
    .analyze();
  const blocking = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}

async function noOverflowAt(page: Page, width: number) {
  await page.setViewportSize({ width, height: 844 });
  await page.waitForTimeout(200);
  expect(await overflowOffenders(page), `@${width}px se desborda`).toEqual([]);
}

const blockOrder = (page: Page) => page.locator("[data-slot=builder-blocks] [data-block]").evaluateAll((els) => els.map((el) => el.getAttribute("data-block")));

/** Del vacío de la pestaña Agentes al borrador con sus preguntas. */
async function describeAndGenerate(page: Page) {
  const res = await page.goto(`/clients/${REF}/agents`);
  expect(res?.status()).toBeLessThan(400);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await expect(page.getByText("Este cliente aún no tiene agentes")).toBeVisible();
  await page.getByRole("link", { name: "Nuevo agente" }).click();
  await expect(page).toHaveURL(new RegExp(`/clients/${REF}/agents/new$`));
  await expect(page.getByRole("heading", { level: 2, name: "Nuevo agente" })).toBeVisible();
  await page.waitForLoadState("networkidle").catch(() => undefined);

  await page.getByRole("textbox", { name: /Nombre/ }).fill("Recepción");
  await page.getByRole("button", { name: /Atiende las citas de la barbería/ }).click();
  await expect(page.getByRole("textbox", { name: /¿Qué tiene que hacer\?/ })).toHaveValue(/Atiende las citas de la barbería/);
  await expectNoSeriousAxe(page);

  await page.getByRole("button", { name: "Generar borrador" }).click();
  // Los bloques llegan en orden: primero «Qué hace», y nunca uno antes que otro anterior.
  await expect(page.getByRole("heading", { level: 4, name: "Qué hace" })).toBeVisible();
  const first = await blockOrder(page);
  expect(first[0]).toBe("identity");
  await expect(page.getByRole("form", { name: "Lo que falta para terminarlo" })).toBeVisible({ timeout: 30_000 });
  expect(await blockOrder(page)).toEqual(["identity", "voice", "instructions", "procedures", "services", "skills", "escalation", "rules", "tests", "questions"]);
}

test.describe("Spec 047 — crear un agente describiéndolo", () => {
  test.beforeEach(async ({ request, page }) => {
    await request.post(`${API}/__test/reset`);
    await page.setViewportSize({ width: 1280, height: 900 });
  });

  test("describir → bloques → responder una pregunta → la pantalla del agente", async ({ page, request }) => {
    await describeAndGenerate(page);

    // «Conectar AgendaPro» en la fila de su habilidad (17.6).
    const connect = page.getByRole("link", { name: "Conectar AgendaPro" });
    await expect(connect).toBeVisible();
    await expect(connect).toHaveAttribute("href", `/clients/${REF}/integrations`);
    // Las descartadas, con su porqué (17.4).
    await expect(page.getByText("Se descartaron 2 preguntas:")).toBeVisible();

    // Cada pregunta dice dónde se guarda (17.5).
    const business = page.locator("[data-question=cancelacion]");
    await expect(business.getByText("Se guarda en la ficha: lo usarán todos sus agentes.")).toBeVisible();
    await expect(page.locator("[data-question=trato]").getByText("Se guarda solo en este agente.")).toBeVisible();
    await expectNoSeriousAxe(page);

    await business.getByRole("radio", { name: "24 horas antes" }).check();
    await page.getByRole("button", { name: "Guardar respuestas" }).click();

    await expect(page).toHaveURL(new RegExp(`/clients/${REF}/agents/${AGENT}$`));
    await expect(page.getByRole("heading", { level: 2, name: "Recepción" })).toBeVisible();
    const sent = await (await request.get(`${API}/__test/state`)).json();
    expect(sent.answers).toEqual([{ question_id: "cancelacion", value: "24 horas antes", scope: "business" }]);

    // La pantalla del agente: sus bloques y las pruebas sin ejecutar tras responder.
    await expect(page.locator("[data-slot=builder-tests]")).toContainText("8 pruebas");
    await expect(page.locator("[data-slot=builder-tests]")).toContainText("8 sin ejecutar");
    await page.waitForLoadState("networkidle").catch(() => undefined);
    // El aviso «Respuestas guardadas.» entra con un fundido: axe mediría el
    // contraste a medio camino. Se mira la pantalla cuando ya se fue.
    await expect(page.getByText("Respuestas guardadas.")).toHaveCount(0, { timeout: 15_000 });
    await expectNoSeriousAxe(page);

    // Editar un bloque en línea y guardarlo con la revisión leída.
    const rules = page.locator("[data-block=rules]");
    await rules.getByRole("button", { name: "Editar «Reglas»" }).click();
    const form = page.getByRole("form", { name: "Editar «Reglas»" });
    await form.getByRole("button", { name: "Añadir regla" }).click();
    await form.getByRole("textbox", { name: "Regla 2" }).fill("No des precios por teléfono");
    await form.getByRole("button", { name: "Guardar" }).click();
    await expect(form).toHaveCount(0);
    await expect(rules.getByText("No des precios por teléfono")).toBeVisible();
    const after = await (await request.get(`${API}/__test/state`)).json();
    expect(after.spec.rules).toEqual(["No ofrezcas descuentos", "No des precios por teléfono"]);
  });

  test("a 390 px nada se desborda: «Nuevo agente» con su borrador y la pantalla del agente", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await describeAndGenerate(page);
    await noOverflowAt(page, 390);

    await page.getByRole("button", { name: "Seguir sin responder" }).click();
    await expect(page).toHaveURL(new RegExp(`/clients/${REF}/agents/${AGENT}$`));
    await expect(page.getByRole("heading", { level: 2, name: "Recepción" })).toBeVisible();
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await noOverflowAt(page, 390);
    await page.locator("[data-block=instructions]").getByRole("button", { name: "Editar «Instrucciones»" }).click();
    await noOverflowAt(page, 390);
    await expectNoSeriousAxe(page);
  });
});
