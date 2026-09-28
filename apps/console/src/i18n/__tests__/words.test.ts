import { describe, expect, it } from "vitest";

import { messages, type Locale, type MessageKey } from "../messages";

/**
 * Las palabras dicen lo que son (spec 018, US4).
 *
 * Nadie tiene que aprender el vocabulario interno de Auphere para usar la
 * consola. Dos cosas se fijan aquí:
 *
 * 1. **«Capacidades» e «Integraciones» no se ven en ninguna parte.** Se
 *    llaman Habilidades y Conectores. Las rutas y las claves siguen siendo
 *    `capabilities` e `integrations` a propósito (decisión de la Fase 0):
 *    cambiarlas obligaría a otra ronda de redirecciones y la única ganancia
 *    sería estética, en una cadena que nadie escribe a mano.
 * 2. **Las dos pantallas de documentos dicen quién las lee.** Son la
 *    confusión que más caro sale: subir al sitio equivocado significa que el
 *    agente no ve lo que debía ver, o que ve lo que no era para él.
 */

const LOCALES: Locale[] = ["es", "en"];

/** Todo el texto que un partner puede llegar a leer, con su clave. */
function visible(): Array<[MessageKey, Locale, string]> {
  const out: Array<[MessageKey, Locale, string]> = [];
  for (const [key, entry] of Object.entries(messages) as Array<[MessageKey, Record<Locale, string>]>) {
    for (const locale of LOCALES) out.push([key, locale, entry[locale] ?? entry.es]);
  }
  return out;
}

describe("Las palabras · Habilidades y Conectores", () => {
  it("«Capacidades» y «Capabilities» no se leen en ninguna pantalla", () => {
    const culpables = visible()
      .filter(([, , text]) => /\bcapacidad(es)?\b|\bcapabilit(y|ies)\b/i.test(text))
      .map(([key, locale, text]) => `${key} [${locale}] → ${text}`);
    expect(culpables, "quedan pantallas llamándolas capacidades").toEqual([]);
  });

  it("«Integraciones» e «Integrations» tampoco", () => {
    const culpables = visible()
      .filter(([, , text]) => /\bintegraci(ón|ones)\b|\bintegrations?\b/i.test(text))
      .map(([key, locale, text]) => `${key} [${locale}] → ${text}`);
    expect(culpables, "quedan pantallas llamándolas integraciones").toEqual([]);
  });

  it("y sí existen los nombres nuevos, en los dos idiomas", () => {
    // Que no aparezcan los viejos no basta: podrían no aparecer **ninguno**.
    expect(messages["clients.nav.capabilities"]).toEqual({ es: "Habilidades", en: "Skills" });
    expect(messages["clients.nav.integrations"]).toEqual({ es: "Conectores", en: "Connectors" });
    expect(messages["cap.title"].es).toBe("Habilidades");
    expect(messages["int.title"].es).toBe("Conectores");
  });
});

describe("Las palabras · quién lee cada cosa", () => {
  it("Conocimiento dice que lo lee el agente de ESE cliente, y solo ése", () => {
    // Sin el «de este cliente» la frase es cierta y no sirve: el partner
    // tiene varios clientes y la pregunta que trae es si lo que sube aquí
    // se va a mezclar con los demás.
    for (const locale of LOCALES) {
      const text = messages["knowledge.description"][locale];
      expect(text, `knowledge.description [${locale}]`).toMatch(
        locale === "es" ? /este cliente/i : /this client/i,
      );
    }
  });

  it("la Guía del partner dice que la lee el Companion y que el agente no", () => {
    for (const locale of LOCALES) {
      const text = messages["playbook.description"][locale];
      expect(text, `playbook.description [${locale}] · quién la lee`).toMatch(/companion/i);
      expect(text, `playbook.description [${locale}] · quién NO la ve`).toMatch(
        locale === "es" ? /no (la )?ve|ningún agente/i : /does not see|no .*agent sees/i,
      );
    }
  });

  it("las dos no se describen igual: si se confunden, es que no las distinguimos", () => {
    for (const locale of LOCALES) {
      expect(messages["knowledge.description"][locale]).not.toBe(messages["playbook.description"][locale]);
    }
  });
});
