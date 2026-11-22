import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { overflowOffenders } from "./audit";

/**
 * Spec 047, historias 10, 11 y 22 (T134, T115 y T111) — en un navegador de
 * verdad: la sección Conocimiento del agente (sus fuentes, cuántas del negocio,
 * quitar con «Deshacer» y «Enseñar» que siempre pide el alcance); la sección
 * Canales (cada número con su estado visible, su ⋯, pausar, pasar a otro
 * agente, desconectar con «Reintentar»); el enlace del dueño (se copia mientras
 * se ve, «Revocar y crear», «WhatsApp login» fuera de la beta); y la página del
 * canal (guardar con `If-Match`, el conflicto, «A todos» sin saldo con su
 * arreglo, deshacer y el historial). axe y 390 px sin desbordar.
 *
 *   pnpm exec playwright test -c e2e/agent-channels.config.ts
 *
 * Contra `agent-channels-mock.mjs`.
 */

const API = "http://127.0.0.1:8717";
const REF = "barberia-cultor";
const RECEPCION = "00000000-0000-4000-8000-0000000000a1";
const VENTAS = "00000000-0000-4000-8000-0000000000a3";
const CH1 = "00000000-0000-4000-8000-0000000000c1";

const agentPage = `/clients/${REF}/agents/${RECEPCION}`;
// Spec 047 (63.1; H5): la configuración del canal se abre dentro del agente.
const channelPage = `${agentPage}?canal=${CH1}`;

async function expectNoSeriousAxe(page: Page) {
  await expect(page.locator("[data-sonner-toast]")).toHaveCount(0, { timeout: 15_000 });
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
    .exclude("iframe")
    .analyze();
  const blocking = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}

// El nombre del agente es el h1 de su pantalla (spec 047, prototipo aprobado); el número de un canal abierto, su h2.
async function go(page: Page, path: string, heading: string | RegExp, level: 1 | 2 = 1) {
  const res = await page.goto(path);
  expect(res?.status(), `${path} respondió ${res?.status()}`).toBeLessThan(400);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await expect(page.getByRole("heading", { level, name: heading })).toBeVisible();
}

// Como el prototipo aprobado (spec 047, «Consola de partners v2»), la pantalla del agente va
// en pestañas: el conocimiento propio vive en la fila «Qué sabe» de «Configuración» y los
// números, en la pestaña «Canales».
const knowledge = (page: Page) => page.getByRole("region", { name: "Lo que solo sabe este agente" });
const channels = (page: Page) => page.getByRole("region", { name: "Canales" });

async function openTab(page: Page, name: string) {
  const tab = page.getByRole("tab", { name });
  await tab.click();
  await expect(tab).toHaveAttribute("aria-selected", "true");
}

/** «Configuración» › «Qué sabe» › «Editar»: abre la fila con las fuentes del agente. */
async function openKnowledge(page: Page) {
  await openTab(page, "Configuración");
  await page.getByRole("region", { name: "Qué sabe" }).getByRole("button", { name: "Editar «Qué sabe»" }).click();
  await expect(knowledge(page)).toBeVisible();
}

