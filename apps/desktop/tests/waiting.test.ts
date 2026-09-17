/**
 * Requisito 5.4 — un solo número.
 *
 * Hoy hay tres reglas distintas para la misma pregunta: la pestaña cuenta todo
 * (`App.tsx`), el icono de la barra del sistema excluye lo informativo y corta
 * en «9+», y el icono de la aplicación excluye lo informativo sin tope. Tres
 * superficies, tres cifras, y ninguna manera de saber cuál es la buena.
 *
 * Aquí se fija **una** definición y se separa de su presentación:
 *
 * * **cuenta** lo que espera una decisión *de esta persona*. Lo informativo no
 *   espera nada, y lo que ella no puede decidir tampoco es suyo: sigue en
 *   Pendientes, con a quién pedírselo, pero no la persigue por el Dock;
 * * **el tope visual** («9+») es decoración de esa cifra, no otra cifra.
 */
import { describe, expect, it } from "vitest";

import { badgeText, waitingFrom, type WaitingItem } from "../src/waiting.js";

const item = (over: Partial<WaitingItem> = {}): WaitingItem => ({
  action_id: crypto.randomUUID(),
  teammate_id: "t1",
  level: "critico",
  since: "2026-09-17T20:00:00Z",
  can_decide: true,
  ...over,
});

describe("qué cuenta como «te espera»", () => {
  it("lo crítico y lo que avisa cuentan", () => {
    const waiting = waitingFrom([item({ level: "critico" }), item({ level: "aviso" })]);
    expect(waiting.count).toBe(2);
  });

  it("lo informativo no espera nada, así que no cuenta", () => {
    const waiting = waitingFrom([item({ level: "informativo" }), item({ level: "critico" })]);
    expect(waiting.count).toBe(1);
  });

  it("lo que esta persona no puede decidir no la persigue", () => {
    const waiting = waitingFrom([item({ can_decide: false }), item({ can_decide: true })]);
    expect(waiting.count).toBe(1);
    // Pero sigue estando en la lista: en Pendientes se ve, con a quién pedírselo.
    expect(waiting.items).toHaveLength(2);
  });

  it("sin nada esperando, la cifra es cero y no hay nada que pintar", () => {
    expect(waitingFrom([]).count).toBe(0);
    expect(badgeText(waitingFrom([]))).toBe("");
  });
});

describe("la cifra es una, y las superficies sólo la presentan", () => {
  it("el mismo derivado alimenta las cuatro", () => {
    const waiting = waitingFrom([item(), item(), item({ level: "informativo" })]);
    // Lista lateral y Pendientes usan `count` tal cual; los iconos, su texto.
    expect(waiting.count).toBe(2);
    expect(badgeText(waiting)).toBe("2");
  });

  it("el tope visual no cambia la cifra, sólo cómo se escribe", () => {
    const muchas = waitingFrom(Array.from({ length: 12 }, () => item()));
    expect(muchas.count).toBe(12);
    expect(badgeText(muchas)).toBe("9+");
  });

  it("y el tope se puede quitar donde hay sitio, sin tocar el derivado", () => {
    const muchas = waitingFrom(Array.from({ length: 12 }, () => item()));
    expect(badgeText(muchas, { cap: false })).toBe("12");
  });
});

describe("decidir baja la cifra en todas partes a la vez", () => {
  it("quitar una decisión deja una menos", () => {
    const uno = item();
    const otro = item();
    const antes = waitingFrom([uno, otro]);
    const despues = waitingFrom([otro]);
    expect(antes.count).toBe(2);
    expect(despues.count).toBe(1);
    expect(badgeText(despues)).toBe("1");
  });

  it("el derivado no guarda estado: es lo que hay, cada vez", () => {
    const lista = [item()];
    const a = waitingFrom(lista);
    const b = waitingFrom(lista);
    expect(a).toEqual(b);
  });
});

describe("el número no dice de qué va", () => {
  it("lo que viaja a los iconos es una cifra, nunca un asunto", () => {
    const waiting = waitingFrom([item()]);
    // El icono se ve en una pantalla compartida, sin sesión delante.
    expect(JSON.stringify(badgeText(waiting))).not.toMatch(/[a-z]{4,}/i);
  });
});
