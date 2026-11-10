/**
 * Recorrido UI de la 047: las palabras de las pantallas que trajo la spec. En
 * pantalla es «conector», nunca «integración», y no hay punto y coma.
 *
 * Estructural sobre el fuente, como `costs-only-in-admin.test.ts`: los textos de
 * estas pantallas están en el propio componente, y un render de un componente de
 * servidor pide la API. Mira los literales entre comillas.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const DASHBOARD = join(__dirname, "..", "..", "app", "(dashboard)");

const SCREENS = [
  "connectors/[slug]/page.tsx",
  "tenants/[id]/sovereign.ts",
  "partners/[id]/limits/page.tsx",
  "builder/sector-tests/page.tsx",
  // T201 (58.5): «Sectores sin guía».
  "builder/sector-guides/page.tsx",
  "builder/sector-guides/sector-guides.ts",
  "builder/sector-guides/missing-labels.tsx",
  "builder/sector-guides/generated-guide.tsx",
  "builder/sector-guides/promote-dialog.tsx",
  "builder/sector-guides/[tenantId]/[guideId]/page.tsx",
];

function literals(source: string): string[] {
  return [...source.matchAll(/"([^"\n]{12,})"/g)].map((m) => m[1] ?? "").filter((s) => /\s/.test(s));
}

describe("las palabras de las pantallas de la 047", () => {
  it.each(SCREENS)("%s no dice «integración» ni usa punto y coma", (file) => {
    const texts = literals(readFileSync(join(DASHBOARD, file), "utf8"));
    expect(texts.filter((t) => /integraci[oó]n/i.test(t))).toEqual([]);
    expect(texts.filter((t) => t.includes(";"))).toEqual([]);
  });
});
