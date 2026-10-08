import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "@/i18n/client";

import { Composer } from "../composer";
import type { ComposerMode } from "../inbox-model";

function view(mode: ComposerMode, o: Partial<Parameters<typeof Composer>[0]> = {}) {
  const props = {
    mode,
    busy: false,
    sendError: null,
    replies: [],
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

/** Spec 030 (R9, R10, T062): the composer offers only what is possible. */
describe("Composer", () => {
  it("while the agent answers, only «Tomar el control»", async () => {
    const props = view({ kind: "agent" });
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByText(/El agente está respondiendo en WhatsApp/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Tomar el control" }));
    expect(props.onTakeOver).toHaveBeenCalled();
  });

  it("another person answering is said with their name", () => {
    view({ kind: "other", name: "Luis" });
    expect(screen.getByText("Luis está atendiendo esta conversación.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tomar el control" })).toBeInTheDocument();
  });

  it("Enter sends, Shift+Enter adds a line", async () => {
    const props = view({ kind: "mine", blocked: null });
    const box = screen.getByRole("textbox", { name: "Escribir un mensaje" });
    await userEvent.type(box, "Hola{Shift>}{Enter}{/Shift}qué tal");
    expect(props.onSend).not.toHaveBeenCalled();
    expect(box).toHaveValue("Hola\nqué tal");
    await userEvent.type(box, "{Enter}");
    expect(props.onSend).toHaveBeenCalledWith("Hola\nqué tal");
    expect(box).toHaveValue("");
  });

  it("an empty draft cannot be sent", () => {
    view({ kind: "mine", blocked: null });
    expect(screen.getByRole("button", { name: "Enviar" })).toBeDisabled();
  });

  it("a refused send gives the draft back", async () => {
    const onSend = vi.fn(async () => false);
    view({ kind: "mine", blocked: null }, { onSend });
    const box = screen.getByRole("textbox", { name: "Escribir un mensaje" });
    await userEvent.type(box, "No llega{Enter}");
    expect(box).toHaveValue("No llega");
  });

  it.each([
    ["window_closed", /Pasaron más de 24 horas/],
    ["channel_disconnected", /número de WhatsApp está desconectado/],
  ] as const)("a closed %s blocks with its sentence", (blocked, sentence) => {
    view({ kind: "mine", blocked });
    expect(screen.getByRole("status")).toHaveTextContent(sentence);
    expect(screen.getByRole("textbox", { name: "Escribir un mensaje" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Enviar" })).toBeDisabled();
  });

  it("the API's refusal is said in words, not codes", () => {
    view({ kind: "mine", blocked: null }, { sendError: "not_assigned_to_you" });
    expect(screen.getByRole("alert")).toHaveTextContent("Ya no atiendes esta conversación");
  });

  it("giving back is always at hand while you answer", async () => {
    const props = view({ kind: "mine", blocked: null });
    await userEvent.click(screen.getByRole("button", { name: "Devolver al agente" }));
    expect(props.onGiveBack).toHaveBeenCalled();
  });
});
