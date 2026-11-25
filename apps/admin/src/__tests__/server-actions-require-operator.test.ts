/**
 * Spec 078 (el panel solo obedece a operadores activos) y spec 079 (y solo
 * dentro de lo que permite su rol).
 *
 * El panel habla con la API con un token de servicio, así que la API no sabe
 * quién pide cada cosa: quien decide es la guarda del panel. Esta prueba lee el
 * código y exige que la guarda de cada superficie sea **lo primero**, con un
 * permiso literal de la matriz (`lib/permissions.ts`):
 *
 * - cada función exportada de un archivo `"use server"` (078 req. 1; 079 2.1);
 * - cada página y layout de servidor de `app/(dashboard)`, y su
 *   `generateMetadata` si lee la API (078 req. 3; 079 2.6). Next no vuelve a
 *   ejecutar un layout al navegar, así que la guarda del layout raíz no basta;
 * - cada handler de cualquier `route.ts` de `app` (no solo `app/api`), que además
 *   devuelve el rechazo (079 2.5).
 *
 * Barre el código; no tiene una lista de sitios (constitución §I). El
 * comprobador vive en `role-guard-checker.ts` y la spec 079 (T024) lo prueba
 * contra ejemplos malos.
 */
import fs from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { checkActions, checkPages, checkRoutes, directive, hasInlineUseServer, parse, sourceFiles, topLevelFunctions } from "./role-guard-checker";

const SRC = path.resolve(__dirname, "..");
const DASHBOARD = path.join(SRC, "app", "(dashboard)");
/** Every `route.ts` under `app`, not only `app/api`: there are some inside `(dashboard)`. */
const APP = path.join(SRC, "app");

/** Abren y cierran la sesión: no pueden exigirla (078, 1.2; 079, 2.8). */
const EXEMPT = new Set([
  "app/(auth)/login/actions.ts::loginAction",
  "app/(auth)/login/actions.ts::logoutAction",
]);

describe("Server Actions del panel (078 req. 1; 079 req. 2 y 4)", () => {
  const report = checkActions(SRC, EXEMPT);

  it("encuentra las acciones (la prueba no pasa en vacío)", () => {
    expect(report.checked).toBeGreaterThan(100);
  });

  it("cada función exportada empieza por requireOperator con un permiso de la matriz", () => {
    expect(report.violations).toEqual([]);
  });

  it("no hay acciones en línea (`\"use server\"` dentro de una función)", () => {
    const inline = sourceFiles(SRC).filter((file) => {
      const text = fs.readFileSync(file, "utf8");
      return text.includes("use server") && hasInlineUseServer(parse(file));
    });
    expect(inline.map((f) => path.relative(SRC, f))).toEqual([]);
  });

  it("las excepciones siguen existiendo (si se renombran, se revisa la lista)", () => {
    const all = new Set(
      sourceFiles(SRC)
        .map((file) => ({ file, sf: parse(file) }))
        .filter(({ sf }) => directive(sf) === "use server")
        .flatMap(({ file, sf }) =>
          topLevelFunctions(sf)
            .filter((f) => f.exported)
            .map((f) => `${path.relative(SRC, file).split(path.sep).join("/")}::${f.name}`),
        ),
    );
    for (const exempt of EXEMPT) expect(all.has(exempt)).toBe(true);
  });
});

describe("Páginas y layouts del panel (078 req. 3; 079 2.6 y 2.7)", () => {
  const report = checkPages(DASHBOARD);

  it("encuentra las páginas (la prueba no pasa en vacío)", () => {
    expect(report.checked).toBeGreaterThan(50);
  });

  it("cada página, layout y generateMetadata que lee la API empieza por requirePageOperator con su permiso", () => {
    expect(report.violations).toEqual([]);
  });
});

describe("Rutas del panel, en cualquier carpeta de app (078 2.3; 079 2.5)", () => {
  const report = checkRoutes(APP);

  it("encuentra las rutas (la prueba no pasa en vacío)", () => {
    expect(report.checked).toBeGreaterThanOrEqual(10);
  });

  it("cada handler empieza por routeOperator con su permiso y devuelve el rechazo", () => {
    expect(report.violations).toEqual([]);
  });
});
