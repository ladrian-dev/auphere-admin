// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require("eslint/config");
const expoConfig = require("eslint-config-expo/flat");

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ["dist/*", "ios/*", "android/*", "src/**/*.gen.ts", "coverage/*"],
  },
  {
    rules: {
      // TypeScript already checks namespace members, and this rule cannot
      // follow expo-notifications' re-exports (false «not found»).
      "import/namespace": "off",
      // Spec 031, D15: colour comes from tokens.gen.ts, never typed by hand.
      "no-restricted-syntax": [
        "error",
        {
          selector: "Literal[value=/^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/]",
          message: "No hex in the app: use a role from useTheme().colors (tokens.gen.ts).",
        },
      ],
    },
  },
  {
    // Spec 069 (R23, /cso L2): the example business only reaches the app through
    // the `__DEV__ && DEMO` require in `client.ts` and `sse.ts`, never a static import.
    files: ["src/**"],
    ignores: ["src/api/demo/**"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["@/api/demo", "@/api/demo/*", "./demo", "./demo/*", "../demo", "../demo/*"],
              message: "The example business is dev-only: reach it through the `__DEV__ && DEMO` require in client.ts or sse.ts.",
            },
          ],
        },
      ],
    },
  },
  {
    // Tests assert the generated hex on purpose, and `require` after `jest.mock`.
    files: ["__tests__/**", "test/**", "jest.setup.tsx"],
    rules: { "no-restricted-syntax": "off", "@typescript-eslint/no-require-imports": "off" },
  },
]);
