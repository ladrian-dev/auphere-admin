import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { overflowOffenders } from "./audit";

/**
 * Spec 047, historia 7 (T081) — crear un agente describiéndolo, en un navegador
 * de verdad: la pestaña Agentes vacía, «Nuevo agente», un ejemplo, «Generar
 * borrador», los cuatro pasos que siguen al trabajo, y la pantalla del agente
 * con las preguntas que faltan encima de su tabla (prototipo `agente.md` §3.2 y
 * §3.3): se responden una a una y en el sitio, y editar un bloque deja las
 * pruebas sin ejecutar. axe en cada pantalla y 390 px sin desbordar.
 *
 *   pnpm exec playwright test -c e2e/builder.config.ts
 *
 * Contra `builder-mock.mjs`: el trabajo suelta tres bloques por consulta.
 */

const API = "http://127.0.0.1:8714";
const REF = "barberia-cultor";
const AGENT = "00000000-0000-4000-8000-0000000000b1";
const JOB = "00000000-0000-4000-8000-0000000000c1";

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

const steps = (page: Page) => page.getByRole("region", { name: "Cómo va el borrador" }).getByRole("listitem");
const stepStates = (page: Page) => steps(page).evaluateAll((els) => els.map((el) => el.getAttribute("data-state")).join(","));
/** Hechos, uno en curso y pendientes, en ese orden: nunca un paso antes que otro anterior. */
const IN_ORDER = /^(done,)*active(,wait)*$/;

/** Del vacío de la pestaña Agentes a la pantalla del agente con sus preguntas. */
async function describeAndGenerate(page: Page, check?: () => Promise<void>) {
  const res = await page.goto(`/clients/${REF}/agents`);
  expect(res?.status()).toBeLessThan(400);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await expect(page.getByText("Este cliente aún no tiene agentes")).toBeVisible();
  await page.getByRole("link", { name: "Nuevo agente" }).first().click();
  await expect(page).toHaveURL(new RegExp(`/clients/${REF}/agents/new$`));
  await expect(page.getByRole("heading", { level: 1, name: "Nuevo agente" })).toBeVisible();
  await page.waitForLoadState("networkidle").catch(() => undefined);

  await page.getByRole("textbox", { name: /Nombre/ }).fill("Recepción");
  // Los ejemplos del prototipo (§3.1) se añaden a «¿Qué tiene que hacer?».
  await page.getByRole("button", { name: "Recepción y citas" }).click();
  await expect(page.getByRole("textbox", { name: /¿Qué tiene que hacer\?/ })).toHaveValue(/Atiende el WhatsApp del negocio/);
  await expectNoSeriousAxe(page);

  await page.getByRole("button", { name: "Generar borrador" }).click();
  // Los cuatro pasos siguen al trabajo de verdad (§3.2): primero se lee la ficha…
  await expect(steps(page)).toHaveCount(4);
  await expect(steps(page).nth(0)).toContainText("Leo la ficha de Barbería Cultor");
  await expect(steps(page).nth(0)).toHaveAttribute("data-state", "active");
  expect(await stepStates(page)).toBe("active,wait,wait,wait");
  // …y cuando llegan las pruebas del caso, el paso dice cuántas, sin saltarse ninguno.
  await expect(steps(page).nth(2)).toContainText("Escribo 8 pruebas del caso");
  expect(await stepStates(page)).toMatch(IN_ORDER);
  await check?.();

  // Con preguntas, la pantalla del agente se abre con su trabajo (`?job=`).
  await expect(page).toHaveURL(new RegExp(`/clients/${REF}/agents/${AGENT}\\?job=${JOB}$`), { timeout: 30_000 });
  await expect(page.getByRole("heading", { level: 1, name: "Recepción" })).toBeVisible();
  await page.waitForLoadState("networkidle").catch(() => undefined);
}

