/**
 * La barra dice que hay una versión esperando — spec 008, R3.7 y R3.8.
 *
 * Lo que estos casos fijan no es que el campo exista, sino **las tres
 * decisiones** que lo rodean y que serían fáciles de deshacer sin querer:
 *
 * 1. Es **ortogonal a `status`**, no un octavo estado. Una máquina puede estar
 *    `conectada` y tener una versión esperando; fundirlo en la enumeración
 *    obligaría a elegir cuál de las dos cosas se pinta.
 * 2. **«Lista» y «esperando» son distintas.** La segunda explica por qué la
 *    aplicación *no* se está actualizando, que es la pregunta que alguien se
 *    hace cuando le dijeron que había versión nueva y sigue viendo la vieja.
 * 3. **Sin versión, no se dice nada** — ni indicador apagado ni pantalla que
 *    explique lo que no tienes (§V: la ausencia se diseña).
 */
import { describe, expect, it } from "vitest";

import {
  actionsFor,
  heartbeatRuns,
  initialState,
  localToolsOffered,
  transition,
} from "../src/workstation-state.js";

const conectada = transition(initialState(), {
  kind: "pair_ok",
  machine: { displayName: "Mac de Luis", hostname: "mac-luis" },
});

describe("la versión esperando", () => {
  it("al principio no hay nada que decir", () => {
    expect(initialState().update).toBeUndefined();
  });

  it("lista para instalar al cerrar", () => {
    const s = transition(conectada, { kind: "update_ready", version: "1.2.0", waiting: false });
    expect(s.update).toEqual({ version: "1.2.0", waiting: false });
  });

  it("esperando: se distingue de lista, y ésa es la diferencia que importa", () => {
    const s = transition(conectada, { kind: "update_ready", version: "1.2.0", waiting: true });
    expect(s.update?.waiting).toBe(true);
  });

  it("cuando deja de haberla, vuelve a no decirse nada — no a «ninguna»", () => {
    const con = transition(conectada, { kind: "update_ready", version: "1.2.0", waiting: false });
    expect(transition(con, { kind: "update_gone" }).update).toBeUndefined();
  });

  it("NO toca el status: seguir conectada y tener versión esperando no se excluyen", () => {
    const s = transition(conectada, { kind: "update_ready", version: "1.2.0", waiting: true });
    expect(s.status).toBe("conectada");
    expect(s.machine).toEqual(conectada.machine);
  });

  it("y por tanto no altera lo que cuelga del status", () => {
    // Las herramientas locales sólo existen en `conectada` (12.3) y el latido
    // sólo corre en `conectada` y `reconectando`. Si una actualización esperando
    // pudiera apagarlos, habría convertido un aviso en una avería.
    const s = transition(conectada, { kind: "update_ready", version: "1.2.0", waiting: true });
    expect(localToolsOffered(s.status)).toBe(true);
    expect(heartbeatRuns(s.status)).toBe(true);
  });

  it("sobrevive a un cambio de estado de conexión: reconectar no borra la versión", () => {
    const con = transition(conectada, { kind: "update_ready", version: "1.2.0", waiting: false });
    const perdida = transition(con, { kind: "link_lost" });
    expect(perdida.update).toEqual({ version: "1.2.0", waiting: false });
  });
});

describe("cuando la plataforma exige una versión más nueva", () => {
  const rechazada = transition(conectada, {
    kind: "version_rejected",
    minimumVersion: "2.0.0",
  });

  it("es un estado propio, y dice qué versión hace falta", () => {
    expect(rechazada.status).toBe("version_no_admitida");
    expect(rechazada.requiredVersion).toBe("2.0.0");
  });

  it("**conserva la máquina**: esto no es desemparejar", () => {
    // Si este caso se cayera, exigir una versión mínima desemparejaría a todo
    // el mundo a la vez — el daño exacto que la puerta venía a evitar.
    expect(rechazada.machine).toEqual(conectada.machine);
  });

  it("ofrece actualizar, y NO introducir código", () => {
    const acciones = actionsFor(rechazada);
    expect(acciones).toContain("actualizar");
    expect(acciones).not.toContain("introducir_codigo");
    expect(acciones).not.toContain("desemparejar");
  });

  it("el puente para: ni latido ni herramientas locales", () => {
    expect(heartbeatRuns(rechazada.status)).toBe(false);
    expect(localToolsOffered(rechazada.status)).toBe(false);
  });

  it("no se pinta como error — como ninguno de los demás", () => {
    expect(rechazada.lastError).toBeUndefined();
  });

  it("se sale solo: al reconectar tras actualizar, vuelve a estar conectada", () => {
    const vuelta = transition(rechazada, {
      kind: "restored",
      machine: { displayName: "Mac de Luis", hostname: "mac-luis" },
    });
    expect(vuelta.status).toBe("conectada");
  });
});
