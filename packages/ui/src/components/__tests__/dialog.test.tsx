import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { axeViolations } from "../../test/axe";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "../dialog";
import { UiCopyProvider } from "../ui-copy";

/**
 * Spec 047 (R47.5 y escenario 4 de la historia 27): un modal retiene el foco,
 * lo devuelve al cerrar, se cierra con Escape y con su botón, y lleva el título
 * enlazado.
 */
function EditClient() {
  return (
    <UiCopyProvider copy={{ close: "Cerrar" }}>
      <button type="button">Antes</button>
      <Dialog>
        <DialogTrigger>Editar cliente</DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Editar Flor y Encanto</DialogTitle>
            <DialogDescription>Nombre, nicho y moneda.</DialogDescription>
          </DialogHeader>
          <label>
            Nombre
            <input defaultValue="Flor y Encanto" />
          </label>
          <DialogFooter showCloseButton>
            <button type="button">Guardar</button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <button type="button">Después</button>
    </UiCopyProvider>
  );
}

async function open() {
  const user = userEvent.setup();
  render(<EditClient />);
  const trigger = screen.getByRole("button", { name: "Editar cliente" });
  await user.click(trigger);
  const dialog = await screen.findByRole("dialog", { name: "Editar Flor y Encanto" });
  return { user, trigger, dialog };
}

describe("Dialog", () => {
  it("lleva el título y la descripción enlazados", async () => {
    const { dialog } = await open();
    expect(dialog).toHaveAccessibleName("Editar Flor y Encanto");
    expect(dialog).toHaveAccessibleDescription("Nombre, nicho y moneda.");
  });

  it("retiene el foco: Tab y Mayús+Tab no salen del modal", async () => {
    const { user, dialog } = await open();
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
    // La trampa de Base UI pone guardas a los dos lados del modal: el foco pasa
    // por la guarda y ella lo devuelve dentro. Se espera a que se asiente y se
    // comprueba dónde queda, que es lo que vive quien usa el teclado.
    const settled = (step: string) =>
      waitFor(() =>
        expect(dialog.contains(document.activeElement), `${step} dejó el foco en ${document.activeElement?.outerHTML.slice(0, 60)}`).toBe(true),
      );
    for (let i = 0; i < 8; i++) {
      await user.tab();
      await settled(`Tab ${i + 1}`);
    }
    for (let i = 0; i < 8; i++) {
      await user.tab({ shift: true });
      await settled(`Mayús+Tab ${i + 1}`);
    }
  });

  it("Escape lo cierra y el foco vuelve a quien lo abrió", async () => {
    const { user, trigger } = await open();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("el botón de cerrar del pie habla el idioma de la consola y cierra", async () => {
    const { user, trigger, dialog } = await open();
    const closes = screen.getAllByRole("button", { name: "Cerrar" });
    // La X de la esquina y el del pie: ninguno dice «Close» en una consola en español.
    expect(closes).toHaveLength(2);
    expect(dialog).not.toHaveTextContent(/\bClose\b/);
    await user.click(closes[closes.length - 1]!);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("pasa axe abierto", async () => {
    await open();
    expect(await axeViolations()).toEqual([]);
  });
});
