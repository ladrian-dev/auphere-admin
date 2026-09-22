// @vitest-environment jsdom
/**
 * Al abrir, se puede escribir — spec 013, Requisito 6.
 *
 * La primera pantalla era un **panel de estado**: «Tu máquina: sin emparejar»,
 * «Nada espera tu decisión», «Crea el primero». Todo cierto y todo
 * administrativo. Lo que decide de qué clase de producto se trata —una
 * herramienta de trabajo o un panel— es qué ocupa el centro al abrir.
 *
 * Lo que este fichero defiende:
 *
 * * con equipo, **hay dónde escribir** y se ve a quién;
 * * **sin equipo, no hay composer**: un sitio donde escribir que no lleva a
 *   ninguna parte es una pantalla que miente (§V, la ausencia se diseña);
 * * la máquina apagada **no impide conversar**, porque conversar no la
 *   necesita — solo ejecutar la necesita.
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import type { Teammate } from "../src/app/bridge";
import { Today } from "../src/app/routes/today";

afterEach(cleanup);

const sofia = { id: "11111111-1111-4111-8111-111111111111", name: "Sofía", job: "Analista" } as Teammate;

const props = {
  workstation: null,
  onOpenWorkstation: vi.fn(),
  waiting: 0,
  status: "ready" as const,
  onRetry: vi.fn(),
  onOpenPending: vi.fn(),
  onCreate: vi.fn(),
  onOpenTeammate: vi.fn(),
};

describe("con equipo (R6.1)", () => {
  it("hay dónde escribir, y se ve a quién se le escribe", () => {
    render(<Today {...props} teammates={[sofia]} onStart={vi.fn()} />);

    expect(screen.getByRole("textbox")).toBeInTheDocument();
    // Aparece dos veces —en el composer y en la lista del equipo— y las dos
    // son correctas: se comprueba que está, no cuántas veces.
    expect(screen.getAllByText(/Sofía/).length).toBeGreaterThan(0);
  });

  it("lo escrito arranca la conversación con ese teammate", async () => {
    const empezar = vi.fn();
    render(<Today {...props} teammates={[sofia]} onStart={empezar} />);

    await userEvent.type(screen.getByRole("textbox"), "analiza agosto");
    await userEvent.click(screen.getByRole("button", { name: /enviar|empezar/i }));

    expect(empezar).toHaveBeenCalledWith(sofia.id, "analiza agosto");
  });

  it("no se envía vacío: el botón no promete lo que no puede hacer", async () => {
    const empezar = vi.fn();
    render(<Today {...props} teammates={[sofia]} onStart={empezar} />);

    await userEvent.click(screen.getByRole("button", { name: /enviar|empezar/i }));

    expect(empezar).not.toHaveBeenCalled();
  });
});

describe("sin equipo (R6.2)", () => {
  it("lo primero es crear uno, y NO hay composer", () => {
    render(<Today {...props} teammates={[]} onStart={vi.fn()} />);

    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByRole("button", { name: /crear/i })).toBeInTheDocument();
  });
});

describe("con la máquina ausente (R6.3, R6.4)", () => {
  it("se puede conversar igual: conversar no necesita la máquina", () => {
    render(
      <Today
        {...props}
        teammates={[sofia]}
        onStart={vi.fn()}
        workstation={{ status: "sin_emparejar", actions: [] } as never}
      />,
    );

    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  it("y el estado de la máquina sigue alcanzable, sin ocupar el centro", () => {
    render(
      <Today
        {...props}
        teammates={[sofia]}
        onStart={vi.fn()}
        workstation={{ status: "sin_emparejar", actions: [] } as never}
      />,
    );

    // Está, pero después del sitio donde se escribe: el orden del documento
    // es el orden de importancia para quien navega con teclado o lector.
    const campo = screen.getByRole("textbox");
    const maquina = screen.getAllByText(/máquina|emparejar/i)[0]!;
    expect(campo.compareDocumentPosition(maquina) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
