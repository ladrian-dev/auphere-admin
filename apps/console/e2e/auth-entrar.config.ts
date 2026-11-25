import { generateKeyPairSync } from "node:crypto";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

/**
 * Spec 066 — Entrar con el líquido vivo, en un navegador de verdad.
 *
 *   pnpm exec playwright test -c e2e/auth-entrar.config.ts
 *
 * Levanta la API simulada de las páginas públicas (`auth-mock.mjs`) y un
 * `next dev` apuntando a ella, con una clave de firma de usar y tirar. Sin
 * sesión: son las páginas de quien todavía no ha entrado. Puertos propios (3112
 * y 8712) para no pisar otra consola.
 */
const ROOT = path.resolve(__dirname, "..");
const WEB_PORT = 3112;
const API_PORT = 8712;
const signingKey = generateKeyPairSync("ed25519").privateKey.export({ type: "pkcs8", format: "pem" }).toString();

export default defineConfig({
  testDir: ".",
  testMatch: /auth-entrar\.e2e\.ts/,
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
  },
  webServer: [
    {
      command: "node e2e/auth-mock.mjs",
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
        // Spec 067: el alta, que en staging está encendida.
        NEXUS_SIGNUP_ENABLED: "true",
      },
      reuseExistingServer: false,
      stdout: "ignore",
      stderr: "pipe",
    },
  ],
});
