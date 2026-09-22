// @vitest-environment jsdom
/**
 * Requisitos 8.4 y 8.5 — declarar el directorio de un cliente, y desemparejar.
 *
 * El silencio que esto cierra (anexo 04, `bar.ts:219`): elegir un directorio que
 * no valía **se ignoraba**. El selector se cerraba, la lista seguía igual, y la
 * persona se quedaba sin saber si había pulsado mal, si el directorio no valía
 * o si la aplicación estaba rota. La validación existía y su motivo se tiraba.
 *
 * Y desemparejar: la barra lo confirmaba con el diálogo **nativo del
 * navegador** (`confirm()`), que no se puede vestir, no dice en qué aplicación
 * estás y en Electron aparece sin contexto. Aquí es un diálogo de la aplicación
 * que explica qué deja de funcionar y qué no.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

const workstationPickDirectory = vi.fn(async (_i?: unknown) => ({ ok: true as const, data: { path_shown: "~/clients/boreal" } }));
const workstationUnpair = vi.fn(async () => ({ ok: true as const, data: null }));
const openConsole = vi.fn(async (_i?: unknown) => ({ ok: true as const, data: null }));

vi.mock("../src/app/bridge", () => ({
  bridge: {
    workstationPickDirectory: (input: unknown) => workstationPickDirectory(input),
    workstationUnpair: () => workstationUnpair(),
    openConsole: (input: unknown) => openConsole(input),
  },
}));

const { Directories } = await import("../src/app/routes/directories");
const { UnpairDialog } = await import("../src/app/routes/unpair-dialog");

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  workstationPickDirectory.mockResolvedValue({ ok: true, data: { path_shown: "~/clients/boreal" } });
});

const CLIENTES = [
  { client_ref: "boreal", name: "Boreal", workdir: null },
  { client_ref: "cultor", name: "Cultor", workdir: "~/clients/cultor" },
];

describe("declarar un directorio", () => {
  it("el que falta se ve como que falta, no como uno vacío", () => {
    render(<Directories clients={CLIENTES} onChanged={vi.fn()} />);
    const fila = screen.getByText("Boreal").closest("li")!;
    expect(fila.textContent).toMatch(/sin declarar|not declared/i);
  });

  it("el que está declarado enseña dónde", () => {
    render(<Directories clients={CLIENTES} onChanged={vi.fn()} />);
    expect(screen.getByText("~/clients/cultor")).toBeInTheDocument();
  });

  it("elegir uno abre el selector del sistema para ese cliente", async () => {
    render(<Directories clients={CLIENTES} onChanged={vi.fn()} />);
    await userEvent.click(screen.getAllByRole("button")[0]!);
    expect(workstationPickDirectory).toHaveBeenCalledWith({ client_ref: "boreal" });
  });
});

describe("el silencio que se cierra: un directorio que no vale", () => {
  it("dice **por qué** no vale, no que «no se pudo»", async () => {
    workstationPickDirectory.mockResolvedValue({ ok: false, code: "invalid", reason: "readable" } as never);
    render(<Directories clients={CLIENTES} onChanged={vi.fn()} />);
    await userEvent.click(screen.getAllByRole("button")[0]!);
    await waitFor(() => expect(screen.getByText(/leer|read/i)).toBeInTheDocument());
  });

  it("y cada motivo tiene su frase: no vale una genérica", async () => {
    const vistos = new Set<string>();
    for (const reason of ["exists", "is_dir", "resolves_within", "readable"]) {
      cleanup();
      workstationPickDirectory.mockResolvedValue({ ok: false, code: "invalid", reason } as never);
      const { container } = render(<Directories clients={CLIENTES} onChanged={vi.fn()} />);
      await userEvent.click(screen.getAllByRole("button")[0]!);
      await waitFor(() => expect(container.querySelector('[role="alert"]')).not.toBeNull());
      vistos.add(container.querySelector('[role="alert"]')!.textContent ?? "");
    }
    expect(vistos.size).toBe(4);
  });

  it("cancelar el selector no es un error: no se dice nada", async () => {
    workstationPickDirectory.mockResolvedValue({ ok: false, code: "cancelled" } as never);
    const { container } = render(<Directories clients={CLIENTES} onChanged={vi.fn()} />);
    await userEvent.click(screen.getAllByRole("button")[0]!);
    await waitFor(() => expect(workstationPickDirectory).toHaveBeenCalled());
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });
});

describe("desemparejar se confirma, y sin el diálogo del navegador (8.5)", () => {
  it("explica qué deja de funcionar", () => {
    render(<UnpairDialog onDone={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByRole("dialog").textContent).toMatch(/dejar[aá]n? de|will stop/i);
  });

  it("y qué **no**: sin eso, desemparejar parece borrar el trabajo", () => {
    render(<UnpairDialog onDone={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByRole("dialog").textContent).toMatch(/siguen|sigue|keep|stay/i);
  });

  it("no usa el diálogo nativo del navegador", async () => {
    const nativo = vi.fn(() => true);
    vi.stubGlobal("confirm", nativo);
    render(<UnpairDialog onDone={vi.fn()} onClose={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /desemparejar|unpair/i }));
    expect(nativo).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("y el botón por defecto no es el destructivo: salir por costumbre no desempareja", () => {
    render(<UnpairDialog onDone={vi.fn()} onClose={vi.fn()} />);
    const botones = screen.getAllByRole("button");
    expect(botones[0]!.textContent).toMatch(/cancelar|cancel/i);
  });

  it("al confirmar, desempareja de verdad", async () => {
    const onDone = vi.fn();
    render(<UnpairDialog onDone={onDone} onClose={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /desemparejar|unpair/i }));
    await waitFor(() => expect(workstationUnpair).toHaveBeenCalledOnce());
    expect(onDone).toHaveBeenCalledOnce();
  });
});

describe("y dice la verdad sobre lo que queda abierto — spec 012, R2", () => {
  /**
   * Desemparejar es un acto **local**: no llama al servidor, y eso lo decidió
   * la spec 002 (R11.2) con razón —archivar lleva el nombre de quien lo hace, y
   * la credencial no gana una sexta operación—. La consecuencia es que la
   * máquina sigue dada de alta hasta que alguien la archive.
   *
   * El texto decía lo contrario, y de dos maneras: daba por apagada la
   * credencial, y prometía «hasta que la vuelvas a emparejar» cuando archivar
   * es terminal y lo que procede es dar de alta otra (R11.5).
   */

  it("dice que la máquina queda pendiente de archivar desde la consola", () => {
    render(<UnpairDialog onDone={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByRole("dialog").textContent).toMatch(
      /pendiente de archivar|pending archiving/i,
    );
  });

  it("y NO promete volver a emparejar esta misma máquina", () => {
    // La mitad que se cuela: es fácil añadir la frase nueva y dejar la vieja,
    // y entonces la pantalla dice las dos cosas a la vez.
    render(<UnpairDialog onDone={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByRole("dialog").textContent).not.toMatch(
      /vuelvas a emparejar|pair it again/i,
    );
  });

  it("dice que archivar es definitivo", () => {
    render(<UnpairDialog onDone={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByRole("dialog").textContent).toMatch(/definitivo|final/i);
  });

  it("tras desemparejar, ofrece el camino para archivarla en vez de dejarlo buscando", async () => {
    render(<UnpairDialog onDone={vi.fn()} onClose={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /desemparejar|unpair/i }));

    const archivar = await screen.findByRole("button", { name: /archivar|archive/i });
    await userEvent.click(archivar);

    expect(openConsole).toHaveBeenCalledWith({ path: "/workstation" });
  });
});
