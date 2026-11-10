import { generateKeyPairSync } from "node:crypto";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

/**
 * Spec 047 (T041) — la barra de guardado del agente y el aviso de conflicto,
 * en un navegador de verdad, contra la API simulada de `agent-draft-mock.mjs`.
 *
 *   pnpm exec playwright test -c e2e/agent-draft.config.ts
 *
 * Como `shell.config.ts`: levanta la API simulada y un `next dev` apuntando a
 * ella, con una clave de firma de usar y tirar y una cookie de sesión que la
 * simulada acepta. Puertos propios (3112 y 8712) para no pisar otra consola.
 * La consola de hoy por defecto: la ola 1 llega a todos los partners.
 */
const ROOT = path.resolve(__dirname, "..");
const WEB_PORT = 3112;
const API_PORT = 8712;
const signingKey = generateKeyPairSync("ed25519").privateKey.export({ type: "pkcs8", format: "pem" }).toString();

export default defineConfig({
  testDir: ".",
  // `.e2e.ts`, not `.spec.ts`: the suite of always (`playwright.config.ts`)
  // runs against a real API, which has no `/__test/*` to play the other tab.
  testMatch: /agent-draft\.e2e\.ts/,
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
  projects: [{ name: "agent-draft" }],
  webServer: [
    {
      command: "node e2e/agent-draft-mock.mjs",
      cwd: ROOT,
      url: `http://127.0.0.1:${API_PORT}/health`,
      env: { MOCK_API_PORT: String(API_PORT), MOCK_CONSOLE_VERSION: process.env.MOCK_CONSOLE_VERSION ?? "v1" },
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
