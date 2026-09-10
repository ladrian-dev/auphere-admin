/**
 * Requisitos 3.4, 3.5, 3.7 — los estados del hilo se derivan y ninguno miente.
 */
import { describe, expect, it } from "vitest";

import { THREAD_STATES, applyInboxChanged, applyTaskState, deriveThreadState, isFailure, type ThreadFacts } from "../src/app-state.js";

const base: ThreadFacts = {
  status: "ready",
  runStatus: "idle",
  reconnecting: false,
  partial: false,
  itemCount: 3,
  taskState: null,
  budgetPaused: false,
  machineNeeded: false,
  machinePresent: true,
};

describe("deriveThreadState", () => {
  it("nombra los nueve estados", () => {
    expect(THREAD_STATES).toHaveLength(9);
    expect(deriveThreadState({ ...base, status: "loading" })).toBe("cargando");
    expect(deriveThreadState({ ...base, status: "error" })).toBe("error");
    expect(deriveThreadState({ ...base, reconnecting: true })).toBe("reconectando");
    expect(deriveThreadState({ ...base, budgetPaused: true })).toBe("en_pausa_por_tope");
    expect(deriveThreadState({ ...base, taskState: "esperandote" })).toBe("esperandote");
    expect(deriveThreadState({ ...base, runStatus: "waiting" })).toBe("esperandote");
    expect(deriveThreadState({ ...base, machineNeeded: true, machinePresent: false })).toBe("maquina_ausente");
    expect(deriveThreadState({ ...base, partial: true })).toBe("parcial");
    expect(deriveThreadState({ ...base, itemCount: 0 })).toBe("vacio");
    expect(deriveThreadState(base)).toBe("normal");
  });
  it("la pausa por tope manda sobre la espera, y la espera sobre la máquina ausente (§V)", () => {
    expect(deriveThreadState({ ...base, budgetPaused: true, taskState: "esperandote" })).toBe("en_pausa_por_tope");
    expect(deriveThreadState({ ...base, taskState: "esperandote", machineNeeded: true, machinePresent: false })).toBe("esperandote");
  });
  it("solo `error` es un fallo, y es el de la pantalla", () => {
    expect(THREAD_STATES.filter(isFailure)).toEqual(["error"]);
  });
});

describe("el roster y la bandeja cambian sin recargar", () => {
  const roster = [
    { id: "a", my_state: "en_espera" as const, my_unread: false },
    { id: "b", my_state: "en_marcha" as const, my_unread: false },
  ];
  it("task.state mueve el estado del teammate y solo el suyo", () => {
    const next = applyTaskState(roster, "b", "esperandote");
    expect(next[1]?.my_state).toBe("esperandote");
    expect(next[0]).toEqual(roster[0]);
    expect(applyTaskState(roster, "b", "terminada")[1]).toMatchObject({ my_state: "en_espera", my_unread: true });
  });
  it("inbox.changed retira la tarjeta decidida", () => {
    expect(applyInboxChanged([{ action_id: "x" }, { action_id: "y" }], "x")).toEqual([{ action_id: "y" }]);
  });
});
