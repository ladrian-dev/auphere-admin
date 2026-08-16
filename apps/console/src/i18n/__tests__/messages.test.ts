import { describe, expect, it } from "vitest";

import { messages, t } from "../messages";

describe("i18n messages", () => {
  it("every key has ES and EN", () => {
    for (const [key, entry] of Object.entries(messages)) {
      expect(entry.es, key).toBeTruthy();
      expect(entry.en, key).toBeTruthy();
    }
  });
  it("interpolates variables", () => {
    expect(t("es", "clients.quota", { used: 3, max: 5 })).toBe("3 de 5 clientes");
    expect(t("en", "clients.quota", { used: 3, max: 5 })).toBe("3 of 5 clients");
  });
});
