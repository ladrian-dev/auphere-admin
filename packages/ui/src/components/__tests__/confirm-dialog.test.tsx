import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "../confirm-dialog";

/**
 * Bug «restaurar un borrador publica sin puerta» (2026-10-29): promover desde el
 * panel de operador es un salto auditado de la puerta y pide el motivo. El
 * diálogo de confirmación lleva el campo y no confirma mientras falte.
 */
function Promote({ onConfirm }: { onConfirm: (reason: string) => void }) {
  const [reason, setReason] = React.useState("");
  return (
    <ConfirmDialog
      open
      onOpenChange={() => {}}
      title="Publicar la versión 4"
      confirmLabel="Publicar"
      cancelLabel="Cancelar"
      confirmDisabled={reason.trim().length < 3}
      onConfirm={() => onConfirm(reason)}
    >
      <label>
        Motivo
        <input value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
    </ConfirmDialog>
  );
}

describe("ConfirmDialog with extra fields", () => {
  it("shows its fields and waits for them before confirming", async () => {
    const onConfirm = vi.fn();
    render(<Promote onConfirm={onConfirm} />);

    const publish = screen.getByRole("button", { name: "Publicar" });
    expect(publish).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Motivo"), "El cliente lo pidió hoy");
    expect(publish).toBeEnabled();
    await userEvent.click(publish);
    expect(onConfirm).toHaveBeenCalledWith("El cliente lo pidió hoy");
  });
});
