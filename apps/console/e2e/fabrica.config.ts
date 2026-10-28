import { generateKeyPairSync } from "node:crypto";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

/**
 * Spec 047 (T162, T165, T168, T174, T176 y T178) — las pantallas que cierran la
 * fábrica de agentes, en un navegador de verdad, contra la API simulada de
 * `fabrica-mock.mjs`:
 *
 *   pnpm exec playwright test -c e2e/fabrica.config.ts
 *
 * Dos personas, una por proyecto, con la misma API simulada y el mismo
 * `next dev`: `lite` es Marta, del negocio (Agentes, Negocio y «Corregir esta
 * respuesta»); `partner` es Luis, owner con la consola nueva (Recepción,
 * Rendimiento, Mejoras y Equipo). La simulada elige a quién contesta por la
 * cookie de sesión. Puertos propios (3119 y 8719) para no pisar otras suites.
 */
const ROOT = path.resolve(__dirname, "..");
const WEB_PORT = 3119;
const API_PORT = 8719;
const signingKey = generateKeyPairSync("ed25519").privateKey.export({ type: "pkcs8", format: "pem" }).toString();

const session = (value: string) => ({
  cookies: [
    {
      name: "nexus-console.session",
      value,
      domain: "localhost",
      path: "/",
      expires: -1,
      httpOnly: true,
      secure: false,
      sameSite: "Lax" as const,
    },
  ],
  origins: [],
});

export default defineConfig({
  testDir: ".",
  // `.e2e.ts`, no `.spec.ts`: la suite de siempre (`playwright.config.ts`) va
  // contra una API de verdad, que no tiene `/__test/*`.
  testMatch: /fabrica-(lite|partner)\.e2e\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 240_000,
  expect: { timeout: 30_000 },
  reporter: [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: `http://localhost:${WEB_PORT}`,
    locale: "es-ES",
    timezoneId: "Europe/Madrid",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "lite", testMatch: /fabrica-lite\.e2e\.ts/, use: { storageState: session("e2e-lite") } },
    { name: "partner", testMatch: /fabrica-partner\.e2e\.ts/, use: { storageState: session("e2e-partner") } },
  ],
  webServer: [
    {
      command: "node e2e/fabrica-mock.mjs",
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
      timeout: 300_000,
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
