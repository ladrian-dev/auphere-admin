import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Spec 048 (requisito 1.1; T015): el panel de operador no ofrece AgendaPro. Ni
 * su asistente («Conectar AgendaPro» con la URL pública), ni su acción, ni la
 * llamada a `PATCH …/integrations/agendapro/public-url`, ni el campo
 * `tenants.agendapro_public_url`, que la migración `0205` borra.
 *
 * Barre el código del panel sin los tests, que pueden nombrarlo para decir que
 * ya no está.
 */
const SRC = join(import.meta.dirname, "..", "..");

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return entry === "__tests__" || entry === "node_modules" ? [] : files(full);
    return /\.(ts|tsx)$/.test(entry) ? [full] : [];
  });
}

describe("spec 048 · el panel sin AgendaPro", () => {
  it("ningún archivo del panel nombra AgendaPro", () => {
    const offenders = files(SRC)
      .filter((file) => /agenda[\s_-]?pro/i.test(readFileSync(file, "utf8")))
      .map((file) => relative(SRC, file));
    expect(offenders).toEqual([]);
  });
});
