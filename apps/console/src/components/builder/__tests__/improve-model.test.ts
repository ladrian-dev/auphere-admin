import { describe, expect, it } from "vitest";

import { t as translate, type MessageKey } from "@/i18n/messages";

import {
  durationText,
  improvementReach,
  originKey,
  performanceColumns,
  performancePeriod,
  reasonKey,
  receptionOf,
  receptionPayload,
  receptionProblems,
} from "../improve-model";

const t = (key: MessageKey, vars?: Record<string, string | number>) => translate("es", key, vars);

/** Spec 047 (T174, T178): las cuentas puras de Rendimiento, Mejoras y Recepción. */
describe("improve-model", () => {
  it("el periodo es 7, 30 o 90; cualquier otra cosa, 30 (51.1)", () => {
    expect(performancePeriod(7)).toBe(7);
    expect(performancePeriod("90")).toBe(90);
    expect(performancePeriod(15)).toBe(30);
    expect(performancePeriod(null)).toBe(30);
  });

  it("las columnas: resueltas sin persona y pasadas a una persona; la última es «Hoy»", () => {
    const cols = performanceColumns(t, {
      series: [
        { day: "2026-10-27", conversations: 3, resolved_without_person: 2, handed_to_person: 1, spent: { amount_micros: 0, currency: "USD" } },
        { day: "2026-10-28", conversations: 1, resolved_without_person: 1, handed_to_person: 0, spent: { amount_micros: 0, currency: "USD" } },
      ],
    });
    expect(cols.map((c) => c.values)).toEqual([
      [2, 1],
      [1, 0],
    ]);
    expect(cols[1]?.label).toBe("Hoy");
    expect(cols[0]?.title).toMatch(/^Martes/);
  });

  it("cuánto duró, en palabras cortas", () => {
    expect(durationText(t, 45)).toBe("45 s");
    expect(durationText(t, 720)).toBe("12 min");
    expect(durationText(t, 3600)).toBe("1 h");
    expect(durationText(t, 4800)).toBe("1 h 20 min");
    expect(durationText(t, null)).toBe("—");
  });

  it("cada motivo de `events.md` §2 tiene sus palabras, y uno nuevo cae en «Otro motivo»", () => {
    for (const code of ["no_balance", "paused_agent", "reception_loop", "escalated", "taken_by_person", "human_takeover"]) {
      expect(t(reasonKey(code)!)).not.toBe("Otro motivo");
    }
    expect(t(reasonKey("brand_new")!)).toBe("Otro motivo");
    expect(reasonKey(null)).toBeNull();
  });

  it("a cuántos afecta una sugerencia, y de dónde viene una corrección", () => {
    expect(improvementReach(t, { kind: "suggestion", conversations_count: 12, contacts_count: 9 })).toBe("12 conversaciones de 9 clientes");
    expect(improvementReach(t, { kind: "correction", conversations_count: 1, contacts_count: 1 })).toBe("Una respuesta que el negocio corrigió");
    expect(originKey("app")).toBe("improve.origin.app");
    expect(originKey("lite_web")).toBe("improve.origin.web");
    expect(originKey(null)).toBe("improve.origin.other");
  });

  it("Recepción: se lee con cuidado, se valida con los límites de la API y se guarda limpia (53.1)", () => {
    expect(receptionOf(undefined)).toEqual({ enabled: false, targets: [] });
    expect(receptionOf({ schema_version: "1", mode: "structured", identity: { name: "R", description: "x" }, ai_disclosure: { decided: true }, reception: { enabled: true, targets: [{ agent_id: "a", when: "x" }, { nope: 1 }] } })).toEqual({
      enabled: true,
      targets: [{ agent_id: "a", when: "x" }],
    });
    expect(receptionProblems({ enabled: false })).toEqual([]);
    expect(receptionProblems({ enabled: true, targets: [] })).toEqual([{ problem: "no_targets" }]);
    expect(receptionProblems({ enabled: true, targets: [{ agent_id: "a", when: "  " }] })).toEqual([{ problem: "when_required", agent_id: "a" }]);
    expect(receptionProblems({ enabled: true, targets: [{ agent_id: "a", when: "x".repeat(301) }] })).toEqual([{ problem: "when_too_long", agent_id: "a" }]);
    expect(receptionProblems({ enabled: true, targets: Array.from({ length: 11 }, (_, i) => ({ agent_id: String(i), when: "x" })) })).toEqual([{ problem: "too_many" }]);
    expect(receptionPayload({ enabled: true, targets: [{ agent_id: "a", when: " al  por mayor " }] })).toEqual({ enabled: true, targets: [{ agent_id: "a", when: "al por mayor" }] });
    expect(receptionPayload({ enabled: false, targets: [{ agent_id: "a", when: "x" }] })).toEqual({ enabled: false });
  });
});
