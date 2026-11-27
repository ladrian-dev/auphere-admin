import { generateKeyPairSync } from "node:crypto";
import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

/**
 * Spec 082 (datos al día) — Reservas, la Bandeja y el contador, en un navegador
 * de verdad con `next dev`, contra la API simulada de `datos-al-dia-mock.mjs`:
 *
 *   pnpm exec playwright test -c e2e/datos-al-dia.config.ts
 *
 * La simulada confirma cada escritura al momento: si la pantalla no la pinta
 * sin recargar, el fallo es de la consola. Puertos propios (3122 y 8722).
 */
const ROOT = path.resolve(__dirname, "..");
const WEB_PORT = 3122;
const API_PORT = 8722;
const signingKey = generateKeyPairSync("ed25519").privateKey.export({ type: "pkcs8", format: "pem" }).toString();

export default defineConfig({
  testDir: ".",
  testMatch: /datos-al-dia\.e2e\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 240_000,
  expect: { timeout: 20_000 },
  reporter: [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: `http://localhost:${WEB_PORT}`,
    locale: "es-ES",
    timezoneId: "America/Caracas",
    trace: "retain-on-failure",
    storageState: {
      cookies: [
        {
          name: "nexus-console.session",
          value: "e2e-lite",
          domain: "localhost",
          path: "/",
          expires: -1,
          httpOnly: true,
          secure: false,
          sameSite: "Lax" as const,
        },
      ],
      origins: [],
    },
  },
  webServer: [
    {
      command: "node e2e/datos-al-dia-mock.mjs",
      cwd: ROOT,
      url: `http://127.0.0.1:${API_PORT}/health`,
      env: { MOCK_API_PORT: String(API_PORT) },
      reuseExistingServer: false,
      stdout: "ignore",
      stderr: "pipe",
    },
    {
      // `E2E_PROD=1`: the production build (`next build` + `next start`), where
      // `<Link>` prefetches and the router caches as it does in prod.
      command: process.env.E2E_PROD
        ? `pnpm exec next build && pnpm exec next start -p ${WEB_PORT}`
        : `pnpm exec next dev -p ${WEB_PORT}`,
      cwd: ROOT,
      url: `http://localhost:${WEB_PORT}/healthz`,
      timeout: 900_000,
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
