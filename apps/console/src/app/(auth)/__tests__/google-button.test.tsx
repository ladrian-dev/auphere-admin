import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { GoogleButton } from "../google-button";

/**
 * «Continuar con Google» — spec 006, Requisito 5.6.
 *
 * Dos reglas, y la segunda existe por un fallo real.
 *
 * 1. **Sin Google, el botón no está.** No gris, no con tooltip: ausente. Un
 *    botón deshabilitado es un anuncio de algo que no puedes tener.
 *
 * 2. **Montar el botón no llama a nada.** Antes decidía si pintarse llamando a
 *    `googleStartAction`, que es el que EMPIEZA un inicio de sesión: acuña un
 *    par PKCE y lo guarda diez minutos en Redis. Como preguntaba al montar y
 *    volvía a llamar al pulsar, cada visita a `/login` —pública— dejaba una
 *    clave que nadie iba a consumir. La disponibilidad ahora llega resuelta
 *    desde el servidor, y este fichero lo fija.
 *
 * El test que vigila la regla 2 es el de «no llama a nada al montar». Los de
 * la regla 1 seguirían verdes con el fallo dentro — que es exactamente por lo
 * que el fallo sobrevivió.
 */
const googleStartAction = vi.fn();
vi.mock("@/lib/auth-actions", () => ({
  googleStartAction: (...a: unknown[]) => googleStartAction(...a),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

beforeEach(() => googleStartAction.mockReset());
afterEach(() => vi.clearAllMocks());

function mount(available: boolean) {
  render(
    <LocaleProvider locale="es">
      <GoogleButton intent="login" available={available} />
    </LocaleProvider>,
  );
}

describe("GoogleButton", () => {
  it("montar NO llama a nada — la pregunta ya venía resuelta del servidor", () => {
    mount(true);
    expect(googleStartAction).not.toHaveBeenCalled();
  });

  it("montar sin Google tampoco llama a nada", () => {
    mount(false);
    expect(googleStartAction).not.toHaveBeenCalled();
  });

  it("IDEAL: con Google disponible, el botón está", () => {
    mount(true);
    expect(screen.getByRole("button", { name: /Google/i })).toBeInTheDocument();
  });

  it("EMPTY: sin Google el botón NO está — ausente, no deshabilitado", () => {
    mount(false);
    expect(screen.queryByRole("button", { name: /Google/i })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("Google");
  });

  it("sólo llama al pulsar, y una sola vez", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    googleStartAction.mockResolvedValue("https://accounts.google.com/o/oauth2/v2/auth?x=1");
    // `window.location.assign` no existe en jsdom como espía utilizable.
    const assign = vi.fn();
    Object.defineProperty(window, "location", { value: { assign }, writable: true });

    mount(true);
    await userEvent.click(screen.getByRole("button", { name: /Google/i }));

    expect(googleStartAction).toHaveBeenCalledTimes(1);
    expect(googleStartAction).toHaveBeenCalledWith("login");
  });
});
