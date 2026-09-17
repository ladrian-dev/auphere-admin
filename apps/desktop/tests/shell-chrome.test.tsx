// @vitest-environment jsdom
/**
 * Requisito 1.1 — la franja superior, y el invariante que sostiene el armazón.
 *
 * El spike de la Fase 0 midió que arrastrar la ventana funciona con la consola
 * pintada encima del panel, **y por qué**: porque no hay solape de regiones de
 * arrastre. La franja es de esta vista y de ninguna otra, y dentro de ella todo
 * lo que se pulsa tiene que declararse «no arrastrable» — una región de
 * arrastre ignora los eventos de puntero, así que un botón que se olvide de
 * hacerlo deja de poder pulsarse.
 *
 * Es exactamente el tipo de cosa que un refactor rompe sin enterarse, y que no
 * se nota hasta que alguien intenta mover la ventana.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import { Strip } from "../src/app/shell/strip";

afterEach(cleanup);

const noop = () => {};

describe("la franja arrastra la ventana", () => {
  it("existe y se declara arrastrable", () => {
    const { container } = render(<Strip title="Sofía" onSearch={noop} />);
    const strip = container.querySelector("header");
    expect(strip?.className).toMatch(/\bdrag\b/);
  });

  it("es la **única** región de arrastre: nada dentro vuelve a declararlo", () => {
    const { container } = render(<Strip title="Sofía" onSearch={noop} />);
    const arrastrables = container.querySelectorAll(".drag");
    expect(arrastrables).toHaveLength(1);
  });

  it("todo lo que se pulsa dentro se declara no arrastrable", () => {
    const { container } = render(<Strip title="Sofía" onSearch={noop} status={<button type="button">Estado</button>} />);
    for (const control of container.querySelectorAll("button, a, input")) {
      expect(control.closest(".no-drag"), `«${control.textContent}» quedaría sin poder pulsarse`).not.toBeNull();
    }
  });

  it("reserva el hueco de los controles de ventana del sistema", () => {
    const { container } = render(<Strip title="Sofía" onSearch={noop} />);
    // En macOS los semáforos se pintan encima de la franja: si el contenido
    // empieza en cero, el título queda debajo de ellos.
    expect(container.querySelector("[data-traffic-lights]")).not.toBeNull();
  });
});

describe("lo que la franja dice", () => {
  it("el título es el objeto en el que se está, no el nombre de la aplicación", () => {
    render(<Strip title="Sofía" onSearch={noop} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Sofía");
    expect(screen.queryByText(/^Auphere$/)).toBeNull();
  });

  it("ofrece la búsqueda de acciones con su atajo a la vista", async () => {
    const onSearch = vi.fn();
    render(<Strip title="Hoy" onSearch={onSearch} />);
    const boton = screen.getByRole("button", { name: /buscar|search/i });
    expect(boton.textContent).toMatch(/⌘K/);
    boton.click();
    expect(onSearch).toHaveBeenCalledOnce();
  });

  it("deja sitio para el estado de la máquina", () => {
    render(<Strip title="Hoy" onSearch={noop} status={<span>reconectando</span>} />);
    expect(screen.getByText("reconectando")).toBeInTheDocument();
  });
});
