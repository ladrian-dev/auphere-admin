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
