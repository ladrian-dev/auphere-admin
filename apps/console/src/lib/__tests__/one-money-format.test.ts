import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Spec 072 (1.4): toda la consola escribe el dinero con `lib/amount.ts` o con
 * `formatMoney` de `@nexus/ui`. Nadie más arma un `style: "currency"` (daría
 * «US$») ni usa `formatCurrency` (el del Admin).
 */
const SRC = join(__dirname, "..", "..");

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "__tests__" || name === "node_modules" ? [] : files(path);
    return /\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

describe("one money format (spec 072, 1.4)", () => {
  it('no screen builds its own Intl currency or uses formatCurrency', () => {
    const offenders = files(SRC)
      .filter((path) => {
        const text = readFileSync(path, "utf8");
        return /style:\s*["']currency["']/.test(text) || /\bformatCurrency\b/.test(text);
      })
      .map((path) => relative(SRC, path));
    expect(offenders).toEqual([]);
  });
});
