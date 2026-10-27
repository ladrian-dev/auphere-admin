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
      await expect(page.getByRole("link", { name: "Necesitan atención · 3" })).toBeVisible();
      const table = page.getByRole("region", { name: "Clientes del partner" });
      await expect(table.getByText("Saldo bajo · quedan 4 días")).toBeVisible();
      await expect(table.getByText("Sin saldo").first()).toBeVisible();
      expect(await overflowOffenders(page)).toEqual([]);
      await expectNoSeriousAxe(page);
    });
  }

  test("el menú ⋯ de una fila lleva lo permitido", async ({ page }) => {
    await page.goto("/clients");
    await page.getByRole("button", { name: "Acciones de Barbería Cultor" }).click();
    for (const item of ["Editar", "Asignar saldo", "Nuevo agente", "Archivar", "Eliminar"]) {
      await expect(page.getByRole("menuitem", { name: item })).toBeVisible();
    }
    await page.keyboard.press("Escape");
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
      await expect(page.getByText("Unos 4 días al ritmo de los últimos 7 días.")).toBeVisible();
      await expect(page.getByText(/Queda menos del 20 % del saldo/)).toBeVisible();
      await expect(page.getByText("Horarios: falta. Sin horario, los agentes no saben cuándo abrís.")).toBeVisible();
      expect(await overflowOffenders(page)).toEqual([]);
      await expectNoSeriousAxe(page);
    });
  }

  test("archivar desde la cabecera ofrece «Deshacer»", async ({ page }) => {
    await page.goto("/clients/barberia-cultor");
    await page.getByRole("button", { name: "Acciones de Barbería Cultor" }).click();
    await page.getByRole("menuitem", { name: "Archivar" }).click();
    const dialog = page.getByRole("dialog", { name: "Archivar Barbería Cultor" });
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Archivar" }).click();
    await expect(dialog).toBeHidden();
    const toast = page.getByText("Barbería Cultor archivado. Sus agentes quedan en pausa.");
    await expect(toast).toBeVisible();
    await page.getByRole("button", { name: "Deshacer" }).click();
    await expect(page.getByText("Barbería Cultor restaurado. Cada agente vuelve a como estaba.")).toBeVisible();
  });
});
