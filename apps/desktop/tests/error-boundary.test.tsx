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

describe("el alta de la máquina", () => {
  it("explica los tres motivos que conoce", () => {
    expect(pairErrorKey("register_sign_in_again")).toBe("pair.error.register_sign_in_again");
    expect(pairErrorKey("register_at_cap")).toBe("pair.error.register_at_cap");
    expect(pairErrorKey("register_unavailable")).toBe("pair.error.register_unavailable");
  });

  it("los códigos del canje retirado ya no son un motivo propio", () => {
    // La spec 012 se llevó el canje del código. Un motivo que la plataforma ya
    // no puede emitir no merece frase propia: cae en el genérico, como
    // cualquier otro desconocido.
    expect(pairErrorKey("pairing_code_invalid")).toBe("pair.error.register_unavailable");
  });

  it("no inventa un motivo para lo que no conoce", () => {
    // «No se pudo dar de alta; tu sesión sigue bien» es verdad en cualquier
    // caso. Nombrar una causa sin saberla, no.
    expect(pairErrorKey("algo_nuevo_del_servidor")).toBe("pair.error.register_unavailable");
    expect(format("es", pairErrorKey("algo_nuevo_del_servidor"))).toContain("Tu sesión sigue bien");
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
