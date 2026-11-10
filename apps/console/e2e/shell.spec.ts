import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { auditView, overflowOffenders } from "./audit";
import { WORLD, searchWorld } from "./fixtures/search";

/**
 * Spec 047 — el marco común de la consola nueva (T007) y su ⌘K (T008), en un
 * navegador de verdad: axe, 390 px, 200 % de zoom y el teclado.
 *
 * Necesita un partner con la consola nueva activada (`console_version: "v2"`).
 * Contra la API simulada del contrato: `pnpm exec playwright test -c
 * e2e/shell.config.ts`. Contra una consola real: la suite de siempre, con
 * `E2E_EMAIL` de un partner activado.
 *
 * La búsqueda se sirve con la respuesta del contrato (`fixtures/search.ts`, la
 * misma regla que la API) interceptando `/api/search` en el navegador: así
 * «Recep» dice lo mismo con la API simulada y con cualquier semilla.
 */

const VIEWS = ["/notifications", "/team", "/keys"] as const;

async function expectNoSeriousAxe(page: Page, include?: string) {
  let builder = new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"]).exclude("iframe");
  if (include) builder = builder.include(include);
  const { violations } = await builder.analyze();
  const blocking = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}

async function openV2(page: Page, path: string = "/notifications") {
  const res = await page.goto(path);
  expect(res?.status(), `${path} respondió ${res?.status()}`).toBeLessThan(400);
  await expect(page.locator("[data-shell=v2]"), "el partner de la prueba no tiene la consola nueva activada").toBeVisible();
  await expect(page.locator("main#main")).toBeVisible();
}

const sidebar = (page: Page) => page.locator("[data-slot=shell-sidebar]");
const mobileNav = (page: Page) => page.locator("[data-slot=shell-mobile-nav]");

