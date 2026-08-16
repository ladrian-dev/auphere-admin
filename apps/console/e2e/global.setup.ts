import { expect, test as setup } from "@playwright/test";

/** Log in once through the real form and persist the session cookie. */
setup("authenticate as a partner owner", async ({ page }) => {
  const email = process.env.E2E_EMAIL;
  const password = process.env.E2E_PASSWORD;
  if (!email || !password) throw new Error("set E2E_EMAIL and E2E_PASSWORD");
  await page.goto("/login");
  // Dev server: wait for hydration before submitting, or the native form
  // submit fires before React attaches the handler.
  await page.waitForLoadState("networkidle");
  await page.getByRole("textbox", { name: /correo|e-mail|email/i }).fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: /entrar|sign in|iniciar/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 90_000 });
  await expect(page.locator("main#main")).toBeVisible();
  await page.context().storageState({ path: "e2e/.auth/owner.json" });
});
