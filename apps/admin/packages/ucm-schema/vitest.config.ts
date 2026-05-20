import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    coverage: {
      provider: "v8",
      include: ["src/**/*.ts"],
      exclude: ["src/**/*.d.ts"],
      thresholds: {
        // Statements/lines/functions held to project standard (>= 90%).
        // Branches relaxed: many branches are defensive null-guards on
        // ChannelLimits fields that are not set on any built-in channel.
        // Coverage of those branches would require synthetic profiles for
        // every single field, which adds tests without adding signal.
        lines: 90,
        branches: 80,
        functions: 90,
        statements: 90,
      },
    },
  },
});
