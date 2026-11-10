import { expect, test, type Page } from "@playwright/test";

import { auditView } from "./audit";

/**
 * Spec 030 (T105): the client console, as a person of a client, over the
 * REAL app — same rules as CP-30 (`a11y.spec.ts`) plus the frontier.
 *
 * Needs a client person with Panel, Inbox, Reservas and Consumo, invited from the
 * admin's «Acceso» tab (or `apps/api/scripts/dev_seed_client_access.py`).
 * It runs as its own project, signed in once by `client.setup.ts`:
 *
 *   E2E_CLIENT_EMAIL=… E2E_CLIENT_PASSWORD=… pnpm test:e2e --project=lite
 *
 * It never sends a message: in an environment with real contacts a send
 * would write to a real person. It opens, reads and checks what is offered.
 */

// Spec 031 (T053): «Tus teléfonos» goes through the same matrix as the modules.
// Spec 043 (T020, T060): Reservas too, in the mode the seeded client has, with
// each of its tabs and the list view (the default view alone left them unaudited).
// Spec 047 (T162, T168): Agentes y Negocio. Un cliente sin esos módulos vuelve a
// su primer módulo, que también se audita; con la consola nueva los tiene.
const LITE_VIEWS = [
  "/",
  "/inbox",
  "/agentes",
  "/negocio",
  "/reservas",
  "/reservas?view=list",
  "/reservas?tab=waitlist",
  "/reservas?tab=settings",
  "/usage",
  "/account/phones",
] as const;
/** The console speaks these two; the cookie is the explicit choice and wins. */
const LOCALES = ["es", "en"] as const;
/** The theme follows the system by default (`ThemeProvider`, `defaultTheme="system"`). */
const SCHEMES = ["light", "dark"] as const;
/** Partner screens a client person must never get (each one lands on its Panel). */
const PARTNER_ONLY = ["/clients", "/audit", "/team", "/keys", "/billing", "/notifications", "/usage/alerts", "/workstation"] as const;

async function inLocaleAndScheme(page: Page, baseURL: string | undefined, locale: string, scheme: "light" | "dark") {
  if (!baseURL) throw new Error("baseURL is not set");
  await page.context().addCookies([{ name: "nexus-console.locale", value: locale, url: baseURL }]);
  await page.emulateMedia({ colorScheme: scheme });
}

test.describe("spec 030 — la consola del cliente", () => {
  test("the sidebar is the client's: Beta, its modules, nothing of the partner", async ({ page }) => {
    await page.goto("/");
    const nav = page.getByRole("navigation").or(page.locator('[aria-label="Primary"]')).first();
    // Spec 045 (R7): the same «Beta» as the partner's console; «lite» was internal jargon.
    await expect(page.getByText("Beta", { exact: true })).toBeVisible();
    await expect(page.getByText("lite", { exact: true })).toHaveCount(0);
    for (const label of [/Panel/, /Bandeja de entrada/, /Consumo/]) {
      await expect(nav.getByRole("link", { name: label })).toBeVisible();
    }
    await expect(nav.getByRole("link", { name: /Clientes/ })).toHaveCount(0);
  });

  test("spec 031: «Tus teléfonos» is in the person's menu and opens its page", async ({ page }) => {
    await page.goto("/");
    // The menu's trigger is named by the person's email (`user-menu.tsx`).
    await page.getByRole("button", { name: process.env.E2E_CLIENT_EMAIL ?? "" }).click();
    await page.getByRole("menuitem", { name: /Tus teléfonos/ }).click();
    await page.waitForURL("**/account/phones");
    await expect(page.getByRole("heading", { name: "Tus teléfonos" })).toBeVisible();
    // Either the list or the empty state — never an error for a person who
    // simply has no phone yet.
    await expect(page.getByRole("list", { name: "Teléfonos con la sesión abierta" }).or(page.getByRole("status"))).toBeVisible();
  });

  for (const path of PARTNER_ONLY) {
    test(`a partner screen is not the client's: ${path}`, async ({ page }) => {
      // «Vuelve a su primer módulo, sin una pantalla que explique lo que no
      // tiene» (US2, scenario 3): no error on the way, not even for a moment.
      // Before T111 the guard's redirect was thrown under `loading.tsx` and
      // Next's Router broke (React #310): a second of «This page couldn't load».
      const errors: string[] = [];
      page.on("pageerror", (e) => errors.push(e.message));
      await page.goto(path);
      await page.waitForURL((url) => url.pathname !== path, { timeout: 30_000 });
      expect(["/", "/inbox", "/reservas", "/usage"]).toContain(new URL(page.url()).pathname);
      await expect(page.locator("main#main")).toBeVisible();
      expect(errors, `${path}: errors while moving the client to its module`).toEqual([]);
    });
  }

  for (const locale of LOCALES) {
    for (const scheme of SCHEMES) {
      for (const path of LITE_VIEWS) {
        test(`axe + overflow on ${path} · ${locale} · ${scheme}`, async ({ page, baseURL }) => {
          await inLocaleAndScheme(page, baseURL, locale, scheme);
          await auditView(page, path, async () => {
            // Prove the matrix is real before auditing it: a cookie the app
            // ignored, or a theme that never left light, would pass silently.
            await expect(page.locator("html")).toHaveAttribute("lang", locale);
            await expect(page.locator("html")).toHaveAttribute("data-theme", scheme);
          });
        });
      }
    }
  }

  test("the Inbox opens a conversation and offers only what is possible", async ({ page }) => {
    await page.goto("/inbox");
    const list = page.getByRole("region", { name: "Conversaciones" });
    const rows = list.getByRole("listitem").getByRole("button");
    // The list loads in the browser: wait for rows or for the empty state
    // (an inbox without conversations must say so — never an empty frame).
    const empty = page.getByText(/Aún no hay conversaciones|No hay conversaciones con estos filtros/);
    await expect(rows.first().or(empty)).toBeVisible();
    if (await empty.isVisible()) return;
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
    expect(visible).toBe(1);
    // The open thread is a view of its own: the same audit as the list.
    await auditView(page, new URL(page.url()).pathname + new URL(page.url()).search);
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
