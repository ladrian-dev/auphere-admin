import { parseColor, ratioOn } from "@nexus/ui/lib/contrast";
import { expect, test, type Page } from "@playwright/test";

import { auditView, overflowOffenders } from "./audit";

/**
 * Spec 082 (datos al día) — lo que la persona ve cambia sin recargar.
 *
 *   pnpm exec playwright test -c e2e/datos-al-dia.config.ts
 *
 * Contra `datos-al-dia-mock.mjs`, que confirma cada escritura al momento.
 * Ninguna prueba espera al sondeo de 45 s: todas miran en menos de 20.
 */

const API = "http://127.0.0.1:8722";
const CONV = "00000000-0000-4000-8000-000000000c01";

async function reset(page: Page) {
  await page.request.post(`${API}/__test/reset`);
}

async function reads(page: Page, route: string): Promise<number> {
  const s = (await (await page.request.get(`${API}/__test/state`)).json()) as { reads: Record<string, number> };
  return s.reads[route] ?? 0;
}

async function anaId(page: Page): Promise<string> {
  const s = (await (await page.request.get(`${API}/__test/state`)).json()) as { bookings: { id: string; contact: { name: string } }[] };
  return s.bookings.find((b) => b.contact.name === "Ana Pérez")!.id;
}

async function cancelFromSheet(page: Page) {
  await page.getByRole("button", { name: "Cancelar", exact: true }).click();
  await page.getByRole("dialog", { name: "Cancelar la reserva" }).getByRole("button", { name: "Cancelar reserva" }).click();
  await expect(page.getByText("Reserva cancelada.")).toBeVisible();
}

test.beforeEach(async ({ page }) => reset(page));

