import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { overflowOffenders } from "./audit";

/**
 * Spec 047, historias 18 a 20 (T124, T099 y T098) — en un navegador de verdad:
 * la pestaña Agentes con el estado de cada uno; pausar (con las conversaciones
 * en curso), reanudar, archivar con el destino de cada número y restaurar; el
 * agente por defecto que pide otro antes de archivarse; el copiloto con «¿Por
 * qué dijo esto?» y «Arreglar» con su alcance; y «Completar con el
 * constructor» en Negocio. axe y 390 px sin desbordar.
 *
 *   pnpm exec playwright test -c e2e/agent-life.config.ts
 *
 * Contra `agent-life-mock.mjs`.
 */

const API = "http://127.0.0.1:8716";
const REF = "barberia-cultor";
const RECEPCION = "00000000-0000-4000-8000-0000000000a1";
const COBROS = "00000000-0000-4000-8000-0000000000a2";
const VENTAS = "00000000-0000-4000-8000-0000000000a3";

async function expectNoSeriousAxe(page: Page) {
  await expect(page.locator("[data-sonner-toast]")).toHaveCount(0, { timeout: 15_000 });
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
    .exclude("iframe")
    .analyze();
  const blocking = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}

async function go(page: Page, path: string, heading: string) {
  const res = await page.goto(path);
  expect(res?.status(), `${path} respondió ${res?.status()}`).toBeLessThan(400);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await expect(page.getByRole("heading", { level: 2, name: heading })).toBeVisible();
}

const agentPage = (id: string) => `/clients/${REF}/agents/${id}`;
const menu = async (page: Page, name: string) => {
  await page.getByRole("button", { name: `Más acciones de ${name}` }).click();
  return page.getByRole("menu");
};

