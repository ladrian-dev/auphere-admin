import { expect, test, type Page } from "@playwright/test";

/**
 * Spec 017 · iteración 1 — la ficha de cliente, recorrida sobre la app real.
 *
 * Lo que fija esta suite es lo que un partner ve y puede hacer: qué falta
 * para que el cliente atienda, un solo botón que lo resuelve, las diez
 * pestañas en tres grupos, el menú «Más» y el borrador publicable desde
 * cualquier pestaña.
 *
 * El reparto por rol está clavado en los módulos puros (`client-nav-model`,
 * `client-header-model`, `lifecycle-status`), que los cubren todos sin
 * montar React. Aquí se recorre con el propietario, que es el único login
 * que el arnés siembra, y con los otros dos **solo si** el entorno trae sus
 * credenciales: `E2E_BUILDER_EMAIL`/`_PASSWORD` y `E2E_ANALYST_EMAIL`/
 * `_PASSWORD`. Sin ellas el caso se salta en voz alta, nunca en silencio.
 */

async function firstClientRef(page: Page): Promise<string> {
  await page.goto("/clients");
  const link = page.locator('a[href^="/clients/"]:not([href="/clients/new"])').first();
  await expect(link).toBeVisible();
  const href = await link.getAttribute("href");
  const ref = href?.split("/clients/")[1]?.split("/")[0];
  if (!ref) throw new Error("no client to walk — seed one first");
  return decodeURIComponent(ref);
}

/** Entra con otras credenciales en un contexto limpio. */
async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByRole("textbox", { name: /correo|e-mail|email/i }).fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: /entrar|sign in|iniciar/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 90_000 });
}

const GROUPS = [/observar|observe/i, /configurar|configure/i, /conectar|connect/i];

