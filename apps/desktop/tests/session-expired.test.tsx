// @vitest-environment jsdom
/**
 * Requisito 3.4 — la sesión caducada se dice donde estás.
 *
 * Perder la sesión es un caso normal: caduca, o alguien la cierra en otra
 * pestaña de la consola. Lo que no es normal es cómo se vivía — la ventana
 * saltaba al inicio de sesión sin decir nada y lo que estuvieras escribiendo
 * desaparecía con el hilo desmontado.
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import { SessionExpired } from "../src/app/routes/session-expired";

afterEach(cleanup);

describe("se dice, y se ofrece volver a entrar", () => {
  it("dice que terminó y que lo escrito sigue ahí", () => {
    render(<SessionExpired reason="anonymous" onSignIn={vi.fn()} />);
    expect(screen.getByRole("heading")).toHaveTextContent(/sesión terminó|session ended/i);
    expect(screen.getByText(/sigue aquí|still here/i)).toBeInTheDocument();
  });

  it("la acción es entrar, no «ir a la consola» a ver qué pasa", async () => {
    const onSignIn = vi.fn();
    render(<SessionExpired reason="anonymous" onSignIn={onSignIn} />);
    await userEvent.click(screen.getByRole("button", { name: /entrar|sign in/i }));
    expect(onSignIn).toHaveBeenCalledOnce();
  });

  it("se anuncia sin robar el foco", () => {
    const { container } = render(<SessionExpired reason="anonymous" onSignIn={vi.fn()} />);
    // Un cambio de estado se anuncia con `status`; `alert` sería interrumpir a
    // alguien por algo que se resuelve entrando otra vez.
    expect(container.querySelector('[role="status"]')).not.toBeNull();
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });
});

describe("no pertenecer a un partner es otra cosa", () => {
  it("no se le dice «tu sesión terminó» a quien sí tiene sesión", () => {
    render(<SessionExpired reason="no_membership" onSignIn={vi.fn()} />);
    expect(screen.queryByText(/sesión terminó|session ended/i)).toBeNull();
    expect(screen.getByRole("heading")).toHaveTextContent(/partner/i);
  });

  it("y no se le promete que lo escrito sigue ahí, porque no es su problema", () => {
    render(<SessionExpired reason="no_membership" onSignIn={vi.fn()} />);
    expect(screen.queryByText(/sigue aquí|still here/i)).toBeNull();
  });
});