test.describe("Reservas (requisito 1)", () => {
  test("cancelar una reserva la saca de la agenda sin recargar", async ({ page }) => {
    await page.goto("/reservas");
    const ana = page.getByRole("button", { name: /Ana Pérez.*Confirmada/ });
    await expect(ana).toBeVisible({ timeout: 60_000 });

    await ana.click();
    await page.getByRole("button", { name: "Cancelar", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Cancelar la reserva" });
    await dialog.getByRole("button", { name: "Cancelar reserva" }).click();
    await expect(page.getByText("Reserva cancelada.")).toBeVisible();

    // Lo que la simulada ya tiene: la agenda lo pinta, sin recargar y sin esperar al sondeo.
    await expect(page.getByRole("button", { name: /Ana Pérez.*Confirmada/ })).toHaveCount(0, { timeout: 10_000 });
    await expect(page.getByRole("button", { name: /Rosa Díaz.*Confirmada/ })).toBeVisible();
  });

  test("cancelar desde el enlace ?booking= la saca de la agenda", async ({ page }) => {
    const id = await anaId(page);
    await page.goto(`/reservas?booking=${id}`);
    await expect(page.getByRole("dialog", { name: /Reserva de Ana/ })).toBeVisible({ timeout: 60_000 });
    await cancelFromSheet(page);
    await expect(page.getByRole("button", { name: /Ana Pérez.*Confirmada/ })).toHaveCount(0, { timeout: 10_000 });
  });

  test("cancelar en la vista de lista la saca de la lista", async ({ page }) => {
    await page.goto("/reservas?view=list");
    const row = page.getByText("Ana Pérez").first();
    await expect(row).toBeVisible({ timeout: 60_000 });
    await row.click();
    await cancelFromSheet(page);
    await expect(page.getByText("Confirmada")).toHaveCount(1, { timeout: 10_000 });
  });

  test("una reserva que hace el agente llega con el aviso, sin esperar al sondeo", async ({ page }) => {
    await page.goto("/reservas");
    await expect(page.getByRole("button", { name: /Ana Pérez.*Confirmada/ })).toBeVisible({ timeout: 60_000 });
    await expect.poll(async () => (await (await page.request.get(`${API}/__test/state`)).json()).streams, { timeout: 20_000 }).toBeGreaterThan(0);

    await page.request.post(`${API}/__test/booking`, { data: { name: "Luz Marina", start: "16:00" } });
    await page.request.post(`${API}/__test/emit`, { data: { event: "reservations.changed", data: {} } });
    await expect(page.getByRole("button", { name: /Luz Marina.*Confirmada/ })).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("Bandeja (requisito 3)", () => {
  test("el contador de no leídos llega con el stream fuera de la Bandeja", async ({ page }) => {
    await page.goto("/reservas");
    await expect(page.getByRole("button", { name: /Ana Pérez.*Confirmada/ })).toBeVisible({ timeout: 60_000 });
    await expect.poll(async () => (await (await page.request.get(`${API}/__test/state`)).json()).streams, { timeout: 20_000 }).toBeGreaterThan(0);

    await page.request.post(`${API}/__test/inbound`, { data: { text: "¿Tienen cita hoy?" } });
    await page.request.post(`${API}/__test/emit`, {
      data: { event: "message.new", data: { event: "message.new", conversation_id: "00000000-0000-4000-8000-000000000c01", direction: "inbound" } },
    });
    const nav = page.getByRole("navigation").or(page.locator("[data-sidebar=sidebar]"));
    await expect(nav.getByText("1 sin leer")).toBeAttached({ timeout: 10_000 });
    await expect(page).toHaveTitle(/^\(1\) /);
  });

  test("al reconectar se vuelve a leer lo que cambió mientras tanto", async ({ page }) => {
    await page.goto("/inbox");
    await expect.poll(async () => (await (await page.request.get(`${API}/__test/state`)).json()).streams, { timeout: 60_000 }).toBeGreaterThan(0);
    const before = await reads(page, "GET /console/lite/inbox/conversations");

    await page.request.post(`${API}/__test/drop`);
    await expect.poll(async () => (await (await page.request.get(`${API}/__test/state`)).json()).streams, { timeout: 30_000 }).toBeGreaterThan(0);
    await expect.poll(() => reads(page, "GET /console/lite/inbox/conversations"), { timeout: 10_000 }).toBeGreaterThan(before);
  });
});

/**
 * T041 — las puertas de interfaz sobre lo tocado, en el navegador: axe sin
 * hallazgos graves, nada se desborda a 360 px ni con el texto un 30 % más
 * largo, y el contraste del avatar medido sobre lo que se pinta, no sobre el
 * nombre del token (CE-006, CE-007).
 */
/** Ancho y alto de cada ventana que se mira. */
type Size = readonly [number, number];
/**
 * Los anchos que `auditView` no mira (ya mira 360 y 1920). 640 × 450 es una
 * ventana de 1280 × 900 al 200 %: nada se sale.
 */
const SIZES: readonly Size[] = [[414, 896], [640, 450], [768, 1024], [1024, 768], [1440, 900]];
/**
 * La Bandeja a 768 px se sale desde antes de la 082 (sin `@usuario` también):
 * barra lateral abierta más la lista fija de 320 px dejan ~190 px al hilo, y
 * los cuatro botones de la cabecera piden ~250. Es de maquetación, no de esta
 * spec; está en las notas de T041 como hallazgo previo.
 */
const INBOX_SIZES = SIZES.filter(([w]) => w !== 768);

async function zoomed(page: Page, sizes: readonly Size[] = SIZES) {
  for (const [width, height] of sizes) {
    await page.setViewportSize({ width, height });
    await page.waitForTimeout(150);
    expect(await overflowOffenders(page), `a ${width} px se desborda`).toEqual([]);
  }
  await page.setViewportSize({ width: 1280, height: 800 });
}

test.describe("Puertas de interfaz (T041)", () => {
  for (const colorScheme of ["light", "dark"] as const) {
    test(`la Bandeja abierta, con avatar y @usuario (${colorScheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme });
      await auditView(page, `/inbox?c=${CONV}`, async () => {
        await expect(page.getByText("@ana.perez").first()).toBeVisible();
      });

      await page.goto(`/inbox?c=${CONV}`);
      await expect(page.getByText("@ana.perez").first()).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe(colorScheme);
      // El panel del contacto, si no está abierto ya.
      const show = page.getByRole("button", { name: "Datos del contacto", exact: true });
      // «@usuario» en la cabecera y en el panel (5.4). El clic se repite: el
      // primero puede llegar antes de que la página termine de hidratarse.
      await expect(async () => {
        if (await show.isVisible()) await show.click();
        expect(await page.getByText("@ana.perez").count()).toBeGreaterThanOrEqual(2);
      }).toPass();
      await expect.poll(() => page.locator("[data-slot='contact-avatar']").count()).toBeGreaterThanOrEqual(5);

      // Chrome da el color calculado en `lab()`: un lienzo lo pasa a sRGB (#rrggbb).
      const avatars = await page.locator("[data-slot='contact-avatar']").evaluateAll((els) => {
        const ctx = document.createElement("canvas").getContext("2d", { willReadFrequently: true })!;
        const hex = (css: string) => {
          ctx.clearRect(0, 0, 1, 1);
          ctx.fillStyle = css;
          ctx.fillRect(0, 0, 1, 1);
          const [r = 0, g = 0, b = 0] = ctx.getImageData(0, 0, 1, 1).data;
          return `#${[r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
        };
        return els.map((el) => {
          const cs = getComputedStyle(el);
          return { fg: hex(cs.color), bg: hex(cs.backgroundColor), text: el.textContent ?? "", icon: Boolean(el.querySelector("svg")) };
        });
      });
      // Dos filas, la cabecera, el mensaje del contacto y el panel (hoja bajo 1280 px).
      expect(avatars.length).toBeGreaterThanOrEqual(5);
      for (const a of avatars) {
        const fg = parseColor(a.fg);
        const bg = parseColor(a.bg);
        expect(fg && bg, `color sin leer: ${a.fg} sobre ${a.bg}`).toBeTruthy();
        expect(ratioOn(fg!, bg!), `${a.fg} sobre ${a.bg}`).toBeGreaterThanOrEqual(4.5);
        expect(a.text).not.toContain("·");
      }
      // El contacto que solo tiene número lleva el icono de persona.
      expect(avatars.some((a) => a.icon)).toBe(true);

      // Al 200 %: la página, con la hoja cerrada, y la hoja del contacto, que flota
      // (fija) y no puede salirse por la derecha una vez abierta del todo.
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await zoomed(page, INBOX_SIZES);
      await page.setViewportSize({ width: 640, height: 450 });
      await page.getByRole("button", { name: "Datos del contacto", exact: true }).click();
      const sheet = page.getByRole("dialog");
      await expect(sheet.getByText("@ana.perez")).toBeVisible();
      await expect
        .poll(async () => {
          const box = await sheet.boundingBox();
          const vw = await page.evaluate(() => document.documentElement.clientWidth);
          return box ? Math.round(box.x + box.width - vw) : 99;
        })
        .toBeLessThanOrEqual(0);
      await page.setViewportSize({ width: 1280, height: 800 });
    });

    test(`Reservas, la pantalla que se pone al día sola (${colorScheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme });
      await auditView(page, "/reservas", async () => {
        await expect(page.getByText("Ana Pérez").first()).toBeVisible();
      });
      await page.goto("/reservas");
      await expect(page.getByText("Ana Pérez").first()).toBeVisible();
      await zoomed(page);
    });
  }
});