test.describe("spec 017 · la ficha de cliente", () => {
  test("la cabecera dice qué falta y ofrece un solo botón", async ({ page }) => {
    const ref = await firstClientRef(page);
    await page.goto(`/clients/${encodeURIComponent(ref)}`);
    await expect(page.locator("main#main")).toBeVisible();

    const setup = page.getByRole("navigation", { name: /puesta en marcha|getting started/i });
    const serving = (await setup.count()) === 0;

    if (serving) {
      // Ya atiende: la puesta en marcha desaparece, que es la regla.
      await expect(page.getByText(/siguiente paso|next step/i)).toHaveCount(0);
    } else {
      // Los cuatro pasos, cada uno con su nombre, y ninguno como ordinal:
      // se pueden hacer en cualquier orden.
      for (const step of [/agente|agent/i, /canal|channel/i, /crédito|credit/i, /activación|activation/i]) {
        await expect(setup.getByText(step).first()).toBeVisible();
      }
      // Un solo botón primario en el bloque, el del paso pendiente.
      const section = page.locator("section", { has: setup });
      await expect(section.getByText(/siguiente paso|next step/i)).toBeVisible();
    }

    // El crédito está en la cabecera, como barra o como su ausencia dicha.
    await expect(
      page.getByText(/quedan .* créditos|credits left|sin crédito asignado|no credit assigned/i).first(),
    ).toBeVisible();
  });

  test("las diez pestañas viven en tres grupos y ninguna desaparece", async ({ page }) => {
    const ref = await firstClientRef(page);
    await page.goto(`/clients/${encodeURIComponent(ref)}`);
    const nav = page.getByRole("navigation", { name: /sección de la ficha|record section/i });
    await expect(nav).toBeVisible();
    for (const group of GROUPS) await expect(nav.getByText(group)).toBeVisible();

    // El propietario ve las once de hoy (las diez de siempre más los datos
    // del cliente, que dejaron de compartir pestaña con los ajustes).
    const links = nav.getByRole("link");
    await expect(links).toHaveCount(11);
    // Exactamente una es la actual.
    await expect(nav.locator('a[aria-current="page"]')).toHaveCount(1);
  });

  test("«Más» es el mismo control en el mismo sitio, y no ofrece eliminar antes de archivar", async ({ page }) => {
    const ref = await firstClientRef(page);
    await page.goto(`/clients/${encodeURIComponent(ref)}`);
    const more = page.getByRole("button", { name: /más acciones|more actions/i });
    await expect(more).toBeVisible();
    await more.click();
    const menu = page.getByRole("menu");
    await expect(menu.getByText(/archivar|archive/i).first()).toBeVisible();
    await expect(menu.getByText(/copiar referencia|copy reference/i)).toBeVisible();
    // Eliminar solo se ofrece archivado: un botón que contesta «archiva
    // primero» es una trampa, no una afordancia.
    const status = await page.getByRole("main").innerText();
    if (!/archivado|archived/i.test(status.slice(0, 400))) {
      await expect(menu.getByText(/^eliminar|^delete/i)).toHaveCount(0);
    }
    await page.keyboard.press("Escape");
  });

  test("el borrador se ve y se revisa desde cualquier pestaña", async ({ page }) => {
    const ref = await firstClientRef(page);
    const base = `/clients/${encodeURIComponent(ref)}`;
    await page.goto(base);
    const bar = page.getByTestId("draft-bar");
    test.skip((await bar.count()) === 0, "este cliente no tiene borrador pendiente");

    // La barra vive en el layout: sigue ahí en una pestaña que no es Agente.
    await page.goto(`${base}/conversations`);
    await expect(page.getByTestId("draft-bar")).toBeVisible();
    await expect(page.getByTestId("draft-bar")).toContainText(/cambios sin publicar|unpublished changes/i);

    // Y la pestaña donde vive el cambio lo dice con su punto.
    const nav = page.getByRole("navigation", { name: /sección de la ficha|record section/i });
    await expect(nav.getByRole("img", { name: /cambios sin publicar|unpublished changes/i }).first()).toBeVisible();

    // Revisar abre la hoja, que trae el diff de verdad y no publica sola.
    await page.getByRole("button", { name: /revisar y publicar|review and publish/i }).click();
    const sheet = page.getByRole("dialog");
    await expect(sheet).toBeVisible();
    await expect(sheet).toContainText(/publicar la versión|publish version/i);
    await expect(sheet.getByRole("columnheader", { name: /antes|before/i })).toBeVisible();
    await expect(sheet.getByRole("columnheader", { name: /ahora|now/i })).toBeVisible();
    await page.getByRole("button", { name: /^cancelar$|^cancel$/i }).click();
    await expect(sheet).toHaveCount(0);
  });

  test("«Capacidades» ya tiene su URL definitiva, aunque la pantalla siga siendo la de herramientas", async ({ page }) => {
    // Spec 017 R2: fijarla en la iteración 1 hace que un enlace guardado hoy
    // siga valiendo cuando la iteración 2 construya la pantalla (T037).
    const ref = await firstClientRef(page);
    const res = await page.goto(`/clients/${encodeURIComponent(ref)}/capabilities`);
    expect(res?.status(), "la URL existe").toBeLessThan(400);
    await expect(page).toHaveURL(new RegExp(`/clients/${ref}/tools$`));
    await expect(page.locator("main#main")).toBeVisible();
  });

  for (const role of ["builder", "analyst"] as const) {
    test(`la ficha vista por un ${role}`, async ({ browser }) => {
      const email = process.env[`E2E_${role.toUpperCase()}_EMAIL`];
      const password = process.env[`E2E_${role.toUpperCase()}_PASSWORD`];
      test.skip(!email || !password, `sin credenciales de ${role}: define E2E_${role.toUpperCase()}_EMAIL y _PASSWORD`);

      const context = await browser.newContext({ storageState: undefined });
      const page = await context.newPage();
      try {
        await signIn(page, email!, password!);
        const ref = await firstClientRef(page);
        await page.goto(`/clients/${encodeURIComponent(ref)}`);
        const nav = page.getByRole("navigation", { name: /sección de la ficha|record section/i });
        await expect(nav).toBeVisible();

        // El menú existe para todos, en el mismo sitio.
        await expect(page.getByRole("button", { name: /más acciones|more actions/i })).toBeVisible();

        if (role === "analyst") {
          // Sin Playground, y sin un botón que contestaría 403.
          await expect(nav.getByRole("link", { name: /playground/i })).toHaveCount(0);
          await expect(page.getByRole("button", { name: /revisar y publicar|review and publish/i })).toHaveCount(0);
        } else {
          await expect(nav.getByRole("link", { name: /playground/i })).toHaveCount(1);
        }
      } finally {
        await context.close();
      }
    });
  }
});
