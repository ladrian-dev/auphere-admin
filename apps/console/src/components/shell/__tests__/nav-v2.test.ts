import { describe, expect, it } from "vitest";

import { PARTNER_MODULES } from "@/lib/principal-access";

import { NAV, navForRole } from "../nav";
import { navV2 } from "../nav-v2";

/**
 * Spec 047 (R47.1): el menú de la consola nueva no tiene etiquetas de grupo.
 * Arriba Panel, Clientes, Consumo, Auditoría, Guía del partner y Teammate;
 * abajo Equipo, Facturación y API. Las entradas, sus permisos y sus módulos
 * son las de `nav.ts`, que no cambia: la app de escritorio lo lee en su
 * prueba de paridad.
 */
const hrefs = (items: { href: string }[]) => items.map((i) => i.href);

describe("navV2", () => {
  it("arriba lo de operar y abajo lo de la cuenta, en el orden del prototipo", () => {
    const nav = navV2("owner", PARTNER_MODULES);
    expect(hrefs(nav.top)).toEqual(["/", "/clients", "/usage", "/audit", "/knowledge", "/workstation"]);
    expect(hrefs(nav.bottom)).toEqual(["/team", "/billing", "/keys"]);
  });

  it("no lleva etiquetas de grupo", () => {
    const nav = navV2("owner", PARTNER_MODULES);
    expect(Object.keys(nav).sort()).toEqual(["bottom", "top"]);
    expect(JSON.stringify(nav)).not.toMatch(/nav\.group\./);
  });

  it("filtra por rol y por módulo como la consola de hoy", () => {
    expect(hrefs([...navV2("billing", PARTNER_MODULES).top, ...navV2("billing", PARTNER_MODULES).bottom])).toEqual([
      "/",
      "/usage",
      "/team",
      "/billing",
    ]);
    const some = navV2("owner", ["panel", "usage", "billing"]);
    expect(hrefs(some.top)).toEqual(["/", "/usage"]);
    expect(hrefs(some.bottom)).toEqual(["/billing"]);
    expect(navV2("analyst", ["panel"]).bottom).toEqual([]);
  });

  it("son las mismas entradas que `NAV`: la consola de hoy no cambia", () => {
    const v1 = navForRole("owner").flatMap((g) => g.items);
    const v2 = navV2("owner", PARTNER_MODULES);
    expect([...v2.top, ...v2.bottom]).toEqual(v1);
    expect(NAV.map((g) => g.labelKey)).toEqual(["nav.group.operate", "nav.group.account"]);
  });
});
