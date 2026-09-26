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
    // Once, no diez: los ajustes del AGENTE y los datos del cliente son dos
    // pantallas distintas, y compartir una pestaña hacía que el punto de
    // «sin publicar» señalara la que no había cambiado.
    expect(RECORD_TABS.map((t) => t.key)).toEqual([
      "overview",
      "conversations",
      "playground",
      "agent",
      "settings",
      "client",
      "capabilities",
      "skills",
      "knowledge",
      "channels",
      "integrations",
      "workstation",
    ]);
  });

  it("agrupa en observar, configurar y conectar, en ese orden", () => {
    const groups = navGroupsFor("owner", base, {});
    expect(groups.map((g) => g.key)).toEqual(["observe", "configure", "connect"]);
    expect(groups.flatMap((g) => g.items)).toHaveLength(12);
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
    // El borrador cambia los ajustes del AGENTE, no el nombre del cliente.
    expect(items.find((i) => i.key === "settings")?.href).toBe(`${base}/agent/settings`);
    expect(items.find((i) => i.key === "client")?.href).toBe(`${base}/settings`);
    // Iteración 1: «Capacidades» aún vive en la pantalla de herramientas.
    expect(items.find((i) => i.key === "capabilities")?.href).toBe(`${base}/tools`);
    // Integraciones tiene URL propia: antes apuntaba a un ancla que no
    // existía en ningún elemento, así que el enlace no llevaba a ninguna parte.
    expect(items.find((i) => i.key === "integrations")?.href).toBe(`${base}/integrations`);
    // Habilidades sigue alcanzable hasta que la iteración 2 la fusione.
    expect(items.find((i) => i.key === "skills")?.href).toBe(`${base}/skills`);
  });

  it("marca con un punto la pestaña donde vive el cambio sin publicar", () => {
    const groups = navGroupsFor("owner", base, { draftScreens: ["settings", "capabilities"] });
    const marked = groups.flatMap((g) => g.items).filter((i) => i.mark === "draft");
    expect(marked.map((i) => i.key)).toEqual(["settings", "capabilities"]);
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
    expect(items.find((i) => i.key === "settings")?.mark).toBe("draft");
  });
});
