import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { Composer } from "../composer";

const replies = [
  { id: "r1", title: "Horario", body: "Abrimos de 10 a 20 h." },
  { id: "r2", title: "Dirección", body: "Calle Mayor 3" },
];

function view(o: Partial<Parameters<typeof Composer>[0]> = {}) {
  const props = {
    mode: { kind: "mine" as const, blocked: null },
    busy: false,
    sendError: null,
    replies,
    repliesApi: { create: vi.fn(async () => true), edit: vi.fn(async () => true), archive: vi.fn(async () => true) },
    attaching: null,
    onTakeOver: vi.fn(),
    onGiveBack: vi.fn(),
    onReopen: vi.fn(),
    onSend: vi.fn(async () => true),
    onAttach: vi.fn(),
    ...o,
  };
  render(
    <LocaleProvider locale="es">
      <Composer {...props} />
    </LocaleProvider>,
  );
  return props;
}

/** Spec 030 (R10.3, R10.4, T084): saved replies and files. */
describe("respuestas guardadas", () => {
  it("picking one leaves its text in the box, unsent", async () => {
    const props = view();
    await userEvent.click(screen.getByRole("button", { name: "Respuestas guardadas" }));
    await userEvent.click(screen.getByRole("button", { name: /^Horario/ }));
    expect(screen.getByRole("textbox", { name: "Escribir un mensaje" })).toHaveValue("Abrimos de 10 a 20 h.");
    expect(props.onSend).not.toHaveBeenCalled();
  });

  it("create, edit and delete from the same panel; Escape closes it", async () => {
    const props = view();
    await userEvent.click(screen.getByRole("button", { name: "Respuestas guardadas" }));
    await userEvent.click(screen.getByRole("button", { name: "Nueva respuesta" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Nombre" }), "Envíos");
    await userEvent.type(screen.getByRole("textbox", { name: "Texto" }), "Enviamos en 48 h.");
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(props.repliesApi.create).toHaveBeenCalledWith({ title: "Envíos", body: "Enviamos en 48 h." });

    await userEvent.click(screen.getByRole("button", { name: "Editar Horario" }));
    const body = screen.getByRole("textbox", { name: "Texto" });
    await userEvent.clear(body);
    await userEvent.type(body, "De 9 a 21 h.");
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(props.repliesApi.edit).toHaveBeenCalledWith("r1", { title: "Horario", body: "De 9 a 21 h." });

    await userEvent.click(screen.getByRole("button", { name: "Borrar Dirección" }));
    expect(props.repliesApi.archive).toHaveBeenCalledWith("r2");

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Respuestas guardadas" })).toBeNull();
    expect(screen.getByRole("button", { name: "Respuestas guardadas" })).toHaveFocus();
  });

  it("an empty list says there is none yet", async () => {
    view({ replies: [] });
    await userEvent.click(screen.getByRole("button", { name: "Respuestas guardadas" }));
    expect(screen.getByText("Aún no tienes respuestas guardadas.")).toBeInTheDocument();
  });
});

describe("archivos", () => {
  function pick(file: File) {
    fireEvent.change(screen.getByTestId("inbox-file"), { target: { files: [file] } });
  }

  it("a file of the wrong type is refused before any upload, saying what is allowed", () => {
    const props = view();
    pick(new File(["gif"], "a.gif", { type: "image/gif" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Solo se pueden enviar imágenes JPG o PNG y documentos PDF.");
    expect(props.onAttach).not.toHaveBeenCalled();
  });

  it("a file over its limit is refused with the limit", () => {
    const props = view();
    const big = new File(["x"], "foto.png", { type: "image/png" });
    Object.defineProperty(big, "size", { value: 5 * 1024 * 1024 + 1 });
    pick(big);
    expect(screen.getByRole("alert")).toHaveTextContent("Ese archivo pasa de 5 MB.");
    expect(props.onAttach).not.toHaveBeenCalled();
  });

  it("a valid one goes; while it goes, the composer says so", () => {
    const props = view();
    const pdf = new File(["%PDF"], "carta.pdf", { type: "application/pdf" });
    pick(pdf);
    expect(props.onAttach).toHaveBeenCalledWith(pdf);
  });

  it("while a file is on its way the attach button waits", () => {
    view({ attaching: "carta.pdf" });
    expect(screen.getByRole("status")).toHaveTextContent("Enviando carta.pdf…");
    expect(screen.getByRole("button", { name: "Adjuntar imagen o PDF" })).toBeDisabled();
  });
});
