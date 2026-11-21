import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { overflowOffenders } from "./audit";

/**
 * Spec 047, historias 25 y 26 (T153, T159, T160) — el dinero en un navegador de
 * verdad: Consumo con sus tres cifras, la tabla por cliente, la gráfica con su
 * tabla, las partidas y el detalle; el modal «Asignar saldo» abierto en el sitio
 * desde la tabla de Consumo, la lista de clientes y el Panel del cliente, con
 * la línea del BCE, «Faltan» y el aviso final; «Pedir saldo» para quien no
 * asigna, con «Pedido hace…»; y «Repartir tu saldo en bolsas». Formato
 * `es-ES`. axe y 390 px sin desbordar.
 *
 *   pnpm exec playwright test -c e2e/money.config.ts
 *
 * Contra `money-mock.mjs`: la cuenta en euros (60,00 €), Flor y Encanto con la
 * bolsa en dólares y Barbería Cultor en euros y vacía.
 */

const API = "http://127.0.0.1:8718";
const FLOR = "flor-y-encanto";
const BARBERIA = "barberia-cultor";

/** Los espacios de `Intl` (duros y finos) como espacios normales. */
const plain = (s: string | null) => (s ?? "").replace(/[  ]/g, " ").replace(/\s+/g, " ").trim();

async function expectNoSeriousAxe(page: Page) {
  await expect(page.locator("[data-sonner-toast]")).toHaveCount(0, { timeout: 15_000 });
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
    .exclude("iframe")
    .analyze();
  const blocking = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}

async function go(page: Page, path: string, heading: string) {
  const res = await page.goto(path);
  expect(res?.status(), `${path} respondió ${res?.status()}`).toBeLessThan(400);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
}

const state = async (request: import("@playwright/test").APIRequestContext) => (await (await request.get(`${API}/__test/state`)).json());

