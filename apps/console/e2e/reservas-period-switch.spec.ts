import { expect, test, type Page } from "@playwright/test";

/**
 * Spec 056 (10.2) — el fallo de Reservas del 6 de noviembre: QA cambiaba de
 * periodo y pulsaba «Hoy», y la agenda salía con la frase técnica de Next.
 * Esta prueba repite esa secuencia diez veces seguidas sobre la consola de
 * verdad, como una persona de cliente, y las diez tienen que cargar.
 *
 * **Manual, contra staging**: no corre en CI ni en `pnpm test:e2e` sin su
 * variable (se salta). Necesita una persona de cliente con Reservas:
 *
 *   E2E_RESERVAS_SWITCH=1 E2E_BASE_URL=https://console.staging.auphere.com \
 *   E2E_CLIENT_EMAIL=… E2E_CLIENT_PASSWORD=… \
 *   pnpm exec playwright test e2e/reservas-period-switch.spec.ts --project=desktop --no-deps
 *
 * Si alguna vuelta falla, el registro de la consola tiene la línea
 * `console.request_error` con el `digest` de la pantalla de error
 * (`src/instrumentation.ts`): ahí está la causa.
 */
test.skip(!process.env.E2E_RESERVAS_SWITCH, "manual, contra staging: E2E_RESERVAS_SWITCH=1 (spec 056, 10.2)");
// Entra ella misma: no hereda la sesión del partner del proyecto `desktop`.
test.use({ storageState: { cookies: [], origins: [] } });

const ROUNDS = 10;
const PERIOD = /^(Periodo|Period)$/;
const VIEW = /^(Vista|View)$/;
/** «Semana › Mes › Lista › Cuadrícula › Día › Día siguiente › Hoy». */
const STEPS: { label: string; group?: RegExp; name: RegExp }[] = [
  { label: "Semana", group: PERIOD, name: /^(Semana|Week)$/ },
  { label: "Mes", group: PERIOD, name: /^(Mes|Month)$/ },
  { label: "Lista", group: VIEW, name: /^(Lista|List)$/ },
  { label: "Cuadrícula", group: VIEW, name: /^(Cuadrícula|Grid)$/ },
  { label: "Día", group: PERIOD, name: /^(Día|Day)$/ },
  { label: "Día siguiente", name: /^(Día siguiente|Next day)$/ },
  { label: "Hoy", name: /^(Hoy|Today)$/ },
];
/** Lo que dice una pantalla que no cargó, en los dos idiomas, y la frase de Next. */
const BROKEN = /No pudimos cargar Reservas|We couldn't load Bookings|No se pudo cargar esta pantalla|This screen could not load|Algo ha fallado|Something went wrong|Server Components|Application error/;

async function signIn(page: Page) {
  const email = process.env.E2E_CLIENT_EMAIL;
  const password = process.env.E2E_CLIENT_PASSWORD;
  if (!email || !password) throw new Error("set E2E_CLIENT_EMAIL and E2E_CLIENT_PASSWORD (a client person with Reservas)");
  await page.goto("/login");
  await page.waitForLoadState("networkidle");
  await page.getByRole("textbox", { name: /correo|e-mail|email/i }).fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole("button", { name: /entrar|sign in|iniciar/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 90_000 });
}

test("diez veces «Semana › Mes › Lista › Cuadrícula › Día › Día siguiente › Hoy», y las diez cargan", async ({ page }) => {
  test.setTimeout(15 * 60_000);
  await signIn(page);
  await page.goto("/reservas");
  const toolbar = page.getByRole("toolbar", { name: /^(Fecha y vista|Date and view)$/ });
  await expect(toolbar).toBeVisible({ timeout: 30_000 });

  for (let round = 1; round <= ROUNDS; round++) {
    for (const step of STEPS) {
      const where = `vuelta ${round}, «${step.label}»`;
      const scope = step.group ? toolbar.getByRole("group", { name: step.group }) : toolbar;
      await scope.getByRole("button", { name: step.name }).click();
      await page.waitForLoadState("load");
      await expect(toolbar, where).toBeVisible({ timeout: 30_000 });
      await expect(page.getByText(BROKEN), where).toHaveCount(0);
    }
  }
});
