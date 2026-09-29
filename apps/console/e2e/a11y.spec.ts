import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/**
 * CP-30 acceptance, measured (PLAN-CONSOLE-V1):
 *
 *  1. zero **serious/critical** axe violations (WCAG 2.0/2.1/2.2 A+AA
 *     rule sets) on every main view;
 *  2. no horizontal scroll of the document at 360 px and 1920 px, and no
 *     visible element wider than the viewport (the "overflow" defect the
 *     design system exists to erase);
 *  3. every view renders in ES and EN (the locale cookie is honoured).
 *
 * The client-scoped views use the first client the partner has. Views
 * that legitimately have no data still render their empty state — that
 * IS the thing being audited.
 */

const CLIENT_VIEWS = [
  "",
  // Spec 018 (R3.1): los ajustes del agente viven dentro de «Agente», así
  // que auditar `/agent/settings` sería auditar dos veces la misma pantalla.
  "/agent",
  // Iteración 2 de la spec 017: `/tools` y `/skills` son ahora redirección
  // permanente a `/capabilities`, así que auditarlas sería auditar dos veces
  // la misma pantalla. Se audita donde vive cada cosa.
  "/capabilities",
  "/capabilities?all=1",
  "/integrations",
  "/knowledge",
  "/playground",
  "/channels",
  "/channels/diagnostics",
  "/conversations",
  // `/settings` se fue: los datos del cliente se editan en el Resumen, que
  // es la vista `""` de arriba y ya se audita.
] as const;

const PARTNER_VIEWS = [
  "/",
  "/clients",
  "/clients/new",
  "/usage",
  "/usage/alerts",
  "/audit",
  "/team",
  "/keys",
  "/billing",
  "/notifications",
] as const;

async function firstClientRef(page: Page): Promise<string> {
  await page.goto("/clients");
  const link = page.locator('a[href^="/clients/"]:not([href="/clients/new"])').first();
  await expect(link).toBeVisible();
  const href = await link.getAttribute("href");
  const ref = href?.split("/clients/")[1]?.split("/")[0];
  if (!ref) throw new Error("no client to audit — seed one first");
  return decodeURIComponent(ref);
}

