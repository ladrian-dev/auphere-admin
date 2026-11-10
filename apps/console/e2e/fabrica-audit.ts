import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

import { overflowOffenders } from "./audit";

/**
 * Spec 047 (T162; requisitos 47.5 a 47.11 y CE-010) — la auditoría de cada
 * pantalla nueva, compartida por `fabrica-lite.e2e.ts` y
 * `fabrica-partner.e2e.ts`:
 *
 * - axe sin incidencias graves ni críticas (WCAG 2.2 AA);
 * - sin desbordamiento horizontal a 390 px ni al 200 % (1280 × 800 al 200 %
 *   deja 640 × 400 px CSS);
 * - con «Reducir transparencia» y «Reducir movimiento»: la capa flotante pasa a
 *   sólida y las transiciones se apagan;
 * - con textos largos en alemán: la consola habla español e inglés, así que se
 *   simula una traducción larga alargando cada texto un 35 % con palabras
 *   compuestas alemanas de verdad, y la pantalla no puede desbordarse a 390 px.
 */
export async function expectNoSeriousAxe(page: Page, label = "") {
  // Los avisos (toasts) se van solos: se audita la pantalla, no su despedida.
  await expect(page.locator("[data-sonner-toast]")).toHaveCount(0, { timeout: 15_000 });
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
    .exclude("iframe")
    .analyze();
  const blocking = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(
    blocking.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`),
    `${label}: incidencias graves o críticas de axe`,
  ).toEqual([]);
}

/** A 390 px (el ancho mínimo de la consola, 47.7) y al 200 % de zoom, nada se sale. */
export async function expectNoOverflow(page: Page, label = "") {
  for (const size of [
    { width: 390, height: 844 },
    { width: 640, height: 400 },
  ]) {
    await page.setViewportSize(size);
    await page.waitForTimeout(200);
    expect(await overflowOffenders(page), `${label} @${size.width}px se desborda`).toEqual([]);
  }
  await page.setViewportSize({ width: 1280, height: 900 });
}

/** «Reducir transparencia» (CDP: Playwright no la emula aún) y «Reducir movimiento». */
export async function preferLessGlassAndMotion(page: Page) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setEmulatedMedia", {
    features: [
      { name: "prefers-reduced-transparency", value: "reduce" },
      { name: "prefers-reduced-motion", value: "reduce" },
    ],
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
}

/** El menú de perfil, abierto con esas preferencias: sólido, sin desenfoque y sin animación. */
export async function expectSolidFloatingLayer(page: Page, open: () => Promise<void>) {
  await open();
  const menu = page.locator("[data-slot=dropdown-menu-content]").first();
  await expect(menu).toBeVisible();
  const style = await menu.evaluate((el) => {
    const cs = getComputedStyle(el);
    return { background: cs.backgroundColor, filter: cs.backdropFilter, animation: cs.animationDuration, transition: cs.transitionDuration };
  });
  expect(/\/\s*0?\.\d+\)$|rgba\([^)]*,\s*0?\.\d+\)$/.test(style.background), `fondo del menú: ${style.background}`).toBe(false);
  expect(style.filter === "none" || style.filter.includes("blur(0px)"), `desenfoque del menú: ${style.filter}`).toBe(true);
  for (const d of [style.animation, style.transition]) expect(parseFloat(d) || 0).toBeLessThan(0.02);
  await page.keyboard.press("Escape");
  await expect(page.locator("[data-slot=dropdown-menu-content]")).toHaveCount(0);
}

// Palabras compuestas como las de una interfaz en alemán (hasta 20 letras): lo
// que de verdad sale al traducir botones y cabeceras, no un caso de laboratorio.
const GERMAN = ["Weiterleitungsregeln", "Öffnungszeiten", "Kundendienst", "Geschäftsführung", "Datenschutzerklärung", "Sonderöffnungstage"];

/**
 * Textos largos en alemán: cada texto visible de `<main>` crece un 35 % con
 * palabras compuestas, que es donde una fila que antes cabía se rompe.
 */
export async function expectLongGermanFits(page: Page, label = "") {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate((words) => {
    const walker = document.createTreeWalker(document.querySelector("main#main") ?? document.body, NodeFilter.SHOW_TEXT);
    const nodes: Text[] = [];
    while (walker.nextNode()) nodes.push(walker.currentNode as Text);
    nodes.forEach((n, i) => {
      const text = n.textContent ?? "";
      if (text.trim().length < 3 || n.parentElement?.closest("svg, script, style")) return;
      const extra = Math.ceil(text.trim().length * 0.35);
      const parts: string[] = [];
      let size = 0;
      for (let k = 0; size < extra; k++) {
        const w = words[(i + k) % words.length]!;
        parts.push(w);
        size += w.length + 1;
      }
      n.textContent = `${text} ${parts.join(" ")}`;
    });
    document.documentElement.lang = "de";
  }, GERMAN);
  await page.waitForTimeout(150);
  expect(await overflowOffenders(page), `${label} @390px se desborda con textos largos en alemán`).toEqual([]);
  await page.setViewportSize({ width: 1280, height: 900 });
}

/** El teclado llega a `target` con Tab desde el principio del contenido, sin trampas. */
export async function expectReachableByTab(page: Page, target: ReturnType<Page["getByRole"]>, max = 60) {
  await page.locator("main#main").focus();
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    if (await target.evaluate((el) => el === document.activeElement).catch(() => false)) return;
  }
  throw new Error("el teclado no llega al control");
}
