import { defineConfig, devices } from "@playwright/test";

/**
 * CP-30 — accessibility, responsive and overflow gate over the REAL app.
 *
 * Runs against an already-running console (``pnpm dev`` on 3110, API on
 * 8000 with the console enabled) — it never boots servers itself, so the
 * same suite works locally and against a preview URL. Credentials come
 * from env (``E2E_EMAIL`` / ``E2E_PASSWORD``); nothing is hard-coded.
 *
 *   pnpm test:e2e
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "e2e/.report" }]],
  timeout: 120_000,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3110",
    trace: "retain-on-failure",
    locale: process.env.E2E_LOCALE ?? "es-ES",
  },
  projects: [
    { name: "setup", testMatch: /global\.setup\.ts/ },
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], storageState: "e2e/.auth/owner.json" },
      dependencies: ["setup"],
    },
  ],
});