async function overflowOffenders(page: Page): Promise<string[]> {
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

async function auditView(page: Page, path: string) {
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

test.describe("CP-30 — axe + overflow on every main view", () => {
  let ref = "";
  test.beforeAll(async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: "e2e/.auth/owner.json" });
    const page = await ctx.newPage();
    ref = await firstClientRef(page);
    await ctx.close();
  });

  for (const path of PARTNER_VIEWS) {
    test(`partner view ${path}`, async ({ page }) => auditView(page, path));
  }
  for (const seg of CLIENT_VIEWS) {
    test(`client view ${seg || "/"}`, async ({ page }) => auditView(page, `/clients/${encodeURIComponent(ref)}${seg}`));
  }

  test("every view renders in EN too (locale cookie)", async ({ page, context }) => {
    await context.addCookies([{ name: "nexus-console.locale", value: "en", domain: "localhost", path: "/" }]);
    for (const path of ["/", "/clients", "/usage", "/team", `/clients/${encodeURIComponent(ref)}/agent`]) {
      await page.goto(path);
      await expect(page.locator("main#main")).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("lang", /en/);
    }
  });

  // Spec 016 (T059): the dialogs of the block, opened, under axe.
  test("spec 016: the move-quota dialog and the model card pass axe when open", async ({ page }) => {
    // Spec 018 (R3.1): la tarjeta de modelo vive ahora dentro de «Agente».
    await page.goto(`/clients/${encodeURIComponent(ref)}/agent`);
    await expect(page.locator("main#main")).toBeVisible();
    const model = page.getByRole("radiogroup", { name: /Modelo|Model/ });
    if (await model.count()) {
      await model.getByRole("radio").last().click();
    }
    let axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "best-practice"]).exclude("iframe").analyze();
    expect(axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);

    await page.goto("/usage");
    await expect(page.locator("main#main")).toBeVisible();
    const qty = page.getByLabel(/Créditos a mover|Credits to move/);
    if ((await qty.count()) === 0) {
      // The move form needs two clients; the seeded partner may have one.
      test.info().annotations.push({ type: "skipped-part", description: "move dialog: the partner has fewer than two clients" });
      return;
    }
    await qty.fill("1");
    await page.getByRole("button", { name: /^Mover cupo$|^Move quota$/ }).click();
    const dialog = page.getByRole("alertdialog").or(page.getByRole("dialog"));
    await expect(dialog).toBeVisible();
    axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "best-practice"]).exclude("iframe").analyze();
    expect(axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([]);
    await page.keyboard.press("Escape");
  });

  // Spec 019 (T018): los **tres pasos** del alta, en los dos idiomas. El
  // barrido de arriba audita `/clients/new`, que es solo el primero: los
  // otros dos solo existen después de elegir y de rellenar, y son justo
  // donde vive el formulario.
  test("spec 019: los tres pasos del alta pasan axe en ES y EN", async ({ page, context }) => {
    for (const locale of ["es", "en"] as const) {
      // Solo la cookie de idioma: limpiarlas todas se lleva la sesión por
      // delante y el alta se convierte en la pantalla de entrar.
      await context.addCookies([
        { name: "nexus-console.locale", value: locale, domain: "localhost", path: "/" },
      ]);
      await page.goto("/clients/new");
      await expect(page.locator("main#main")).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("lang", new RegExp(locale));

      const siguiente = page.getByRole("button", { name: /^Continuar$|^Continue$/ });
      for (const paso of ["plantilla", "negocio", "revisión"]) {
        const axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
          .exclude("iframe")
          .analyze();
        expect(
          axe.violations
            .filter((v) => v.impact === "serious" || v.impact === "critical")
            .map((v) => `${v.id}: ${v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | ")}`),
          `alta · ${paso} [${locale}]`,
        ).toEqual([]);
        expect(await overflowOffenders(page), `alta · ${paso} [${locale}] @1280px`).toEqual([]);

        if (paso === "plantilla") {
          await page.getByRole("radio").first().click();
          await siguiente.click();
        } else if (paso === "negocio") {
          await page.getByLabel(/Nombre del negocio|Business name/).fill(`Axe ${locale} ${Date.now().toString(36)}`);
          const direccion = page.getByLabel(/Dirección|Address/);
          if (await direccion.count()) await direccion.fill("Calle Mayor 1");
          await siguiente.click();
        }
      }
    }
    await context.addCookies([
      { name: "nexus-console.locale", value: "es", domain: "localhost", path: "/" },
    ]);
  });

  // Spec 018 (T025): los tres catálogos **con filtro puesto**. La barra sin
  // filtrar ya la audita el barrido de arriba; lo que aquí se mira es el
  // estado que solo existe al filtrar — pastilla marcada, contador movido, y
  // el cartel de «nada coincide» con su salida.
  test("spec 018: the three catalogs pass axe with a filter on", async ({ page }) => {
    const base = `/clients/${encodeURIComponent(ref)}`;
    for (const path of [
      `${base}/capabilities?tab=active`,
      `${base}/capabilities?q=zzzz`,
      `${base}/integrations?tab=active`,
      `${base}/channels?tab=active`,
    ]) {
      await page.goto(path);
      await expect(page.locator("main#main")).toBeVisible();
      const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "best-practice"]).exclude("iframe").analyze();
      expect(
        axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id),
        `${path} con filtro puesto`,
      ).toEqual([]);
      // Y a 360 px, que es donde la barra de tres gestos tiene que envolver.
      await page.setViewportSize({ width: 360, height: 800 });
      expect(await overflowOffenders(page), `${path} @360px se desborda`).toEqual([]);
      await page.setViewportSize({ width: 1280, height: 800 });
    }
  });

  // Spec 018 (T031): las pantallas renombradas, **en los dos idiomas**. Esta
  // iteración solo cambia texto, y por eso mismo hace falta: «Habilidades» es
  // más largo que «Capacidades» en español y «Connectors» más que
  // «Integrations» no lo es, pero `auditView` mide a 360 px con el texto al
  // 130 %, que es donde una palabra de más rompe una fila que antes cabía.
  test("spec 018: the renamed screens hold up in ES and EN", async ({ page, context }) => {
    const base = `/clients/${encodeURIComponent(ref)}`;
    const rutas = [`${base}/capabilities`, `${base}/integrations`, `${base}/knowledge`, "/knowledge"];
    for (const locale of ["es", "en"] as const) {
      await context.clearCookies({ name: "nexus-console.locale" });
      await context.addCookies([{ name: "nexus-console.locale", value: locale, domain: "localhost", path: "/" }]);
      for (const path of rutas) await auditView(page, `${path}`);
    }
    await context.clearCookies({ name: "nexus-console.locale" });
  });

  test("keyboard: skip link and command palette", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: /saltar|skip/i });
    await expect(skip).toBeFocused();
    await page.keyboard.press("Meta+k");
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });
});