test.describe("Spec 047 — el dinero: Consumo, «Asignar saldo», «Pedir saldo» y el reparto en bolsas", () => {
  test.beforeEach(async ({ request, page }) => {
    await request.post(`${API}/__test/reset`);
    await page.setViewportSize({ width: 1280, height: 900 });
  });

  test("Consumo en el orden de la demo (spec 072): la gráfica, las cuatro cifras con Meta, la tabla, los avisos y el detalle", async ({ page }) => {
    await go(page, "/usage", "Consumo");
    // 4.1: el orden de la página.
    const order = await page.locator("[data-slot=usage-spend], [data-slot=usage-figures], [data-slot=usage-balance], [data-slot=usage-detail]").evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.slot));
    expect(order).toEqual(["usage-spend", "usage-figures", "usage-balance", "usage-detail"]);

    // 4.2: la gráfica dice su ventana; el periodo y el cliente, sin el desplegable de partida (D3).
    const chart = page.locator("#gasto");
    await expect(chart.getByRole("heading", { name: "Gasto por día · últimos 30 días" })).toBeVisible();
    await expect(chart.getByRole("listbox", { name: "Gasto por día" })).toBeVisible();
    await expect(chart.getByRole("combobox", { name: "Partida" })).toHaveCount(0);
    await chart.getByRole("button", { name: "7 días" }).click();
    await expect(page).toHaveURL(/days=7/);
    await expect(chart.locator("table tbody tr")).toHaveCount(7);

    // 4.3: cuatro cifras; Meta con su marca y sin «≈».
    const figures = page.locator("[data-slot=usage-figures]");
    await expect(figures.locator("[data-slot=usage-figure]")).toHaveCount(4);
    expect(plain(await figures.textContent())).toContain("60,00 €");
    const meta = figures.locator("[data-slot=usage-figure]").nth(3);
    await expect(meta.getByTestId("meta-mark")).toHaveCount(1);
    await expect(meta).toContainText("Mensajes de Meta");
    await expect(meta).not.toContainText(/aprox\.|≈/);
    await expect(meta).toContainText("lo que el negocio paga a Meta");

    // 4.4: sin las tarjetas de partidas.
    await expect(page.locator("[data-slot=usage-lines]")).toHaveCount(0);

    const table = page.getByRole("region", { name: "Saldo por cliente" });
    const flor = table.locator(`tr[data-client=${FLOR}]`);
    expect(plain(await flor.textContent())).toContain("15,50 USD");
    const barberia = table.locator(`tr[data-client=${BARBERIA}]`);
    await expect(barberia.getByText("Sin saldo")).toBeVisible();
    await expect(barberia.getByRole("button", { name: "Asignar saldo" })).toHaveCount(0);

    // El detalle técnico, plegado, con el CSV.
    const detail = page.locator("[data-slot=usage-detail]");
    await detail.locator("summary").click();
    await expect(detail.getByRole("button", { name: "Descargar CSV" })).toHaveAttribute("href", /\/api\/usage\/export\?days=7&lang=es/);
    // 1.2: ningún «US$».
    await expect(page.locator("main")).not.toContainText("US$");
    await expectNoSeriousAxe(page);
  });

  test("Consumo pasa axe en oscuro (spec 072, 7.2)", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark" });
    await go(page, "/usage", "Consumo");
    await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
    await expectNoSeriousAxe(page);
  });

  test("«Asignar saldo» desde la tabla de Consumo: otra cantidad con coma, el recibo y el aviso final", async ({ page, request }) => {
    await go(page, "/usage", "Consumo");
    const row = page.locator(`tr[data-client=${BARBERIA}]`);
    await row.getByRole("button", { name: /^Acciones de / }).click();
    await page.getByRole("menuitem", { name: "Asignar saldo" }).click();
    const dialog = page.getByRole("dialog", { name: "Asignar saldo a Barbería Cultor" });
    await expect(dialog).toBeVisible();
    await expect(page).toHaveURL(/\/usage$/);
    await dialog.getByText("Otra cantidad", { exact: true }).click();
    await dialog.getByRole("textbox", { name: "Otra cantidad, en €" }).fill("12,5");
    const receipt = dialog.locator("[data-slot=assign-receipt]");
    await expect(receipt).toHaveAttribute("role", "status");
    await expect.poll(async () => plain(await receipt.textContent())).toContain("Asignas12,50 €");
    expect(plain(await receipt.textContent())).toContain("Te queda en el tuyo47,50 €");
    await expect(dialog.getByRole("checkbox", { name: "Avisarme cuando le quede menos del 20 %" })).toBeChecked();
    await expectNoSeriousAxe(page);
    // Spec 072 §6.1: el botón dice el importe.
    await dialog.getByRole("button", { name: /^Asignar 12,50\s€$/ }).click();
    await expect(page.locator("[data-sonner-toast]").first()).toContainText("Asignados 12,50");
    expect(plain(await page.locator("[data-sonner-toast]").first().textContent())).toContain("Asignados 12,50 € a Barbería Cultor. En tu cuenta quedan 47,50 €.");
    const sent = await state(request);
    expect(sent.assigns).toHaveLength(1);
    expect(sent.assigns[0].body).toMatchObject({ amount: { amount_micros: 1_250_000, currency: "EUR" }, alert_low: true });
    expect(sent.assigns[0].key).toMatch(/^assign:/);
    await expect(row.getByText("Sin saldo")).toHaveCount(0);
  });

  test("desde la lista de clientes, con la línea del BCE y «Faltan» si no llega", async ({ page }) => {
    await go(page, "/clients", "Clientes");
    await page.getByRole("button", { name: "Acciones de Flor y Encanto" }).click();
    await page.getByRole("menuitem", { name: "Asignar saldo" }).click();
    const dialog = page.getByRole("dialog", { name: "Asignar saldo a Flor y Encanto" });
    await expect(dialog).toBeVisible();
    await expect(page).toHaveURL(/\/clients$/);
    const receipt = dialog.locator("[data-slot=assign-receipt]");
    await expect(receipt).toContainText("1 € = 1,0852 USD · BCE 26 oct 2026");
    // Spec 072 §6.3: lo que sale de la cuenta en otra moneda es una nota de «Asignas».
    expect(plain(await receipt.textContent())).toContain("de tu cuenta");
    await dialog.getByText(/^100,00\sUSD$/).click();
    await expect(receipt.getByText(/^Faltan 32,15\s€$/)).toBeVisible();
    await expect(receipt.getByRole("link", { name: "Recargar mi cuenta" })).toHaveAttribute("href", "/billing?recargar=33");
    await expect(dialog.getByRole("button", { name: /^Asignar 100,00\sUSD$/ })).toBeDisabled();
    await expectNoSeriousAxe(page);
  });

  test("desde el Panel del cliente", async ({ page, request }) => {
    await go(page, `/clients/${FLOR}`, "Flor y Encanto");
    await page.locator("[data-slot=client-panel]").getByRole("button", { name: "Asignar saldo" }).click();
    const dialog = page.getByRole("dialog", { name: "Asignar saldo a Flor y Encanto" });
    await dialog.getByRole("button", { name: /^Asignar 20,00\sUSD$/ }).click();
    await expect(page.locator("[data-sonner-toast]").first()).toContainText("Asignados 20,00");
    expect((await state(request)).assigns[0]).toMatchObject({ ref: FLOR, body: { amount: { amount_micros: 2_000_000, currency: "USD" } } });
  });

  test("«Pedir saldo» para quien no asigna: una nota y, después, «Pedido hace…»", async ({ page, request }) => {
    await request.post(`${API}/__test/role`, { data: { role: "builder" } });
    await go(page, "/usage", "Consumo");
    const row = page.locator(`tr[data-client=${BARBERIA}]`);
    await expect(row.getByRole("button", { name: "Asignar saldo" })).toHaveCount(0);
    // La acción vive en el ⋯ de la fila (regla de los tres puntos, 2026-10-30).
    await row.getByRole("button", { name: /^Acciones de / }).click();
    await expect(page.getByRole("menuitem", { name: "Asignar saldo" })).toHaveCount(0);
    await page.getByRole("menuitem", { name: "Pedir saldo" }).click();
    const dialog = page.getByRole("dialog", { name: "Pedir saldo para Barbería Cultor" });
    await dialog.getByRole("textbox", { name: /Nota/ }).fill("Se le acaba el viernes");
    await expectNoSeriousAxe(page);
    await dialog.getByRole("button", { name: "Pedir saldo" }).click();
    await expect(row.getByText("Pedido hace un momento")).toBeVisible();
    expect((await state(request)).requests).toEqual([{ ref: BARBERIA, note: "Se le acaba el viernes" }]);
    // Al volver, la API dice que ya se pidió hoy: el botón sigue diciéndolo.
    await go(page, "/usage", "Consumo");
    await expect(row.getByText(/^Pedido hace/)).toBeVisible();
  });

  test("«Repartir tu saldo en bolsas»: la propuesta y la confirmación", async ({ page, request }) => {
    await request.post(`${API}/__test/migration`);
    await go(page, "/usage", "Consumo");
    await expect(page.getByText(/Cada cliente pasa a tener su bolsa/)).toBeVisible();
    await page.getByRole("button", { name: "Repartir tu saldo en bolsas" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Repartir tu saldo en bolsas" })).toBeVisible();
    const table = page.getByRole("region", { name: "La propuesta por cliente" });
    expect(plain(await table.textContent())).toContain("Flor y Encanto12,50 USD");
    expect(plain(await table.textContent())).toContain("Total19,50 USD");
    await expectNoSeriousAxe(page);
    // Se puede ajustar: solo va lo que cambió.
    await page.getByRole("textbox", { name: /Lo que pasa a la bolsa de Barbería Cultor/ }).fill("10");
    await page.getByRole("button", { name: "Confirmar el reparto" }).click();
    await expect(page.getByText("Listo: 2 clientes tienen ya su bolsa.").first()).toBeVisible();
    const sent = await state(request);
    expect(sent.confirmed).toBe(1);
    expect(sent.adjust).toEqual({ [BARBERIA]: 1_000_000 });
  });

  test("a 390 px nada se desborda: Consumo y el modal", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await go(page, "/usage", "Consumo");
    await page.waitForTimeout(300);
    expect(await overflowOffenders(page), "@390px Consumo se desborda").toEqual([]);
    await page.locator(`tr[data-client=${BARBERIA}]`).getByRole("button", { name: /^Acciones de / }).click();
    await page.getByRole("menuitem", { name: "Asignar saldo" }).click();
    await expect(page.getByRole("dialog", { name: "Asignar saldo a Barbería Cultor" })).toBeVisible();
    await page.waitForTimeout(300);
    expect(await overflowOffenders(page), "@390px el modal se desborda").toEqual([]);
  });
});