test.describe("Spec 047 — el conocimiento y los canales de un agente", () => {
  test.beforeEach(async ({ request, page }) => {
    await request.post(`${API}/__test/reset`);
    await page.setViewportSize({ width: 1280, height: 900 });
  });

  test("Conocimiento: sus fuentes, las del negocio, quitar con «Deshacer» y «Enseñar» con su alcance", async ({ page, request }) => {
    // El ancla de siempre (`#agente-conocimiento`) lleva a «Configuración» con «Qué sabe» abierta.
    await go(page, `${agentPage}#agente-conocimiento`, "Recepción");
    await expect(page.getByRole("tab", { name: "Configuración" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("button", { name: "Cerrar «Qué sabe»" })).toHaveAttribute("aria-expanded", "true");
    const section = knowledge(page);
    await expect(section.getByRole("list", { name: "Fuentes de este agente" }).getByText("Tarifas mayoristas")).toBeVisible();
    await expect(section.getByText("Además sabe 2 fuentes del negocio, que ven todos sus agentes.")).toBeVisible();
    await expect(section.getByRole("link", { name: "Verlas en Negocio" })).toHaveAttribute("href", `/clients/${REF}/knowledge`);
    await expectNoSeriousAxe(page);

    await section.getByRole("button", { name: "Quitar Tarifas mayoristas" }).click();
    const restorable = section.getByRole("list", { name: "Quitadas hace poco" });
    await expect(restorable.getByText(/se puede deshacer hasta las/)).toBeVisible();
    await restorable.getByRole("button", { name: "Deshacer quitar Tarifas mayoristas" }).click();
    await expect(section.getByRole("list", { name: "Fuentes de este agente" }).getByText("Tarifas mayoristas")).toBeVisible();
    await expect(restorable).toHaveCount(0);

    await section.getByRole("button", { name: "Enseñar" }).click();
    const dialog = page.getByRole("dialog", { name: "Enseñar algo a Recepción" });
    await dialog.getByRole("textbox", { name: /Lo que debe saber/ }).fill("En agosto cerramos dos semanas");
    await dialog.getByRole("button", { name: "Enseñar" }).click();
    await expect(dialog.getByText("Elige quién debe saberlo.")).toBeVisible();
    await expectNoSeriousAxe(page);
    await dialog.getByRole("radio", { name: /Solo este agente/ }).check();
    // Desde la 4729e0e6 las pruebas no se vuelven a pasar solas: quedan desactualizadas.
    await expect(dialog.getByText("Después, las pruebas de este agente quedan desactualizadas.")).toBeVisible();
    await dialog.getByRole("button", { name: "Enseñar" }).click();
    await expect(dialog).toHaveCount(0);
    await expect(section.getByRole("list", { name: "Fuentes de este agente" }).getByText("En agosto cerramos dos semanas")).toBeVisible();
    const sent = await (await request.get(`${API}/__test/state`)).json();
    expect(sent.taught).toEqual([{ text: "En agosto cerramos dos semanas", scope: "agent" }]);
  });

  test("Negocio dice de qué capa son sus fuentes", async ({ page }) => {
    const res = await page.goto(`/clients/${REF}/knowledge`);
    expect(res?.status()).toBeLessThan(400);
    await expect(page.getByText(/Todas estas fuentes las ven todos los agentes de este cliente/)).toBeVisible();
    await expect(page.getByText("Carta del negocio")).toBeVisible();
  });

  test("Canales: el estado de cada número, su ⋯, pausar, pasar a otro agente y desconectar con «Reintentar»", async ({ page, request }) => {
    await go(page, agentPage, "Recepción");
    await openTab(page, "Canales");
    const section = channels(page);
    const list = section.getByRole("list", { name: "Canales de este agente" });
    await expect(list.getByRole("listitem").filter({ hasText: "+34 611 20 48 93" }).getByText("Solo mi equipo")).toBeVisible();
    await expect(list.getByRole("listitem").filter({ hasText: "+34 611 20 48 94" }).getByText("Con problemas · la app lleva días sin abrirse")).toBeVisible();
    await expect(list.getByRole("link", { name: "Configurar +34 611 20 48 93" })).toHaveAttribute("href", channelPage);

    await section.getByRole("button", { name: "Más acciones de +34 611 20 48 93" }).click();
    const menu = page.getByRole("menu");
    await expect(menu.getByRole("menuitem")).toHaveText(["Configuración", "Pasar a otro agente", "Pausar este canal", "Desconectar"]);
    await menu.getByRole("menuitem", { name: "Pausar este canal" }).click();
    await expect(list.getByRole("listitem").filter({ hasText: "+34 611 20 48 93" }).getByText("En pausa")).toBeVisible();
    await expectNoSeriousAxe(page);

    await section.getByRole("button", { name: "Más acciones de +34 611 20 48 94" }).click();
    await page.getByRole("menu").getByRole("menuitem", { name: "Desconectar" }).click();
    const confirm = page.getByRole("dialog", { name: "¿Desconectar +34 611 20 48 94?" });
    await confirm.getByRole("button", { name: "Desconectar" }).click();
    // «Falta terminar en Meta» va debajo de la lista, en la misma pestaña.
    const tab = page.getByRole("tabpanel", { name: "Canales" });
    await expect(tab.getByText("Falta terminar en Meta")).toBeVisible();
    await tab.getByRole("button", { name: "Reintentar" }).click();
    await expect(tab.getByText("Falta terminar en Meta")).toHaveCount(0);

    await section.getByRole("button", { name: "Más acciones de +34 611 20 48 93" }).click();
    await page.getByRole("menu").getByRole("menuitem", { name: "Pasar a otro agente" }).click();
    const move = page.getByRole("dialog", { name: "Pasar +34 611 20 48 93 a otro agente" });
    await expect(move.getByRole("radio", { name: "Ventas" })).toBeChecked();
    await expectNoSeriousAxe(page);
    await move.getByRole("button", { name: "Pasar el número" }).click();
    // Sin números, quien puede escribir ve el asistente para conectar el primero (prototipo, `agente.md` §7).
    await expect(tab.getByRole("list", { name: "Canales de este agente" })).toHaveCount(0);
    await expect(tab.getByRole("region", { name: "Elige un canal" })).toBeVisible();
    const sent = await (await request.get(`${API}/__test/state`)).json();
    expect(sent.moves).toEqual([{ channel: CH1, to: VENTAS }]);
    expect(sent.disconnects).toEqual(["00000000-0000-4000-8000-0000000000c2", "00000000-0000-4000-8000-0000000000c2"]);
  });

  test("el enlace del dueño: se copia mientras se ve, «Revocar y crear» y «WhatsApp login» fuera de la beta", async ({ page, request, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await go(page, agentPage, "Recepción");
    // El enlace se crea desde «Añadir otro canal» › WhatsApp › «Compartir un enlace» (prototipo, `agente.md` §7.1).
    await openTab(page, "Canales");
    await page.getByRole("button", { name: "Añadir otro canal" }).click();
    await page.getByRole("region", { name: "Elige un canal" }).getByRole("button", { name: "Conectar WhatsApp" }).click();
    await page.getByRole("dialog", { name: "Conectar WhatsApp" }).getByRole("button", { name: "Compartir un enlace" }).click();
    const dialog = page.getByRole("dialog", { name: "Enlace para el cliente" });
    await expect(dialog.getByText(/abre el enlace en su navegador/)).toBeVisible();
    await expect(dialog.getByText(/desde su teléfono/)).toHaveCount(0);
    const form = dialog.locator("[data-slot=owner-link]");

    await form.getByRole("radio", { name: /WhatsApp login \(beta\)/ }).check();
    await form.getByRole("button", { name: "Crear enlace" }).click();
    await expect(form.getByText(/WhatsApp login no está disponible para el país de este negocio/)).toBeVisible();
    await expect(form.getByRole("radio", { name: /WhatsApp login/ })).toHaveCount(0);
    await expect(page.getByText(/sin Facebook/i)).toHaveCount(0);

    await form.getByRole("button", { name: "Crear enlace" }).click();
    const created = form.getByRole("textbox", { name: "Enlace para el dueño" });
    await expect(created).toHaveValue(/\/connect\/whatsapp\/tok_/);
    await expect(form.getByText(/Cópialo ahora: por seguridad no se vuelve a enseñar/)).toBeVisible();
    await form.getByRole("button", { name: "Copiar enlace" }).click();
    // El aviso llega tras escribir en el portapapeles: se espera a que salga (y se vaya) antes de pasar axe.
    await expect(page.getByText("Enlace copiado.")).toBeVisible();
    await expectNoSeriousAxe(page);

    // Al volver, el enlace ya no se puede ver: solo que está pendiente, encima de los números.
    await page.reload();
    await page.waitForLoadState("networkidle").catch(() => undefined);
    await openTab(page, "Canales");
    const panel = page.locator("[data-slot=agent-channels] > [data-slot=owner-link]");
    await expect(panel.getByText("Enlace pendiente · app WhatsApp Business")).toBeVisible();
    await expect(panel.getByRole("textbox", { name: "Enlace para el dueño" })).toHaveCount(0);
    await panel.getByRole("button", { name: "Crear otro enlace" }).click();
    await expect(panel.getByText(/el anterior deja de funcionar/)).toBeVisible();
    await panel.getByRole("button", { name: "Revocar y crear" }).click();
    await expect(panel.getByRole("textbox", { name: "Enlace para el dueño" })).toHaveValue(/\/connect\/whatsapp\/tok_/);
    const sent = await (await request.get(`${API}/__test/state`)).json();
    expect(sent.links).toEqual([{ mode: "coexistence" }, { mode: "coexistence", replace: true }]);
  });

  test("la página del canal: guardar con su revisión, el conflicto, «A todos» sin saldo, deshacer e historial", async ({ page, request }) => {
    await go(page, `/clients/${REF}/channels/${CH1}`, "+34 611 20 48 93", 2);
    await expect(page).toHaveURL(new RegExp(`${channelPage.replace("?", "\\?")}$`));
    await expect(page.getByRole("tab", { name: "Canales" })).toHaveAttribute("aria-selected", "true");
    for (const name of ["A quién responde", "Escalado a personas", "Comprobaciones"]) {
      await expect(page.getByRole("region", { name })).toBeVisible();
    }
    await page.getByRole("button", { name: /Más ajustes/ }).last().click();
    for (const name of ["Mensaje de espera", "Historial"]) {
      await expect(page.getByRole("region", { name })).toBeVisible();
    }
    await expect(page.getByText("Los avisos por WhatsApp saldrán de este número.")).toBeVisible();
    await expect(page.locator("[data-slot=channel-triggers]").getByText("Cuando pide hablar con una persona")).toBeVisible();
    await expectNoSeriousAxe(page);

    // «A todos» sin saldo: el error lleva su arreglo.
    await page.getByRole("radio", { name: /A todos/ }).check();
    await page.getByRole("button", { name: "Guardar" }).click();
    const audience = page.getByRole("region", { name: "A quién responde" });
    await expect(audience.getByText(/«A todos» necesita saldo en la bolsa del cliente/)).toBeVisible();
    // Spec 047 (45.1): el arreglo abre «Asignar saldo» aquí mismo, sin salir de la página del canal.
    await audience.getByRole("button", { name: "Asignar saldo" }).click();
    const assign = page.getByRole("dialog", { name: "Asignar saldo a Barbería Cultor" });
    await expect(assign).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(assign).toHaveCount(0);
    // Una excepción (solo se ve con «A todos») y el mensaje de espera; otra persona guarda antes.
    const exceptions = page.getByRole("region", { name: "Excepciones" });
    await exceptions.getByRole("textbox", { name: /Número nuevo/ }).fill("+56 9 1234 5678");
    await exceptions.getByRole("button", { name: "Añadir a Excepciones" }).click();
    await page.getByRole("radio", { name: /Solo mi equipo/ }).check();
    await page.getByRole("textbox", { name: /^Mensaje/ }).fill("Gracias por escribir. Te respondemos enseguida.");
    await request.post(`${API}/__test/bump`);
    await page.getByRole("button", { name: "Guardar" }).click();
    await expect(page.getByText("Alguien guardó antes que tú")).toBeVisible();
    await expect(page.getByText(/Mientras editabas cambió el mensaje de espera/)).toBeVisible();
    await expectNoSeriousAxe(page);
    await page.getByRole("button", { name: "Guardar los míos encima" }).click();
    await expect(page.getByText("Todo guardado.")).toBeVisible();
    const sent = await (await request.get(`${API}/__test/state`)).json();
    expect(sent.saves).toEqual([
      {
        revision: 4,
        config: {
          audience: { mode: "team_only", test_numbers: ["+34611204893"], exceptions: ["+56912345678"] },
          escalation: { summary: true, recipients: [{ name: "Marta", via: "whatsapp", phone_e164: "+34600000009" }] },
          wait_message: "Gracias por escribir. Te respondemos enseguida.",
        },
      },
    ]);
    const history = page.getByRole("list", { name: "Historial" });
    await expect(history.getByText("Excepciones: ninguno → 1 número")).toBeVisible();

    await page.getByRole("button", { name: "Deshacer el último cambio" }).click();
    await expect(history.getByText("Deshecho", { exact: true })).toBeVisible();
    await expectNoSeriousAxe(page);
  });

  test("a 390 px nada se desborda: la pantalla del agente, el modal de pasar y la página del canal", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await go(page, agentPage, "Recepción");
    await openTab(page, "Canales");
    await expect(channels(page).getByRole("list", { name: "Canales de este agente" })).toBeVisible();
    await page.waitForTimeout(300);
    expect(await overflowOffenders(page), "@390px la pantalla del agente se desborda").toEqual([]);
    await openKnowledge(page);
    await page.waitForTimeout(300);
    expect(await overflowOffenders(page), "@390px «Qué sabe» se desborda").toEqual([]);
    await knowledge(page).getByRole("button", { name: "Enseñar" }).click();
    await expect(page.getByRole("dialog", { name: "Enseñar algo a Recepción" })).toBeVisible();
    await page.waitForTimeout(300);
    expect(await overflowOffenders(page), "@390px «Enseñar» se desborda").toEqual([]);
    await page.keyboard.press("Escape");
    await openTab(page, "Canales");
    await channels(page).getByRole("button", { name: "Más acciones de +34 611 20 48 93" }).click();
    await page.getByRole("menu").getByRole("menuitem", { name: "Pasar a otro agente" }).click();
    await expect(page.getByRole("dialog", { name: "Pasar +34 611 20 48 93 a otro agente" })).toBeVisible();
    await page.waitForTimeout(300);
    expect(await overflowOffenders(page), "@390px el modal se desborda").toEqual([]);
    await expectNoSeriousAxe(page);

    await go(page, channelPage, "+34 611 20 48 93", 2);
    await page.getByRole("region", { name: "Escalado a personas" }).getByRole("button", { name: "Añadir persona" }).click();
    await page.waitForTimeout(300);
    expect(await overflowOffenders(page), "@390px la página del canal se desborda").toEqual([]);
    await expectNoSeriousAxe(page);
  });
});
