import { generateKeyPairSync } from "node:crypto";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

/**
 * Spec 047 (T065, T067) — la lista de clientes, la cabecera con sus pestañas y
 * el Panel de la consola nueva en un navegador de verdad, contra la API
 * simulada del contrato (`client-records-mock-api.mjs`):
 *
 *   pnpm exec playwright test -c e2e/client-records.config.ts
 *
 * Igual que `clients-v2.config.ts`, con sus propios puertos (3113 y 8713) para
 * no pisar ni la consola de 3110 ni las otras suites.
 */
const ROOT = path.resolve(__dirname, "..");
const WEB_PORT = 3113;
const API_PORT = 8713;
const signingKey = generateKeyPairSync("ed25519").privateKey.export({ type: "pkcs8", format: "pem" }).toString();

export default defineConfig({
  testDir: ".",
  testMatch: /client-records\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: `http://localhost:${WEB_PORT}`,
    locale: "es-ES",
    timezoneId: "Europe/Madrid",
    trace: "retain-on-failure",
    storageState: {
      cookies: [
        {
          name: "nexus-console.session",
          value: "e2e-contract-mock",
          domain: "localhost",
          path: "/",
          expires: -1,
          httpOnly: true,
          secure: false,
          sameSite: "Lax",
        },
      ],
      origins: [],
    },
  },
  projects: [{ name: "client-records" }],
  webServer: [
    {
      command: "node e2e/client-records-mock-api.mjs",
      cwd: ROOT,
      url: `http://127.0.0.1:${API_PORT}/health`,
      env: { MOCK_API_PORT: String(API_PORT) },
      reuseExistingServer: false,
      stdout: "ignore",
      stderr: "pipe",
    },
    {
      command: `pnpm exec next dev -p ${WEB_PORT}`,
      cwd: ROOT,
      url: `http://localhost:${WEB_PORT}/healthz`,
      timeout: 240_000,
      env: {
        NEXUS_BACKEND_URL: `http://127.0.0.1:${API_PORT}`,
        NEXUS_CONSOLE_ORIGIN: `http://localhost:${WEB_PORT}`,
        NEXUS_CONSOLE_JWT_PRIVATE_KEY: signingKey,
      },
      reuseExistingServer: false,
      stdout: "ignore",
      stderr: "pipe",
    },
  ],
});