test.describe("Spec 047 — la vida de los agentes, el copiloto y el constructor del cliente", () => {
  test.beforeEach(async ({ request, page }) => {
    await request.post(`${API}/__test/reset`);
    await page.setViewportSize({ width: 1280, height: 900 });
  });

  test("la pestaña Agentes dice el estado de cada uno y abre la pestaña que le toca", async ({ page }) => {
    await go(page, `/clients/${REF}/agents`, "Agentes");
    const list = page.getByRole("list", { name: "Agentes del cliente" });
    const recepcion = list.getByRole("link", { name: /Recepción/ });
    await expect(recepcion.getByText("Atendiendo")).toBeVisible();
    await expect(recepcion.getByText("Por defecto")).toBeVisible();
    await expect(list.getByRole("link", { name: /Ventas/ })).toHaveAttribute("href", `/clients/${REF}/channels`);
    await expect(list.getByRole("link", { name: /Ventas/ }).getByText("Listo · sin canal")).toBeVisible();
    await expectNoSeriousAxe(page);
  });

  test("pausar con conversaciones en curso, reanudar, archivar con sus números y restaurar", async ({ page, request }) => {
    await go(page, agentPage(COBROS), "Cobros");
    await (await menu(page, "Cobros")).getByRole("menuitem", { name: "Pausar" }).click();
    const confirm = page.getByRole("dialog", { name: "¿Pausar Cobros?" });
    await expect(confirm.getByText(/Hay 3 conversaciones en curso/)).toBeVisible();
    await confirm.getByRole("button", { name: "Pausar igualmente" }).click();
    await expect(page.getByText("Pausado · a mano")).toBeVisible();
    await expect(page.getByText(/En pausa: no responde en ninguno de sus números/)).toBeVisible();

    await (await menu(page, "Cobros")).getByRole("menuitem", { name: "Reanudar" }).click();
    await expect(page.getByText("Atendiendo", { exact: true })).toBeVisible();

    await (await menu(page, "Cobros")).getByRole("menuitem", { name: "Archivar" }).click();
    const archive = page.getByRole("dialog", { name: "Archivar Cobros" });
    await archive.getByRole("combobox", { name: "Quién atiende +34 600 000 001" }).selectOption(VENTAS);
    await archive.getByRole("combobox", { name: "Quién atiende +34 600 000 002" }).selectOption("pause");
    await expectNoSeriousAxe(page);
    await archive.getByRole("button", { name: "Archivar" }).click();

    await expect(page.locator("[data-slot=archived-agent]")).toBeVisible();
    await expect(page.getByText("Archivado", { exact: true })).toBeVisible();
    const sent = await (await request.get(`${API}/__test/state`)).json();
    expect(sent.archives).toEqual([
      {
        agent: COBROS,
        channels: [
          { channel_id: "00000000-0000-4000-8000-0000000000c1", to: VENTAS },
          { channel_id: "00000000-0000-4000-8000-0000000000c2", to: "pause" },
        ],
      },
    ]);
    await expectNoSeriousAxe(page);

    await page.getByRole("button", { name: "Restaurar" }).click();
    await expect(page.getByText("Pausado · a mano")).toBeVisible();
    await expect(page.getByRole("button", { name: "Más acciones de Cobros" })).toBeVisible();
  });

  test("el agente por defecto pide elegir otro antes de archivarse", async ({ page, request }) => {
    await go(page, agentPage(RECEPCION), "Recepción");
    await (await menu(page, "Recepción")).getByRole("menuitem", { name: "Archivar" }).click();
    const archive = page.getByRole("dialog", { name: "Archivar Recepción" });
    await expect(archive.getByText(/Recepción es el agente por defecto/)).toBeVisible();
    await expect(archive.getByRole("button", { name: "Archivar" })).toHaveCount(0);
    await archive.getByRole("combobox", { name: "Nuevo agente por defecto" }).selectOption(VENTAS);
    await archive.getByRole("button", { name: "Cambiar el agente por defecto" }).click();
    await expect(archive.getByRole("button", { name: "Archivar" })).toBeVisible();
    const sent = await (await request.get(`${API}/__test/state`)).json();
    expect(sent.agents[VENTAS].is_default).toBe(true);
    expect(sent.agents[RECEPCION].is_default).toBe(false);
  });

  test("el copiloto: «¿Por qué dijo esto?» con sus fuentes y «Arreglar» con su alcance", async ({ page, request }) => {
    await go(page, agentPage(COBROS), "Cobros");
    await page.getByRole("button", { name: "¿Por qué dijo esto en Dice el horario del domingo?" }).click();
    const panel = page.getByRole("region", { name: "Copiloto" });
    await expect(panel.getByText(/la ficha dice que el domingo está cerrado/)).toBeVisible();
    await expect(panel.getByRole("link", { name: "Abrir Ficha · Horario" })).toHaveAttribute("href", `/clients/${REF}/business#business-hours`);
    await expect(panel.getByRole("link", { name: "Abrir Instrucción · Qué haces" })).toHaveAttribute("href", "#bloque-instructions");

    await panel.getByRole("radio", { name: "En la ficha (lo sabrán todos los agentes)" }).check();
    await panel.getByRole("textbox", { name: /El dato correcto/ }).fill("Los domingos está cerrado");
    await panel.getByRole("button", { name: "Corregir" }).click();
    await expect(page.getByText("Corregido. Vuelve a ejecutar la prueba para comprobarlo.").first()).toBeVisible();
    const sent = await (await request.get(`${API}/__test/state`)).json();
    expect(sent.copilot).toEqual([{ message: "¿Por qué dijo esto?", context: { test_id: "00000000-0000-4000-8000-0000000000f2" } }]);
    expect(sent.fixes).toEqual([{ test_id: "00000000-0000-4000-8000-0000000000f2", scope: "business", value: "Los domingos está cerrado" }]);
    await expectNoSeriousAxe(page);
  });

  test("«Completar con el constructor» propone por secciones y agentes que no se crean solos", async ({ page, request }) => {
    const res = await page.goto(`/clients/${REF}/business`);
    expect(res?.status()).toBeLessThan(400);
    await page.waitForLoadState("networkidle").catch(() => undefined);
    const panel = page.locator("[data-slot=client-builder]");
    await panel.getByRole("button", { name: "Completar con el constructor" }).click();
    await expect(panel.getByText("Listo: revisa lo que propone.")).toBeVisible({ timeout: 20_000 });
    const policy = panel.getByRole("listitem", { name: "Cancelación" });
    await expect(policy.getByText("Sugerido · confirma")).toBeVisible();
    await policy.getByRole("button", { name: "Aceptar Cancelación" }).click();
    await expect(panel.getByRole("listitem", { name: "Cancelación" })).toHaveCount(0);
    await panel.getByRole("button", { name: "Descartar ¿Aceptáis tarjeta?" }).click();
    await expect(panel.getByText("No queda nada por confirmar.")).toBeVisible();
    const sent = await (await request.get(`${API}/__test/state`)).json();
    expect(sent.decisions.map((d: { decision: string }) => d.decision)).toEqual(["accept", "discard"]);
    await expectNoSeriousAxe(page);

    await panel.getByRole("link", { name: "Crear el agente Recordatorios" }).click();
    await expect(page).toHaveURL(/\/agents\/new\?name=Recordatorios/);
    await expect(page.getByRole("textbox", { name: /Nombre/ })).toHaveValue("Recordatorios");
    await expect(page.getByRole("textbox", { name: /¿Qué tiene que hacer\?/ })).toHaveValue(/Recuerda las citas del día siguiente/);
  });

  test("a 390 px nada se desborda: la pantalla del agente con el copiloto y el modal de archivar", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await go(page, agentPage(COBROS), "Cobros");
    await page.getByRole("button", { name: "¿Por qué dijo esto en Dice el horario del domingo?" }).click();
    await expect(page.getByRole("region", { name: "Copiloto" }).getByText(/la ficha dice que el domingo está cerrado/)).toBeVisible();
    await page.waitForTimeout(300);
    expect(await overflowOffenders(page), "@390px se desborda").toEqual([]);
    await (await menu(page, "Cobros")).getByRole("menuitem", { name: "Archivar" }).click();
    await expect(page.getByRole("dialog", { name: "Archivar Cobros" })).toBeVisible();
    await page.waitForTimeout(300);
    expect(await overflowOffenders(page), "@390px el modal se desborda").toEqual([]);
    await expectNoSeriousAxe(page);
  });
});
