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
