import { expect, test, type Page } from "@playwright/test";

import { expectLongGermanFits, expectNoOverflow, expectNoSeriousAxe, expectReachableByTab, expectSolidFloatingLayer, preferLessGlassAndMotion } from "./fabrica-audit";

/**
 * Spec 047 (T168, T176 y T162) — la consola lite de Marta, del negocio, en un
 * navegador de verdad: «Agentes» (pausar con la cifra de conversaciones,
 * reanudar, la pausa del sistema explicada), «Negocio» (precio sin nombre,
 * horario con `If-Match` e `Idempotency-Key`, «Deshacer») y «Corregir esta
 * respuesta» en la Bandeja (el tipo antes de enviar, los datos personales que
 * bloquean, deshacer un dato). Cada pantalla: axe, 390 px, 200 %, teclado,
 * «Reducir transparencia/movimiento», sus estados y textos largos en alemán.
 *
 *   pnpm exec playwright test -c e2e/fabrica.config.ts --project=lite
 *
 * Contra `fabrica-mock.mjs`.
 */

const API = "http://127.0.0.1:8719";
const RECEPCION = "00000000-0000-4000-8000-0000000000a1";
const CONV = "00000000-0000-4000-8000-000000000c01";

async function mode(page: Page, parts: Record<string, string>) {
  await page.request.post(`${API}/__test/mode`, { data: parts });
}

async function state(page: Page) {
  return (await (await page.request.get(`${API}/__test/state`)).json()) as {
    pauses: { agent: string; confirm: boolean }[];
    keys: { section: string; key: string | null }[];
    corrections: { kind: string; status: string; lesson: string; scope: string }[];
  };
}

async function open(page: Page, path: string, heading: string | RegExp) {
  const res = await page.goto(path);
  expect(res?.status(), `${path} respondió ${res?.status()}`).toBeLessThan(400);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
}

