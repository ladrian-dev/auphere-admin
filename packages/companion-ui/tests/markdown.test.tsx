import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Markdown } from "../src/components/markdown";

/**
 * Lo que el agente escribe se puede leer — spec 013, Requisito 2.
 *
 * El timeline pintaba todo con `<p whitespace-pre-wrap>`, así que una
 * respuesta con lista, tabla y bloque de código se veía como texto plano con
 * las comillas a la vista. El agente **ya escribe en Markdown** —su prompt se
 * lo pide—, de modo que el producto estaba generando algo que el producto no
 * sabía enseñar.
 *
 * Los tres bloques de abajo no son el mismo test en tres tamaños:
 *
 * * el primero es **que se vea**;
 * * el segundo es **que no ejecute nada**, y es el que justifica la elección de
 *   librería: se construyen elementos de React, no cadenas de HTML, así que
 *   R2.3 se cumple por construcción y no por acertar con un sanitizador;
 * * el tercero es **el streaming**, donde la sintaxis está incompleta por
 *   definición.
 */

beforeEach(() => {
  vi.stubGlobal("open", vi.fn());
});
afterEach(() => vi.unstubAllGlobals());

describe("se pinta como lo que es (R2.1)", () => {
  it("títulos, listas, énfasis y enlaces", () => {
    render(
      <Markdown
        text={"## Resumen\n\n- primero\n- segundo\n\nEsto es **importante** y [un enlace](https://auphere.com)."}
      />,
    );

    expect(screen.getByRole("heading", { name: "Resumen" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("importante").tagName).toBe("STRONG");
    expect(screen.getByRole("link", { name: "un enlace" })).toBeInTheDocument();
  });

  it("tablas de GFM, que no son Markdown estándar", () => {
    render(<Markdown text={"| mes | ventas |\n|---|---|\n| agosto | 120 |\n| julio | 98 |"} />);

    const tabla = screen.getByRole("table");
    expect(within(tabla).getByRole("columnheader", { name: "ventas" })).toBeInTheDocument();
    expect(within(tabla).getAllByRole("row")).toHaveLength(3);
  });

  it("bloques de código, con su lenguaje", () => {
    render(<Markdown text={'```python\nprint("hola")\n```'} />);

    const code = document.querySelector("pre code");
    expect(code).not.toBeNull();
    expect(code?.textContent).toContain('print("hola")');
  });
});

describe("no ejecuta ni carga nada de lo que venga dentro (R2.3)", () => {
  // El mensaje puede ser texto de un desconocido por WhatsApp. Esta es la
  // superficie hostil de verdad, y el motivo de que no haya `rehype-raw`.
  it("el HTML crudo no se convierte en HTML", () => {
    const { container } = render(<Markdown text={'<script>window.robado = 1</script>\n\ntexto normal'} />);

    expect(container.querySelector("script")).toBeNull();
    expect((window as unknown as { robado?: number }).robado).toBeUndefined();
    expect(screen.getByText("texto normal")).toBeInTheDocument();
  });

  it("no se carga ninguna imagen remota", () => {
    const { container } = render(<Markdown text={"![x](https://rastreador.example/pixel.png)"} />);

    expect(container.querySelector("img")).toBeNull();
  });

  it("un enlace `javascript:` no llega al documento", () => {
    const { container } = render(<Markdown text={"[púlsame](javascript:alert(1))"} />);

    const href = container.querySelector("a")?.getAttribute("href") ?? "";
    expect(href.startsWith("javascript:")).toBe(false);
  });
});

describe("mientras el texto llega a trozos (R2.4)", () => {
  it("un bloque de código sin cerrar no se lleva por delante el resto", () => {
    // CommonMark dice que un cercado sin cerrar llega al final del documento,
    // así que esto es correcto y no hay que «arreglarlo»: lo que se comprueba
    // es que se pinta algo legible en vez de romperse.
    const { container } = render(<Markdown text={'Mira esto:\n\n```python\nprint("a med'} />);

    expect(screen.getByText(/Mira esto/)).toBeInTheDocument();
    expect(container.querySelector("pre")).not.toBeNull();
  });

  it("un énfasis abierto no deja asteriscos sueltos por la pantalla", () => {
    // Esto sí lo arregla `remend`: cierra lo que quedó a medias.
    render(<Markdown text={"el resultado es **importan"} />);

    expect(document.body.textContent).not.toContain("**");
  });
});

describe("un mensaje enorme no bloquea la ventana (R2.5)", () => {
  it("pinta una parte, dice que hay más, y deja ver el resto", async () => {
    const enorme = "línea de relleno que no dice nada\n\n".repeat(2000);
    render(<Markdown text={enorme} />);

    const masBoton = screen.getByRole("button", { name: /ver el resto|mostrar más/i });
    expect(masBoton).toBeInTheDocument();
    const antes = document.body.textContent?.length ?? 0;
    expect(antes).toBeLessThan(enorme.length);

    await userEvent.click(masBoton);
    expect((document.body.textContent?.length ?? 0)).toBeGreaterThan(antes);
  });
});

describe("copiar un bloque de código (R2.2)", () => {
  it("da el código y nada más: ni el resto del mensaje ni las comillas", async () => {
    const escrito = vi.fn(() => Promise.resolve());
    Object.assign(navigator, { clipboard: { writeText: escrito } });

    render(<Markdown text={'Prueba esto:\n\n```python\nprint("hola")\n```\n\nY luego cuéntame.'} />);

    await userEvent.click(screen.getByRole("button", { name: /copiar/i }));

    expect(escrito).toHaveBeenCalledWith('print("hola")');
  });
});

describe("lo que ya está cerrado no se mueve al llegar más texto (R2.4)", () => {
  /**
   * **Este test pasó sin escribir una línea de implementación, y eso es el
   * hallazgo.** La tarea T020 daba por hecho que habría que partir el texto en
   * bloques y memorizar los cerrados para evitar que parpadearan. No hace
   * falta: React reconcilia por tipo y posición, así que un `<h1>` que sigue
   * siendo el mismo `<h1>` **no se remonta** aunque el Markdown se vuelva a
   * parsear entero.
   *
   * Lo que sí ocurre, y no se puede evitar, es que el bloque **en curso**
   * cambie de forma —una cabecera de tabla a medias se ve como párrafo hasta
   * que llega la fila delimitadora que GFM exige—. Eso no es un defecto: es
   * que hasta ese momento no hay información para saber qué va a ser.
   *
   * Queda una preocupación real y **sin medir**: volver a parsear todo el
   * texto en cada trozo es trabajo cuadrático sobre un mensaje largo. Es un
   * problema de coste, no de parpadeo, y optimizarlo sin medirlo sería añadir
   * maquinaria a ciegas. Anotado en la bitácora de `tasks.md`.
   */
  it("un bloque ya cerrado conserva su nodo cuando llega más texto", () => {
    const { rerender, container } = render(<Markdown text={"# Título\n\nprimer párrafo\n\n| mes |"} />);
    const tituloAntes = container.querySelector("h1");

    rerender(<Markdown text={"# Título\n\nprimer párrafo\n\n| mes | ventas |\n|---|---|\n| ago | 120 |"} />);

    // El mismo nodo, no uno nuevo: si se rehiciera, React lo habría
    // reemplazado y esta identidad fallaría.
    expect(container.querySelector("h1")).toBe(tituloAntes);
    expect(screen.getByRole("table")).toBeInTheDocument();
  });
});
