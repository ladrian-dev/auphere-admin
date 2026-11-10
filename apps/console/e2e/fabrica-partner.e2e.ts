import { expect, test, type Page } from "@playwright/test";

import { expectLongGermanFits, expectNoOverflow, expectNoSeriousAxe, expectReachableByTab, expectSolidFloatingLayer, preferLessGlassAndMotion } from "./fabrica-audit";

/**
 * Spec 047 (T174, T178, T165 y T162) — la pantalla del agente del partner con
 * la consola nueva, en un navegador de verdad: Recepción (marcar, destinos de
 * este cliente y cuándo, guardado en el borrador), Rendimiento (30 días en
 * bloques, la píldora con el teclado y las conversaciones con solo metadatos),
 * Mejoras (aceptar con su resultado, descartar con su motivo) y «Qué puede hacer
 * cada rol» en Equipo. Cada pantalla: axe, 390 px, 200 %, teclado, «Reducir
 * transparencia/movimiento», sus estados (con el parcial) y textos largos en
 * alemán. Los avisos que llevan a `?tab=performance` y `?tab=improvements` caen
 * en su sección.
 *
 *   pnpm exec playwright test -c e2e/fabrica.config.ts --project=partner
 *
 * Contra `fabrica-mock.mjs`.
 */

const API = "http://127.0.0.1:8719";
const REF = "barberia-cultor";
const RECEPCION = "00000000-0000-4000-8000-0000000000a1";
const VENTAS = "00000000-0000-4000-8000-0000000000a3";
const agentPage = `/clients/${REF}/agents/${RECEPCION}`;

async function mode(page: Page, parts: Record<string, string>) {
  await page.request.post(`${API}/__test/mode`, { data: parts });
}

async function state(page: Page) {
  return (await (await page.request.get(`${API}/__test/state`)).json()) as {
    reception: { enabled: boolean; targets?: { agent_id: string; when: string }[] } | null;
    specSaves: { revision: number }[];
    decisions: { id: string; decision: string; reason?: string }[];
  };
}

async function open(page: Page, path: string) {
  const res = await page.goto(path);
  expect(res?.status(), `${path} respondió ${res?.status()}`).toBeLessThan(400);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await expect(page.getByRole("heading", { level: 2, name: "Recepción" }).first()).toBeVisible();
}

const section = (page: Page, name: string) => page.getByRole("region", { name, exact: true });

