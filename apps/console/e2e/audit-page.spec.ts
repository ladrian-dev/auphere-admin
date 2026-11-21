import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * Spec 073 (§1, 5.2) — la Auditoría que se lee, en un navegador de verdad:
 * a 1280 px la tabla no se desplaza de lado (WCAG 1.4.10), con la barra lateral
 * abierta; los días van en filas de grupo; «Solo cambios» deja fuera los
 * accesos; y pasa axe (serious/critical) en claro y en oscuro.
 *
 *   pnpm exec playwright test -c e2e/shell.config.ts audit-page
 */
async function expectNoSeriousAxe(page: Page) {
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
    .exclude("iframe")
    .analyze();
  const blocking = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}

test.describe("Auditoría (spec 073)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("a 1280 px cabe sin desplazarse de lado, con los días agrupados y «Solo cambios» por defecto", async ({ page }) => {
    await page.goto("/audit");
    const table = page.getByRole("table", { name: "Auditoría" });
    await expect(table).toBeVisible();
    const sideways = await page.locator("[data-slot=audit-card] [data-slot=table-container]").evaluate((el) => el.scrollWidth - el.clientWidth);
    expect(sideways, "la tabla no se desplaza de lado").toBeLessThanOrEqual(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    await expect(page.locator("th[scope=colgroup]")).toHaveCount(2);
    await expect(table.getByText("tú · partner").first()).toBeVisible();
    await expect(table.getByText("Luis entró en la consola.")).toHaveCount(0);

    await page.getByRole("button", { name: "Todo, con accesos" }).click();
    await expect(page).toHaveURL(/view=all/);
    await expect(table.getByText("entró en la consola.")).toBeVisible();
    await expectNoSeriousAxe(page);
  });

  test("a 1024 px «Qué pasó» se lee: el cliente y la categoría van bajo la frase (revisión de staging)", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 800 });
    await page.goto("/audit");
    const table = page.getByRole("table", { name: "Auditoría" });
    await expect(table).toBeVisible();
    const what = await table.locator("thead th", { hasText: "Qué pasó" }).evaluate((th) => th.getBoundingClientRect().width);
    expect(what, "«Qué pasó» no se queda en una columna de una palabra").toBeGreaterThanOrEqual(240);
    await expect(table.locator("thead th", { hasText: "Cliente" })).toBeHidden();
    await expect(table.locator("[data-slot=audit-folded]").first()).toBeVisible();
    const sideways = await page.locator("[data-slot=audit-card] [data-slot=table-container]").evaluate((el) => el.scrollWidth - el.clientWidth);
    expect(sideways).toBeLessThanOrEqual(0);
  });

  test("pasa axe en oscuro", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark" });
    await page.goto("/audit");
    await expect(page.getByRole("table", { name: "Auditoría" })).toBeVisible();
    await expectNoSeriousAxe(page);
  });
});
