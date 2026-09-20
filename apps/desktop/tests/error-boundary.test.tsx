// @vitest-environment jsdom
/**
 * La ventana no se queda en negro.
 *
 * Cuando algo lanza durante el render, React desmonta el árbol entero. En un
 * navegador queda la barra de direcciones y una recarga; **en una ventana de
 * Electron no queda nada**: la aplicación parece muerta y la única salida es
 * cerrarla y volver a abrirla, perdiendo lo que hubiera escrito.
 *
 * El caso que lo destapó era de una línea —un código de error de emparejamiento
 * que la tabla de textos no tenía— y por eso aquí se prueban las tres capas,
 * que son independientes a propósito:
 *
 * 1. la tabla de textos no lanza ante una clave que no existe;
 * 2. la pantalla de emparejamiento no inventa claves;
 * 3. y si aun así algo lanza, el armazón lo sostiene y ofrece salida.
 *
 * Las tres, porque arreglar solo la primera dejaría la ventana en negro con el
 * siguiente campo inesperado que llegue del servidor.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "./dom-matchers";

import { ErrorBoundary } from "../src/app/feedback/error-boundary";
import { format } from "../src/app/i18n";
import { pairErrorKey } from "../src/app/routes/pair-errors";

afterEach(cleanup);

beforeEach(() => {
  // React registra el error en consola aunque el boundary lo capture. Es ruido
  // esperado, no un fallo: silenciarlo deja legible lo que sí importa.
  vi.spyOn(console, "error").mockImplementation(() => {});
});

function Explota(): never {
  throw new Error("algo que el servidor devolvió y nadie esperaba");
}

describe("una clave de texto que no existe", () => {
  it("no lanza: registra y devuelve la clave", () => {
    // @ts-expect-error justo el caso que el tipo impide y el runtime permite:
    // una clave armada en tiempo de ejecución con lo que diga la plataforma.
    expect(() => format("es", "pair.error.codigo_que_no_existe")).not.toThrow();
  });

  it("y deja constancia, porque es un defecto", () => {
    // @ts-expect-error ver arriba.
    format("es", "pair.error.codigo_que_no_existe");
    expect(console.error).toHaveBeenCalled();
  });
});

describe("la pantalla de emparejamiento", () => {
  it("explica los códigos que conoce", () => {
    expect(pairErrorKey("pairing_code_invalid")).toBe("pair.error.pairing_code_invalid");
    expect(pairErrorKey("pairing_rate_limited")).toBe("pair.error.pairing_rate_limited");
  });

  it("no inventa un motivo para lo que no conoce", () => {
    // «No se pudo emparejar; tu máquina sigue como estaba» es verdad en
    // cualquier caso. Decir «el código ya no vale» sin saberlo, no.
    expect(pairErrorKey("algo_nuevo_del_servidor")).toBe("pair.error.pairing_unavailable");
    expect(format("es", pairErrorKey("algo_nuevo_del_servidor"))).toContain("sigue como estaba");
  });
});

describe("y si algo lanza de todos modos", () => {
  it("la ventana enseña una salida en vez de quedarse vacía", () => {
    const { container } = render(
      <ErrorBoundary>
        <Explota />
      </ErrorBoundary>,
    );

    expect(container).not.toBeEmptyDOMElement();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /volver a cargar/i })).toBeInTheDocument();
  });

  it("enseña el detalle, para que escribirnos sirva de algo", () => {
    render(
      <ErrorBoundary>
        <Explota />
      </ErrorBoundary>,
    );
    expect(screen.getByText(/nadie esperaba/)).toBeInTheDocument();
  });

  it("no depende de la tabla de textos, que puede ser justo lo roto", () => {
    render(
      <ErrorBoundary lang="en">
        <Explota />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("heading", { name: "The screen broke" })).toBeInTheDocument();
  });

  it("cuando no lanza nada, no se nota que está", () => {
    render(
      <ErrorBoundary>
        <p>el contenido de siempre</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("el contenido de siempre")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
