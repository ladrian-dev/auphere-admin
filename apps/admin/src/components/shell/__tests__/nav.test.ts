import { describe, expect, it } from "vitest";

import { NAV, allNavItems, isActive } from "../nav";

describe("operator panel navigation (spec 031, R2)", () => {
  it("declares the groups and entries in the agreed order (R2.1)", () => {
    expect(NAV.map((g) => g.label)).toEqual([null, "Gestionar", "Plataforma", "Instancia"]);
    expect(allNavItems().map((i) => i.label)).toEqual([
      "Panel",
      "Partners",
      "Clientes",
      "Altas",
      "Tickets",
      "Conectores",
      "Canales de Auphere",
      "Playground QA",
      "Estado",
    ]);
  });

  it("speaks Spanish only", () => {
    const labels = allNavItems().map((i) => i.label);
    for (const english of ["Tenants", "Connectors", "Auphere channels", "Signups"]) {
      expect(labels).not.toContain(english);
    }
  });

  it("keeps a section lit on its child routes (R2.2)", () => {
    const byHref = Object.fromEntries(allNavItems().map((i) => [i.href, i]));
    expect(isActive("/partners/abc/money", byHref["/partners"])).toBe(true);
    expect(isActive("/tenants/abc/agent", byHref["/tenants"])).toBe(true);
    expect(isActive("/partnersx", byHref["/partners"])).toBe(false);
  });

  it("lights the home only on the root", () => {
    const home = allNavItems()[0];
    expect(isActive("/", home)).toBe(true);
    expect(isActive("/partners", home)).toBe(false);
  });
});
