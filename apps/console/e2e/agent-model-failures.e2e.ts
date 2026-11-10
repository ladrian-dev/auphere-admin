import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { overflowOffenders } from "./audit";

/**
 * Bug `el-probador-tapa-los-fallos-del-modelo` en un navegador de verdad: el chat de
 * prueba, la tarjeta y la lista de pruebas y «Guardar» cuando ningún modelo responde.
 * Lo que las pruebas de componente no ven: que el aviso no quede debajo de una hoja
 * modal, ni se salga a 360 px.
 *
 *   pnpm exec playwright test -c e2e/agent-quality.config.ts e2e/agent-model-failures.e2e.ts
 *
 * Contra `agent-quality-mock.mjs`, con `POST /__test/model`.
 */

const API = "http://127.0.0.1:8715";
const PAGE = "/clients/barberia-cultor/agents/00000000-0000-4000-8000-0000000000b1";

async function open(page: Page) {
  const res = await page.goto(PAGE);
  expect(res?.status(), `${PAGE} respondió ${res?.status()}`).toBeLessThan(400);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.getByRole("tab", { name: "Configuración" }).click();
  await expect(page.locator("[data-slot=agent-playground]")).toBeVisible();
}

async function expectNoSeriousAxe(page: Page, scope: string) {
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
    .include(scope)
    .analyze();
  const blocking = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}

test.describe("Sin modelo", () => {
  test.beforeEach(async ({ request, page }) => {
    await request.post(`${API}/__test/reset`);
    await page.setViewportSize({ width: 1280, height: 900 });
  });

  test("el chat dice que el agente no llegó a contestar y conserva lo escrito", async ({ page, request }) => {
    await request.post(`${API}/__test/model`, { data: { mode: "down" } });
    await open(page);
    const chat = page.locator("[data-slot=agent-playground]");
    const box = chat.getByRole("textbox", { name: "Mensaje del cliente" });
    await box.fill("¿A qué hora abrís mañana?");
    await chat.getByRole("button", { name: "Enviar" }).click();

    const failure = chat.locator("[data-slot=playground-failure]");
    await expect(failure).toContainText("El modelo no respondió, así que el agente no llegó a contestar");
    await expect(chat.getByText(/Disculpa, tuve un inconveniente/)).toBeVisible();
    await expect(chat.getByRole("button", { name: "¿Por qué dijo esto?" })).toHaveCount(0);
    await expect(box).toHaveValue("¿A qué hora abrís mañana?");
    await expect(failure).toBeInViewport();
    await expect(chat.getByRole("list", { name: "Conversación de prueba" })).toHaveAttribute("tabindex", "0");
    await expectNoSeriousAxe(page, "[data-slot=agent-playground]");

    await page.setViewportSize({ width: 360, height: 800 });
    await page.waitForTimeout(150);
    expect(await overflowOffenders(page), "@360px se desborda").toEqual([]);
    await expectNoSeriousAxe(page, "[data-slot=agent-playground]");
  });

  test("las pruebas dicen que no se pudo probar y no ofrecen «Arreglar»", async ({ page, request }) => {
    await request.post(`${API}/__test/model`, { data: { mode: "down" } });
    await open(page);
    const box = page.locator("[data-slot=tests-box]");
    await box.getByRole("button", { name: "Ejecutar todas" }).click();
    await expect(box.getByRole("alert").first()).toContainText("No se pudo probar: ningún modelo respondió", { timeout: 30_000 });

    await page.reload();
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await page.getByRole("tab", { name: "Configuración" }).click();
    await expect(box.getByRole("alert").first()).toContainText("Sin probar porque el modelo no respondió: 5");
    await page.getByRole("button", { name: /Más ajustes/ }).first().click();
    const row = page.locator("[data-slot=test-row][data-status=model_failed]").first();
    await expect(row.getByText("No se pudo probar", { exact: true })).toBeVisible();
    await expect(row.getByText("Por qué falló")).toHaveCount(0);
    await expect(row.getByRole("button", { name: /Arreglar/ })).toHaveCount(0);
    await expectNoSeriousAxe(page, "[data-slot=test-list]");
  });

  for (const [mode, text] of [
    ["down", "No se pudo probar esta versión porque ningún modelo respondió"],
    ["saving", "Hay una pasada de pruebas en marcha"],
  ] as const) {
    test(`«Guardar» desde la hoja del diff: el aviso no se queda debajo de ella (${mode})`, async ({ page, request }) => {
      await open(page);
      const box = page.locator("[data-slot=tests-box]");
      await box.getByRole("button", { name: "Ejecutar todas" }).click();
      await expect(box.getByRole("heading", { level: 2 })).toContainText("pasan", { timeout: 30_000 });
      await request.post(`${API}/__test/model`, { data: { mode } });

      const bar = page.locator("[data-slot=publish-bar]");
      await bar.getByRole("button", { name: "Guardar igualmente" }).click();
      const sheet = page.getByRole("dialog", { name: "Qué cambia al guardar" });
      await sheet.getByRole("textbox", { name: /Nota del cambio/ }).fill("Lista de espera");
      await sheet.getByRole("button", { name: "Guardar cambios" }).click();

      await expect(sheet).toHaveCount(0, { timeout: 30_000 });
      await expect(bar.getByRole("alert")).toContainText(text);
      await expect(bar.getByRole("alert")).toBeInViewport();
      // Terminada la salida de la hoja, nadie le quita el foco.
      await expect(bar.getByRole("alert")).toBeFocused();
      await expectNoSeriousAxe(page, "[data-slot=publish-bar]");
    });
  }
});
