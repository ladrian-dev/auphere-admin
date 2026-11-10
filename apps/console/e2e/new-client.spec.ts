import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { overflowOffenders } from "./audit";

/**
 * Spec 047 (T050, historia 3) — «Nuevo cliente» en la consola nueva, en un
 * navegador de verdad: los tres datos, los chips de «Irá a la ficha» (el correo
 * no es una web), «Más ajustes» con lo deducido de una web `.cl`, el alta que
 * lleva al Panel con el aviso, y los gates de UI: axe, 390 px y 200 % de zoom,
 * y el foco que vuelve a quien abrió el modal.
 *
 *   pnpm exec playwright test -c e2e/clients-v2.config.ts
 */

const API = "http://127.0.0.1:8712";

async function expectNoSeriousAxe(page: Page, include?: string) {
  let builder = new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"]).exclude("iframe");
  if (include) builder = builder.include(include);
  const { violations } = await builder.analyze();
  const blocking = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}

async function openModal(page: Page) {
  const res = await page.goto("/clients");
  expect(res?.status()).toBeLessThan(400);
  await expect(page.locator("[data-shell=v2]")).toBeVisible();
  const trigger = page.getByRole("button", { name: "Nuevo cliente" });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Nuevo cliente" });
  await expect(dialog).toBeVisible();
  return { trigger, dialog };
}

test.describe("Spec 047 — el alta en tres datos", () => {
  test("los tres datos, los chips sin el correo y «Más ajustes» de una web .cl", async ({ page }) => {
    const { dialog } = await openModal(page);
    const create = dialog.getByRole("button", { name: "Crear cliente" });
    await expect(create).toBeDisabled();
    await expect(dialog.getByText("Nombre y nicho son obligatorios")).toBeVisible();

    await dialog.getByRole("textbox", { name: /Nombre/ }).fill("Flor y Encanto");
    await dialog.getByRole("textbox", { name: /Nicho/ }).fill("Florería de barrio");
    await dialog.getByRole("textbox", { name: /Información adicional/ }).fill("flor-y-encanto.cl · @florencanto · escríbenos a hola@flor-y-encanto.cl");

    const chips = dialog.getByRole("list", { name: "Enlaces que irán a la ficha" }).getByRole("listitem");
    await expect(chips).toHaveCount(2);
    await expect(chips.nth(0)).toContainText("flor-y-encanto.cl");
    await expect(chips.nth(0)).toContainText("Web");
    await expect(chips.nth(1)).toContainText("@florencanto");
    await expect(chips.nth(1)).toContainText("Instagram");
    await expect(dialog.getByRole("combobox", { name: "Red de @florencanto" })).toBeVisible();

    await dialog.getByRole("button", { name: "Más ajustes" }).click();
    await expect(dialog.getByRole("combobox", { name: "País" })).toHaveValue("CL");
    await expect(dialog.getByRole("combobox", { name: "Zona horaria" })).toHaveValue("America/Santiago");
    await expect(dialog.getByRole("combobox", { name: /Moneda de los precios/ })).toHaveValue("CLP");
    await expect(dialog.getByRole("combobox", { name: /Moneda de la bolsa/ })).toHaveValue("USD");

    await expectNoSeriousAxe(page, "[data-slot=client-modal]");
    await expect(create).toBeEnabled();
  });

  test("crear lleva al Panel del cliente con el aviso y manda lo deducido", async ({ page, request }) => {
    const { dialog } = await openModal(page);
    await dialog.getByRole("textbox", { name: /Nombre/ }).fill("Barbería Cultor");
    await dialog.getByRole("button", { name: "Añadir «Barbería» al nicho" }).click();
    await expect(dialog.getByRole("textbox", { name: /Nicho/ })).toHaveValue("Barbería");
    await dialog.getByRole("textbox", { name: /Información adicional/ }).fill("cultorbarber.es · @cultorbarber");
    await expect(dialog.getByRole("list", { name: "Enlaces que irán a la ficha" }).getByRole("listitem")).toHaveCount(2);
    await dialog.getByRole("button", { name: "Crear cliente" }).click();

    await expect(page).toHaveURL(/\/clients\/barberia-cultor$/);
    await expect(page.getByText("Barbería Cultor creado.")).toBeVisible();
    const sent = (await (await request.get(`${API}/__created`)).json()) as { body: Record<string, unknown>; idempotency_key: string | null }[];
    const last = sent.at(-1);
    expect(last, "la API simulada no recibió el alta").toBeDefined();
    if (!last) return;
    expect(last.body).toMatchObject({ name: "Barbería Cultor", niche: "Barbería", country: "ES", timezone: "Europe/Madrid", price_currency: "EUR", eu_only: true });
    expect(last.idempotency_key).toMatch(/^alta-/);
  });

  test("Escape cierra el modal y el foco vuelve a «Nuevo cliente»", async ({ page }) => {
    const { trigger, dialog } = await openModal(page);
    await expect(dialog.getByRole("textbox", { name: /Nombre/ })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("a 390 px y a 200 % de zoom el modal cabe, se desplaza y se puede crear", async ({ page }) => {
    for (const size of [
      { width: 390, height: 844 },
      // 200 % de zoom sobre 1280 × 800: la página ve 640 × 400 píxeles CSS.
      { width: 640, height: 400 },
    ]) {
      await page.setViewportSize(size);
      const { dialog } = await openModal(page);
      await dialog.getByRole("textbox", { name: /Información adicional/ }).fill("flor-y-encanto.cl · @florencanto");
      await dialog.getByRole("button", { name: "Más ajustes" }).click();
      expect(await overflowOffenders(page), `${size.width}×${size.height}`).toEqual([]);
      const submit = dialog.getByRole("button", { name: "Crear cliente" });
      await submit.scrollIntoViewIfNeeded();
      await expect(submit).toBeInViewport();
      await expectNoSeriousAxe(page, "[data-slot=client-modal]");
      await page.keyboard.press("Escape");
    }
  });

  test("/clients/new lleva al modal abierto en la consola nueva", async ({ page }) => {
    await page.goto("/clients/new");
    await expect(page).toHaveURL(/\/clients\?new=1$/);
    await expect(page.getByRole("dialog", { name: "Nuevo cliente" })).toBeVisible();
  });
});
