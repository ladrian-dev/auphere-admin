// @vitest-environment jsdom
/**
 * Requisito 4.2 — un hilo que no se pudo abrir **no está vacío**.
 *
 * Es uno de los cinco P0. La cadena era sutil: `threadOpen` no tenía rama de
 * error, `useCompanion` arranca en `ready`, y el vacío se decide por «cero
 * elementos». Resultado: si la plataforma no contestaba, la pantalla decía «tu
 * hilo con Sofía está vacío» — una frase tranquilizadora sobre algo que había
 * fallado. Ahí se pierde la confianza en todo lo demás que dice la pantalla.
 */
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import { ThreadOpenError } from "../src/app/routes/thread-open-error";

afterEach(cleanup);

describe("se dice que falló, no que está vacío", () => {
  it("nombra el fallo y no promete una conversación vacía", () => {
    render(<ThreadOpenError name="Sofía" onRetry={vi.fn()} />);
    expect(screen.getByText(/no se pudo|could not/i)).toBeInTheDocument();
    expect(screen.queryByText(/está vacío|is empty/i)).toBeNull();
  });

  it("dice que el trabajo sigue en el servidor: esto es la pantalla", () => {
    render(<ThreadOpenError name="Sofía" onRetry={vi.fn()} />);
    expect(screen.getByText(/servidor|server/i)).toBeInTheDocument();
  });

  it("ofrece reintentar, que es lo único que hace falta", async () => {
    const onRetry = vi.fn();
    render(<ThreadOpenError name="Sofía" onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: /reintentar|retry/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("no enseña códigos crudos", () => {
    const { container } = render(<ThreadOpenError name="Sofía" onRetry={vi.fn()} detail="HTTP 500 thread_open_failed" />);
    expect(container.textContent).not.toMatch(/HTTP 500|thread_open_failed/);
  });
});

describe("y el detalle técnico existe, pero para soporte", () => {
  it("se puede copiar sin ensuciar la pantalla", () => {
    render(<ThreadOpenError name="Sofía" onRetry={vi.fn()} detail="HTTP 500" />);
    const copiar = screen.getByRole("button", { name: /detalle|details/i });
    expect(copiar).toBeInTheDocument();
  });

  it("sin detalle no hay nada que copiar: la ausencia se diseña", () => {
    render(<ThreadOpenError name="Sofía" onRetry={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /detalle|details/i })).toBeNull();
  });
});