test.describe("Spec 047 — la consola lite: Agentes, Negocio y corregir respuestas", () => {
  test.beforeEach(async ({ page }) => {
    await page.request.post(`${API}/__test/reset`);
    await page.setViewportSize({ width: 1280, height: 900 });
  });

  test("la barra lateral trae Agentes y Negocio, en el orden de la API", async ({ page }) => {
    await open(page, "/agentes", "Agentes");
    const links = page.getByRole("link", { name: /^(Panel|Bandeja de entrada|Agentes|Negocio|Consumo)$/ });
    await expect(links.first()).toBeVisible();
    const names = (await links.allTextContents()).map((s) => s.trim()).filter(Boolean);
    expect(names.indexOf("Agentes")).toBeGreaterThan(names.indexOf("Bandeja de entrada"));
    expect(names.indexOf("Negocio")).toBe(names.indexOf("Agentes") + 1);
  });

  test("Agentes: el estado de cada uno, pausar con confirmación y la cifra, reanudar, y la pausa del sistema explicada", async ({ page }) => {
    await open(page, "/agentes", "Agentes");
    const recepcion = page.getByRole("region", { name: "Recepción" });
    await expect(recepcion.getByText("Atendiendo")).toBeVisible();
    await expect(recepcion.getByText("2 conversaciones en curso")).toBeVisible();
    await expect(recepcion.getByRole("list", { name: "Números de Recepción" }).getByText("A todos")).toBeVisible();
    const ventas = page.getByRole("region", { name: "Ventas mayoristas" });
    await expect(ventas.getByText("Pausado · sin saldo")).toBeVisible();
    await expect(ventas.getByText(/Vuelve a atender solo en cuanto haya saldo/)).toBeVisible();
    await expect(ventas.getByRole("button", { name: "Reanudar" })).toHaveCount(0);
    // Nada de lo que es del partner (50.3).
    await expect(page.getByRole("button", { name: /Archivar|Publicar|Nuevo agente|Pedir saldo/ })).toHaveCount(0);
    await expectNoSeriousAxe(page, "/agentes");

    // Con el teclado: «Pausar» se alcanza, el modal retiene el foco y Escape lo cierra devolviéndolo.
    const pause = recepcion.getByRole("button", { name: "Pausar", exact: true });
    await expectReachableByTab(page, pause);
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: "¿Pausar Recepción?" });
    await expect(dialog.getByText(/Tiene 2 conversaciones en curso, que pasarán a la Bandeja/)).toBeVisible();
    // El foco no puede quedarse fuera (Base UI lo devuelve con centinelas: se mide dónde reposa).
    for (let i = 0; i < 6; i++) {
      await page.keyboard.press("Tab");
      await expect.poll(() => page.evaluate(() => !!document.activeElement?.closest("[role=dialog]")), { timeout: 2_000 }).toBe(true);
    }
    await expectNoSeriousAxe(page, "/agentes · pausar");
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(pause).toBeFocused();

    await pause.click();
    await page.getByRole("dialog").getByRole("button", { name: "Pausar el agente" }).click();
    await expect(recepcion.getByText("Pausado · a mano")).toBeVisible();
    await expect(recepcion.getByText("Lo pausó alguien de tu equipo desde la web.")).toBeVisible();
    expect((await state(page)).pauses).toEqual([{ agent: RECEPCION, confirm: true }]);

    await recepcion.getByRole("button", { name: "Reanudar", exact: true }).click();
    await expect(recepcion.getByText("Atendiendo")).toBeVisible();

    // Un número solo, con su propia confirmación.
    await recepcion.getByRole("button", { name: "Pausar el número" }).click();
    await page.getByRole("dialog", { name: "¿Pausar el número +34 611 20 48 93?" }).getByRole("button", { name: "Pausar el número" }).click();
    await expect(recepcion.getByRole("list", { name: "Números de Recepción" }).getByText("En pausa")).toBeVisible();

    await expectNoOverflow(page, "/agentes");
    await expectLongGermanFits(page, "/agentes");
  });

  test("Agentes: cargando, vacío y error con reintento", async ({ page }) => {
    await mode(page, { agents: "slow" });
    await page.goto("/agentes", { waitUntil: "commit" });
    await expect(page.getByRole("status", { name: "Cargando tus agentes" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Recepción" })).toBeVisible();

    await mode(page, { agents: "empty" });
    await open(page, "/agentes", "Agentes");
    await expect(page.getByText("Aún no tienes agentes")).toBeVisible();
    await expectNoSeriousAxe(page, "/agentes vacío");

    await mode(page, { agents: "fail" });
    await open(page, "/agentes", "Agentes");
    await expect(page.getByText("No pudimos leer tus agentes")).toBeVisible();
    await expectNoSeriousAxe(page, "/agentes con error");
    await mode(page, { agents: "ok" });
    await page.getByRole("button", { name: "Reintentar" }).click();
    await expect(page.getByRole("region", { name: "Recepción" })).toBeVisible();
  });

  test("Negocio: el precio sin el nombre, el horario con su revisión, «Deshacer» y las claves de idempotencia", async ({ page }) => {
    await open(page, "/negocio", "Negocio");
    for (const name of ["Horario", "Fechas especiales", "Servicios", "Sedes", "Últimos cambios"]) {
      await expect(page.getByRole("region", { name })).toBeVisible();
    }
    await expect(page.getByText("Lunes y martes de 10:00 a 20:00 · sábado de 10:00 a 14:00")).toBeVisible();
    await expect(page.getByRole("button", { name: /Duplicar/ })).toHaveCount(0);
    await expectNoSeriousAxe(page, "/negocio");

    const services = page.getByRole("region", { name: "Servicios" });
    await services.getByRole("button", { name: "Editar Corte clásico" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("textbox", { name: /Nombre/ })).toHaveAttribute("readonly", "");
    await expectNoSeriousAxe(page, "/negocio · servicio");
    const amount = dialog.getByRole("textbox", { name: /Importe/ });
    await amount.fill("18");
    await dialog.getByRole("button", { name: "Guardar servicio" }).click();
    await expect(services.getByText(/18,00/)).toBeVisible();
    const history = page.getByRole("region", { name: "Últimos cambios" });
    await expect(history.getByText(/Marta · desde la web/)).toBeVisible();

    await page.getByRole("region", { name: "Horario" }).getByRole("button", { name: "Guardar horario" }).click();
    await expect.poll(async () => (await state(page)).keys.map((k) => k.section)).toEqual(["services", "hours"]);
    for (const k of (await state(page)).keys) expect(k.key, `${k.section} sin Idempotency-Key`).toMatch(/.{8,}/);

    await history.getByRole("button", { name: "Deshacer el cambio de Servicios" }).click();
    await expect(services.getByText(/15,00/)).toBeVisible();
    await expect(history.getByText(/deshecho/)).toBeVisible();

    await expectNoOverflow(page, "/negocio");
    await expectLongGermanFits(page, "/negocio");
  });

  test("Negocio: cargando, vacío y error con reintento", async ({ page }) => {
    await mode(page, { business: "slow" });
    await page.goto("/negocio", { waitUntil: "commit" });
    await expect(page.getByRole("status", { name: "Cargando tu negocio" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Horario" })).toBeVisible();

    await mode(page, { business: "empty" });
    await open(page, "/negocio", "Negocio");
    await expect(page.getByRole("region", { name: "Servicios" }).getByText(/Todavía no hay servicios/)).toBeVisible();
    await expect(page.getByRole("region", { name: "Últimos cambios" }).getByText("Aún no hay cambios.")).toBeVisible();
    await expectNoSeriousAxe(page, "/negocio vacío");

    await mode(page, { business: "fail" });
    await open(page, "/negocio", "Negocio");
    await expect(page.getByText("No pudimos leer tu negocio")).toBeVisible();
    await mode(page, { business: "ok" });
    await page.getByRole("button", { name: "Reintentar" }).click();
    await expect(page.getByRole("region", { name: "Horario" })).toBeVisible();
  });

  test("Bandeja: «Corregir esta respuesta» — comportamiento con datos personales que bloquean, y un dato que se deshace", async ({ page }) => {
    await page.goto(`/inbox?c=${CONV}`);
    await expect(page.getByRole("log").getByText("No tenemos aparcamiento, lo siento.")).toBeVisible();
    const correct = page.getByRole("button", { name: "Corregir esta respuesta" });
    await expect(correct).toHaveCount(1);
    await correct.click();
    let dialog = page.getByRole("dialog", { name: "Corregir esta respuesta" });
    await expect(dialog).toBeVisible();
    await expectNoSeriousAxe(page, "corregir · escribir");
    await dialog.getByRole("textbox", { name: /Cómo debió responder/ }).fill("No des citas los festivos, llama a Ana al +34 600 11 22 33");
    await dialog.getByRole("radio", { name: /Solo este agente/ }).check();
    await dialog.getByRole("button", { name: "Continuar" }).click();
    await expect(dialog.getByText("Es un comportamiento")).toBeVisible();
    const pii = dialog.locator("[data-slot=correction-pii]");
    await expect(pii.getByText("Un teléfono en tu corrección: «+34 600 11 22 33»")).toBeVisible();
    await expect(pii.getByText("Un nombre en tu corrección: «Ana»")).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Enviar la propuesta" })).toBeDisabled();
    await expectNoSeriousAxe(page, "corregir · datos personales");
    await dialog.getByRole("textbox", { name: "Tu corrección" }).fill("No des citas los festivos");
    await dialog.getByRole("button", { name: "Enviar la propuesta" }).click();
    await expect(dialog.getByText(/Quien gestiona tus agentes lo verá en las mejoras del agente/)).toBeVisible();
    await dialog.locator("[data-slot=correction-done]").getByRole("button", { name: "Cerrar" }).click();
    await expect(dialog).toBeHidden();

    await correct.click();
    dialog = page.getByRole("dialog", { name: "Corregir esta respuesta" });
    await dialog.getByRole("textbox", { name: /Cómo debió responder/ }).fill("El aparcamiento más cercano está en la calle de atrás");
    await dialog.getByRole("radio", { name: /Todo el negocio/ }).check();
    await dialog.getByRole("button", { name: "Continuar" }).click();
    await expect(dialog.getByText("Es un dato")).toBeVisible();
    await expect(dialog.getByRole("textbox", { name: /Lo que preguntó el cliente/ })).toHaveValue("¿Hay aparcamiento cerca del local?");
    await dialog.getByRole("button", { name: "Guardar el dato" }).click();
    await expect(dialog.getByText("Hecho. Recepción lo sabe desde el siguiente mensaje.")).toBeVisible();
    await dialog.getByRole("button", { name: "Deshacer" }).click();
    await expect(dialog.getByText("Deshecho. El agente vuelve a responder como antes.")).toBeVisible();
    // Escape cierra el modal (47.5).
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();

    const sent = (await state(page)).corrections.map((c) => [c.kind, c.status, c.scope, c.lesson]);
    expect(sent).toEqual([
      ["behavior", "proposed", "agent", "No des citas los festivos"],
      ["data", "undone", "business", "El aparcamiento más cercano está en la calle de atrás"],
    ]);
  });

  test("Bandeja: la vista en vivo dice «Reconectando…» si se cae el directo", async ({ page }) => {
    await mode(page, { stream: "down" });
    await page.goto(`/inbox?c=${CONV}`);
    await expect(page.getByText("Reconectando…")).toBeVisible();
    await expect(page.getByRole("log").getByText("No tenemos aparcamiento, lo siento.")).toBeVisible();
  });

  test("«Reducir transparencia» y «Reducir movimiento»: el menú flotante pasa a sólido y sin animación", async ({ page }) => {
    await preferLessGlassAndMotion(page);
    await open(page, "/agentes", "Agentes");
    await expectSolidFloatingLayer(page, () => page.getByRole("button", { name: "marta@cultor.example" }).click());
    await expectNoSeriousAxe(page, "/agentes sin vidrio");
  });
});
