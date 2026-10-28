import { describe, expect, it } from "vitest";

import { t as translate } from "@/i18n/messages";

import { cardHref, destinations, isDefault, menuItems, otherLiveAgents, visibleText, visibleTone } from "../life-model";

import { AGENTS, CH1, CH2, COBROS, REF, VENTAS, agent, header } from "./life-fixtures";

const t = (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>) => translate("es", key, vars);

/** Spec 047 (T124; requisitos 25.5, 26.1, 28.1) — la vida de un agente sin pintar nada. */
describe("el estado visible (25.5)", () => {
  it("dice los mismos textos que toda la consola, con el motivo de la pausa", () => {
    expect(visibleText(t, { code: "serving", tone: "positive", reason: null })).toBe("Atendiendo");
    expect(visibleText(t, { code: "testing", tone: "info", reason: null })).toBe("En prueba");
    expect(visibleText(t, { code: "ready_no_channel", tone: "info", reason: null })).toBe("Listo · sin canal");
    expect(visibleText(t, { code: "draft", tone: "muted", reason: null })).toBe("Borrador");
    expect(visibleText(t, { code: "archived", tone: "muted", reason: null })).toBe("Archivado");
    expect(visibleText(t, { code: "paused", tone: "warn", reason: "no_balance" })).toBe("Pausado · sin saldo");
    expect(visibleText(t, { code: "paused", tone: "warn", reason: "client_archived" })).toBe("Pausado · cliente archivado");
    expect(visibleText(t, { code: "paused", tone: "warn", reason: null })).toBe("Pausado · a mano");
    expect(visibleTone({ code: "paused", tone: "warn", reason: null })).toBe("warn");
    expect(visibleTone({ code: "x", tone: "rainbow", reason: null })).toBe("muted");
  });
});

describe("la tarjeta y el ⋯", () => {
  it("la tarjeta abre la pestaña que le toca (26.1)", () => {
    expect(cardHref(REF, agent({ opens: "builder" }))).toBe(`/clients/${REF}/agents/11111111-1111-4111-8111-111111111111`);
    expect(cardHref(REF, agent({ opens: "channels" }))).toBe(`/clients/${REF}/channels`);
    expect(cardHref(REF, agent({ opens: "overview" }))).toBe(`/clients/${REF}/agents/11111111-1111-4111-8111-111111111111`);
    expect(isDefault(agent({ is_default: undefined, is_principal: true }))).toBe(true);
    expect(isDefault(agent({ is_default: false, is_principal: true }))).toBe(false);
  });

  it("el ⋯ solo ofrece lo permitido, en orden", () => {
    expect(menuItems(header({ allowed: ["archive", "make_default", "rename", "pause"] }))).toEqual(["rename", "pause", "make_default", "archive"]);
    expect(menuItems(header({ allowed: ["restore"] }))).toEqual(["restore"]);
    expect(menuItems(header({ allowed: [] }))).toEqual([]);
  });

  it("archivar pide el destino de cada número (28.1)", () => {
    expect(otherLiveAgents(AGENTS, COBROS).map((a) => a.id)).not.toContain(COBROS);
    const channels = [{ id: CH1 }, { id: CH2 }];
    expect(destinations(channels, { [CH1]: VENTAS })).toBeNull();
    expect(destinations(channels, { [CH1]: VENTAS, [CH2]: "pause" })).toEqual([
      { channel_id: CH1, to: VENTAS },
      { channel_id: CH2, to: "pause" },
    ]);
    expect(destinations([], {})).toEqual([]);
  });
});
