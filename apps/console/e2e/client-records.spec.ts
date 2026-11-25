import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { overflowOffenders } from "./audit";

/**
 * Spec 047 (T065, T067; historias 15 y 16) — la lista de clientes y el Panel del
 * cliente en un navegador de verdad, con los gates de UI: axe (WCAG 2.2 AA), sin
 * desbordar la página a 390 px ni a 200 % de zoom (la tabla se desplaza dentro de
 * su caja), los textos largos alemanes, las pestañas en píldora y archivar con
 * «Deshacer».
 *
 *   pnpm exec playwright test -c e2e/client-records.config.ts
 */

async function expectNoSeriousAxe(page: Page) {
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
    .exclude("iframe")
    .analyze();
  const blocking = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}

const SIZES = [
  { name: "escritorio", width: 1280, height: 800 },
  { name: "390 px", width: 390, height: 844 },
  // 200 % de zoom sobre 1280 × 800: la página ve 640 × 400 píxeles CSS.
  { name: "200 %", width: 640, height: 400 },
];

test.describe("Spec 047 — la lista de clientes", () => {
  for (const size of SIZES) {
    test(`la lista dice quién necesita algo, sin desbordar (${size.name})`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      const res = await page.goto("/clients");
      expect(res?.status()).toBeLessThan(400);
      await expect(page.locator("[data-slot=clients-list-v2]")).toBeVisible();
      await expect(page.getByRole("combobox", { name: "Filtrar clientes" })).toContainText("Necesitan atención (3)");
      // Spec 074 (M01): por debajo de 760 px, una tarjeta por cliente en lugar de la tabla.
      const table =
        size.width < 760 ? page.getByRole("list", { name: "Clientes del partner" }) : page.getByRole("region", { name: "Clientes del partner" });
      await expect(table.getByText("Saldo bajo · quedan 4 días")).toBeVisible();
      await expect(table.getByText("Sin saldo").first()).toBeVisible();
      await expect(table.getByRole("meter").first()).toBeVisible();
      await expect(table.getByRole("button", { name: "Acciones de Barbería Cultor" })).toBeVisible();
      expect(await overflowOffenders(page)).toEqual([]);
      await expectNoSeriousAxe(page);
    });
  }

  test("el menú ⋯ de una fila lleva lo permitido", async ({ page }) => {
    await page.goto("/clients");
    await page.getByRole("button", { name: "Acciones de Barbería Cultor" }).click();
    for (const item of ["Editar cliente", "Asignar saldo", "Archivar", "Eliminar…"]) {
      await expect(page.getByRole("menuitem", { name: item, exact: true })).toBeVisible();
    }
    await page.keyboard.press("Escape");
  });

  test("en el móvil, el ⋯ de cada tarjeta lleva lo mismo y mide 44 × 44 (spec 074, M01)", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/clients");
    const cards = page.getByRole("list", { name: "Clientes del partner" });
    await expect(page.getByRole("region", { name: "Clientes del partner" })).toBeHidden();
    const more = cards.getByRole("button", { name: "Acciones de Barbería Cultor" });
    const box = await more.boundingBox();
    expect(box?.width).toBeGreaterThanOrEqual(44);
    expect(box?.height).toBeGreaterThanOrEqual(44);
    const name = await cards.getByRole("link", { name: "Barbería Cultor" }).boundingBox();
    expect(name?.height).toBeGreaterThanOrEqual(44);
    await more.click();
    for (const item of ["Editar cliente", "Asignar saldo", "Archivar", "Eliminar…"]) {
      await expect(page.getByRole("menuitem", { name: item, exact: true })).toBeVisible();
    }
    await page.keyboard.press("Escape");
    expect(await overflowOffenders(page)).toEqual([]);
  });
});

test.describe("Spec 047 — el Panel del cliente", () => {
  for (const size of SIZES) {
    test(`el Panel cuenta cómo va, con sus pestañas (${size.name})`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      const res = await page.goto("/clients/friseursalon");
      expect(res?.status()).toBeLessThan(400);
      await expect(page.locator("[data-slot=client-panel]")).toBeVisible();
      const tabs = page.getByRole("navigation", { name: "Secciones del cliente" });
      await expect(tabs.getByRole("link", { name: "Panel" })).toHaveAttribute("aria-current", "page");
      // Spec 070: la lente de vidrio se coloca bajo la pestaña activa.
      await expect(tabs.locator("[data-slot=client-tabs]")).toHaveAttribute("data-lens-ready", "");
      const lens = await tabs.locator("[data-slot=lens]").boundingBox();
      const active = await tabs.getByRole("link", { name: "Panel" }).boundingBox();
      expect(lens && active && Math.abs(lens.x - active.x) < 2 && Math.abs(lens.width - active.width) < 2, "la lente no está bajo «Panel»").toBe(true);
      // Spec 072 (2.1–2.3): la barra se llena con lo que queda y dice cuánto dura.
      const balance = page.locator("[data-slot=panel-balance]");
      const meter = balance.getByRole("meter");
      await expect(meter).toHaveAccessibleName("6,00 USD · quedan de 16,00 USD. Unos 4 días a este ritmo");
      await expect(meter).toHaveAttribute("aria-valuenow", "15");
      await expect(meter).toHaveAttribute("data-tone", "warn");
      await expect(balance.locator("[data-slot=bag-pace]")).toHaveText("Unos 4 días a este ritmo");
      await expect(balance.getByRole("alert")).toContainText("Queda menos del 20 % del saldo.");
      // «Este mes», con las tres cifras del Panel.
      const month = page.locator("[data-slot=panel-month]");
      await expect(month.getByRole("definition")).toHaveText(["128", "84 %", "21"]);
      // Lo que falta en la ficha ya no se anuncia en el Panel (prototipo de la
      // spec 047, Andrés, 2026-10-28): lo marca Negocio, a una pestaña.
      await expect(page.getByText(/Horarios: falta/)).toHaveCount(0);
      await expect(tabs.getByRole("link", { name: "Negocio" })).toHaveAttribute("href", "/clients/friseursalon/business");
      expect(await overflowOffenders(page)).toEqual([]);
      await expectNoSeriousAxe(page);
    });
  }

  test("archivar desde la cabecera ofrece «Deshacer»", async ({ page }) => {
    await page.goto("/clients/barberia-cultor");
    await page.getByRole("button", { name: "Acciones de Barbería Cultor" }).click();
    // Archivar no pregunta (prototipo, 7.4): se deshace desde el aviso.
    await page.getByRole("menuitem", { name: "Archivar" }).click();
    const toast = page.getByText("Barbería Cultor archivado. Sus agentes quedan en pausa.");
    await expect(toast).toBeVisible();
    await page.getByRole("button", { name: "Deshacer" }).click();
    await expect(page.getByText("Barbería Cultor restaurado. Cada agente vuelve a como estaba.")).toBeVisible();
  });
});
