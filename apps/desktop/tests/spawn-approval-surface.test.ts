/**
 * Requisitos 11.2 y 11.3 — el estado que enseñamos coincide con lo ocurrido.
 *
 * Esto existe por un hallazgo concreto de la evaluación: `spawn list` del
 * sustrato informó **`✅`** de un subagente que su propia notificación registraba
 * como **`❌`, rechazado por falta de superficie**. Si nuestra pantalla reflejara
 * su listado, heredaríamos esa mentira — y §V dice que la pantalla no miente.
 *
 * La defensa no es «leer mejor su listado»: es **no tratarlo como autoritativo**.
 * Lo autoritativo es el resultado de la aprobación; el listado es una pista.
 */
import { describe, expect, it } from "vitest";

import { displayedSpawnState, type SpawnEvidence } from "../src/spawn-state.js";

const evidence = (over: Partial<SpawnEvidence> = {}): SpawnEvidence => ({
  listedAs: null,
  approval: null,
  finished: null,
  waitingOn: null,
  ...over,
});

describe("no se hereda la mentira del listado", () => {
  it("un rechazo gana al `✅` del listado", () => {
    const state = displayedSpawnState(evidence({ listedAs: "ok", approval: "rejected" }));
    expect(state).toBe("rechazado");
  });

  it("sin evidencia de aprobación, el listado NO basta para decir que corre", () => {
    expect(displayedSpawnState(evidence({ listedAs: "ok" }))).toBe("desconocido");
  });

  it("`desconocido` es un estado legítimo y distinto de `ocioso`", () => {
    expect(displayedSpawnState(evidence())).toBe("desconocido");
    expect(displayedSpawnState(evidence())).not.toBe("ocioso");
  });
});

describe("lo que sí puede afirmarse", () => {
  it("aprobado y en marcha", () => {
    expect(displayedSpawnState(evidence({ approval: "approved" }))).toBe("ejecutando");
  });

  it("aprobado y terminado", () => {
    expect(
      displayedSpawnState(evidence({ approval: "approved", finished: "completed" })),
    ).toBe("completado");
  });

  it("aprobado y fallado no se pinta como completado", () => {
    expect(displayedSpawnState(evidence({ approval: "approved", finished: "failed" }))).toBe(
      "fallado",
    );
  });
});

describe("esperar a otro es `bloqueado`, no ocioso (Requisito 11.4)", () => {
  it("un subagente que espera a otro se dice bloqueado", () => {
    const state = displayedSpawnState(evidence({ approval: "approved", waitingOn: "otro-agente" }));
    expect(state).toBe("bloqueado");
  });

  it("bloqueado gana a ejecutando: es más informativo y más honesto", () => {
    expect(displayedSpawnState(evidence({ approval: "approved", waitingOn: "x" }))).not.toBe(
      "ejecutando",
    );
  });

  it("un subagente sin aprobar que espera sigue siendo desconocido", () => {
    expect(displayedSpawnState(evidence({ waitingOn: "x" }))).toBe("desconocido");
  });
});
