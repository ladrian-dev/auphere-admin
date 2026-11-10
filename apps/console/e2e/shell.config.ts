import { generateKeyPairSync } from "node:crypto";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

/**
 * Spec 047 (T007, T008) — el marco nuevo en un navegador de verdad, contra la
 * API simulada del contrato (`mock-api.mjs`).
 *
 *   pnpm exec playwright test -c e2e/shell.config.ts
 *
 * La suite de siempre (`playwright.config.ts`) corre contra una consola y una
 * API reales y necesita un partner con la consola nueva activada para
 * `shell.spec.ts`. Esta configuración la hace reproducible antes de eso: levanta
 * la API simulada y un `next dev` apuntando a ella, con una clave de firma de
 * usar y tirar (la API simulada no la comprueba), y entra con una cookie de
 * sesión que la API simulada acepta. Puertos propios (3111 y 8711) para no
 * pisar una consola que ya esté corriendo en 3110.
 */
const ROOT = path.resolve(__dirname, "..");
const WEB_PORT = 3111;
const API_PORT = 8711;
const signingKey = generateKeyPairSync("ed25519").privateKey.export({ type: "pkcs8", format: "pem" }).toString();

export default defineConfig({
  testDir: ".",
  testMatch: /shell\.spec\.ts/,
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
  projects: [{ name: "shell" }],
  webServer: [
    {
      command: "node e2e/mock-api.mjs",
      cwd: ROOT,
      url: `http://127.0.0.1:${API_PORT}/health`,
      env: { MOCK_API_PORT: String(API_PORT), MOCK_CONSOLE_VERSION: process.env.MOCK_CONSOLE_VERSION ?? "v2" },
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
