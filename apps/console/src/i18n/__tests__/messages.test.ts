import { describe, expect, it } from "vitest";

import { messages, t } from "../messages";

const LEAKS = ["NEXUS_", "LITELLM_", "sk-", "NEXUS_META_APP_ID"] as const;

describe("i18n messages", () => {
  it("every key has ES and EN", () => {
    for (const [key, entry] of Object.entries(messages)) {
      expect(entry.es, key).toBeTruthy();
      expect(entry.en, key).toBeTruthy();
    }
  });
  it("interpolates variables", () => {
    // `clients.quota` («{used} de {max} clientes») era el ejemplo hasta que
    // el límite de clientes se retiró (spec 019): el crédito interpola igual
    // y sí existe.
    expect(t("es", "clients.quota.value", { remaining: "3,00 US$", cap: "5,00 US$" })).toBe("Quedan 3,00 US$ de 5,00 US$");
    expect(t("en", "clients.quota.value", { remaining: "$3.00", cap: "$5.00" })).toBe("$3.00 of $5.00 left");
  });
  it("una clave con `.one` dice el singular cuando la cuenta es 1 (spec 046)", () => {
    expect(t("es", "clients.count", { count: 1 })).toBe("1 cliente");
    expect(t("es", "clients.count", { count: 3 })).toBe("3 clientes");
    expect(t("es", "hu.usage.unpriced", { count: "1" })).toMatch(/^1 registro del periodo/);
    expect(t("es", "clients.audience.only", { n: 1 })).toBe("Responde solo a 1 número");
    expect(t("en", "clients.audience.only", { n: 2 })).toBe("Answers only 2 numbers");
    // Sin hermano `.one`, la clave se queda como está.
    expect(t("es", "ch.quota", { used: 1, max: 1 })).toBe("1 de 1 canales");
  });
  it("ninguna frase deja el plural a medias con «(s)»", () => {
    for (const [key, entry] of Object.entries(messages)) {
      expect(entry.es, key).not.toMatch(/(?<!http)\(s\)/);
    }
  });
  it("partner-facing copy never names env vars, proxy keys, or sk-", () => {
    for (const [key, entry] of Object.entries(messages)) {
      for (const locale of ["es", "en"] as const) {
        const copy = entry[locale];
        for (const leak of LEAKS) {
          expect(copy, key + "." + locale).not.toContain(leak);
        }
      }
    }
  });
});
