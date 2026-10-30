import { describe, expect, it } from "vitest";

import { crumbsFor } from "../crumbs";

const names = { t1: "Volumen 03", p1: "Demo Auditoría", c1: "WhatsApp Ventas", woocommerce: "WooCommerce", k1: "TCK-42" };

describe("breadcrumb trail (spec 035)", () => {
  it("names the client once, without its slug or a «Cliente» label", () => {
    expect(crumbsFor("/tenants/t1", names)).toEqual([
      { label: "Clientes", href: "/tenants" },
      { label: "Volumen 03", href: null },
    ]);
  });

  it("follows a tab and a record below it", () => {
    expect(crumbsFor("/tenants/t1/channels/c1", names).map((c) => c.label)).toEqual([
      "Clientes",
      "Volumen 03",
      "Canales",
      "WhatsApp Ventas",
    ]);
    expect(crumbsFor("/tenants/t1/connectors/woocommerce", names).at(-1)).toEqual({ label: "WooCommerce", href: null });
  });

  it("stops the channel wizard at the channel: its rail says the step", () => {
    expect(crumbsFor("/tenants/t1/channels/new/whatsapp/agent", names).map((c) => c.label)).toEqual([
      "Clientes",
      "Volumen 03",
      "Canales",
      "Añadir canal",
      "WhatsApp",
    ]);
  });

  it("speaks the sidebar's words for sections and pages", () => {
    expect(crumbsFor("/", names)).toEqual([{ label: "Panel", href: null }]);
    expect(crumbsFor("/auphere/channels", names)).toEqual([{ label: "Números de Auphere", href: null }]);
    expect(crumbsFor("/partners/p1/money", names).map((c) => c.label)).toEqual(["Partners", "Demo Auditoría", "Facturas"]);
    expect(crumbsFor("/qa/t1/chat", names).map((c) => c.label)).toEqual(["Playground QA", "Volumen 03"]);
    expect(crumbsFor("/tickets/k1", names).map((c) => c.label)).toEqual(["Tickets", "TCK-42"]);
    expect(crumbsFor("/tenants/new", names).map((c) => c.label)).toEqual(["Clientes", "Nuevo cliente"]);
    expect(crumbsFor("/tenants/t1/capabilities", names).at(-1)?.label).toBe("Habilidades");
    expect(crumbsFor("/tenants/t1/playground", names).at(-1)?.label).toBe("Playground");
    // Spec 047 (T150): the catalog, the router and its anomalies, the certifications.
    expect(crumbsFor("/models", names)).toEqual([{ label: "Modelos", href: null }]);
    expect(crumbsFor("/router/anomalies", names).map((c) => c.label)).toEqual(["Router", "Anomalías"]);
    expect(crumbsFor("/certifications", names)).toEqual([{ label: "Certificaciones", href: null }]);
    // Spec 047 (T117, T087, T090, T100): la beta por país y el constructor.
    expect(crumbsFor("/channels/whatsapp-login", names)).toEqual([
      { label: "Canales", href: "/channels" },
      { label: "Beta «WhatsApp login»", href: null },
    ]);
    expect(crumbsFor("/builder/sector-tests", names).map((c) => c.label)).toEqual(["Constructor", "Pruebas del sector"]);
    expect(crumbsFor("/builder/judge-calibration", names).map((c) => c.label)).toEqual(["Constructor", "Calibración del juez"]);
    expect(crumbsFor("/builder/eval", names).map((c) => c.label)).toEqual(["Constructor", "Evaluación"]);
    // Spec 047 (T201, 58.5): los sectores sin guía y una guía generada, un solo registro.
    expect(crumbsFor("/builder/sector-guides", names).map((c) => c.label)).toEqual(["Constructor", "Sectores sin guía"]);
    expect(crumbsFor("/builder/sector-guides/t1/g1", { ...names, g1: "Gimnasio · Gimnasio Norte" })).toEqual([
      { label: "Constructor", href: "/builder" },
      { label: "Sectores sin guía", href: "/builder/sector-guides" },
      { label: "Gimnasio · Gimnasio Norte", href: null },
    ]);
    expect(crumbsFor("/builder/sector-guides/t1/g1", names).at(-1)).toEqual({ label: "Guía generada", href: null });
    // Spec 047 (T172): las palancas del partner.
    expect(crumbsFor("/partners/p1/limits", names).at(-1)).toEqual({ label: "Tope y moneda", href: null });
  });

  it("only the last step is not a link", () => {
    const trail = crumbsFor("/tenants/t1/agent", names);
    expect(trail.slice(0, -1).every((c) => c.href)).toBe(true);
    expect(trail.at(-1)?.href).toBeNull();
  });
});