test.describe("Spec 047 — crear un agente describiéndolo", () => {
  test.beforeEach(async ({ request, page }) => {
    await request.post(`${API}/__test/reset`);
    await page.setViewportSize({ width: 1280, height: 900 });
  });

  test("describir → los pasos → responder una pregunta → la pantalla del agente", async ({ page, request }) => {
    await describeAndGenerate(page);

    // Las preguntas que faltan, encima de la tabla del agente (§3.3), con las descartadas y su porqué (17.4).
    const questions = page.getByRole("region", { name: "Me faltan 2 datos" });
    await expect(questions).toBeVisible();
    await expect(questions.getByText("Validé 4 preguntas posibles y descarté 2:")).toBeVisible();
    await expect(questions.getByText("Ya estaba en la ficha del negocio.")).toBeVisible();
    // Cada pregunta dice dónde se guarda (17.5).
    const business = page.locator("[data-question=cancelacion]");
    await expect(business.getByText("Se guarda en la ficha: lo usarán todos sus agentes.")).toBeVisible();
    await expect(page.locator("[data-question=trato]").getByText("Se guarda solo en este agente.")).toBeVisible();
    // «Conectar Google Calendar» en la fila de su habilidad (17.6).
    const can = page.getByRole("region", { name: "Qué puede hacer" });
    await expect(can.getByRole("listitem").filter({ hasText: "Mientras no esté conectada" }).getByRole("button", { name: "Conectar Google Calendar" })).toBeVisible();
    // Las pruebas que escribió, todavía sin ejecutar.
    // La primera, la de la cabecera (la otra está en «Más ajustes»).
    await expect(page.locator("[data-slot=builder-tests]").first()).toContainText("8 pruebas");
    await expect(page.getByRole("heading", { level: 2, name: "Pruebas · 8 sin ejecutar" })).toBeVisible();
    await expectNoSeriousAxe(page);

    // Elegir una opción la guarda al momento, con su `scope`, y queda respondida en el sitio.
    await business.getByRole("button", { name: "24 horas antes" }).click();
    await expect(page.getByRole("region", { name: "Me falta 1 dato" })).toBeVisible();
    await expect(business).toHaveAttribute("data-answered", "true");
    await expect(business).toContainText("24 horas antes · en la ficha del negocio");
    await expect
      .poll(async () => (await (await request.get(`${API}/__test/state`)).json()).answers)
      .toEqual([{ question_id: "cancelacion", value: "24 horas antes", scope: "business" }]);
    await expect(page).toHaveURL(new RegExp(`/clients/${REF}/agents/${AGENT}\\?job=${JOB}$`));
    await expectNoSeriousAxe(page);

    // Editar un bloque en línea y guardarlo con la revisión leída.
    await page.getByRole("button", { name: "Editar «Qué hace»" }).click();
    const rules = page.getByRole("region", { name: "Reglas" });
    await rules.getByRole("button", { name: "Editar «Reglas»" }).click();
    const form = page.getByRole("form", { name: "Editar «Reglas»" });
    await form.getByRole("button", { name: "Añadir regla" }).click();
    await form.getByRole("textbox", { name: "Regla 2" }).fill("No des precios por teléfono");
    await form.getByRole("button", { name: "Guardar" }).click();
    await expect(form).toHaveCount(0);
    // Guardado, la fila vuelve a su resumen, con la regla nueva dentro.
    const does = page.getByRole("region", { name: "Qué hace" });
    await expect(does).toContainText("1 sección de instrucciones · 2 reglas");
    await expect(does.getByRole("group")).toContainText("No des precios por teléfono");
    const after = await (await request.get(`${API}/__test/state`)).json();
    expect(after.spec.rules).toEqual(["No ofrezcas descuentos", "No des precios por teléfono"]);
    await expect(page.getByRole("heading", { level: 2, name: "Pruebas · 8 sin ejecutar" })).toBeVisible();

    // «Conectar Google Calendar» lleva a Conectores, aquí mismo (62.3).
    await can.getByRole("button", { name: "Conectar Google Calendar" }).click();
    await expect(page.getByRole("tab", { name: "Conectores" })).toHaveAttribute("aria-selected", "true");
  });

  test("a 390 px nada se desborda: «Nuevo agente», sus pasos y la pantalla del agente", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await describeAndGenerate(page, () => noOverflowAt(page, 390));
    await noOverflowAt(page, 390);
    await page.getByRole("button", { name: "Editar «Qué hace»" }).click();
    await page.getByRole("region", { name: "Instrucciones" }).getByRole("button", { name: "Editar «Instrucciones»" }).click();
    await expect(page.getByRole("form", { name: "Editar «Instrucciones»" })).toBeVisible();
    await noOverflowAt(page, 390);
    await expectNoSeriousAxe(page);
  });
});
