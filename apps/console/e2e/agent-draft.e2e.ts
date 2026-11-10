import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { auditView, overflowOffenders } from "./audit";

/**
 * Spec 047, historia 2 (T041) — una sola barra de guardado en el agente y el
 * aviso de conflicto con los dos cambios, en un navegador de verdad: axe,
 * 390 px, 200 % y el teclado.
 *
 *   pnpm exec playwright test -c e2e/agent-draft.config.ts
 *
 * Contra `agent-draft-mock.mjs`: `/__test/other-writes` es la otra pestaña
 * (Lucía cambia el tono y las instrucciones del mismo borrador).
 */

const API = "http://127.0.0.1:8712";
const PAGE = "/clients/panaderia-la-espiga/agent";

async function expectNoSeriousAxe(page: Page) {
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
    .exclude("iframe")
    .analyze();
  const blocking = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}

async function open(page: Page) {
  const res = await page.goto(PAGE);
  expect(res?.status(), `${PAGE} respondió ${res?.status()}`).toBeLessThan(400);
  // Typing before React hydrates lands in the server's HTML and nobody hears it.
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await expect(page.getByRole("textbox", { name: "Instrucciones" })).toBeVisible();
}

const bar = (page: Page) => page.getByRole("region", { name: "Cambios sin guardar" });
const instructions = (page: Page) => page.getByRole("textbox", { name: "Instrucciones" });

test.describe("Spec 047 — el borrador del agente", () => {
  test.beforeEach(async ({ request, page }) => {
    await request.post(`${API}/__test/reset`);
    await page.setViewportSize({ width: 1280, height: 900 });
  });

  test("una sola barra guarda las instrucciones y los ajustes en el mismo borrador", async ({ page }) => {
    await open(page);
    await expect(bar(page)).toHaveCount(0);
    // The settings form lost its own button: the bar is the only way to save.
    await expect(page.getByRole("button", { name: "Guardar borrador" })).toHaveCount(0);

    const summary = bar(page).locator("[data-slot=draft-save-summary]");
    await instructions(page).fill("Atiende con calma y ofrece el pan del día.");
    await expect(summary).toHaveText("Cambios sin guardar en Instrucciones");
    await page.getByRole("textbox", { name: "Objetivo" }).fill("vender el pan del día");
    await expect(summary).toHaveText("Cambios sin guardar en Instrucciones y Ajustes");
    await expect(page.getByRole("button", { name: "Guardar", exact: true })).toHaveCount(1);

    await bar(page).getByLabel("Nota del cambio (opcional)").fill("Pan del día");
    await page.getByRole("button", { name: "Guardar", exact: true }).click();
    await expect(bar(page)).toHaveCount(0);

    const history = page.getByRole("list", { name: "Versiones" });
    const draft = history.getByRole("listitem").first();
    await expect(draft.getByText("v2", { exact: true })).toBeVisible();
    await expect(draft.getByText("Borrador", { exact: true })).toBeVisible();
    await expect(draft.getByText("desde v1")).toBeVisible();
    await expect(draft.getByText("Pan del día")).toBeVisible();
    await expect(page.getByText("Borrador v2 de Recepción, desde v1")).toBeVisible();
  });

  test("dos personas a la vez: la segunda ve los cambios de la primera y no se pierde nada", async ({ page, request }) => {
    await open(page);
    await instructions(page).fill("Mis instrucciones.");
    // The other tab saves first.
    await request.post(`${API}/__test/other-writes`);
    await page.getByRole("button", { name: "Guardar", exact: true }).click();

    const heading = page.getByRole("heading", { name: "Hay cambios más nuevos de lucia@ladrian.studio" });
    await expect(heading).toBeVisible();
    await expect(heading).toBeFocused();
    const notice = page.locator("[data-slot=draft-conflict]");
    await expect(notice.getByText("Tono", { exact: true })).toBeVisible();
    await expect(notice.getByText(/Los dos habéis cambiado Instrucciones/)).toBeVisible();
    // What this person typed is still there; nothing of it was saved.
    await expect(instructions(page)).toHaveValue("Mis instrucciones.");
    const stillTheirs = await (await request.get(`${API}/console/clients/panaderia-la-espiga/agents/00000000-0000-4000-8000-0000000000a1/draft`)).json();
    expect(stillTheirs.system_prompt).toBe("Atiende rápido: la cola es larga.");

    await expectNoSeriousAxe(page);
    for (const width of [390, 640]) {
      // 640 px is 1280 px at 200 % zoom.
      await page.setViewportSize({ width, height: 900 });
      await page.waitForTimeout(150);
      expect(await overflowOffenders(page), `@${width}px se desborda`).toEqual([]);
    }
    await page.setViewportSize({ width: 1280, height: 900 });

    await notice.getByRole("button", { name: "Guardar los míos encima" }).click();
    await expect(bar(page)).toHaveCount(0);
    const merged = await (await request.get(`${API}/console/clients/panaderia-la-espiga/agents/00000000-0000-4000-8000-0000000000a1/draft`)).json();
    expect(merged.system_prompt).toBe("Mis instrucciones.");
    // Lucía's tone is still in the draft: saving on top kept what was not in conflict.
    expect(merged.settings.tone.style).toBe("formal");
  });

  test("la pestaña con la barra abierta pasa axe, no desborda y aguanta el texto largo", async ({ page }) => {
    await auditView(page, PAGE, async () => {
      await page.waitForLoadState("networkidle").catch(() => undefined);
      await instructions(page).fill("Una instrucción nueva para que la barra esté a la vista.");
      await expect(bar(page)).toBeVisible();
    });
  });

  test("con el teclado: se escribe, se llega a Guardar y se guarda", async ({ page }) => {
    await open(page);
    await instructions(page).focus();
    await page.keyboard.press("End");
    await page.keyboard.type(" Sin prisa.");
    const save = page.getByRole("button", { name: "Guardar", exact: true });
    await save.focus();
    await expect(save).toBeFocused();
    await expectNoSeriousAxe(page);
    await page.keyboard.press("Enter");
    await expect(bar(page)).toHaveCount(0);
  });
});
