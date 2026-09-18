// @vitest-environment jsdom
/**
 * Requisitos 7.6 y 7.7 — la lista de puesta en marcha.
 *
 * Tres cosas que la hacen distinta de la tarjeta que ya existe en la consola,
 * y que el anexo 04 anotó como defectuosa: «Tu puesto de trabajo · 0 de 4
 * pasos», cuyos pasos enlazaban **todos a la misma página**, que es la que ya
 * estabas mirando.
 *
 * * **deriva de lo que ya existe**: sesión, puesto, roster, turnos, permisos.
 *   No es un dato nuevo que alguien tenga que mantener al día, porque un dato
 *   así se desincroniza el primer día y entonces la lista miente;
 * * **no bloquea nada**: es una lectura. Se puede trabajar con pasos a medias;
 * * **cada paso lleva a su acción o dice por qué está bloqueado**. Un paso sin
 *   destino es la versión con casillas de «no puedes».
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import { SETUP_STEPS, type SetupFacts, deriveSetup, pendingSteps } from "../src/setup-checklist";
import { SetupList } from "../src/app/routes/setup";

afterEach(cleanup);

/** Todo hecho. De aquí se va quitando una cosa cada vez. */
const LISTO: SetupFacts = {
  signedIn: true,
  hasPartner: true,
  workstation: "conectada",
  executorPresent: true,
  teammates: 1,
  finishedTurns: 1,
  notificationsGranted: true,
  planAllowsTeammates: true,
};

const paso = (facts: SetupFacts, key: (typeof SETUP_STEPS)[number]) =>
  deriveSetup(facts).find((s) => s.key === key)!;

describe("cada paso sale de algo que ya se sabe", () => {
  it("los seis pasos están, y en el orden en que se hacen", () => {
    expect([...SETUP_STEPS]).toEqual([
      "cuenta_lista",
      "maquina_emparejada",
      "ejecutor_presente",
      "primer_teammate",
      "primer_turno",
      "avisos_concedidos",
    ]);
  });

  it("con todo hecho no queda ninguno pendiente", () => {
    expect(pendingSteps(deriveSetup(LISTO))).toHaveLength(0);
  });

  it("sin sesión, la cuenta no está lista", () => {
    expect(paso({ ...LISTO, signedIn: false }, "cuenta_lista").state).toBe("pendiente");
  });

  it("la máquina se lee del puesto, no de una copia", () => {
    expect(paso({ ...LISTO, workstation: "sin_emparejar" }, "maquina_emparejada").state).toBe("pendiente");
    expect(paso({ ...LISTO, workstation: "conectada" }, "maquina_emparejada").state).toBe("hecho");
  });

  it("y el ejecutor sólo se pregunta con la máquina emparejada", () => {
    // Preguntar si el ejecutor corre en una máquina que no está emparejada es
    // pedir algo que todavía no tiene sentido: no aplica.
    expect(paso({ ...LISTO, workstation: "sin_emparejar", executorPresent: false }, "ejecutor_presente").state).toBe("no_aplica");
  });

  it("el primer turno no aplica sin ningún teammate", () => {
    expect(paso({ ...LISTO, teammates: 0, finishedTurns: 0 }, "primer_turno").state).toBe("no_aplica");
  });
});

describe("un paso bloqueado dice por qué, y no se pinta como pendiente", () => {
  it("sin plan que admita teammates, crear el primero está bloqueado", () => {
    const step = paso({ ...LISTO, teammates: 0, planAllowsTeammates: false }, "primer_teammate");
    expect(step.state).toBe("pendiente");
    expect(step.blocked_reason_key).toBeTruthy();
  });

  it("y ese bloqueo lleva a donde se resuelve, no a donde se descubre", () => {
    const step = paso({ ...LISTO, teammates: 0, planAllowsTeammates: false }, "primer_teammate");
    expect(step.section).toBe("cuenta");
  });

  it("sin bloqueo, el paso lleva a donde se hace", () => {
    const step = paso({ ...LISTO, teammates: 0 }, "primer_teammate");
    expect(step.blocked_reason_key).toBeUndefined();
    expect(step.section).toBe("teammate");
  });
});

describe("y en pantalla no bloquea nada", () => {
  const pintar = (facts: SetupFacts, onGo = vi.fn()) => {
    render(<SetupList steps={deriveSetup(facts)} onGo={onGo} />);
    return onGo;
  };

  it("los pasos hechos se ven hechos, no desaparecen", () => {
    // Que desaparezcan deja sin saber si se hicieron o si la lista se rompió.
    pintar({ ...LISTO, teammates: 0 });
    expect(screen.getAllByRole("listitem")).toHaveLength(SETUP_STEPS.length);
  });

  it("un paso pendiente lleva a su sección de un clic", async () => {
    const onGo = pintar({ ...LISTO, teammates: 0, finishedTurns: 0 });
    await userEvent.click(screen.getAllByRole("button")[0]!);
    expect(onGo).toHaveBeenCalledWith("teammate");
  });

  it("un paso hecho no ofrece un botón que no lleva a nada", () => {
    pintar(LISTO);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("con todo hecho se felicita y se sale, en vez de dejar la lista puesta", () => {
    pintar(LISTO);
    expect(screen.getByText(/todo listo|all set/i)).toBeInTheDocument();
  });

  it("no hay ninguna casilla marcable: esto es una lectura, no una tarea", () => {
    const { container } = render(<SetupList steps={deriveSetup({ ...LISTO, teammates: 0 })} onGo={vi.fn()} />);
    expect(container.querySelector('input[type="checkbox"]')).toBeNull();
  });
});
