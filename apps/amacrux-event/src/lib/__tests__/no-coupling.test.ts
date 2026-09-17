import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { scan } from "../../../scripts/no-env-leaks-rules.mjs";

/**
 * Puerta de aislamiento (constitución §I) adaptada: no hay tenant, así que la
 * prueba es que la app no nombra secretos fuera del servidor ni importa nada
 * de la plataforma Nexus.
 */
describe("no acoplamiento con la plataforma ni fugas de secretos", () => {
  it("src/ está limpio", () => {
    const violations: string[] = scan(resolve(__dirname, "../../.."));
    expect(violations).toEqual([]);
  });
});
