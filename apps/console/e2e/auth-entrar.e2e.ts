import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

/**
 * Spec 066 — Entrar con el líquido vivo, en un navegador de verdad.
 *
 * Lo que jsdom no puede decir: que la pantalla se parte o se apila según el
 * ancho, que el líquido pinta de verdad (WebGL) sin tapar el formulario, que
 * sigue vivo al pasar de Entrar a Recuperar, que no hay desplazamiento lateral
 * a 320 px, y que axe no encuentra nada grave.
 */

async function ready(page: Page, path: string) {
  await page.goto(path);
  await page.waitForLoadState("networkidle");
}

async function axe(page: Page) {
  const r = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
    .analyze();
  return r.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => `${v.id}: ${v.nodes[0]?.target}`);
}

test("a 1280 px la pantalla se parte: el líquido a la izquierda y la página a la derecha (R1.1)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await ready(page, "/login");
  const hero = page.getByTestId("auth-hero");
  const h1 = page.getByRole("heading", { level: 1, name: "Inicia sesión." });
  const hb = (await hero.boundingBox())!;
  const fb = (await h1.boundingBox())!;
  expect(hb.x + hb.width).toBeLessThanOrEqual(fb.x);
  expect(hb.height).toBeGreaterThan(700);
  await expect(page.getByText("Tus clientes, siempre al alcance.")).toBeVisible();
});

test("el líquido pinta con WebGL, no recibe el foco y no tapa el formulario (R2.8, R2.9)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await ready(page, "/login");
  const cv = page.locator(".auth-liquid-gl");
  await expect(cv).toHaveAttribute("data-live", "");
  await expect(cv).toHaveAttribute("aria-hidden", "true");
  // Lo que hay en el centro del campo de correo es el campo, no el lienzo.
  const email = page.getByRole("textbox", { name: "Correo" });
  const b = (await email.boundingBox())!;
  const top = await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.tagName, { x: b.x + b.width / 2, y: b.y + b.height / 2 });
  expect(top).toBe("INPUT");
});

test("al pasar de Entrar a Recuperar, el líquido sigue y el correo viaja sin la URL (R1.3, R4.3)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await ready(page, "/login");
  await expect(page.locator(".auth-liquid-gl")).toHaveAttribute("data-live", "");
  await page.locator(".auth-liquid-gl").evaluate((el) => el.setAttribute("data-mark", "same"));
  await page.getByRole("textbox", { name: "Correo" }).fill("ana@agencia.com");
  await page.getByRole("link", { name: /olvidado/i }).click();
  await page.waitForURL("**/forgot");
  expect(page.url()).not.toContain("ana");
  await expect(page.getByRole("textbox", { name: "Correo" })).toHaveValue("ana@agencia.com");
  // El mismo lienzo: el layout no se volvió a montar.
  await expect(page.locator('.auth-liquid-gl[data-mark="same"]')).toHaveCount(1);
});

test("Recuperar: «enviado» repite el correo y deja reenviar a los 30 s (R4.4)", async ({ page }) => {
  await ready(page, "/forgot");
  await page.getByRole("textbox", { name: "Correo" }).fill("ana@agencia.com");
  await page.getByRole("button", { name: "Mandarme el enlace" }).click();
  await expect(page.getByText("Si ana@agencia.com tiene cuenta, ya tiene un enlace esperando.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Reenviar en \d+ s$/ })).toBeDisabled();
});

test("a 390 px el líquido es una franja encima, y a 320 px nada se sale de lado (R1.2)", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await ready(page, "/login");
  const hb = (await page.getByTestId("auth-hero").boundingBox())!;
  const fb = (await page.getByRole("heading", { level: 1 }).boundingBox())!;
  expect(Math.round(hb.height)).toBe(200);
  expect(hb.y + hb.height).toBeLessThanOrEqual(fb.y);
  await expect(page.getByText("Tus clientes, siempre al alcance.")).toBeHidden();
  for (const path of ["/login", "/forgot", "/reset/tok_abcdefghijklmnop"]) {
    await page.setViewportSize({ width: 320, height: 700 });
    await ready(page, path);
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(over, path).toBeLessThanOrEqual(0);
  }
});

test("Contraseña nueva: reglas en vivo, y un enlace muerto tiene su pantalla (R5)", async ({ page }) => {
  await ready(page, "/reset/tok_abcdefghijklmnop");
  const fields = page.locator('input[autocomplete="new-password"]');
  await fields.nth(0).fill("Auphere2026!");
  await fields.nth(1).fill("Auphere2026!");
  await expect(page.getByTestId("reset-rules").locator("li[data-ok]")).toHaveCount(2);
  await page.goto("/reset/dead_abcdefghijklmnop");
  await page.waitForLoadState("networkidle");
  await page.locator('input[autocomplete="new-password"]').nth(0).fill("Auphere2026!");
  await page.locator('input[autocomplete="new-password"]').nth(1).fill("Auphere2026!");
  await page.getByRole("button", { name: "Cambiar la contraseña" }).click();
  await expect(page.getByText("Este enlace ya no vale")).toBeVisible();
});

test.describe("con reducir movimiento", () => {
  test("pinta un cuadro quieto (R2.6)", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.setViewportSize({ width: 1280, height: 800 });
    await ready(page, "/login");
    const cv = page.locator(".auth-liquid-gl");
    await expect(cv).toHaveAttribute("data-live", "");
    const a = await cv.screenshot();
    await page.mouse.move(200, 300);
    await page.mouse.down();
    await page.mouse.up();
    await page.waitForTimeout(600);
    const b = await cv.screenshot();
    expect(Buffer.compare(a, b)).toBe(0);
  });
});

test("axe no encuentra nada grave en las tres páginas, en claro y en oscuro (R6.3)", async ({ page }) => {
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    for (const path of ["/login", "/forgot", "/reset/tok_abcdefghijklmnop"]) {
      await ready(page, path);
      expect(await axe(page), `${path} (${scheme})`).toEqual([]);
    }
  }
});
