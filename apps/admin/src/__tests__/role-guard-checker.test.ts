/**
 * Spec 079, requisito 4 (T024): the structural test bites. The checker runs
 * against bad examples written to a temporary folder — outside `src`, so they
 * never reach `tsc`, the linter or the real sweep — and must name each one.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterAll, describe, expect, it } from "vitest";

import { checkActions, checkPages, checkRoutes } from "./role-guard-checker";

const ROOT = fs.mkdtempSync(path.join(os.tmpdir(), "role-guard-"));

function write(rel: string, body: string): void {
  const file = path.join(ROOT, rel);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, body);
}

write(
  "actions/bad.ts",
  `"use server";
import { requireOperator } from "@/lib/session";
const p = "money";
export async function noArgument() { await requireOperator(); return 1; }
export async function variableArgument() { await requireOperator(p); return 1; }
export async function unknownPermission() { await requireOperator("everything"); return 1; }
export async function insideTry() { try { await requireOperator("read"); } catch { return 0; } return 1; }
export async function afterWrite() { await fetch("/x"); await requireOperator("money"); }
async function helper(permission: string, n: number) { await requireOperator(permission); return n; }
async function lazyHelper(n: number) { await requireOperator("read"); return n; }
export async function helperWithoutLiteral() { return helper(p, 1); }
export async function helperNotForwarding() { return lazyHelper(1); }
export async function good() { await requireOperator("read"); return 1; }
export async function goodViaHelper() { return helper("money", 1); }
`,
);

write(
  "dashboard/x/page.tsx",
  `export default async function Page() { const data = await fetch("/x"); return data; }`,
);
write(
  "dashboard/y/page.tsx",
  `import { requirePageOperator } from "@/lib/session";
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await requirePageOperator("read");
  return id;
}`,
);

write(
  "app/api/forgets/route.ts",
  `import { routeOperator } from "@/lib/session";
export async function POST() { const op = await routeOperator("qa"); return Response.json(op); }`,
);
write(
  "app/(dashboard)/x/download/route.ts",
  `export async function GET() { return Response.json({}); }`,
);
write(
  "app/api/good/route.ts",
  `import { routeOperator } from "@/lib/session";
export async function GET() {
  const op = await routeOperator("read");
  if (op instanceof Response) return op;
  return Response.json({ id: op.id });
}`,
);

afterAll(() => fs.rmSync(ROOT, { recursive: true, force: true }));

describe("el comprobador de la guarda muerde (spec 079, 4.1, 4.2 y 4.4)", () => {
  it("nombra cada acción mala y deja pasar las buenas", () => {
    const { checked, violations } = checkActions(path.join(ROOT, "actions"));
    expect(checked).toBe(9);
    expect(violations).toEqual([
      "bad.ts::noArgument: sin permiso",
      "bad.ts::variableArgument: el permiso no es un literal",
      "bad.ts::unknownPermission: permiso desconocido «everything»",
      "bad.ts::insideTry: no empieza por requireOperator",
      "bad.ts::afterWrite: no empieza por requireOperator",
      "bad.ts::helperWithoutLiteral: «helper» no recibe el permiso como literal",
      "bad.ts::helperNotForwarding: «lazyHelper» no empieza por requireOperator(<su primer parámetro>)",
    ]);
  });

  it("nombra la página sin guarda y acepta leer params antes de ella", () => {
    expect(checkPages(path.join(ROOT, "dashboard")).violations).toEqual([
      "x/page.tsx::default: no empieza por requirePageOperator",
    ]);
  });

  it("nombra la ruta que no devuelve el rechazo y la que no tiene guarda, también fuera de app/api", () => {
    expect(checkRoutes(path.join(ROOT, "app")).violations.sort()).toEqual([
      "(dashboard)/x/download/route.ts::GET: no empieza por routeOperator",
      "api/forgets/route.ts::POST: no devuelve el rechazo de routeOperator",
    ]);
  });
});
