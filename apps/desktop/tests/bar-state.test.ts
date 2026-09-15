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
  barActions,
  withSurface,
  heartbeatRuns,
  initialState,
  localToolsOffered,
  statusCopyKey,
  statusTone,
  transition,
  type BarState,
} from "../src/bar-state.js";

const connected = (): BarState =>
  transition(transition(initialState(), { kind: "pair_started" }), {
    kind: "pair_ok",
    machine: { displayName: "MacBook de Luis", hostname: "mac.local" },
  });

describe("los siete estados (12.2)", () => {
  it("son exactamente los del contrato", () => {
    expect([...BAR_STATUSES]).toEqual([
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
  it("arranca sin emparejar, sin máquina y sin ofrecer nada apagado (1.1)", () => {
    const s = initialState();
    expect(s.status).toBe("sin_emparejar");
    expect(s.machine).toBeUndefined();
    expect(actionsFor(s)).toEqual(["introducir_codigo"]);
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

  it("cookie fuera → sin_sesion; misma persona → conectada; otra → oferta de emparejar", () => {
    const gone = transition(connected(), { kind: "session_gone" });
    expect(gone.status).toBe("sin_sesion");
    expect(actionsFor(gone)).toEqual([]);
    expect(transition(gone, { kind: "session_same_person" }).status).toBe("conectada");
    const other = transition(gone, { kind: "session_other_person" });
    expect(other.status).toBe("sin_emparejar");
    expect(other.pairedByOther).toBe(true);
    expect(actionsFor(other)).toEqual(["introducir_codigo"]);
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

/**
 * Volver a la pantalla del equipo — spec 009, Historia 1.
 *
 * WHILE la superficie visible es la consola, la barra DEBE ofrecer la vuelta.
 * WHILE es la pantalla del equipo, NO DEBE ofrecerla.
 *
 * **`volver_a_la_app` no pasa por `actionsFor(state)`, y eso es el diseño.**
 * `actionsFor` decide a partir de `status`, que son los siete estados de
 * conexión; volver no depende de si la máquina está emparejada, sino de qué se
 * ve. Meterla ahí la haría desaparecer con el `if (!state.encryptionAvailable)
 * return []`, y encerrar a alguien en la consola porque el llavero está
 * bloqueado sería un castigo sin causa. Por eso existe `barActions`, que
 * compone las dos mitades.
 */
describe("volver a la pantalla del equipo (spec 009, R1)", () => {
  it("con la consola delante, la barra ofrece volver", () => {
    const s: BarState = { ...connected(), surface: "console" };
    expect(barActions(s)).toContain("volver_a_la_app");
  });

  it("en la pantalla del equipo no la ofrece: no hay botón que no lleve a ningún sitio", () => {
    const s = connected();
    expect(barActions(s)).not.toContain("volver_a_la_app");
  });

  it("sin cifrado disponible SIGUE ofreciéndose: volver no guarda nada", () => {
    const s: BarState = {
      status: "sin_emparejar",
      links: [],
      encryptionAvailable: false,
      surface: "console",
    };
    // Lo demás sí desaparece —no se puede emparejar sin dónde guardar— …
    expect(actionsFor(s)).toEqual([]);
    // … pero volver, no.
    expect(barActions(s)).toEqual(["volver_a_la_app"]);
  });

  it("el estado que se empuja lleva la superficie, y la ausencia es ausencia", () => {
    const base = connected();
    expect(withSurface(base, "console").surface).toBe("console");
    // No `surface: "app"`: **el campo no está**. Dos formas de decir lo mismo
    // obligarían a la barra a distinguirlas.
    expect(withSurface(base, "app").surface).toBeUndefined();
    // Y la vuelta aparece y desaparece con él, que es lo que se ve.
    expect(barActions(withSurface(base, "console"))).toContain("volver_a_la_app");
    expect(barActions(withSurface(base, "app"))).not.toContain("volver_a_la_app");
  });

  it("cambiar de superficie NO toca el estado de conexión", () => {
    const base = connected();
    const enConsola = withSurface(base, "console");
    expect(enConsola.status).toBe(base.status);
    expect(enConsola.machine).toEqual(base.machine);
    expect(actionsFor(enConsola)).toEqual(actionsFor(base));
  });

  it("no se cuela en ninguno de los siete estados cuando no hay consola delante", () => {
    for (const status of BAR_STATUSES) {
      const s: BarState = { status, links: [], encryptionAvailable: true };
      expect(barActions(s)).not.toContain("volver_a_la_app");
    }
  });
});

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
