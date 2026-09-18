// @vitest-environment jsdom
/**
 * Requisitos 7.1 y 7.2 — entrar **desde la propia pantalla**.
 *
 * Cierra `009-T029`, que es el P0 más embarazoso de los cinco: el flujo de
 * entrada por navegador estaba entero —PKCE, oyente efímero en `127.0.0.1`,
 * canje contra la consola— y **no lo llamaba nadie**. Un camino completo sin
 * disparador es código que pasa las pruebas y no existe para la persona.
 *
 * Lo que se pintaba en su lugar: «Sin sesión. Entra en la consola para ver tu
 * equipo» con un botón «Ir a la consola», que devolvía a `/login`, que devolvía
 * a la aplicación sin sesión. El anexo 04 lo anotó como bucle.
 *
 * Y R8.7 sigue en pie: **ningún formulario de credenciales propio**. Esta
 * pantalla tiene un botón, no un campo de contraseña.
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

const signInStart = vi.fn(async () => null);
const signInCancel = vi.fn(async () => null);
const openConsole = vi.fn(async () => null);
const writeText = vi.fn(async () => undefined);

vi.mock("../src/app/bridge", () => ({
  bridge: {
    signInStart: () => signInStart(),
    signInCancel: () => signInCancel(),
    openConsole: () => openConsole(),
  },
}));

const { SignIn } = await import("../src/app/routes/sign-in");

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  Object.assign(navigator, { clipboard: { writeText } });
});

describe("sin sesión, se entra desde aquí", () => {
  it("hay una acción de entrar, y es la principal", async () => {
    render(<SignIn state={null} />);
    await userEvent.click(screen.getByRole("button", { name: /entrar|sign in/i }));
    expect(signInStart).toHaveBeenCalledOnce();
  });

  it("y dice que se abre el navegador, porque es donde va a pasar", () => {
    render(<SignIn state={null} />);
    expect(screen.getByText(/navegador|browser/i)).toBeInTheDocument();
  });

  it("no hay ningún formulario de credenciales propio (8.7)", () => {
    const { container } = render(<SignIn state={null} />);
    expect(container.querySelector('input[type="password"]')).toBeNull();
    expect(container.querySelector("form")).toBeNull();
  });

  it("ya no manda «a la consola» a dar vueltas", () => {
    render(<SignIn state={null} />);
    expect(screen.queryByRole("button", { name: /ir a la consola|go to the console/i })).toBeNull();
  });
});

describe("mientras se espera al navegador (7.2)", () => {
  const esperando = { state: "esperando" as const, since: "2026-09-18T10:00:00Z", url: "https://console.example/desktop-auth?x=1" };

  it("las tres salidas están: abrir de nuevo, copiar el enlace y cancelar", () => {
    render(<SignIn state={esperando} />);
    for (const nombre of [/abrir de nuevo|open again/i, /copiar|copy/i, /cancelar|cancel/i]) {
      expect(screen.getByRole("button", { name: nombre })).toBeInTheDocument();
    }
  });

  it("volver a abrir no arranca otra entrada: reabre la misma", async () => {
    // Arrancar otra generaría otro `state` y otro par PKCE, y la pestaña que la
    // persona tiene abierta dejaría de valer sin que nadie se lo dijera.
    render(<SignIn state={esperando} />);
    await userEvent.click(screen.getByRole("button", { name: /abrir de nuevo|open again/i }));
    expect(openConsole).not.toHaveBeenCalled();
    expect(signInStart).toHaveBeenCalledOnce();
  });

  it("copiar el enlace copia el de verdad, para pegarlo en otro navegador", async () => {
    render(<SignIn state={esperando} />);
    await userEvent.click(screen.getByRole("button", { name: /copiar|copy/i }));
    expect(writeText).toHaveBeenCalledWith(esperando.url);
  });

  it("cancelar cancela, y no deja el oyente abierto a su suerte", async () => {
    render(<SignIn state={esperando} />);
    await userEvent.click(screen.getByRole("button", { name: /cancelar|cancel/i }));
    expect(signInCancel).toHaveBeenCalledOnce();
  });

  it("mientras espera no se ofrece entrar otra vez: sería empezar de cero", () => {
    render(<SignIn state={esperando} />);
    expect(screen.queryByRole("button", { name: /^entrar$|^sign in$/i })).toBeNull();
  });
});
