/**
 * Requisitos 1.1, 1.3, 12.2 y 12.3 — la máquina de siete estados de la barra.
 *
 * Contrato en `specs/002-identidad-app-escritorio/contracts/desktop-bar.md`.
 * Ningún estado se pinta como error; las herramientas locales solo existen en
 * `conectada`; el latido solo corre en `conectada` y `reconectando`.
 */
import { describe, expect, it } from "vitest";

import {
  BAR_STATUSES,
  actionsFor,
  heartbeatRuns,
  initialState,
  localToolsOffered,
  statusCopyKey,
  statusTone,
  transition,
  type BarState,
} from "../src/workstation-state.js";

const connected = (): BarState =>
  transition(transition(initialState(), { kind: "pair_started" }), {
    kind: "pair_ok",
    machine: { displayName: "MacBook de Luis", hostname: "mac.local" },
  });

describe("los estados del puesto (12.2)", () => {
  it("son exactamente los del contrato", () => {
    expect([...BAR_STATUSES]).toEqual([
      // Spec 010: antes del primer veredicto no se afirma nada.
      "comprobando",
      "sin_emparejar",
      "emparejando",
      "conectada",
      "reconectando",
      "sin_sesion",
      "volver_a_emparejar",
      "archivada_desde_consola",
      // Spec 008. Añadir uno aquí sin tocar `contracts/desktop-bar.md` es
      // justo lo que este caso impide: la lista y el contrato se leen juntos.
      "version_no_admitida",
    ]);
  });

  it("ninguno tiene tono de error, y todos tienen copy", () => {
    for (const status of BAR_STATUSES) {
      expect(statusTone(status)).toBe("estado");
      expect(statusCopyKey(status)).toMatch(/^workstation\.bar\./);
    }
  });

  it("ningún estado contiene una cifra de consumo (8.2)", () => {
    for (const status of BAR_STATUSES) {
      expect(statusCopyKey(status)).not.toMatch(/usage|consumo|tokens|saldo/);
    }
  });
});

describe("herramientas locales y latido (12.3, 1.3)", () => {
  it("las herramientas locales solo existen en conectada", () => {
    for (const status of BAR_STATUSES) {
      expect(localToolsOffered(status)).toBe(status === "conectada");
    }
  });

  it("el latido corre en conectada y reconectando, y en ningún otro", () => {
    for (const status of BAR_STATUSES) {
      expect(heartbeatRuns(status)).toBe(status === "conectada" || status === "reconectando");
    }
  });
});

describe("transiciones del contrato", () => {
  it("arranca comprobando, sin máquina y sin ofrecer nada apagado (1.1)", () => {
    // Spec 010 R3.6: hasta la spec 009 arrancaba en `sin_emparejar`, es decir,
    // afirmando algo que todavía no había preguntado. Ahora no ofrece nada
    // porque todavía no sabe qué hace falta.
    const s = initialState();
    expect(s.status).toBe("comprobando");
    expect(s.machine).toBeUndefined();
    expect(actionsFor(s)).toEqual([]);
  });

  it("emparejar: sin_emparejar → emparejando → conectada", () => {
    const s = transition(initialState(), { kind: "pair_started" });
    expect(s.status).toBe("emparejando");
    expect(actionsFor(s)).toEqual([]);
    const c = transition(s, { kind: "pair_ok", machine: { displayName: "m", hostname: "m.local" } });
    expect(c.status).toBe("conectada");
    expect(c.machine?.displayName).toBe("m");
  });

  it("un código que no vale vuelve a sin_emparejar y lo dice como estado", () => {
    const s = transition(transition(initialState(), { kind: "pair_started" }), {
      kind: "pair_failed",
      code: "pairing_code_invalid",
    });
    expect(s.status).toBe("sin_emparejar");
    expect(s.lastError).toEqual({ code: "pairing_code_invalid" });
  });

  it("red o 5xx → reconectando; el latido vuelve → conectada", () => {
    const r = transition(connected(), { kind: "link_lost" });
    expect(r.status).toBe("reconectando");
    expect(transition(r, { kind: "link_ok" }).status).toBe("conectada");
  });

  it("cookie fuera → sin_sesion; misma persona → conectada; otra → sin máquina y sin nada que teclear", () => {
    const gone = transition(connected(), { kind: "session_gone" });
    expect(gone.status).toBe("sin_sesion");
    expect(actionsFor(gone)).toEqual([]);
    expect(transition(gone, { kind: "session_same_person" }).status).toBe("conectada");
    const other = transition(gone, { kind: "session_other_person" });
    expect(other.status).toBe("sin_emparejar");
    expect(other.pairedByOther).toBe(true);
    // Con la spec 012 aquí no se ofrece nada que teclear: si esa persona puede
    // tener máquina, se le registra al entrar; y si no, teclear un código
    // tampoco la habría conseguido.
    expect(actionsFor(other)).toEqual([]);
  });

  it("401 y pairing_required → volver_a_emparejar; device_archived → archivada_desde_consola", () => {
    expect(transition(connected(), { kind: "unauthorized" }).status).toBe("volver_a_emparejar");
    expect(transition(connected(), { kind: "pairing_required" }).status).toBe("volver_a_emparejar");
    expect(transition(connected(), { kind: "archived" }).status).toBe("archivada_desde_consola");
  });

  it("desemparejar vuelve a sin_emparejar y olvida la máquina", () => {
    const s = transition(connected(), { kind: "unpaired" });
    expect(s.status).toBe("sin_emparejar");
    expect(s.machine).toBeUndefined();
    expect(s.links).toEqual([]);
  });

  it("los vínculos llegan con el sondeo y la barra sabe cuántos directorios faltan", () => {
    const s = transition(connected(), {
      kind: "links_updated",
      links: [
        { clientRef: "cultor", clientName: "Cultor", needsDirectory: true },
        { clientRef: "retail", clientName: "Retail", needsDirectory: false },
      ],
    });
    expect(s.links.filter((l) => l.needsDirectory)).toHaveLength(1);
    expect(actionsFor(s)).toEqual(["directorios", "desemparejar"]);
  });

  it("la barra dice si no hay cifrado disponible, y entonces no ofrece emparejar", () => {
    const s = { ...initialState(), encryptionAvailable: false };
    expect(actionsFor(s)).toEqual([]);
  });
});

