import { describe, expect, it } from "vitest";

import { messages } from "@/i18n/messages";
import type { MessageKey } from "@/i18n/messages";

import { settingValue } from "../draft-setting-value";

/**
 * Spec 017 · R3.2: la hoja de revisión existe para que el partner decida
 * mirando. Un volcado de JSON («enabled: ✓ · triggers: user_asks_human,
 * angry, out_of_scope») no es mirar nada.
 *
 * Se prueba contra el ES real, no contra un doble, para que una clave mal
 * escrita se caiga aquí y no en pantalla.
 */
const t = (key: MessageKey, vars?: Record<string, string | number>) => {
  const raw = messages[key]?.es ?? key;
  return vars ? raw.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? `{${k}}`)) : raw;
};

describe("cómo se lee un ajuste del agente", () => {
  it("la identidad se dice por su nombre, y su ausencia también", () => {
    expect(settingValue(t, "identity", { name: "Espiga", persona: "" })).toBe("Se presenta como «Espiga»");
    expect(settingValue(t, "identity", { name: "", persona: "" })).toBe("Sin nombre propio");
  });

  it("el horario distingue atender siempre de tener franjas", () => {
    expect(settingValue(t, "schedule", { weekly: {}, timezone: "Europe/Madrid" })).toBe("Atiende siempre");
    expect(settingValue(t, "schedule", { weekly: { mon: [["09:00", "18:00"]], tue: [] }, timezone: "Europe/Madrid" })).toBe(
      "Con horario: 1 días con franja (Europe/Madrid)",
    );
  });

  it("el escalado cuenta las situaciones en vez de enumerar claves internas", () => {
    expect(settingValue(t, "escalation", { enabled: true, triggers: ["user_asks_human", "angry", "out_of_scope"] })).toBe(
      "Pasa a una persona en 3 situaciones",
    );
    expect(settingValue(t, "escalation", { enabled: false, triggers: [] })).toBe("Nunca pasa a una persona");
  });

  it("el aviso de IA se dice en los dos sentidos", () => {
    expect(settingValue(t, "ai_disclosure", { enabled: true })).toBe("Avisa de que es una IA");
    expect(settingValue(t, "ai_disclosure", { enabled: false })).toBe("No avisa de que es una IA");
  });

  it("los idiomas dicen en cuál responde y cuáles admite", () => {
    expect(settingValue(t, "languages", { primary: "es", allowed: ["es", "en"] })).toBe("Responde en es; admite es, en");
  });

  it("un objetivo largo se recorta en vez de romper la fila", () => {
    const long = "a".repeat(400);
    const shown = settingValue(t, "objective", long);
    expect(shown.length).toBeLessThan(130);
    expect(shown.endsWith("…»")).toBe(true);
    expect(settingValue(t, "objective", "   ")).toBe("Sin objetivo escrito");
  });

  it("lo que no existe se dice, no se deja en blanco", () => {
    expect(settingValue(t, "schedule", null)).toBe("sin definir");
    expect(settingValue(t, "cualquiera", undefined)).toBe("sin definir");
  });

  it("un campo que la consola no conozca se resume, sin claves vacías y sin desaparecer", () => {
    // Que falte una frase nunca puede esconder un cambio.
    expect(settingValue(t, "futuro", { algo: "sí", vacio: "", lista: [] })).toBe("algo: sí");
    expect(settingValue(t, "futuro", { vacio: "", lista: [] })).toBe("sin definir");
  });
});
