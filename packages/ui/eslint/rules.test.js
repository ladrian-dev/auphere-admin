import { RuleTester } from "eslint";
import { describe, expect, it } from "vitest";

import plugin, { checkSpacingToken } from "./index.js";

// ESLint's RuleTester drives vitest's describe/it itself, so ``run`` is
// called at suite level (never inside an ``it``).
const tester = new RuleTester({
  languageOptions: {
    ecmaVersion: 2022,
    sourceType: "module",
    parserOptions: { ecmaFeatures: { jsx: true } },
  },
});

describe("nexus-ui/no-raw-colors", () => {
  tester.run("no-raw-colors", plugin.rules["no-raw-colors"], {
    valid: [
      'const c = "bg-primary text-status-danger";',
      'const c = "shadow-[0_0_0_3px_color-mix(in_oklab,var(--color-status-positive)_18%,transparent)]";',
      'const c = "text-[color:var(--color-primary-deep)]";',
    ],
    invalid: [
      { code: 'const c = "#2CC295";', errors: 1 },
      { code: 'const c = <div className="text-[#0D0F01]" />;', errors: 1 },
      { code: "const c = `rgb(1, 2, 3)`;", errors: 1 },
      { code: 'const c = "hsl(120 50% 50%)";', errors: 1 },
      { code: 'const c = "oklch(0.7 0.1 160)";', errors: 1 },
    ],
  });
});

describe("nexus-ui/spacing-scale", () => {
  it("exposes the checker", () => {
    expect(checkSpacingToken("gap-1.5")).not.toBeNull();
    expect(checkSpacingToken("gap-2")).toBeNull();
    expect(checkSpacingToken("h-[32px]")).toBeNull();
    expect(checkSpacingToken("h-[30px]")).not.toBeNull();
  });
  tester.run("spacing-scale", plugin.rules["spacing-scale"], {
    valid: [
      'const c = "p-4 gap-2 h-8 size-4 w-full max-w-prose inset-0 -mt-1 md:px-6";',
      'const c = "w-[calc(100%-2rem)] max-h-(--available-height) w-1/2 h-[32px] top-[50%]";',
      'const c = "min-w-24 w-64 leading-tight text-sm ring-3 opacity-50";',
    ],
    invalid: [
      { code: 'const c = "gap-1.5";', errors: 1 },
      { code: 'const c = "px-2.5 py-0.5";', errors: 2 },
      { code: 'const c = "size-3.5";', errors: 1 },
      { code: 'const c = "h-[30px]";', errors: 1 },
      { code: 'const c = "-bottom-[5px]";', errors: 1 },
    ],
  });
});

describe("nexus-ui/radius-enum", () => {
  tester.run("radius-enum", plugin.rules["radius-enum"], {
    valid: [
      'const c = "rounded-md rounded-t-md rounded-full rounded-none rounded-sm rounded hover:rounded-md";',
    ],
    invalid: [
      { code: 'const c = "rounded-lg";', errors: 1 },
      { code: 'const c = "rounded-xl rounded-b-2xl";', errors: 2 },
      { code: 'const c = "rounded-[2px]";', errors: 1 },
      { code: 'const c = "rounded-4xl";', errors: 1 },
    ],
  });
});

describe("nexus-ui/no-palette-colors", () => {
  tester.run("no-palette-colors", plugin.rules["no-palette-colors"], {
    valid: ['const c = "bg-muted text-muted-foreground border-border bg-status-danger/10";'],
    invalid: [
      { code: 'const c = "text-slate-500";', errors: 1 },
      { code: 'const c = "bg-zinc-100 dark:text-emerald-300";', errors: 2 },
    ],
  });
});
