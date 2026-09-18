// @vitest-environment jsdom
/**
 * Requisito 7.5 — sin pertenencia a partner: **dos salidas y ningún bucle**.
 *
 * El recorrido que documentó el anexo 04: entrar con una cuenta que no
 * pertenece a ningún partner llevaba a `/desktop-auth` → `/login` → `/` →
 * `/no-access`, cuyo botón «Entrar» va a `/login`, que vuelve a `/`, que vuelve
 * a `/no-access`. La aplicación, mientras tanto, esperaba los cinco minutos.
 *
 * Dos salidas y las dos llevan a alguna parte: **usar una invitación** —que es
 * lo que de verdad falta— y **entrar con otra cuenta**, que empieza de cero en
 * vez de reintentar la misma. Ninguna de las dos vuelve al punto de partida.
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

const signInStart = vi.fn(async () => null);
const openConsole = vi.fn(async (_input?: unknown) => null);

vi.mock("../src/app/bridge", () => ({
  bridge: { signInStart: () => signInStart(), openConsole: (input: unknown) => openConsole(input) },
}));

const { NoPartner } = await import("../src/app/routes/no-partner");

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe("se explica, en vez de dejar a alguien dando vueltas", () => {
  it("dice lo que pasa: la cuenta no pertenece a ningún partner", () => {
    render(<NoPartner />);
    expect(screen.getByRole("heading")).toHaveTextContent(/partner/i);
  });

  it("y no dice «no puedes» y se queda ahí: hay exactamente dos salidas", () => {
    render(<NoPartner />);
    expect(screen.getAllByRole("button")).toHaveLength(2);
  });
});

describe("las dos salidas llevan a alguna parte", () => {
  it("entrar con otra cuenta **empieza de cero**, no reintenta la misma", async () => {
    render(<NoPartner />);
    await userEvent.click(screen.getByRole("button", { name: /otra cuenta|another account/i }));
    expect(signInStart).toHaveBeenCalledOnce();
  });

  it("la invitación lleva a donde se canjea, no a la portada", async () => {
    // `/` era exactamente el bucle: portada → sin acceso → entrar → portada.
    // La invitación llega por correo con su enlace, así que la acción es
    // abrirla: pegarla aquí es lo único que la aplicación no puede adivinar.
    render(<NoPartner />);
    await userEvent.type(
      screen.getByRole("textbox"),
      "https://console.auphere.com/invite/abcdefghijklmnop1234",
    );
    await userEvent.click(screen.getByRole("button", { name: /invitación|invitation|invite/i }));
    expect(openConsole).toHaveBeenCalledTimes(1);
    const destino = openConsole.mock.calls[0]?.[0] as { path: string };
    expect(destino.path).not.toBe("/");
    expect(destino.path).toBe("/invite/abcdefghijklmnop1234");
  });

  it("y un enlace que no es una invitación no se abre: no se adivina un destino", async () => {
    render(<NoPartner />);
    await userEvent.type(screen.getByRole("textbox"), "https://console.auphere.com/login");
    await userEvent.click(screen.getByRole("button", { name: /invitación|invitation|invite/i }));
    expect(openConsole).not.toHaveBeenCalled();
    expect(screen.getByText(/no parece una invitación|does not look like an invitation/i)).toBeInTheDocument();
  });

  it("ninguna de las dos es «ir a la consola» a ver qué pasa", () => {
    render(<NoPartner />);
    expect(screen.queryByRole("button", { name: /^ir a la consola$|^go to the console$/i })).toBeNull();
  });
});
