/**
 * Requisito 7 — tres niveles y una política que no se puede inflar.
 */
import { describe, expect, it } from "vitest";

import {
  DEFAULT_PREFS,
  type Pending,
  badgeCount,
  normalisePrefs,
  onArrival,
  onOpen,
} from "../src/notifications-policy.js";

const item = (level: Pending["level"], id = "a1", can_decide = true): Pending => ({
  action_id: id,
  level,
  teammate: "Sofía",
  title: "Asignar el rol de atención",
  can_decide,
});

/**
 * Spec 010, R5.5 y R12.2: avisar depende ahora de si la ventana está delante y
 * de en qué idioma habla la cuenta. Estos casos son los de **sin foco**, que es
 * cuando el aviso del sistema tiene sentido; los del foco puesto y el resumen
 * agrupado por teammate viven en `notifications-focus.test.ts`.
 */
const FONDO = { windowFocused: false, lang: "es" as const };
/** Con el ruido bajado. El permiso del sistema no entra en esta política. */
const SILENCIADO = { silenceAviso: true, permission: "concedido" as const };

describe("el número es el mismo que el de las demás superficies (spec 010, 5.4)", () => {
  it("lo que esta persona no puede decidir no marca el icono", () => {
    // La regla vive en `waiting.ts` y la comparten las cuatro superficies:
    // antes cada una contaba a su manera y la ventana decía tres cifras.
    const effects = onArrival(item("critico"), DEFAULT_PREFS, [item("critico", "a1", false)], FONDO);
    expect(effects.find((e) => e.kind === "badge")).toEqual({ kind: "badge", count: 0 });
  });
});

describe("un aviso que llega con la aplicación abierta", () => {
  it("crítico interrumpe con el sistema operativo y marca la bandeja", () => {
    const effects = onArrival(item("critico"), DEFAULT_PREFS, [item("critico")], FONDO);
    expect(effects).toContainEqual({ kind: "badge", count: 1 });
    // R5.6: el cuerpo dice **el motivo**, nunca el título de la propuesta —
    // que es donde acababa el comando literal o el cliente final.
    expect(effects).toContainEqual({
      kind: "notify",
      title: "Sofía",
      body: "Espera tu decisión",
      actionId: "a1",
    });
  });

  it("aviso marca la bandeja y NO interrumpe", () => {
    const effects = onArrival(item("aviso"), DEFAULT_PREFS, [item("aviso")], FONDO);
    expect(effects.some((e) => e.kind === "notify")).toBe(false);
    expect(effects).toContainEqual({ kind: "badge", count: 1 });
  });

  it("informativo no hace nada, ni siquiera contar", () => {
    const effects = onArrival(item("informativo"), DEFAULT_PREFS, [item("informativo")], FONDO);
    expect(effects).toEqual([{ kind: "badge", count: 0 }]);
    expect(badgeCount([item("informativo"), item("aviso", "a2")])).toBe(1);
  });
});

describe("al abrir con cosas esperando (7.3)", () => {
  // Spec 010 R5.6: el resumen se agrupa **por teammate**. Antes era uno solo
  // titulado «Tu equipo te espera», que no dejaba saber quién espera; y como
  // estas tres son de Sofía, siguen siendo un aviso, no tres.
  it("avisa UNA vez por teammate, no una por tarjeta", () => {
    const pending = [item("critico", "a1"), item("critico", "a2"), item("aviso", "a3")];
    const notifies = onOpen(pending, DEFAULT_PREFS, FONDO).filter((e) => e.kind === "notify");
    expect(notifies).toHaveLength(1);
    expect(notifies[0]).toMatchObject({ title: "Sofía", body: "3 cosas esperan tu decisión", actionId: null });
  });

  it("con una sola, el aviso lleva a su tarjeta", () => {
    const notifies = onOpen([item("critico", "solo")], DEFAULT_PREFS, FONDO).filter((e) => e.kind === "notify");
    expect(notifies[0]).toMatchObject({ title: "Sofía", actionId: "solo" });
  });

  it("sin nada que espere, no suena", () => {
    expect(onOpen([], DEFAULT_PREFS, FONDO)).toEqual([{ kind: "badge", count: 0 }]);
    expect(onOpen([item("informativo")], DEFAULT_PREFS, FONDO)).toEqual([{ kind: "badge", count: 0 }]);
  });
});

describe("la preferencia solo baja el ruido (7.5)", () => {
  it("silenciar `aviso` calla el resumen cuando solo hay avisos", () => {
    const pending = [item("aviso", "a1"), item("aviso", "a2")];
    expect(onOpen(pending, SILENCIADO, FONDO).some((e) => e.kind === "notify")).toBe(false);
    expect(onOpen(pending, SILENCIADO, FONDO)).toContainEqual({ kind: "badge", count: 2 });
  });

  it("silenciar `aviso` NO calla lo crítico", () => {
    const pending = [item("critico", "a1"), item("aviso", "a2")];
    expect(onOpen(pending, SILENCIADO, FONDO).some((e) => e.kind === "notify")).toBe(true);
  });

  // Spec 010 R7.8: estas preferencias llevan además lo que se sabe del permiso
  // del sistema. `desconocido` es el punto de partida y no se puede fabricar.
  it("no hay forma de subir el nivel de nada: la preferencia es un booleano", () => {
    expect(normalisePrefs(SILENCIADO)).toEqual(SILENCIADO);
    expect(normalisePrefs(undefined)).toEqual({ silenceAviso: false, permission: "desconocido" });
    expect(normalisePrefs({ shout: true } as never)).toEqual({ silenceAviso: false, permission: "desconocido" });
  });

  it("y el permiso guardado sobrevive, salvo que sea uno inventado", () => {
    expect(normalisePrefs({ silenceAviso: false, permission: "denegado" }).permission).toBe("denegado");
    expect(normalisePrefs({ silenceAviso: false, permission: "quizá" } as never).permission).toBe("desconocido");
  });
});
