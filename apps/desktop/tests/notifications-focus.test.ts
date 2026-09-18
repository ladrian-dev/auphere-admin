/**
 * Requisitos 5.5, 5.6 y 12.2 — el aviso del sistema: cuándo, qué dice, y en qué
 * idioma.
 *
 * Tres cosas que estaban mal y que no se ven mirando la pantalla, porque pasan
 * fuera de ella:
 *
 * * **se avisaba con la ventana delante.** El contrato de la taxonomía es
 *   tajante —«aviso del sistema: sólo con la ventana sin foco»— y avisar por el
 *   sistema operativo de algo que la persona está mirando es la manera más
 *   rápida de que apague los avisos de esta aplicación para siempre.
 * * **el cuerpo era el título de la propuesta.** «Ejecutar `rm -rf /tmp/x` en
 *   Boreal» acaba en el centro de notificaciones del sistema, visible en una
 *   pantalla compartida y sin sesión delante. El aviso dice **el motivo**;
 *   el asunto se lee dentro.
 * * **el resumen estaba sólo en español** (`notifications-policy.ts`), dentro de
 *   una aplicación que habla dos idiomas.
 */
import { describe, expect, it } from "vitest";

import { type Pending, onArrival, onOpen } from "../src/notifications-policy.js";

const PREFS = { silenceAviso: false, permission: "concedido" as const };
const FONDO = { windowFocused: false, lang: "es" as const };

const pending = (over: Partial<Pending> = {}): Pending => ({
  action_id: "a-1",
  level: "critico",
  teammate: "Sofía",
  title: "Ejecutar `rm -rf /tmp/boreal` en Boreal",
  can_decide: true,
  ...over,
});

const notifies = (effects: ReturnType<typeof onArrival>) => effects.filter((e) => e.kind === "notify");
const badges = (effects: ReturnType<typeof onArrival>) => effects.filter((e) => e.kind === "badge");

describe("con la ventana delante, el sistema operativo no se usa", () => {
  it("una llegada crítica no saca un aviso del sistema", () => {
    const item = pending();
    const effects = onArrival(item, PREFS, [item], { windowFocused: true, lang: "es" });
    expect(notifies(effects)).toHaveLength(0);
  });

  it("pero el número sí se actualiza: eso no interrumpe a nadie", () => {
    const item = pending();
    const effects = onArrival(item, PREFS, [item], { windowFocused: true, lang: "es" });
    expect(badges(effects)).toHaveLength(1);
  });

  it("y al abrir con cosas esperando tampoco, porque se ven al abrir", () => {
    const item = pending();
    expect(notifies(onOpen([item], PREFS, { windowFocused: true, lang: "es" }))).toHaveLength(0);
  });

  it("sin foco sí, que es para lo que existe", () => {
    const item = pending();
    expect(notifies(onArrival(item, PREFS, [item], FONDO))).toHaveLength(1);
  });
});

describe("dice el motivo, nunca el contenido", () => {
  it("el cuerpo no lleva el título de la propuesta", () => {
    const item = pending();
    const [aviso] = notifies(onArrival(item, PREFS, [item], FONDO));
    expect(aviso).toBeDefined();
    if (aviso?.kind !== "notify") throw new Error("sin aviso");
    expect(aviso.body).not.toMatch(/rm -rf/);
    expect(aviso.body).not.toMatch(/Boreal/);
  });

  it("y dice lo que pasa: espera tu decisión", () => {
    const item = pending();
    const [aviso] = notifies(onArrival(item, PREFS, [item], FONDO));
    if (aviso?.kind !== "notify") throw new Error("sin aviso");
    expect(aviso.body).toMatch(/espera tu decisión/i);
    // El teammate sí: es quién, no qué.
    expect(aviso.title).toBe("Sofía");
  });
});

describe("agrupa por teammate: una notificación por quien espera", () => {
  it("tres cosas del mismo teammate no son tres avisos", () => {
    const items = [
      pending({ action_id: "a-1" }),
      pending({ action_id: "a-2" }),
      pending({ action_id: "a-3" }),
    ];
    const avisos = notifies(onOpen(items, PREFS, FONDO));
    expect(avisos).toHaveLength(1);
    if (avisos[0]?.kind !== "notify") throw new Error("sin aviso");
    expect(avisos[0].title).toBe("Sofía");
    expect(avisos[0].body).toMatch(/3/);
  });

  it("dos teammates son dos avisos, cada uno con su nombre", () => {
    const items = [pending({ action_id: "a-1" }), pending({ action_id: "a-2", teammate: "Nilo" })];
    const avisos = notifies(onOpen(items, PREFS, FONDO));
    expect(avisos).toHaveLength(2);
    expect(avisos.map((a) => (a.kind === "notify" ? a.title : ""))).toEqual(["Sofía", "Nilo"]);
  });

  it("con una sola, el aviso lleva a su tarjeta; con varias, a la bandeja", () => {
    const uno = notifies(onOpen([pending()], PREFS, FONDO));
    expect(uno[0]?.kind === "notify" ? uno[0].actionId : null).toBe("a-1");
    const varios = notifies(onOpen([pending({ action_id: "a-1" }), pending({ action_id: "a-2" })], PREFS, FONDO));
    expect(varios[0]?.kind === "notify" ? varios[0].actionId : "x").toBeNull();
  });
});

describe("y habla el idioma de la cuenta (12.2)", () => {
  it("en inglés no quedan restos de español", () => {
    const items = [pending({ action_id: "a-1" }), pending({ action_id: "a-2" })];
    const avisos = notifies(onOpen(items, PREFS, { windowFocused: false, lang: "en" }));
    if (avisos[0]?.kind !== "notify") throw new Error("sin aviso");
    expect(avisos[0].body).toMatch(/waiting/i);
    expect(avisos[0].body).not.toMatch(/esperan|decisiones/);
  });

  it("y el español sigue siendo el recurso cuando no consta el idioma", () => {
    const item = pending();
    const avisos = notifies(onArrival(item, PREFS, [item], { windowFocused: false, lang: "es" }));
    if (avisos[0]?.kind !== "notify") throw new Error("sin aviso");
    expect(avisos[0].body).toMatch(/espera tu decisión/i);
  });
});
