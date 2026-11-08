import { describe, expect, it } from "vitest";

import { t as translate, type MessageKey } from "@/i18n/messages";

import { REASONS, inboxReasonText, reasonKey } from "../waiting-reasons";

const es = (key: MessageKey, vars?: Record<string, string | number>) => translate("es", key, vars);
const en = (key: MessageKey, vars?: Record<string, string | number>) => translate("en", key, vars);

/**
 * Spec 056 (T010; requisito 7): los motivos de escalado pasan por **una** tabla
 * de textos, la del constructor. La Bandeja no enseña nunca un código.
 */
describe("waiting-reasons (spec 056)", () => {
  it("la tabla tiene los motivos de la API, con los dos que faltaban", () => {
    // `WAITING_REASONS` de `db/models/conversation.py`, más `booking_unbacked` (T002)
    // y `taken_by_person`, que la API da como motivo del traspaso.
    for (const code of [
      "no_balance",
      "agent_cap",
      "paused_agent",
      "paused_channel",
      "paused_client",
      "archived_client",
      "channel_problem",
      "agent_unpublished",
      "out_of_audience",
      "no_model",
      "provider_failure",
      "turn_limit",
      "escalated",
      "human_takeover",
      "reception_loop",
      "booking_unbacked",
      "taken_by_person",
    ]) {
      expect(REASONS.has(code)).toBe(true);
      expect(es(reasonKey(code)!)).not.toBe("Otro motivo");
      expect(en(reasonKey(code)!)).not.toBe("Another reason");
    }
  });

  it("reasonKey se porta igual que en el constructor", () => {
    expect(reasonKey("no_balance")).toBe("waiting.reason.no_balance");
    expect(reasonKey("brand_new")).toBe("waiting.reason.other");
    expect(reasonKey(null)).toBeNull();
    expect(reasonKey("")).toBeNull();
  });

  it("los dos motivos nuevos, en palabras", () => {
    expect(es("waiting.reason.booking_unbacked")).toBe("El agente dio por hecha una cita que no existe");
    expect(en("waiting.reason.booking_unbacked")).toBe("The agent confirmed a booking that does not exist");
    expect(es("waiting.reason.out_of_audience")).toBe("Fuera de su audiencia");
  });

  it("agent_unpublished dice «Agente sin publicar» (7.3, contrato de eventos de la 047)", () => {
    expect(inboxReasonText("agent_unpublished", es)).toBe("Agente sin publicar");
  });

  it("un código conocido da el texto de la tabla (7.1)", () => {
    expect(inboxReasonText("no_balance", es)).toBe("Sin saldo");
    expect(inboxReasonText("booking_unbacked", es)).toBe("El agente dio por hecha una cita que no existe");
    expect(inboxReasonText("provider_failure", en)).toBe("The model failed");
  });

  it("escalated, un código que no está en la tabla o nada dan «El agente pidió ayuda», nunca el código (7.2)", () => {
    for (const raw of ["escalated", "brand_new_reason", "x9", null, undefined, "", "   "]) {
      expect(inboxReasonText(raw, es)).toBe("El agente pidió ayuda");
    }
    expect(inboxReasonText("brand_new_reason", en)).toBe("The agent asked for help");
  });

  it("el texto libre del agente sale tal cual", () => {
    expect(inboxReasonText("Pide un reembolso", es)).toBe("Pide un reembolso");
    expect(inboxReasonText("  quiere hablar con el dueño  ", es)).toBe("quiere hablar con el dueño");
    expect(inboxReasonText("Refund_request 2", es)).toBe("Refund_request 2");
  });
});
