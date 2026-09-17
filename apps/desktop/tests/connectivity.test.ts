/**
 * Requisitos 3.1 y 3.2 — «sin red» no es «sin sesión».
 *
 * Éste es uno de los cinco fallos que impiden completar el recorrido básico:
 * hoy, cualquier excepción al preguntar quién está dentro se convierte en «no
 * hay nadie», y la aplicación manda a la persona a iniciar sesión… sin red,
 * sobre la página de error del navegador. Es la peor versión posible de un
 * corte de wifi.
 *
 * La distinción es de tres estados, no de dos: `online`, `offline` y
 * **`unconfirmed`** — «no pude preguntar». El tercero conserva el último
 * veredicto en vez de inventar uno nuevo.
 */
import { describe, expect, it } from "vitest";

import { type Connectivity, connectivityFrom, keepsLastVerdict, noteFailure, noteSuccess } from "../src/connectivity.js";

const t0 = "2026-09-17T20:00:00.000Z";
const t1 = "2026-09-17T20:00:30.000Z";

describe("los tres estados se distinguen", () => {
  it("una respuesta buena deja la conexión en `online`", () => {
    expect(noteSuccess({ state: "unconfirmed", since: t0 }, t1).state).toBe("online");
  });

  it("un fallo de red deja `offline`, no «sin sesión»", () => {
    const next = noteFailure({ state: "online", since: t0 }, { kind: "network" }, t1);
    expect(next.state).toBe("offline");
  });

  it("una respuesta que no se pudo interpretar deja `unconfirmed`", () => {
    const next = noteFailure({ state: "online", since: t0 }, { kind: "unknown" }, t1);
    expect(next.state).toBe("unconfirmed");
  });

  it("un 401 **sí** es una respuesta: la conexión está bien", () => {
    // Que la plataforma conteste «no hay sesión» no es un problema de red, y
    // confundirlos es lo que hace que un corte de wifi eche a la persona.
    const next = noteSuccess({ state: "offline", since: t0 }, t1);
    expect(next.state).toBe("online");
  });
});

describe("mientras no se pueda confirmar, no se afirma nada nuevo", () => {
  it("`offline` y `unconfirmed` conservan el último veredicto", () => {
    expect(keepsLastVerdict({ state: "offline", since: t0 })).toBe(true);
    expect(keepsLastVerdict({ state: "unconfirmed", since: t0 })).toBe(true);
  });

  it("`online` no: lo que diga la plataforma manda", () => {
    expect(keepsLastVerdict({ state: "online", since: t0 })).toBe(false);
  });
});

describe("desde cuándo", () => {
  it("el reloj se reinicia al cambiar de estado", () => {
    const caido = noteFailure({ state: "online", since: t0 }, { kind: "network" }, t1);
    expect(caido.since).toBe(t1);
  });

  it("y no se reinicia mientras el estado siga siendo el mismo", () => {
    const caido: Connectivity = { state: "offline", since: t0 };
    const sigueCaido = noteFailure(caido, { kind: "network" }, t1);
    expect(sigueCaido.since).toBe(t0);
  });
});

describe("cómo se construye desde lo que ve el proceso principal", () => {
  it("sin ningún intento todavía, no se sabe", () => {
    expect(connectivityFrom(null, t0)).toEqual({ state: "unconfirmed", since: t0 });
  });

  it("con un error de red conocido, offline", () => {
    expect(connectivityFrom({ kind: "network" }, t0).state).toBe("offline");
  });
});
