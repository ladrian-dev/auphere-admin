import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { axeViolations } from "../../test/axe";
import { Popover, PopoverContent, PopoverTitle, PopoverTrigger } from "../popover";

/**
 * Spec 047 (R47.3, R47.9): el desplegable de la campana es un popover — una
 * capa flotante (vidrio) con título, que se cierra con Escape y devuelve el foco.
 */
function Bell() {
  return (
    <Popover>
      <PopoverTrigger aria-label="Notificaciones">🔔</PopoverTrigger>
      <PopoverContent>
        <PopoverTitle>Notificaciones</PopoverTitle>
        <a href="/notifications">Ver todas</a>
      </PopoverContent>
    </Popover>
  );
}

describe("Popover", () => {
  it("abre una capa con título, de vidrio", async () => {
    const user = userEvent.setup();
    render(<Bell />);
    await user.click(screen.getByRole("button", { name: "Notificaciones" }));
    const layer = await screen.findByRole("dialog", { name: "Notificaciones" });
    expect(layer.className).toMatch(/\bglass\b/);
    expect(screen.getByRole("link", { name: "Ver todas" })).toBeInTheDocument();
  });

  it("Escape la cierra y el foco vuelve al botón", async () => {
    const user = userEvent.setup();
    render(<Bell />);
    const trigger = screen.getByRole("button", { name: "Notificaciones" });
    await user.click(trigger);
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(trigger).toHaveFocus();
  });

  it("pasa axe abierta", async () => {
    const user = userEvent.setup();
    render(<Bell />);
    await user.click(screen.getByRole("button", { name: "Notificaciones" }));
    await screen.findByRole("dialog");
    expect(await axeViolations()).toEqual([]);
  });
});