test.describe("Spec 047 — el marco de la consola nueva", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.route("**/api/search?*", async (route) => {
      const q = new URL(route.request().url()).searchParams.get("q") ?? "";
      await route.fulfill({ json: searchWorld(q) });
    });
  });

  test("cada vista dentro del marco pasa axe, no desborda a 360 ni a 1920 px y aguanta el texto largo", async ({ page }) => {
    for (const view of VIEWS) {
      await page.setViewportSize({ width: 1280, height: 800 });
      await auditView(page, view, async () => {
        await expect(page.locator("[data-shell=v2]")).toBeVisible();
      });
    }
  });

  test("escritorio: el menú lateral sin etiquetas de grupo, las migas y la página actual", async ({ page }) => {
    await openV2(page, "/team");
    const nav = sidebar(page).getByRole("navigation", { name: "Menú principal" });
    await expect(nav).toBeVisible();
    await expect(mobileNav(page)).toBeHidden();
    await expect(nav.getByRole("link", { name: "Equipo" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByText("Operar", { exact: true })).toHaveCount(0);
    const crumbs = page.getByRole("navigation", { name: "Migas de pan" });
    await expect(crumbs.getByText("Equipo")).toHaveAttribute("aria-current", "page");
    await expect(crumbs.getByRole("link")).toHaveCount(0);
    await expectNoSeriousAxe(page);
  });

  test("teclado: el salto al contenido, plegar a 64 px con el nombre en tooltip, y se recuerda", async ({ page }) => {
    await openV2(page);
    await page.keyboard.press("Tab");
    await expect(page.getByRole("link", { name: "Saltar al contenido" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("main#main")).toBeFocused();

    const toggle = page.getByRole("button", { name: "Plegar menú" });
    await toggle.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("button", { name: "Abrir menú" })).toHaveAttribute("aria-expanded", "false");
    await expect.poll(() => sidebar(page).evaluate((el) => Math.round(el.getBoundingClientRect().width))).toBe(64);

    const api = sidebar(page).getByRole("link", { name: "API" });
    await api.hover();
    await expect(page.locator("[data-slot=tooltip-content]")).toHaveText("API");
    await expectNoSeriousAxe(page);

    await page.reload();
    await expect.poll(() => sidebar(page).evaluate((el) => Math.round(el.getBoundingClientRect().width))).toBe(64);
    await page.getByRole("button", { name: "Abrir menú" }).click();
    await expect.poll(() => sidebar(page).evaluate((el) => Math.round(el.getBoundingClientRect().width))).toBeGreaterThan(64);
  });

  test("cada pantalla tiene su URL y el botón atrás vuelve a la anterior", async ({ page }) => {
    await openV2(page, "/notifications");
    await sidebar(page).getByRole("link", { name: "Equipo" }).click();
    await expect(page).toHaveURL(/\/team$/);
    await sidebar(page).getByRole("link", { name: "API" }).click();
    await expect(page).toHaveURL(/\/keys$/);
    await page.goBack();
    await expect(page).toHaveURL(/\/team$/);
    await expect(sidebar(page).getByRole("link", { name: "Equipo" })).toHaveAttribute("aria-current", "page");
    await page.goBack();
    await expect(page).toHaveURL(/\/notifications$/);
  });

  test("390 px: la barra superior conserva el menú, el perfil y el tema, sin desbordar", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openV2(page);
    await expect(sidebar(page)).toBeHidden();
    const bar = mobileNav(page);
    await expect(bar).toBeVisible();
    await expect(bar.getByRole("link", { name: "API" })).toBeAttached();
    expect(await overflowOffenders(page)).toEqual([]);
    await expectNoSeriousAxe(page);

    await page.locator("[data-slot=shell-mobile-profile] [data-slot=dropdown-menu-trigger]").click();
    const menu = page.getByRole("menu");
    await expect(menu.getByRole("menuitemradio")).toHaveText(["Claro", "Oscuro", "Sistema"]);
    await expect(menu.getByRole("menuitem", { name: "Cerrar sesión" })).toBeVisible();
    await menu.getByRole("menuitemradio", { name: "Oscuro" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    // Elegir el tema cierra el menú; se audita cuando ha terminado de irse.
    await expect(menu).toBeHidden();
    expect(await overflowOffenders(page)).toEqual([]);
    await expectNoSeriousAxe(page);
  });

  test("200 % de zoom: el marco pasa a la barra superior y nada se sale", async ({ page }) => {
    // Una ventana de 1280 × 800 al 200 % deja 640 × 400 px CSS: es lo que se mide.
    await page.setViewportSize({ width: 640, height: 400 });
    await openV2(page, "/team");
    await expect(sidebar(page)).toBeHidden();
    await expect(mobileNav(page)).toBeVisible();
    await expect(page.locator("[data-slot=shell-mobile-profile]")).toBeVisible();
    expect(await overflowOffenders(page)).toEqual([]);
    await expectNoSeriousAxe(page);
  });

  test("⌘K: «Recep» trae los agentes con su cliente; flechas e Intro abren, Escape cierra", async ({ page }) => {
    await openV2(page);
    await page.keyboard.press("ControlOrMeta+k");
    const input = page.getByRole("combobox", { name: "Buscar y navegar" });
    await expect(input).toBeFocused();
    const list = page.getByRole("listbox", { name: "Buscar y navegar" });
    // Sin escribir: las pantallas y las acciones que la persona puede usar.
    await expect(list.getByRole("group", { name: "Pantallas" }).getByRole("option", { name: "Equipo" })).toBeVisible();
    await expect(list.getByRole("group", { name: "Acciones" }).getByRole("option", { name: "Nuevo cliente" })).toBeVisible();

    await input.pressSequentially("Recep");
    const agents = list.getByRole("group", { name: "Agentes" });
    await expect(agents.getByRole("option")).toHaveText(["RecepciónFlor y Encanto", "RecepcionistaClínica Dental Sonrisa"]);
    await expect(agents.getByRole("option", { name: "Recepción, Flor y Encanto" })).toBeVisible();
    await expect(list.getByRole("group", { name: "Pantallas" })).toHaveCount(0);
    await expectNoSeriousAxe(page, "[data-slot=command-palette]");

    await page.keyboard.press("ArrowDown");
    await expect(agents.getByRole("option", { name: "Recepcionista, Clínica Dental Sonrisa" })).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(new RegExp(`/clients/clinica-dental-sonrisa/agents/${WORLD.agents[1]!.agent_id}$`));

    // Atrás vuelve a la pantalla de antes; el atajo vale en cuanto la página está viva.
    await page.goBack();
    await expect(page).toHaveURL(/\/notifications$/);
    await expect(async () => {
      await page.keyboard.press("ControlOrMeta+k");
      await expect(page.getByRole("dialog")).toBeVisible({ timeout: 1_000 });
    }).toPass();
    // Un cliente por su nombre, con sus pestañas; una acción por su texto.
    await page.getByRole("combobox", { name: "Buscar y navegar" }).pressSequentially("flor");
    const clients = list.getByRole("group", { name: "Clientes" });
    await expect(clients.getByRole("option")).toHaveText(["Flor y EncantoFloristería", "Flor y Encanto · Negocio", "Flor y Encanto · Agentes"]);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toBeHidden();
  });

  test("la campana: los 5 últimos, «Marcar todo como leído» y «Ver todas»; Escape devuelve el foco", async ({ page }) => {
    await openV2(page);
    const bell = page.getByRole("button", { name: /^Notificaciones/ });
    await bell.click();
    const panel = page.getByRole("dialog", { name: "Notificaciones" });
    await expect(panel).toBeVisible();
    await expect(panel.getByRole("link", { name: "Ver todas" })).toHaveAttribute("href", "/notifications");
    await expect(panel.getByRole("status", { name: "Cargando" })).toBeHidden();
    expect(await panel.getByRole("listitem").count()).toBeLessThanOrEqual(5);
    await expectNoSeriousAxe(page, "[data-slot=popover-content]");

    const markAll = panel.getByRole("button", { name: "Marcar todo como leído" });
    if (await markAll.isVisible()) {
      await markAll.click();
      await expect(markAll).toBeHidden();
      await expect(page.getByRole("button", { name: "Notificaciones", exact: true })).toBeVisible();
    }
    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();
    await expect(bell).toBeFocused();
  });

  test("«Reducir transparencia» pasa el vidrio a sólido y «Reducir movimiento» apaga las animaciones", async ({ page }) => {
    await openV2(page);
    const trigger = sidebar(page).locator("[data-slot=dropdown-menu-trigger]");
    const glassOf = () =>
      page.locator("[data-slot=dropdown-menu-content]").evaluate((el) => {
        const cs = getComputedStyle(el);
        return { background: cs.backgroundColor, filter: cs.backdropFilter };
      });
    const translucent = (color: string) => /\/\s*0?\.\d+\)$|rgba\([^)]*,\s*0?\.\d+\)$/.test(color);

    // Se mide cuando el menú ha terminado de entrar: durante la animación el
    // fondo pasa por valores intermedios.
    await trigger.click();
    await expect.poll(async () => (await glassOf()).filter).toContain("blur(20px)");
    const glass = await glassOf();
    expect(translucent(glass.background), `fondo del menú: ${glass.background}`).toBe(true);
    await page.keyboard.press("Escape");
    await expect(page.locator("[data-slot=dropdown-menu-content]")).toHaveCount(0);

    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-transparency", value: "reduce" }] });
    await trigger.click();
    await expect.poll(async () => (await glassOf()).filter).toContain("blur(0px)");
    await expect.poll(async () => translucent((await glassOf()).background)).toBe(false);
    await page.keyboard.press("Escape");

    await page.emulateMedia({ reducedMotion: "reduce" });
    const duration = await sidebar(page).evaluate((el) => parseFloat(getComputedStyle(el).transitionDuration));
    expect(duration).toBeLessThan(0.001);
  });
});
