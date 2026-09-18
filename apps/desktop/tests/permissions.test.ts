/**
 * Requisitos 7.8 y 7.10 — los permisos del sistema operativo.
 *
 * Dos reglas y un estado incómodo:
 *
 * * **se piden al usarlos por primera vez, explicando para qué.** Pedirlos al
 *   arrancar, todos de golpe y sin contexto, es la razón por la que la gente
 *   los deniega: nadie concede acceso a algo que todavía no sabe para qué es;
 * * **denegado se dice**: qué deja de funcionar y cómo concederlo. Un permiso
 *   denegado y callado se vive como una aplicación rota.
 *
 * Y `desconocido` existe a propósito. macOS no deja preguntar por el estado de
 * los avisos —`systemPreferences` cubre cámara y micrófono, no éstos—, así que
 * antes de pedirlo **no consta**. Asumir «concedido» pondría la lista de puesta
 * en marcha a decir que algo está hecho sin saberlo, que es justo §V.
 */
import { describe, expect, it } from "vitest";

import {
  PERMISSION_STATES,
  type PermissionState,
  askedFor,
  explains,
  losesWhenDenied,
  nextAfterAttempt,
} from "../src/permissions.js";

describe("los tres estados, y por qué son tres", () => {
  it("desconocido no es concedido", () => {
    expect([...PERMISSION_STATES]).toEqual(["desconocido", "concedido", "denegado"]);
  });

  it("antes de pedirlo, no consta", () => {
    expect(askedFor("desconocido")).toBe(false);
    expect(askedFor("concedido")).toBe(true);
    expect(askedFor("denegado")).toBe(true);
  });
});

describe("se pide al usarlo, no al arrancar", () => {
  it("un intento que sale bien deja constancia de que se concedió", () => {
    expect(nextAfterAttempt("desconocido", { shown: true })).toBe("concedido");
  });

  it("y uno que no, de que no", () => {
    expect(nextAfterAttempt("desconocido", { shown: false })).toBe("denegado");
  });

  it("lo ya concedido no se degrada por un fallo puntual", () => {
    // Un aviso que no salió porque el sistema estaba en No molestar no es una
    // denegación, y tratarlo como tal pondría la lista a mentir al revés.
    expect(nextAfterAttempt("concedido", { shown: false })).toBe("concedido");
  });

  it("y lo denegado se recupera en cuanto uno sale", () => {
    expect(nextAfterAttempt("denegado", { shown: true })).toBe("concedido");
  });
});

describe("cada permiso dice para qué, antes de pedirlo (7.8)", () => {
  it("los avisos explican qué van a hacer con ellos", () => {
    expect(explains("notifications")).toMatch(/\w{4,}/);
  });
});

describe("denegado dice qué deja de funcionar y cómo concederlo (7.10)", () => {
  it("nombra lo que se pierde, no «algo puede no funcionar»", () => {
    const perdida = losesWhenDenied("notifications");
    expect(perdida.loses).toMatch(/\w{4,}/);
    // Y lo que **sigue** funcionando, que es casi todo: sin eso, denegar
    // parece romper la aplicación.
    expect(perdida.keeps).toMatch(/\w{4,}/);
  });

  it("y lleva a los ajustes del sistema, no a una explicación de dónde están", () => {
    expect(losesWhenDenied("notifications").settings).toMatch(/^x-apple\.systempreferences:/);
  });
});

describe("lo que este módulo NO hace", () => {
  it("no afirma un estado que el sistema no deja consultar", () => {
    // `desconocido` es el punto de partida, y sólo lo mueve un intento real.
    let state: PermissionState = "desconocido";
    state = nextAfterAttempt(state, { shown: true });
    expect(state).toBe("concedido");
  });
});
