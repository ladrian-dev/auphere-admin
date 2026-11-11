import { describe, expect, it } from "vitest";

import { ROUTER_PANEL_VISIBLE } from "@/lib/router-panel";

import { NAV, allNavItems, isActive, navFor } from "../nav";

describe("operator panel navigation (spec 031, R2)", () => {
  it("declares the groups and entries in the agreed order (R2.1)", () => {
    expect(NAV.map((g) => g.label)).toEqual([null, "Gestionar", "Plataforma", "Instancia"]);
    expect(allNavItems().map((i) => i.label)).toEqual([
      "Panel",
      "Partners",
      "Clientes",
      "Consumo",
      "Altas",
      "Tickets",
      "Canales",
      "Conectores",
      "Números de Auphere",
      "Playground QA",
      // Spec 047 (T150): el catálogo de modelos. Router y Certificaciones,
      // aparcados por la spec 059 (requisito 2).
      "Modelos",
      // Spec 047 (T087, T090, T100): la calidad del constructor.
      "Constructor",
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

/** Spec 059, historia 2: the router is parked behind one setting. */
describe("the parked router (2.1, 2.2, 2.7)", () => {
  it("is parked by default, in every environment", () => {
    expect(ROUTER_PANEL_VISIBLE).toBe(false);
  });

  it("parked, neither the sidebar nor the command palette offer Router or Certificaciones", () => {
    const hrefs = allNavItems().map((i) => i.href);
    expect(hrefs).not.toContain("/router");
    expect(hrefs).not.toContain("/certifications");
    expect(navFor(false)).toEqual(NAV);
  });

  it("visible, both come back where they were, and nothing else changes", () => {
    const visible = navFor(true).flatMap((g) => g.items.map((i) => i.label));
    expect(visible).toEqual([
      "Panel",
      "Partners",
      "Clientes",
      "Consumo",
      "Altas",
      "Tickets",
      "Canales",
      "Conectores",
      "Números de Auphere",
      "Playground QA",
      "Modelos",
      "Router",
      "Certificaciones",
      "Constructor",
      "Estado",
    ]);
    const parked = navFor(false).flatMap((g) => g.items.map((i) => i.label));
    expect(visible.filter((l) => l !== "Router" && l !== "Certificaciones")).toEqual(parked);
  });
});