test.describe("Spec 047 — el agente del partner: Recepción, Rendimiento y Mejoras, y Equipo", () => {
  test.beforeEach(async ({ page }) => {
    await page.request.post(`${API}/__test/reset`);
    await page.setViewportSize({ width: 1280, height: 900 });
  });

  test("Recepción: marcarla, elegir a quién deriva y cuándo, y guardarlo en el borrador", async ({ page }) => {
    await open(page, agentPage);
    const nav = page.getByRole("navigation", { name: "Partes del agente" });
    await expect(nav.getByRole("link", { name: "Recepción" })).toHaveAttribute("href", "#agente-recepcion");
    const reception = section(page, "Recepción");
    await expect(reception.getByText("No deriva")).toBeVisible();
    await reception.getByRole("button", { name: "Editar Recepción" }).click();
    await reception.getByRole("checkbox", { name: /Este agente es Recepción/ }).check();
    // Solo los demás agentes de este cliente; uno en pausa se avisa.
    await expect(reception.getByRole("checkbox", { name: "Derivar a Recepción" })).toHaveCount(0);
    await expect(reception.getByText(/En pausa ahora/)).toBeVisible();
    await reception.getByRole("checkbox", { name: "Derivar a Ventas mayoristas" }).check();
    await reception.getByRole("textbox", { name: /Cuándo derivar a Ventas mayoristas/ }).fill("Quiere comprar al por mayor");
    await expectNoSeriousAxe(page, "Recepción · editar");
    await reception.getByRole("button", { name: "Guardar en el borrador" }).click();
    await expect(reception.getByText("Es Recepción")).toBeVisible();
    await expect(reception.getByRole("list", { name: "A quién deriva" }).getByText("Cuándo: Quiere comprar al por mayor")).toBeVisible();
    await expect(page.locator("[data-slot=agent-reception]")).toHaveText("Recepción");
    expect((await state(page)).reception).toEqual({ enabled: true, targets: [{ agent_id: VENTAS, when: "Quiere comprar al por mayor" }] });
  });

  test("Rendimiento: 30 días en bloques, la píldora con el teclado y las conversaciones con solo metadatos", async ({ page }) => {
    await open(page, `${agentPage}?tab=performance`);
    const perf = section(page, "Rendimiento");
    await expect(perf).toBeInViewport();
    await expect(perf.getByText("Últimos 30 días")).toBeVisible();
    await expect(perf.getByRole("tab", { name: "30 días" })).toHaveAttribute("aria-selected", "true");
    await expect(perf.locator("[data-slot=performance-figures]").getByText("Conversaciones")).toBeVisible();
    await expect(perf.getByRole("listbox", { name: "Conversaciones por día" })).toBeVisible();
    const table = perf.getByRole("table", { name: "Conversaciones", exact: true });
    await expect(table.getByRole("columnheader")).toHaveText(["Fecha", "Canal", "Duración", "Mensajes", "Resultado", "Motivo del traspaso", "Gasto"]);
    await expect(table.getByText("Derivaciones en bucle")).toBeVisible();
    await expect(table.getByText("En curso")).toBeVisible();
    await expect(perf.getByText(/Nunca los mensajes ni quién era el cliente/)).toBeVisible();
    await expectNoSeriousAxe(page, "Rendimiento");

    const tab30 = perf.getByRole("tab", { name: "30 días" });
    await expectReachableByTab(page, tab30, 120);
    await page.keyboard.press("ArrowRight");
    await expect(perf.getByRole("tab", { name: "90 días" })).toBeFocused();
    await expect(perf.getByText("Últimos 90 días")).toBeVisible();
    await expect(perf.getByRole("tab", { name: "90 días" })).toHaveAttribute("aria-selected", "true");

    const rows = table.getByRole("row");
    await expect(rows).toHaveCount(7);
    await perf.getByRole("button", { name: "Ver más" }).click();
    await expect(rows).toHaveCount(9);
    await expect(perf.getByRole("button", { name: "Ver más" })).toHaveCount(0);
  });

  test("Mejoras: el aviso cae aquí; aceptar dice en qué queda el borrador y descartar pide el motivo", async ({ page }) => {
    await open(page, `${agentPage}?tab=improvements`);
    const improvements = section(page, "Mejoras");
    await expect(improvements).toBeInViewport();
    const list = improvements.getByRole("list", { name: "Mejoras por decidir" });
    await expect(list.getByText("12 conversaciones de 9 clientes")).toBeVisible();
    await expect(list.getByText("Corrección del negocio")).toBeVisible();
    await expect(list.getByText("Desde la app")).toBeVisible();
    await expectNoSeriousAxe(page, "Mejoras");

    // Dos mejoras con dos botones: cada fila los pliega en «⋯» (la regla de los tres puntos).
    await list.getByText("Ver propuesta").first().click();
    await expect(list.getByText("Prueba nueva: Pregunta por el aparcamiento")).toBeVisible();
    await list.getByRole("button", { name: /^Acciones de «12 clientes/ }).click();
    await page.getByRole("menuitem", { name: "Aceptar" }).click();
    await expect(improvements.getByText(/El cambio y su prueba están en el borrador \(revisión 5\)/)).toBeVisible();

    await improvements.getByRole("button", { name: "Descartar" }).click();
    const dialog = page.getByRole("dialog", { name: "¿Por qué la descartas?" });
    await expect(dialog.getByText("El negocio no recibe tu motivo. Queda en la auditoría.")).toBeVisible();
    await expectNoSeriousAxe(page, "Mejoras · descartar");
    await dialog.getByRole("textbox", { name: /Motivo/ }).fill("Los festivos sí abrimos");
    await dialog.getByRole("button", { name: "Descartar" }).click();
    await expect(improvements.getByText("Nada que mejorar por ahora")).toBeVisible();
    const decisions = (await state(page)).decisions.map((d) => [d.decision, d.reason ?? null]);
    expect(decisions).toEqual([
      ["accept", null],
      ["discard", "Los festivos sí abrimos"],
    ]);
  });

  test("los estados: parcial (el rendimiento falla y lo demás sigue), vacío y error con reintento", async ({ page }) => {
    await mode(page, { performance: "fail", improvements: "empty", conversations: "empty" });
    await open(page, agentPage);
    const perf = section(page, "Rendimiento");
    await expect(perf.getByText("No pudimos leer el rendimiento")).toBeVisible();
    await expect(perf.getByText("Aún no hay conversaciones de este agente.")).toBeVisible();
    await expect(section(page, "Mejoras").getByText("Nada que mejorar por ahora")).toBeVisible();
    await expect(section(page, "Pruebas")).toBeVisible();
    await expectNoSeriousAxe(page, "agente parcial");
    await mode(page, { performance: "ok" });
    await perf.getByRole("button", { name: "Reintentar" }).click();
    await expect(perf.getByText("Últimos 30 días")).toBeVisible();

    await mode(page, { performance: "empty", improvements: "fail" });
    await open(page, agentPage);
    await expect(section(page, "Rendimiento").getByText("Sin conversaciones en estos 30 días.")).toBeVisible();
    await expect(section(page, "Mejoras").getByText("No pudimos leer las mejoras")).toBeVisible();
  });

  test("la pantalla del agente a 390 px, al 200 %, con textos largos en alemán y sin vidrio ni movimiento", async ({ page }) => {
    await preferLessGlassAndMotion(page);
    await open(page, agentPage);
    await expectSolidFloatingLayer(page, () => page.locator("[data-slot=shell-sidebar] [data-slot=dropdown-menu-trigger]").click());
    await expectNoOverflow(page, "agente");
    await expectLongGermanFits(page, "agente");
  });

  test("Equipo: «Qué puede hacer cada rol» a la vista, accesible y sin desbordar", async ({ page }) => {
    const res = await page.goto("/team");
    expect(res?.status()).toBeLessThan(400);
    const table = page.getByRole("table", { name: "Qué puede hacer cada rol" });
    await expect(table).toBeVisible();
    await expect(table.getByRole("columnheader")).toHaveText(["Qué se puede hacer", "Propietario", "Administrador", "Constructor", "Analista", "Facturación"]);
    await expect(table.getByRole("row", { name: /Facturación y pagos/ }).getByRole("cell")).toHaveText(["Sí", "No", "No", "No", "Sí"]);
    await expectNoSeriousAxe(page, "/team");
    await expectNoOverflow(page, "/team");
    await expectLongGermanFits(page, "/team");
  });
});
