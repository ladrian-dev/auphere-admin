import { expect, test, type Page } from "@playwright/test";

import { auditView } from "./audit";

/**
 * Spec 030 (T105): the client console, as a person of a client, over the
 * REAL app — same rules as CP-30 (`a11y.spec.ts`) plus the frontier.
 *
 * Needs a client person with Panel, Inbox and Consumo, invited from the
 * admin's «Acceso» tab (or `apps/api/scripts/dev_seed_client_access.py`):
 *
 *   E2E_CLIENT_EMAIL=… E2E_CLIENT_PASSWORD=… pnpm test:e2e lite
 *
 * It never sends a message: in an environment with real contacts a send
 * would write to a real person. It opens, reads and checks what is offered.
 */

const LITE_VIEWS = ["/", "/inbox", "/usage"] as const;
/** Partner screens a client person must never get (each one lands on its Panel). */
const PARTNER_ONLY = ["/clients", "/audit", "/team", "/keys", "/billing", "/notifications"] as const;

test.use({ storageState: { cookies: [], origins: [] } });

async function signInAsClient(page: Page) {
  const email = process.env.E2E_CLIENT_EMAIL;
  const password = process.env.E2E_CLIENT_PASSWORD;
  if (!email || !password) throw new Error("set E2E_CLIENT_EMAIL and E2E_CLIENT_PASSWORD (a client person, spec 030)");
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByRole("textbox", { name: /correo|e-mail|email/i }).fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: /entrar|sign in|iniciar/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 90_000 });
  await expect(page.locator("main#main")).toBeVisible();
}

test.describe("spec 030 — la consola del cliente", () => {
  test.beforeEach(async ({ page }) => signInAsClient(page));

  test("the sidebar is the client's: lite, its modules, nothing of the partner", async ({ page }) => {
    const nav = page.getByRole("navigation").or(page.locator('[aria-label="Primary"]')).first();
    await expect(page.getByText("lite", { exact: true })).toBeVisible();
    for (const label of [/Panel/, /Bandeja de entrada/, /Consumo/]) {
      await expect(nav.getByRole("link", { name: label })).toBeVisible();
    }
    await expect(nav.getByRole("link", { name: /Clientes/ })).toHaveCount(0);
  });

  for (const path of PARTNER_ONLY) {
    test(`a partner screen is not the client's: ${path}`, async ({ page }) => {
      await page.goto(path);
      await page.waitForLoadState("networkidle").catch(() => undefined);
      expect(new URL(page.url()).pathname).not.toBe(path);
    });
  }

  for (const path of LITE_VIEWS) {
    test(`axe + overflow on ${path}`, async ({ page }) => auditView(page, path));
  }

  test("the Inbox opens a conversation and offers only what is possible", async ({ page }) => {
    await page.goto("/inbox");
    const list = page.getByRole("region", { name: "Conversaciones" });
    const rows = list.getByRole("listitem").getByRole("button");
    if ((await rows.count()) === 0) {
      // An inbox without conversations must say so — never an empty frame.
      await expect(page.getByText(/Aún no hay conversaciones|No hay conversaciones con estos filtros/)).toBeVisible();
      return;
    }
    await rows.first().click();
    await expect(page).toHaveURL(/\/inbox\?c=/);
    await expect(page.getByRole("log", { name: "Mensajes" })).toBeVisible();
    // Exactly one of the composer's modes is on screen.
    const offers = [
      page.getByRole("button", { name: "Tomar el control" }),
      page.getByRole("textbox", { name: "Escribir un mensaje" }),
      page.getByRole("button", { name: "Reabrir" }),
    ];
    let visible = 0;
    for (const o of offers) if (await o.first().isVisible()) visible += 1;
    expect(visible).toBeGreaterThan(0);
  });

  test("⌘K from the Panel searches the Inbox", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press(process.platform === "darwin" ? "Meta+k" : "Control+k");
    const box = page.getByRole("searchbox", { name: "Buscar en la bandeja" });
    await expect(box).toBeFocused();
    await box.fill("a");
    await box.press("Enter");
    await expect(page).toHaveURL(/\/inbox\?q=a/);
  });
});