/*
 * Spec 010, T139 — **«volver al equipo» se retira con la barra.**
 *
 * Existía porque la ventana enseñaba **una superficie u otra**: con la consola
 * delante, la barra tenía que ofrecer la vuelta. Con el armazón, la consola se
 * pinta **dentro del panel** y no hay a dónde volver — la persona elige
 * secciones, no superficies. `withSurface` y `barActions` se van con ella.
 *
 * Lo que sí se conserva, y sigue abajo: que `actionsFor` no ofrezca nada sin
 * cifrado disponible, y que los estados decidan las acciones.
 */

/**
 * El canje del código de sesión — spec 009, Historia 2.
 *
 * Aquí sólo se comprueba **cómo se cuenta**, que es lo que la barra decide. Que
 * el código sirva o no lo decide la plataforma, y eso vive en
 * `apps/api/tests/integration/test_session_codes.py`.
 */
describe("el canje del código de sesión (spec 009, R4.7)", () => {
  it("un canje fallido se pinta como estado, nunca en rojo", () => {
    const s = transition(initialState(), { kind: "redeem_failed" });
    // Los siete estados son de conexión y ninguno es un error (12.2). Un código
    // que no vale no convierte la barra en una alarma.
    expect(statusTone(s.status)).toBe("estado");
    expect(s.lastError?.code).toBe("session_code_invalid");
  });

  it("fallar el canje no toca el estado de conexión ni olvida nada", () => {
    const base = connected();
    const tras = transition(base, { kind: "redeem_failed" });
    expect(tras.status).toBe(base.status);
    expect(tras.machine).toEqual(base.machine);
  });
});

/**
 * Spec 010 — lo que faltaba para que el puesto no mienta.
 *
 * Tres huecos que la auditoría encontró y que la sesión del 2026-09-17 vio en
 * vivo: la barra decía «no emparejada» **antes de saberlo**, y se quedó toda la
 * sesión en `reconectando` sin decir de qué se reconectaba ni desde cuándo,
 * mientras la consola, en la misma ventana, daba la máquina por emparejada.
 */
describe("el primer pintado no adivina (spec 010, 3.6)", () => {
  it("antes del primer veredicto el estado es `comprobando`", () => {
    expect(initialState().status).toBe("comprobando");
  });

  it("y `comprobando` no ofrece emparejar: todavía no se sabe si hace falta", () => {
    expect(actionsFor(initialState())).toEqual([]);
  });

  it("sigue siendo un estado, no un error", () => {
    expect(statusTone("comprobando")).toBe("estado");
  });
});

describe("desde cuándo y por qué (spec 010, 3.6 y 3.7)", () => {
  const t0 = "2026-09-17T20:00:00.000Z";

  it("cada estado sabe desde cuándo lo es", () => {
    const start = transition(initialState(), { kind: "person" }, { now: t0 });
    expect(start.since).toBe(t0);
    const later = transition(start, { kind: "pairing_required" }, { now: "2026-09-17T20:05:00.000Z" });
    expect(later.since).toBe("2026-09-17T20:05:00.000Z");
  });

  it("un estado que no cambia conserva su `since`: no se reinicia el reloj", () => {
    const start = { ...initialState(), status: "reconectando" as const, since: t0 };
    const same = transition(start, { kind: "link_lost" }, { now: "2026-09-17T21:00:00.000Z" });
    expect(same.status).toBe("reconectando");
    expect(same.since).toBe(t0);
  });

  it("`reconectando` puede decir de qué se reconecta", () => {
    const sinEjecutor = transition(
      { ...initialState(), status: "conectada", links: [], encryptionAvailable: true },
      { kind: "link_lost", cause: "sin_ejecutor" },
      { now: t0 },
    );
    expect(sinEjecutor.status).toBe("reconectando");
    expect(sinEjecutor.cause).toBe("sin_ejecutor");
  });

  it("y al recuperar la conexión la causa se olvida", () => {
    const conMaquina: BarState = {
      ...initialState(),
      status: "conectada",
      machine: { displayName: "MacBook de Luis", hostname: "luis.local" },
      encryptionAvailable: true,
      links: [],
    };
    const roto = transition(conMaquina, { kind: "link_lost", cause: "sin_red" }, { now: t0 });
    const bien = transition(roto, { kind: "link_ok" }, { now: t0 });
    expect(bien.status).toBe("conectada");
    expect(bien.cause).toBeUndefined();
  });

  it("sin causa conocida no se inventa ninguna", () => {
    const roto = transition(
      { ...initialState(), status: "conectada", encryptionAvailable: true, links: [] },
      { kind: "link_lost" },
      { now: t0 },
    );
    expect(roto.cause).toBeUndefined();
  });
});
