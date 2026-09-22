import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MessageActions } from "../src/components/message-actions";

/**
 * Se puede corregir el tiro — spec 013, Requisito 5.
 *
 * Nada de esto existía: para cambiar una palabra de la pregunta había que
 * escribirla entera otra vez, y para llevarse una respuesta a otro sitio,
 * seleccionarla a mano sin arrastrar el resto del hilo.
 *
 * La decisión que más se nota está en el segundo bloque: **se copia el texto
 * tal como se escribió, no el pintado**. Con Markdown de por medio son dos
 * cosas distintas — una lista pintada pierde los guiones, una tabla pierde las
 * tuberías, y lo que se pega en otro sitio ya no es lo que había.
 */

afterEach(() => vi.restoreAllMocks());

function clipboardSpy() {
  const escrito = vi.fn(() => Promise.resolve());
  Object.assign(navigator, { clipboard: { writeText: escrito } });
  return escrito;
}

describe("copiar (R5.2)", () => {
  it("da el texto tal como se escribió, no como se pintó", async () => {
    const escrito = clipboardSpy();
    render(<MessageActions text={"- uno\n- dos"} canEdit={false} canRetry={false} />);

    await userEvent.click(screen.getByRole("button", { name: /copiar/i }));

    expect(escrito).toHaveBeenCalledWith("- uno\n- dos");
  });
});

describe("editar y reintentar (R5.1)", () => {
  it("editar devuelve el texto para volver a enviarlo", async () => {
    const editar = vi.fn();
    render(<MessageActions text="la pregunta" canEdit canRetry={false} onEdit={editar} />);

    await userEvent.click(screen.getByRole("button", { name: /editar/i }));

    expect(editar).toHaveBeenCalledWith("la pregunta");
  });

  it("reintentar rehace el turno desde ahí", async () => {
    const otra = vi.fn();
    render(<MessageActions text="x" canEdit={false} canRetry onRetry={otra} />);

    await userEvent.click(screen.getByRole("button", { name: /reintentar/i }));

    expect(otra).toHaveBeenCalledOnce();
  });
});

describe("cuando no se puede (R5.3, R5.4)", () => {
  it("con un turno en marcha, editar NO está disponible y se dice por qué", () => {
    render(<MessageActions text="x" canEdit={false} canRetry={false} blockedReason="turno_en_marcha" />);

    expect(screen.queryByRole("button", { name: /editar/i })).toBeNull();
    // Un control que falla al pulsarlo parece roto. Uno ausente con su motivo
    // al lado es una pantalla honesta (§V).
    expect(screen.getByText(/en marcha/i)).toBeInTheDocument();
  });

  it("con una decisión pendiente, se pide esa decisión antes que nada", () => {
    render(<MessageActions text="x" canEdit={false} canRetry={false} blockedReason="decision_pendiente" />);

    // «confirmación pendiente» es el vocabulario que la aplicación ya usa en
    // el composer. Inventar otro aquí sería una tercera forma de decir lo
    // mismo, que es como se empieza a divergir.
    expect(screen.getByText(/confirmación pendiente/i)).toBeInTheDocument();
  });

  it("copiar sigue disponible aunque lo demás esté bloqueado", async () => {
    // Copiar no cambia nada: bloquearlo sería castigar sin motivo.
    const escrito = clipboardSpy();
    render(<MessageActions text="x" canEdit={false} canRetry={false} blockedReason="turno_en_marcha" />);

    await userEvent.click(screen.getByRole("button", { name: /copiar/i }));
    expect(escrito).toHaveBeenCalledWith("x");
  });
});
