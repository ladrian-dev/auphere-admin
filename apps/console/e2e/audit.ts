import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

/**
 * The CP-30 audit of one view (axe serious/critical, no overflow at 360 and
 * 1920 px, and the «30 % longer text» test), shared by the partner suite
 * (`a11y.spec.ts`) and the client console's (`lite.spec.ts`, spec 030).
 */
export async function overflowOffenders(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const out: string[] = [];
    if (document.documentElement.scrollWidth > vw + 1) out.push(`document scrollWidth ${document.documentElement.scrollWidth} > ${vw}`);
    for (const el of Array.from(document.querySelectorAll<HTMLElement>("body *"))) {
      const cs = getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden" || cs.position === "fixed") continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      // An element may be wider than the viewport only inside a scroll container.
      if (r.right > vw + 1 && !el.closest("[data-scroll-x], .overflow-x-auto, .overflow-auto, table, pre, code")) {
        out.push(`${el.tagName.toLowerCase()}${el.id ? `#${el.id}` : ""}.${String(el.className).split(" ").slice(0, 3).join(".")} right=${Math.round(r.right)}`);
        if (out.length > 5) break;
      }
    }
    return out;
  });
}

export async function auditView(page: Page, path: string) {
  const res = await page.goto(path);
  expect(res?.status(), `${path} responded ${res?.status()}`).toBeLessThan(400);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await expect(page.locator("main#main")).toBeVisible();

  const axe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
    .exclude("iframe")
    .analyze();
  const blocking = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(
    blocking.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`),
    `${path}: serious/critical axe violations`,
  ).toEqual([]);

  for (const width of [360, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    await page.waitForTimeout(150);
    expect(await overflowOffenders(page), `${path} @${width}px overflows`).toEqual([]);
  }
  // Prueba de «texto largo»: cada nodo visible dentro de <main> crece ~30 %
  // y el layout no puede desbordarse a 360 px. La app solo habla español e
  // inglés; esto NO añade un idioma, simula que una traducción sale más
  // larga que la otra, que entre esos dos ya pasa. Es lo que caza los
  // desbordamientos antes de que los vea un partner.
  await page.setViewportSize({ width: 360, height: 900 });
  await page.evaluate(() => {
    const walker = document.createTreeWalker(document.querySelector("main#main") ?? document.body, NodeFilter.SHOW_TEXT);
    const nodes: Text[] = [];
    while (walker.nextNode()) nodes.push(walker.currentNode as Text);
    for (const n of nodes) {
      const t = n.textContent ?? "";
      if (t.trim().length < 4) continue;
      // Chart labels (SVG) come from data, not copy — not subject to translation growth.
      if (n.parentElement?.closest("svg")) continue;
      // Palabras largas de verdad (14 caracteres), separadas por espacios.
      const extra = Math.ceil(t.trim().length * 0.3);
      const words = Math.max(1, Math.round(extra / 15));
      n.textContent = t + " adicionalmente".repeat(words);
    }
  });
  await page.waitForTimeout(100);
  expect(await overflowOffenders(page), `${path} @360px se desborda con el texto un 30 % más largo`).toEqual([]);
  await page.setViewportSize({ width: 1280, height: 800 });
}

