import { describe, expect, it } from "vitest";

import type { ClientSetupDetail } from "@/lib/backend";

import { nextAction, SETUP_ORDER, setupSteps, whoCanResolve } from "../client-header-model";

/**
 * Spec 017 · R1: la cabecera dice qué falta para que el cliente atienda y
 * ofrece UN solo botón, el del paso pendiente. Los cuatro pasos son
 * independientes: se resuelven en cualquier orden, pero «lo siguiente» se
 * elige siempre en el mismo, para que dos personas mirando la misma ficha
 * vean lo mismo.
 */
const base = "/clients/panaderia";

const setup = (over: Partial<ClientSetupDetail> = {}): ClientSetupDetail => ({
  agent: true,
  channel: true,
  quota: true,
  active: true,
  next: null,
  ...over,
});

describe("los pasos de la puesta en marcha", () => {
  it("son cuatro, siempre en el mismo orden", () => {
    expect(SETUP_ORDER).toEqual(["agent", "channel", "quota", "activation"]);
    expect(setupSteps(setup()).map((s) => s.step)).toEqual(["agent", "channel", "quota", "activation"]);
  });

  it("cada uno lleva su nombre y su estado real, sin inventarse una secuencia", () => {
    // El paso 3 hecho y el 2 no: imposible en una secuencia, normal aquí.
    const steps = setupSteps(setup({ channel: false, next: "channel" }));
    expect(steps.map((s) => s.done)).toEqual([true, false, true, true]);
    expect(steps.map((s) => s.label)).toEqual([
      "clients.setup.agent",
      "clients.setup.channel",
      "clients.setup.quota",
      "clients.setup.activation",
    ]);
    expect(steps.filter((s) => s.next).map((s) => s.step)).toEqual(["channel"]);
  });

  it("sin lectura de la API, nada está hecho y nada es el siguiente", () => {
    const steps = setupSteps(null);
    expect(steps.every((s) => !s.done && !s.next)).toBe(true);
  });
});

describe("el botón de la cabecera", () => {
  it("no existe cuando el cliente ya atiende", () => {
    expect(nextAction(setup(), "owner", base)).toBeNull();
  });

  it("lleva a la pantalla que resuelve el paso, con su porqué", () => {
    const agent = nextAction(setup({ agent: false, next: "agent" }), "owner", base);
    expect(agent).toMatchObject({ kind: "link", href: `${base}/agent`, label: "clients.setup.next.agent", why: "clients.setup.why.agent" });

    const channel = nextAction(setup({ channel: false, next: "channel" }), "owner", base);
    expect(channel).toMatchObject({ kind: "link", href: `${base}/channels` });
  });

  it("manda el crédito a la pantalla de consumo, que es la que lo asigna hoy", () => {
    expect(nextAction(setup({ quota: false, next: "quota" }), "owner", base)).toMatchObject({ kind: "link", href: "/usage" });
  });

  it("activar pide confirmación en vez de navegar: ese clic pone al agente a atender", () => {
    expect(nextAction(setup({ active: false, next: "activation" }), "owner", base)).toMatchObject({ kind: "activate" });
  });

  it("no se pinta cuando quien mira no puede resolver ese paso", () => {
    // Un botón que da 403 es peor que ningún botón.
    expect(nextAction(setup({ agent: false, next: "agent" }), "analyst", base)).toBeNull();
    expect(nextAction(setup({ channel: false, next: "channel" }), "analyst", base)).toBeNull();
    // El crédito lo mueve quien lleva el consumo, no quien edita el agente.
    expect(nextAction(setup({ quota: false, next: "quota" }), "builder", base)).toBeNull();
    expect(nextAction(setup({ quota: false, next: "quota" }), "owner", base)).not.toBeNull();
  });

  it("dice quién puede resolverlo cuando quien mira no puede", () => {
    expect(whoCanResolve("agent")).toBe("clients.setup.who.agents");
    expect(whoCanResolve("quota")).toBe("clients.setup.who.usage");
  });
});
