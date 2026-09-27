import { describe, expect, it } from "vitest";

import { navGroupsFor, RECORD_TABS } from "../client-nav-model";

/**
 * Spec 017 · R2: las diez pestañas de la ficha en tres grupos, y cada rol
 * ve solo las que puede abrir. El modelo es puro a propósito: qué ve cada
 * rol es una decisión, y una decisión se prueba sin montar React.
 *
 * La autoridad sigue siendo la API (cada ruta comprueba su permiso); esto
 * decide qué se PINTA, para que nadie llegue a un 403 por un enlace que no
 * debería haber visto.
 */
const base = "/clients/panaderia";

describe("las pestañas de la ficha", () => {
  it("cubre todas las pestañas de hoy: ninguna desaparece", () => {
    // Nueve. Eran once: la spec 018 retiró «Ajustes» (los del agente viven
    // dentro de «Agente», que son dos mitades de lo mismo) y «Datos del
    // cliente» (se editan en el Resumen, que es donde ya se leían). Ninguna
    // función se perdió: `parity.md`, filas 22–37.
    expect(RECORD_TABS.map((t) => t.key)).toEqual([
      "overview",
      "conversations",
      "playground",
      "agent",
      "capabilities",
      "knowledge",
      "channels",
      "integrations",
      "workstation",
    ]);
  });

  it("agrupa en observar, configurar y conectar, en ese orden", () => {
    const groups = navGroupsFor("owner", base, {});
    expect(groups.map((g) => g.key)).toEqual(["observe", "configure", "connect"]);
    expect(groups.flatMap((g) => g.items)).toHaveLength(9);
  });

  it("el propietario lo ve todo; el analista pierde el Playground", () => {
    const owner = navGroupsFor("owner", base, {}).flatMap((g) => g.items.map((i) => i.key));
    const analyst = navGroupsFor("analyst", base, {}).flatMap((g) => g.items.map((i) => i.key));
    expect(owner).toContain("playground");
    expect(analyst).not.toContain("playground");
    // Lo demás sigue ahí: un analista observa y lee la configuración.
    expect(analyst).toContain("agent");
    expect(analyst).toContain("channels");
  });

  it("el rol de facturación no llega a la ficha", () => {
    expect(navGroupsFor("billing", base, {})).toEqual([]);
  });

  it("construye el enlace de cada pestaña bajo la ficha, con la raíz en Resumen", () => {
    const items = navGroupsFor("owner", base, {}).flatMap((g) => g.items);
    expect(items.find((i) => i.key === "overview")?.href).toBe(base);
    expect(items.find((i) => i.key === "agent")?.href).toBe(`${base}/agent`);
    // Los ajustes del agente y los datos del cliente ya no son pestañas: sus
    // URLs siguen vivas como redirección, pero no se ofrecen dos veces.
    expect(items.find((i) => i.key === "settings")).toBeUndefined();
    expect(items.find((i) => i.key === "client")).toBeUndefined();
    // Iteración 2: «Capacidades» ya tiene su pantalla.
    expect(items.find((i) => i.key === "capabilities")?.href).toBe(`${base}/capabilities`);
    // Integraciones tiene URL propia: antes apuntaba a un ancla que no
    // existía en ningún elemento, así que el enlace no llevaba a ninguna parte.
    expect(items.find((i) => i.key === "integrations")?.href).toBe(`${base}/integrations`);
    // Habilidades ya no es una pestaña: vive dentro de Capacidades. Su URL
    // sigue existiendo como redirección, pero no se ofrece dos veces.
    expect(items.find((i) => i.key === "skills")).toBeUndefined();
  });

  it("marca con un punto la pestaña donde vive el cambio sin publicar", () => {
    const groups = navGroupsFor("owner", base, { draftScreens: ["settings", "capabilities"] });
    const marked = groups.flatMap((g) => g.items).filter((i) => i.mark === "draft");
    expect(marked.map((i) => i.key)).toEqual(["agent", "capabilities"]);
  });

  it("«prompt» sin publicar se señala en Agente, que es donde se lee", () => {
    const groups = navGroupsFor("owner", base, { draftScreens: ["prompt"] });
    const marked = groups.flatMap((g) => g.items).filter((i) => i.mark === "draft");
    expect(marked.map((i) => i.key)).toEqual(["agent"]);
  });

  it("una incidencia en el canal se señala en Canales, y gana al borrador", () => {
    const groups = navGroupsFor("owner", base, { draftScreens: ["settings"], incidents: ["channels"] });
    const items = groups.flatMap((g) => g.items);
    expect(items.find((i) => i.key === "channels")?.mark).toBe("incident");
    // R3.2: el borrador de los ajustes del agente marca «Agente», que es
    // donde ahora se editan.
    expect(items.find((i) => i.key === "agent")?.mark).toBe("draft");
  });
});
