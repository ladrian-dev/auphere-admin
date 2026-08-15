import tseslint from "typescript-eslint";

import nexusUi from "./eslint/index.js";

export default tseslint.config(
  { ignores: ["dist/**", "storybook-static/**", "node_modules/**"] },
  ...tseslint.configs.recommended,
  // The design-system rules apply to the components, not to the rule
  // sources/tests themselves (their fixtures contain the forbidden tokens).
  { ...nexusUi.configs.recommended, files: ["src/**/*.{ts,tsx}", ".storybook/**/*.{ts,tsx}"] },
  {
    files: ["**/*.{ts,tsx}"],
    rules: {
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
    },
  },
);
