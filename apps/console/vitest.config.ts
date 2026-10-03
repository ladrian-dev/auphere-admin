import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      // ``import "server-only"`` is Next's build-time guard against a Client
      // Component importing server code. Vitest has no such boundary, so the
      // guard resolves to an empty module (spec 016: server-action tests).
      "server-only": path.resolve(__dirname, "./src/test/server-only.ts"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["node_modules", ".next"],
    env: {
      NEXUS_CONSOLE_JWT_PRIVATE_KEY: "test",
    },
  },
});
