import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { DesktopCode } from "../desktop-code/desktop-code";

/**
 * La pantalla del código de escritorio — spec 009, Requisito 3.1.
 *
 * **Lo que esta pantalla tiene que hacer bien no es enseñar ocho caracteres: es
 * decir qué hacer con ellos.** Quien llega aquí acaba de autenticarse con
 * Google en su navegador y no tiene ni idea de por qué no está ya dentro de la
 * aplicación. Un código sin instrucción es un callejón.
 *
 * Y tiene que decir que **caduca**, porque el que no lo sepa lo dejará abierto
 * en una pestaña y volverá dentro de media hora.
 */
function paint(props: Partial<React.ComponentProps<typeof DesktopCode>> = {}) {
  render(
    <LocaleProvider locale="es">
      <DesktopCode code="K7MP4XQ2" {...props} />
    </LocaleProvider>,
  );
}

describe("la pantalla del código de escritorio", () => {
  it("enseña el código en grupos, como se dicta en voz alta", () => {
    paint();
    // `display_code` lo parte: K7MP-4XQ2. Ocho seguidos se teclean mal.
    expect(screen.getByText(/K7MP-4XQ2/)).toBeInTheDocument();
  });

  it("dice qué hacer con él, no sólo cuál es", () => {
    paint();
    expect(screen.getByRole("status")).toHaveTextContent(/barra|aplicaci/i);
  });

  it("dice que caduca", () => {
    paint();
    expect(screen.getByRole("status")).toHaveTextContent(/10|diez/i);
  });

  it("si no se pudo emitir, lo dice y no finge un código", () => {
    paint({ code: null });
    expect(screen.queryByText(/K7MP-4XQ2/)).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/no se pudo|inténtal/i);
  });
});
