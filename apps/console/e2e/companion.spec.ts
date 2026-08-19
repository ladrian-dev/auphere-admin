import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";

/**
 * CO-03 acceptance over the real app — the same bar CP-30 set for the 22
 * console views, applied to the drawer:
 *
 *  1. zero **serious/critical** axe violations with the drawer OPEN (a
 *     dialog is exactly where a11y regressions hide, because the audit of
 *     the page behind it never opens it);
 *  2. no horizontal overflow at 360 px and 1920 px, and none with the
 *     German-string expansion (+30 %);
 *  3. the keyboard contract of §14: ⌘J opens, focus is trapped, `Esc`
 *     closes, and the width grabber responds to arrows — WCAG 2.2 2.5.7
 *     forbids a drag-only control;
 *  4. ES and EN both render.
 *
 * What is NOT here, and why: the confirmation flow end to end. CO-04 has
 * not built `hitl.requested` yet, so nothing can emit one against a live
 * API. That path is covered by the unit tests with contract fixtures
 * (`src/components/companion/__tests__/`) and becomes an e2e case in
 * Phase 2, when the two halves meet.
 */
const DRAWER = '[data-slot="sheet-content"]';

/**
 * Wait for the opening orchestration to finish.
 *
 * `toBeVisible()` resolves the moment the popup is in the DOM, which is the
 * START of the 200 ms fade, not the end. Auditing then samples half-faded
 * pixels and every reading is wrong in the same direction: axe read the
 * near-black title as `#a4a9a4` on `#e7eaea` (1.97:1) when the settled
 * colours are near-black on white (~19:1), and the focus trap is not armed
 * yet either. §14 budgets one opening orchestration at =300 ms, so waiting
 * for it to settle is the honest gate, not a sleep.
 */
async function settled(page: Page): Promise<void> {
  await expect(page.locator(DRAWER)).toBeVisible();
  await page.waitForFunction(
    (sel) => {
      const el = document.querySelector(sel);
      if (!el) return false;
      const cs = getComputedStyle(el);
      return cs.opacity === "1" && cs.transform !== "none" ? true : cs.opacity === "1";
    },
    DRAWER,
    { timeout: 5_000 },
  );
  // One more frame so the composited layer is flat before anything samples it.
  await page.waitForTimeout(120);
}

async function openDrawer(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.locator("main#main")).toBeVisible();
  await page.getByRole("button", { name: /companion/i }).first().click();
  await settled(page);
}

async function overflowOffenders(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const out: string[] = [];
    if (document.documentElement.scrollWidth > vw + 1) {
      out.push(`document scrollWidth ${document.documentElement.scrollWidth} > ${vw}`);
    }
    for (const el of Array.from(document.querySelectorAll<HTMLElement>("body *"))) {
      const cs = getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden" || cs.position === "fixed") continue;
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (r.right > vw + 1 && !el.closest("[data-scroll-x], .overflow-x-auto, .overflow-auto, table, pre, code")) {
        out.push(`${el.tagName.toLowerCase()}.${String(el.className).split(" ").slice(0, 3).join(".")} right=${Math.round(r.right)}`);
        if (out.length > 5) break;
      }
    }
    return out;
  });
}

