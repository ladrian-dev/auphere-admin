// @vitest-environment jsdom
/**
 * Requisitos 4.3, 4.4 y 4.8 — en qué punto está el turno.
 *
 * Hasta ahora la pantalla del hilo distinguía **dos** situaciones: el botón de
 * enviar cambiaba a un cuadrado, y ya. Razonando, llamando a una herramienta,
 * esperando la primera palabra del servidor y esperando una decisión tuya se
 * veían exactamente igual — y «enviando» no se veía en absoluto, porque hasta
 * que el servidor abre el turno `runStatus` sigue en reposo.
 *
 * Los ocho estados del requisito 4.3 se derivan, no se guardan: guardarlos
 * sería una segunda verdad que se desincroniza con el stream a la primera
 * reconexión, que es el error que la spec 003 ya documentó con `task.state`.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import "./dom-matchers";

import { TURN_STATES, type TurnFacts, deriveTurnState, offersStop, turnFactsOf } from "../src/turn-state";
import { TurnStatus } from "../src/app/routes/turn-status";

afterEach(cleanup);

/** Un turno en marcha del que se van cambiando los hechos, uno a uno. */
const EN_MARCHA: TurnFacts = {
  sending: false,
  runStatus: "running",
  thinking: false,
  tool: null,
  awaitingDecision: false,
};

describe("los ocho estados del turno se distinguen", () => {
  it("enviando: el mensaje salió y el servidor todavía no abrió el turno", () => {
    // El caso que no existía: `runStatus` sigue en reposo y la pantalla se veía
    // igual que antes de escribir nada.
    expect(deriveTurnState({ ...EN_MARCHA, sending: true, runStatus: "idle" })).toBe("enviando");
  });

  it("esperando: el turno está abierto y aún no ha dicho nada", () => {
    expect(deriveTurnState(EN_MARCHA)).toBe("esperando");
  });

  it("razonando: hay un bloque de pensamiento sin cerrar", () => {
    expect(deriveTurnState({ ...EN_MARCHA, thinking: true })).toBe("razonando");
  });

  it("herramienta: se está usando una, y se nombra", () => {
    expect(deriveTurnState({ ...EN_MARCHA, thinking: true, tool: "Buscar en la agenda" })).toBe("herramienta");
  });

  it("esperando decisión: manda sobre cualquier otra cosa que esté pasando", () => {
    // Lo que la persona tiene que hacer gana a lo que la máquina esté haciendo.
    expect(deriveTurnState({ ...EN_MARCHA, thinking: true, tool: "x", awaitingDecision: true })).toBe("esperando_decision");
    expect(deriveTurnState({ ...EN_MARCHA, runStatus: "waiting", awaitingDecision: true })).toBe("esperando_decision");
  });

  it("terminado cuando cerró bien, y también cuando cerró en el tope", () => {
    expect(deriveTurnState({ ...EN_MARCHA, runStatus: "completed" })).toBe("terminado");
    // El tope **no es un fallo**: el turno cerró limpio y lo hecho está arriba.
    // Que además haya tope lo dice la banda del compositor, no esto.
    expect(deriveTurnState({ ...EN_MARCHA, runStatus: "paused" })).toBe("terminado");
  });

  it("detenido es lo que detuvo la persona; cortarse por el servidor es fallar", () => {
    expect(deriveTurnState({ ...EN_MARCHA, runStatus: "cancelled" })).toBe("detenido");
    expect(deriveTurnState({ ...EN_MARCHA, runStatus: "interrupted" })).toBe("fallido");
    expect(deriveTurnState({ ...EN_MARCHA, runStatus: "error" })).toBe("fallido");
  });

  it("y sin turno todavía no se inventa ninguno", () => {
    expect(deriveTurnState({ ...EN_MARCHA, runStatus: "idle" })).toBeNull();
  });
});

describe("detener está mientras trabaja — en los tres estados, no en uno", () => {
  it("se ofrece en esperando, razonando y herramienta", () => {
    for (const estado of ["esperando", "razonando", "herramienta"] as const) {
      expect(offersStop(estado), `no se ofrece detener en ${estado}`).toBe(true);
    }
  });

  it("y no se ofrece donde no hay nada que detener", () => {
    // Detener lo que ya cerró sería un botón que no hace nada, y `stop()`
    // sin turno vivo vuelve en silencio: eso es exactamente un fallo mudo.
    for (const estado of ["enviando", "esperando_decision", "terminado", "detenido", "fallido"] as const) {
      expect(offersStop(estado), `se ofrece detener en ${estado}`).toBe(false);
    }
    expect(offersStop(null)).toBe(false);
  });
});

describe("los hechos se leen del hilo, no se guardan aparte", () => {
  const item = (kind: string, extra: Record<string, unknown> = {}) => ({ kind, id: "i", runId: "r", ...extra });

  it("un pensamiento sin cerrar es razonar; cerrado, no", () => {
    expect(turnFactsOf({ runStatus: "running", items: [item("thinking", { endedAt: null })] }, false).thinking).toBe(true);
    expect(turnFactsOf({ runStatus: "running", items: [item("thinking", { endedAt: 2 })] }, false).thinking).toBe(false);
  });

  it("la herramienta en marcha se lee con su nombre humano", () => {
    const hechos = turnFactsOf(
      { runStatus: "running", items: [item("tool", { status: "running", label: "Leer el calendario" })] },
      false,
    );
    expect(hechos.tool).toBe("Leer el calendario");
  });

  it("una tarjeta resuelta ya no es una decisión que espera", () => {
    expect(turnFactsOf({ runStatus: "waiting", items: [item("action", { state: "pending" })] }, false).awaitingDecision).toBe(true);
    expect(turnFactsOf({ runStatus: "waiting", items: [item("action", { state: "resolved" })] }, false).awaitingDecision).toBe(false);
  });
});

describe("lo que se pinta dice qué se está haciendo", () => {
  it("nombra la herramienta en vez de decir «trabajando»", () => {
    render(<TurnStatus state="herramienta" tool="Leer el calendario" />);
    expect(screen.getByRole("status")).toHaveTextContent(/Leer el calendario/);
  });

  it("cada estado que se anuncia trae una frase, no un punto suspensivo suelto", () => {
    for (const estado of TURN_STATES) {
      cleanup();
      const { container } = render(<TurnStatus state={estado} tool={null} />);
      const dicho = container.querySelector('[role="status"]');
      if (!dicho) continue; // terminado y esperando_decision se dicen en otro sitio
      expect(dicho.textContent?.trim().length ?? 0, `«${estado}» se anuncia sin decir nada`).toBeGreaterThan(8);
    }
  });

  it("terminado no deja un cartel puesto: la respuesta es el anuncio", () => {
    const { container } = render(<TurnStatus state="terminado" tool={null} />);
    expect(container.querySelector('[role="status"]')).toBeNull();
  });

  it("esperando decisión tampoco: lo dice la tarjeta que hay que responder", () => {
    // Anunciarlo aquí además de en la tarjeta serían dos avisos de lo mismo, y
    // el segundo enseña a ignorar los dos.
    const { container } = render(<TurnStatus state="esperando_decision" tool={null} />);
    expect(container.querySelector('[role="status"]')).toBeNull();
  });

  it("se anuncia sin interrumpir: nunca `alert`", () => {
    const { container } = render(<TurnStatus state="razonando" tool={null} />);
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });
});
