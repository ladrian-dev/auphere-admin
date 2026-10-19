import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const setAccess = vi.fn();
vi.mock("../actions", () => ({ setPartnerAccessAction: (...a: unknown[]) => setAccess(...a) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import type { PartnerAccessOut } from "@/lib/backend";

import { ModulesForm } from "../modules-form";

const access: PartnerAccessOut = {
  console_enabled: true,
  modules: ["panel", "clients", "usage", "billing"],
  catalog: [],
};

describe("ModulesForm (spec 032)", () => {
  beforeEach(() => {
    setAccess.mockReset();
    setAccess.mockResolvedValue({ ok: true, data: access });
  });

  it("draws one tile per module, grouped, with what is on checked", () => {
    render(<ModulesForm partnerId="p1" access={access} />);
    for (const name of ["Panel", "Clientes", "Consumo", "Auditoría", "Equipo", "Facturación", "API", "Companion"]) {
      expect(screen.getByText(name)).toBeTruthy();
    }
    expect((screen.getByRole("checkbox", { name: /Facturación/ }) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole("checkbox", { name: /Companion/ }) as HTMLInputElement).checked).toBe(false);
    expect(screen.getByText("3 de 6 activos")).toBeTruthy();
  });

  it("saves only when something changed, in canonical order", async () => {
    render(<ModulesForm partnerId="p1" access={access} />);
    const save = screen.getByRole("button", { name: "Guardar módulos" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.click(screen.getByRole("checkbox", { name: /Companion/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /Equipo/ }));
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    await vi.waitFor(() => expect(setAccess).toHaveBeenCalled());
    expect(setAccess).toHaveBeenCalledWith("p1", {
      console_enabled: true,
      modules: ["panel", "clients", "usage", "team", "billing", "companion"],
    });
  });

  it("refuses a console that is on with no view, and says why", () => {
    render(<ModulesForm partnerId="p1" access={{ ...access, modules: ["panel"] }} />);
    fireEvent.click(screen.getByRole("checkbox", { name: /Panel/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /Companion/ }));
    expect(screen.getByRole("alert").textContent).toMatch(/al menos una sección/);
    expect((screen.getByRole("button", { name: "Guardar módulos" }) as HTMLButtonElement).disabled).toBe(true);
    expect(setAccess).not.toHaveBeenCalled();
  });

  it("never disables a tile when the console is off", () => {
    render(<ModulesForm partnerId="p1" access={{ ...access, console_enabled: false }} />);
    for (const box of screen.getAllByRole("checkbox")) {
      expect((box as HTMLInputElement).disabled).toBe(false);
    }
    expect(screen.getByText(/se aplicará al encenderla/)).toBeTruthy();
  });
});
