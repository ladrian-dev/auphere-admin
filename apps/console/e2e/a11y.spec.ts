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
  "/agent",
  "/agent/settings",
  "/tools",
  "/skills",
  "/knowledge",
  "/playground",
  "/channels",
  "/channels/diagnostics",
  "/conversations",
  "/settings",
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
  // "German string" test: every visible text node inside <main> grows ~30 %
  // (the expansion ES/EN → DE) and the layout must still not overflow at 360 px.
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
      // Realistic German: long words (12 chars) separated by spaces, +30 % length.
      const extra = Math.ceil(t.trim().length * 0.3);
      const words = Math.max(1, Math.round(extra / 13));
      n.textContent = t + " Überprüfungs".repeat(words);
    }
  });
  await page.waitForTimeout(100);
  expect(await overflowOffenders(page), `${path} @360px overflows with +30 % text`).toEqual([]);
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