test.describe("CO-03 — the Companion drawer", () => {
  test("zero serious/critical axe violations with the drawer open", async ({ page }) => {
    await openDrawer(page);
    const axe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
      .exclude("iframe")
      .analyze();
    const blocking = axe.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(
      blocking.map((v) => `${v.id} (${v.impact}): ${v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | ")}`),
      "serious/critical axe violations in the Companion drawer",
    ).toEqual([]);
  });

  test("the empty state suggests from the page it was opened on, not generically", async ({ page }) => {
    // §14 forbids generic suggestions. Two different routes must not
    // produce the same three.
    await openDrawer(page);
    const home = await page.locator(DRAWER).getByRole("button").allInnerTexts();
    await page.keyboard.press("Escape");
    await page.goto("/usage");
    await expect(page.locator("main#main")).toBeVisible();
    await page.getByRole("button", { name: /companion/i }).first().click();
    await settled(page);
    const usage = await page.locator(DRAWER).getByRole("button").allInnerTexts();
    expect(usage.join("|")).not.toEqual(home.join("|"));
  });

  test("keyboard: ⌘J opens, focus is trapped, Esc closes", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("main#main")).toBeVisible();
    await page.keyboard.press("Meta+j");
    const drawer = page.locator(DRAWER);
    await settled(page);

    // Focus trap: tabbing many times must never leave the dialog.
    //
    // Measured, not asserted from the source: Base UI contains focus with
    // guard sentinels (`data-base-ui-focus-guard`, `aria-hidden`) that sit
    // OUTSIDE the popup element and bounce focus back from their own focus
    // handler. Reading `activeElement` synchronously after `press("Tab")`
    // catches that hand-off in flight and reports a false escape — and
    // because the next Tab is then pressed from that intermediate spot, the
    // drift compounds until focus really is on page content.
    //
    // What a focus trap actually guarantees is CONTAINMENT: focus cannot
    // come to rest outside. Polled that way this drawer is 20/20 clean.
    for (let i = 0; i < 25; i += 1) {
      await page.keyboard.press("Tab");
      await expect
        .poll(
          () => page.evaluate((sel) => !!document.activeElement?.closest(sel), DRAWER),
          { timeout: 2_000, message: `focus came to rest outside the drawer after ${i + 1} tabs` },
        )
        .toBe(true);
    }

    await page.keyboard.press("Escape");
    await expect(drawer).toHaveCount(0);
  });

  test("the width grabber works with the keyboard (WCAG 2.2 2.5.7)", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await openDrawer(page);
    const handle = page.getByRole("separator", { name: /ancho|width/i });
    await expect(handle).toBeVisible();
    await handle.focus();
    const before = Number(await handle.getAttribute("aria-valuenow"));
    await page.keyboard.press("ArrowLeft");
    const after = Number(await handle.getAttribute("aria-valuenow"));
    expect(after).toBeGreaterThan(before);

    // …and it persists across a reload.
    await page.reload();
    await page.getByRole("button", { name: /companion/i }).first().click();
    await settled(page);
    const restored = Number(await page.getByRole("separator", { name: /ancho|width/i }).getAttribute("aria-valuenow"));
    expect(restored).toBe(after);
  });

  test("the timeline is a polite log and the assertive region starts empty", async ({ page }) => {
    await openDrawer(page);
    const log = page.getByRole("log");
    await expect(log).toHaveAttribute("aria-live", "polite");
    // Assertive is reserved for `hitl.requested` and nothing else, so with
    // no pending confirmation it must be silent.
    // Scoped to the drawer on purpose: Next renders its own
    // `#__next-route-announcer__` with the same attribute, so a bare
    // selector matches two elements and says nothing about ours.
    const assertive = page.locator(DRAWER).locator('[aria-live="assertive"]');
    await expect(assertive).toHaveCount(1);
    await expect(assertive).toHaveText("");
  });

  test("no horizontal overflow at 360 px and 1920 px, nor with +30 % text", async ({ page }) => {
    await openDrawer(page);
    for (const width of [360, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      await page.waitForTimeout(150);
      expect(await overflowOffenders(page), `drawer @${width}px overflows`).toEqual([]);
    }

    await page.setViewportSize({ width: 360, height: 900 });
    await page.evaluate((sel) => {
      const root = document.querySelector(sel) ?? document.body;
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      const nodes: Text[] = [];
      while (walker.nextNode()) nodes.push(walker.currentNode as Text);
      for (const n of nodes) {
        const t = n.textContent ?? "";
        if (t.trim().length < 4) continue;
        if (n.parentElement?.closest("svg")) continue;
        const extra = Math.ceil(t.trim().length * 0.3);
        const words = Math.max(1, Math.round(extra / 13));
        n.textContent = t + " Überprüfungs".repeat(words);
      }
    }, DRAWER);
    await page.waitForTimeout(100);
    expect(await overflowOffenders(page), "drawer @360px overflows with +30 % text").toEqual([]);
  });

  test("the drawer renders in English too", async ({ page, context }) => {
    await context.addCookies([{ name: "nexus-console.locale", value: "en", domain: "localhost", path: "/" }]);
    await openDrawer(page);
    await expect(page.locator(DRAWER)).toContainText(/Consult|Build/);
  });

  test("the active thread travels in the URL so it can be shared", async ({ page }) => {
    await openDrawer(page);
    const composer = page.getByRole("textbox", { name: /companion|mensaje|message/i });
    await composer.fill("¿cuántos clientes tengo?");
    await composer.press("Enter");
    // The turn starts (202) and the thread id lands in the query string.
    await expect
      .poll(() => new URL(page.url()).searchParams.get("companion"), { timeout: 30_000 })
      .not.toBeNull();
  });
});
