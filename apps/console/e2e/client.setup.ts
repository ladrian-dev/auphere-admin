import { expect, test as setup } from "@playwright/test";

/**
 * Spec 030 (T105): sign the client person in ONCE and persist the session.
 *
 * Signing in before every test was what the first `lite.spec.ts` did, and it
 * cannot work: the login allows 10 attempts per minute per e-mail
 * (`LOGIN_ATTEMPTS_PER_MINUTE`), and the suite has more tests than that.
 */
setup("authenticate as a client person", async ({ page }) => {
  const email = process.env.E2E_CLIENT_EMAIL;
  const password = process.env.E2E_CLIENT_PASSWORD;
  if (!email || !password) throw new Error("set E2E_CLIENT_EMAIL and E2E_CLIENT_PASSWORD (a client person, spec 030)");
  await page.goto("/login");
  // Dev server: wait for hydration before submitting (see global.setup.ts).
  await page.waitForLoadState("networkidle");
  await page.getByRole("textbox", { name: /correo|e-mail|email/i }).fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: /entrar|sign in|iniciar/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 90_000 });
  await expect(page.locator("main#main")).toBeVisible();
  await page.context().storageState({ path: "e2e/.auth/client.json" });
});
