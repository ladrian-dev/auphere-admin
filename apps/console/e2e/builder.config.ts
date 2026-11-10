import { generateKeyPairSync } from "node:crypto";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

/**
 * Spec 047 (T081) — el constructor de agentes de la consola nueva en un
 * navegador de verdad, contra la API simulada de `builder-mock.mjs`:
 *
 *   pnpm exec playwright test -c e2e/builder.config.ts
 *
 * Como `agent-draft.config.ts`: levanta la API simulada y un `next dev`
 * apuntando a ella, con una clave de firma de usar y tirar y una cookie de
 * sesión que la simulada acepta. Puertos propios (3114 y 8714) para no pisar
 * otra consola ni las otras suites.
 */
const ROOT = path.resolve(__dirname, "..");
const WEB_PORT = 3114;
const API_PORT = 8714;
const signingKey = generateKeyPairSync("ed25519").privateKey.export({ type: "pkcs8", format: "pem" }).toString();

export default defineConfig({
  testDir: ".",
  // `.e2e.ts`, no `.spec.ts`: la suite de siempre (`playwright.config.ts`) va
  // contra una API de verdad, que no tiene `/__test/*`.
  testMatch: /builder\.e2e\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 180_000,
  expect: { timeout: 20_000 },
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
  projects: [{ name: "builder" }],
  webServer: [
    {
      command: "node e2e/builder-mock.mjs",
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
