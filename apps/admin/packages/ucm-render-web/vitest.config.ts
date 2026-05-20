import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    globals: false,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.d.ts"],
      thresholds: {
        // Branches relaxed: components have many optional-content guards
        // (header/footer in List, screen in Flow, caption fallback in
        // Media) that the canonical fixtures don't exercise without
        // synthetic payloads. Covering them adds tests without signal
        // — same call as in `@nexus/ucm-schema`.
        lines: 90,
        functions: 90,
        statements: 90,
        branches: 70,
      },
    },
  },
});
