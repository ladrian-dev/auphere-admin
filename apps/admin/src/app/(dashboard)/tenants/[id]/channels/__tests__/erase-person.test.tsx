import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ErasePersonDialog } from "../[channelId]/erase-person-dialog";

const erase = vi.fn();
vi.mock("../actions", () => ({ erasePersonAction: (...args: unknown[]) => erase(...args) }));
const toastError = vi.fn();
const toastOk = vi.fn();
vi.mock("sonner", () => ({
  toast: { error: (...a: unknown[]) => toastError(...a), success: (...a: unknown[]) => toastOk(...a) },
}));

describe("Borrar los datos de una persona (spec 049, 5.5)", () => {
  beforeEach(() => {
    erase.mockReset();
    toastError.mockReset();
    toastOk.mockReset();
  });

  async function open() {
    render(<ErasePersonDialog tenantId="t" channelId="c" />);
    await userEvent.click(screen.getByRole("button", { name: /Borrar datos de una persona/ }));
  }

  it("pide a quién y quién lo pidió antes de dejar borrar", async () => {
    await open();
    const go = screen.getByRole("button", { name: "Borrar los datos" });
    expect(go).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Identificador de la persona"), "17841400");
    expect(go).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Quién lo pidió"), "ana@example.com");
    expect(go).toBeEnabled();
  });

  it("borra y dice cuántos mensajes vació", async () => {
    erase.mockResolvedValue({ ok: true, data: { erased: true, messages_emptied: 4 } });
    await open();
    await userEvent.type(screen.getByLabelText("Identificador de la persona"), "17841400");
    await userEvent.type(screen.getByLabelText("Quién lo pidió"), "ana@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Borrar los datos" }));
    expect(erase).toHaveBeenCalledWith("t", "c", { identifier: "17841400", requested_by: "ana@example.com" });
    expect(toastOk).toHaveBeenCalledWith("Datos borrados: 4 mensajes vaciados.");
  });

  it("si no existe esa persona lo dice en palabras", async () => {
    erase.mockResolvedValue({ ok: false, error: "person not found" });
    await open();
    await userEvent.type(screen.getByLabelText("Identificador de la persona"), "x");
    await userEvent.type(screen.getByLabelText("Quién lo pidió"), "ana@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Borrar los datos" }));
    expect(toastError).toHaveBeenCalledWith("No hay nadie con ese identificador en este canal.");
  });
});
