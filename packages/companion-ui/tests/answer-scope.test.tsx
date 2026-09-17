/**
 * Spec 010, Requisito 4.6 — la respuesta acota su propio alcance.
 *
 * «WHERE el sistema solo pudo leer parte de lo pedido, la respuesta DEBE acotar
 * su propio alcance diciendo qué parte cubre.»
 *
 * El caso real: una herramienta del turno falla, su tarjeta lo dice, y debajo
 * llega una respuesta redactada como si estuviera completa. La tarjeta se pliega
 * o se pierde al desplazar; la respuesta se queda. Quien lee acaba tomando por
 * exhaustivo algo que no lo es, y ése es el peor fallo posible de §V: no se ve
 * como un error, se ve como una pantalla bien resuelta.
 *
 * El aviso va **pegado a la respuesta**, no arriba del registro: arriba está el
 * de la conversación incompleta, que es otra cosa —lo que falta es historia, no
 * alcance— y ponerlos juntos haría que ninguno de los dos se leyera.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CompanionLocaleProvider as LocaleProvider } from "../src/i18n";
import { type CompanionState, companionReducer, emptyCompanionState, unreadSources } from "../src/state";
import { Timeline } from "../src/components/timeline";
import * as f from "./fixtures";

afterEach(cleanup);

function build(runId: string, events: ReturnType<typeof f.ev>[], base = emptyCompanionState): CompanionState {
  return events.reduce((s, ev) => companionReducer(s, { type: "event", runId, ev, now: 1_000 }), base);
}

function paint(state: CompanionState) {
  render(
    <LocaleProvider locale="es">
      <Timeline
        state={state}
        status="ready"
        errorDetail={null}
        partial={false}
        currentUserId={null}
        deciding={false}
        decisionFailure={null}
        suggestions={[]}
        onRetry={vi.fn()}
        onSuggestion={vi.fn()}
        onAnswerSlot={vi.fn()}
        onDecide={vi.fn()}
      />
    </LocaleProvider>,
  );
}

const FALLA = [f.toolStarted(1, "tc-1"), f.toolCompleted(2, "tc-1", false)];
const VA_BIEN = [f.toolStarted(1, "tc-1"), f.toolCompleted(2, "tc-1", true)];

describe("qué se pudo leer de verdad", () => {
  it("una herramienta que falló deja el turno con el alcance recortado", () => {
    expect(unreadSources(build("run-1", FALLA), "run-1")).toEqual(["Consultando el consumo de Boreal"]);
  });

  it("si todas fueron bien, no hay nada que acotar", () => {
    expect(unreadSources(build("run-1", VA_BIEN), "run-1")).toEqual([]);
  });

  it("el turno de antes no contamina el de ahora", () => {
    // Que en el turno anterior fallara una lectura no recorta la respuesta de
    // éste: el alcance es del turno, no de la conversación.
    const antes = build("run-1", FALLA);
    const ahora = build("run-2", [f.textDelta(1, "Listo.")], antes);
    expect(unreadSources(ahora, "run-2")).toEqual([]);
  });
});

describe("y la respuesta lo dice, donde se lee la respuesta", () => {
  it("nombra lo que no pudo leer", () => {
    paint(build("run-1", [...FALLA, f.textDelta(3, "Boreal gastó poco este mes.")]));
    expect(screen.getByTestId("answer-scope").textContent).toMatch(/Consultando el consumo de Boreal/);
  });

  it("sin fallos no se pinta: una respuesta completa no se disculpa", () => {
    paint(build("run-1", [...VA_BIEN, f.textDelta(3, "Boreal gastó poco este mes.")]));
    expect(screen.queryByTestId("answer-scope")).toBeNull();
  });

  it("no es un error: no interrumpe ni se pinta en rojo", () => {
    paint(build("run-1", [...FALLA, f.textDelta(3, "Boreal gastó poco este mes.")]));
    const aviso = screen.getByTestId("answer-scope");
    expect(aviso.getAttribute("role")).not.toBe("alert");
    expect(aviso.className).not.toMatch(/text-status-danger/);
  });
});
