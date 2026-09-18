// @vitest-environment jsdom
/**
 * Requisitos 8.2, 8.3 y 11.1 — emparejar sin salir, y **sin que nada quede
 * fuera de la vista**.
 *
 * Éste es el P0-2 de la investigación. La hoja del código vivía dentro de una
 * ventana de 44 px de alto con `overflow: hidden`: el campo se pintaba fuera de
 * la vista, el foco iba a un cuadro invisible y la ayuda —«Pídelo en la
 * consola: Puesto de trabajo → Emparejar esta máquina»— tampoco se veía. La
 * persona tecleaba a ciegas en una barra de la que sólo se veía la primera
 * línea.
 *
 * Aquí el recorrido entero cabe: pedir el código, verlo, teclearlo, y saber qué
 * pasó. Y se completa con el teclado, que es como se pega un código.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import "./dom-matchers";

const HERE = dirname(fileURLToPath(import.meta.url));

const workstationPair = vi.fn(async (_i?: unknown) => ({ ok: true as const, data: { machine_name: "MacBook de Luis" } }));
const openConsole = vi.fn(async (_i?: unknown) => null);

vi.mock("../src/app/bridge", () => ({
  bridge: {
    workstationPair: (input: unknown) => workstationPair(input),
    openConsole: (input: unknown) => openConsole(input),
  },
}));

const { PairDialog } = await import("../src/app/routes/pair-dialog");

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  workstationPair.mockResolvedValue({ ok: true, data: { machine_name: "MacBook de Luis" } });
});

describe("el recorrido entero está a la vista (8.2)", () => {
  it("dice dónde se pide el código, y lleva allí", async () => {
    render(<PairDialog onDone={vi.fn()} onClose={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /pedir|ask|conseguir/i }));
    const destino = openConsole.mock.calls[0]?.[0] as { path: string };
    expect(destino.path).toBe("/workstation");
  });

  it("y el campo donde se teclea está aquí mismo, con su nombre", () => {
    render(<PairDialog onDone={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByRole("textbox", { name: /código|code/i })).toBeInTheDocument();
  });

  it("es un diálogo de verdad: atrapa el foco y se cierra con Escape", async () => {
    const onClose = vi.fn();
    render(<PairDialog onDone={vi.fn()} onClose={onClose} />);
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("se completa con el teclado, que es como se pega un código", async () => {
    const onDone = vi.fn();
    render(<PairDialog onDone={onDone} onClose={vi.fn()} />);
    const campo = screen.getByRole("textbox", { name: /código|code/i });
    await userEvent.type(campo, "ABCD2345{Enter}");
    await waitFor(() => expect(workstationPair).toHaveBeenCalledWith({ code: "ABCD2345" }));
  });
});

describe("el código se lee como se teclea", () => {
  it("las minúsculas suben solas: el alfabeto del código es en mayúsculas", async () => {
    render(<PairDialog onDone={vi.fn()} onClose={vi.fn()} />);
    await userEvent.type(screen.getByRole("textbox", { name: /código|code/i }), "abcd2345");
    expect(screen.getByRole("textbox", { name: /código|code/i })).toHaveValue("ABCD2345");
  });

  it("y hasta que no está entero no se manda nada", async () => {
    render(<PairDialog onDone={vi.fn()} onClose={vi.fn()} />);
    await userEvent.type(screen.getByRole("textbox", { name: /código|code/i }), "ABC{Enter}");
    expect(workstationPair).not.toHaveBeenCalled();
  });
});

describe("cada fallo tiene su mensaje (8.3)", () => {
  it("un código que ya no vale dice eso, y qué hacer", async () => {
    workstationPair.mockResolvedValue({ ok: false, code: "pairing_code_invalid" } as never);
    render(<PairDialog onDone={vi.fn()} onClose={vi.fn()} />);
    await userEvent.type(screen.getByRole("textbox", { name: /código|code/i }), "ABCD2345{Enter}");
    await waitFor(() => expect(screen.getByText(/ya no vale|no longer valid/i)).toBeInTheDocument());
  });

  it("demasiados intentos es otro mensaje, no el mismo", async () => {
    workstationPair.mockResolvedValue({ ok: false, code: "pairing_rate_limited" } as never);
    render(<PairDialog onDone={vi.fn()} onClose={vi.fn()} />);
    await userEvent.type(screen.getByRole("textbox", { name: /código|code/i }), "ABCD2345{Enter}");
    await waitFor(() => expect(screen.getByText(/intentos|attempts/i)).toBeInTheDocument());
  });

  it("y tras un fallo el código sigue escrito: no se teclea dos veces a ciegas", async () => {
    workstationPair.mockResolvedValue({ ok: false, code: "pairing_code_invalid" } as never);
    render(<PairDialog onDone={vi.fn()} onClose={vi.fn()} />);
    await userEvent.type(screen.getByRole("textbox", { name: /código|code/i }), "ABCD2345{Enter}");
    await waitFor(() => expect(screen.getByText(/ya no vale|no longer valid/i)).toBeInTheDocument());
    expect(screen.getByRole("textbox", { name: /código|code/i })).toHaveValue("ABCD2345");
  });
});

describe("al salir bien, se cierra y lo dice quien tiene que decirlo", () => {
  it("avisa a quien lo abrió con el nombre de la máquina", async () => {
    const onDone = vi.fn();
    render(<PairDialog onDone={onDone} onClose={vi.fn()} />);
    await userEvent.type(screen.getByRole("textbox", { name: /código|code/i }), "ABCD2345{Enter}");
    await waitFor(() => expect(onDone).toHaveBeenCalledWith("MacBook de Luis"));
  });

  it("y no se queda con un mensaje de éxito puesto: lo dice el estado de la máquina", async () => {
    // R8.3: todas las superficies lo reflejan solas. Un «¡emparejada!» aquí
    // sería el segundo sitio donde se cuenta lo mismo.
    const onDone = vi.fn();
    render(<PairDialog onDone={onDone} onClose={vi.fn()} />);
    await userEvent.type(screen.getByRole("textbox", { name: /código|code/i }), "ABCD2345{Enter}");
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(screen.queryByText(/emparejada|paired/i)).toBeNull();
  });
});

/**
 * Requisito 8.3 — al emparejar, **todas** las superficies lo reflejan sin que
 * la persona recargue nada.
 *
 * Es un test estructural sobre el pegamento: montarlo de verdad exigiría
 * Electron y una máquina emparejándose. Lo que vigila es que los tres caminos
 * sigan existiendo, porque el fallo aquí es silencioso — la pantalla se queda
 * con lo de antes y parece que el emparejamiento no funcionó.
 */
describe("el emparejamiento llega a todas las superficies", () => {
  const MAIN = readFileSync(join(HERE, "..", "src", "electron", "main.ts"), "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/\/\/.*$/gm, "");

  it("el estado de la máquina se empuja en cada cambio", () => {
    expect(MAIN).toMatch(/onBarState\(\(state\) => pushApp\("app:workstation"/);
  });

  it("la puerta vuelve a derivar el veredicto: emparejar cambia lo que se puede hacer", () => {
    expect(MAIN).toMatch(/onIdentityChanged\(/);
    const bloque = MAIN.slice(MAIN.indexOf("onIdentityChanged("));
    expect(bloque.slice(0, 300)).toMatch(/gate\.refresh\(\)/);
  });

  it("y la consola embebida se recarga sola si está mirando el puesto", () => {
    // Su diálogo seguía con la cuenta atrás de un código ya canjeado: dos
    // fuentes de verdad sobre el mismo hecho.
    const bloque = MAIN.slice(MAIN.indexOf("onIdentityChanged("));
    expect(bloque.slice(0, 300)).toMatch(/workstation.*reload\(\)/s);
  });
});
