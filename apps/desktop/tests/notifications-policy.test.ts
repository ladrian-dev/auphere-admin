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

const item = (level: Pending["level"], id = "a1"): Pending => ({
  action_id: id,
  level,
  teammate: "Sofía",
  title: "Asignar el rol de atención",
});

describe("un aviso que llega con la aplicación abierta", () => {
  it("crítico interrumpe con el sistema operativo y marca la bandeja", () => {
    const effects = onArrival(item("critico"), DEFAULT_PREFS, [item("critico")]);
    expect(effects).toContainEqual({ kind: "badge", count: 1 });
    expect(effects).toContainEqual({
      kind: "notify",
      title: "Sofía",
      body: "Asignar el rol de atención",
      actionId: "a1",
    });
  });

  it("aviso marca la bandeja y NO interrumpe", () => {
    const effects = onArrival(item("aviso"), DEFAULT_PREFS, [item("aviso")]);
    expect(effects.some((e) => e.kind === "notify")).toBe(false);
    expect(effects).toContainEqual({ kind: "badge", count: 1 });
  });

  it("informativo no hace nada, ni siquiera contar", () => {
    const effects = onArrival(item("informativo"), DEFAULT_PREFS, [item("informativo")]);
    expect(effects).toEqual([{ kind: "badge", count: 0 }]);
    expect(badgeCount([item("informativo"), item("aviso", "a2")])).toBe(1);
  });
});

describe("al abrir con cosas esperando (7.3)", () => {
  it("avisa UNA vez en resumen, no una por tarjeta", () => {
    const pending = [item("critico", "a1"), item("critico", "a2"), item("aviso", "a3")];
    const notifies = onOpen(pending, DEFAULT_PREFS).filter((e) => e.kind === "notify");
    expect(notifies).toHaveLength(1);
    expect(notifies[0]).toMatchObject({ title: "Tu equipo te espera", body: "3 decisiones esperando", actionId: null });
  });

  it("con una sola, el aviso lleva a su tarjeta", () => {
    const notifies = onOpen([item("critico", "solo")], DEFAULT_PREFS).filter((e) => e.kind === "notify");
    expect(notifies[0]).toMatchObject({ title: "Sofía", actionId: "solo" });
  });

  it("sin nada que espere, no suena", () => {
    expect(onOpen([], DEFAULT_PREFS)).toEqual([{ kind: "badge", count: 0 }]);
    expect(onOpen([item("informativo")], DEFAULT_PREFS)).toEqual([{ kind: "badge", count: 0 }]);
  });
});

describe("la preferencia solo baja el ruido (7.5)", () => {
  it("silenciar `aviso` calla el resumen cuando solo hay avisos", () => {
    const pending = [item("aviso", "a1"), item("aviso", "a2")];
    expect(onOpen(pending, { silenceAviso: true }).some((e) => e.kind === "notify")).toBe(false);
    expect(onOpen(pending, { silenceAviso: true })).toContainEqual({ kind: "badge", count: 2 });
  });

  it("silenciar `aviso` NO calla lo crítico", () => {
    const pending = [item("critico", "a1"), item("aviso", "a2")];
    expect(onOpen(pending, { silenceAviso: true }).some((e) => e.kind === "notify")).toBe(true);
  });

  it("no hay forma de subir el nivel de nada: la preferencia es un booleano", () => {
    expect(normalisePrefs({ silenceAviso: true })).toEqual({ silenceAviso: true });
    expect(normalisePrefs(undefined)).toEqual({ silenceAviso: false });
    expect(normalisePrefs({ shout: true } as never)).toEqual({ silenceAviso: false });
  });
});
