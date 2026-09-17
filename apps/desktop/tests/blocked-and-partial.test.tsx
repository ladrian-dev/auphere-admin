// @vitest-environment jsdom
/**
 * Requisitos 4.6 y 4.7 — el alcance acotado y «bloqueado no es ocioso».
 *
 * Dos huecos que el anexo 04 de la investigación dejó por escrito:
 *
 * * **«Hilo, bloqueado (esperar a otro teammate)»: ni `deriveThreadState` ni el
 *   roster lo contemplaban.** El vocabulario no tenía forma de decirlo, así que
 *   no había ni siquiera dónde poner el arreglo.
 * * **En la lista lateral el estado de un teammate no se ve.** Esperar una
 *   decisión tuya, estar en pausa por el tope y no tener nada que hacer se
 *   pintaban exactamente igual: el nombre y nada más. El roster viejo lo decía
 *   con un punto de color y una etiqueta invisible (WCAG 1.4.1), y esa pantalla
 *   ya no se usa.
 *
 * Qué es alcanzable hoy y qué no, dicho a las claras: `en_pausa_por_tope` y
 * `maquina_ausente` son bloqueos que ya ocurren. «Esperando a otro teammate» no
 * existe todavía en la plataforma —no hay delegación entre teammates—, así que
 * aquí se comprueba que **el vocabulario lo admite y no lo confunde con ocioso**,
 * no que se esté recibiendo de ningún sitio.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import "./dom-matchers";

import { MY_STATES, type ThreadFacts, deriveThreadState, isIdle } from "../src/app-state";
import { Sidebar } from "../src/app/shell/sidebar";

afterEach(cleanup);

const NORMAL: ThreadFacts = {
  status: "ready",
  runStatus: "idle",
  reconnecting: false,
  partial: false,
  itemCount: 3,
  taskState: null,
  budgetPaused: false,
  machineNeeded: false,
  machinePresent: true,
  blockedOn: null,
};

const LATERAL = {
  active: "hoy" as const,
  onSelect: () => {},
  permissions: [] as string[],
  waiting: 0,
  selectedTeammate: null,
  onSelectTeammate: () => {},
};

describe("el hilo sabe decir «bloqueado»", () => {
  it("esperar a otro no es ni normal ni vacío", () => {
    expect(deriveThreadState({ ...NORMAL, blockedOn: "Nilo" })).toBe("bloqueado");
  });

  it("pero lo que te espera a ti manda: es lo único que tú puedes desbloquear", () => {
    expect(deriveThreadState({ ...NORMAL, blockedOn: "Nilo", runStatus: "waiting" })).toBe("esperandote");
  });

  it("y un hilo bloqueado sin nada escrito no se llama vacío", () => {
    expect(deriveThreadState({ ...NORMAL, blockedOn: "Nilo", itemCount: 0 })).toBe("bloqueado");
  });
});

describe("ocioso es un estado, y sólo uno", () => {
  it("el único estado ocioso es no tener nada que hacer", () => {
    const ociosos = MY_STATES.filter(isIdle);
    expect(ociosos).toEqual(["en_espera"]);
  });

  it("esperarte, el tope y esperar a otro son bloqueos, no ocio", () => {
    for (const estado of ["esperandote", "en_pausa_por_tope", "bloqueado"] as const) {
      expect(isIdle(estado), `${estado} se cuenta como ocioso`).toBe(false);
    }
  });
});

describe("y en la lista lateral se ve, no sólo se oye", () => {
  const conEstado = (state: (typeof MY_STATES)[number]) => [{ id: "t-1", name: "Sofía", unread: false, state }];

  it("cada estado que no es ocio se dice con palabras", () => {
    for (const estado of ["esperandote", "en_pausa_por_tope", "bloqueado", "en_marcha"] as const) {
      cleanup();
      render(<Sidebar {...LATERAL} rosterStatus="ready" teammates={conEstado(estado)} />);
      const fila = screen.getByRole("button", { name: /Sofía/ });
      // Con palabras dentro del propio botón: un punto de color no lo dice a
      // quien no distingue colores, y una etiqueta invisible no lo dice a quien
      // mira la pantalla (WCAG 1.4.1).
      expect(fila.textContent ?? "", `«${estado}» no se lee en la fila`).toMatch(/\S/);
      expect(fila.textContent).not.toBe("Sofía");
    }
  });

  it("y el que sí es ocio no añade ruido: la ausencia se diseña", () => {
    render(<Sidebar {...LATERAL} rosterStatus="ready" teammates={conEstado("en_espera")} />);
    expect(screen.getByRole("button", { name: /Sofía/ }).textContent).toBe("Sofía");
  });

  it("bloqueado y ocioso no se leen igual", () => {
    render(<Sidebar {...LATERAL} rosterStatus="ready" teammates={conEstado("bloqueado")} />);
    const bloqueado = screen.getByRole("button", { name: /Sofía/ }).textContent;
    cleanup();
    render(<Sidebar {...LATERAL} rosterStatus="ready" teammates={conEstado("en_espera")} />);
    expect(screen.getByRole("button", { name: /Sofía/ }).textContent).not.toBe(bloqueado);
  });
});
