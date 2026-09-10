/**
 * Requisitos 7.1, 7.5, 8.1 y 8.4 (spec 002) — los clientes a los que sirve una máquina.
 *
 * Vincular no pide ruta: el directorio lo declara la máquina. Sin clientes que
 * vincular no hay selector apagado: se dice por qué. Y el estado «pendiente de
 * declarar» es un estado, no un campo.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
const linkClientAction = vi.fn();
vi.mock("@/app/(console)/workstation/actions", () => ({
  linkClientAction: (raw: unknown) => linkClientAction(raw),
  unlinkClientAction: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { LocaleProvider } from "@/i18n/client";

import { MachineClients } from "../machine-clients";

function clients(props: Partial<React.ComponentProps<typeof MachineClients>> = {}) {
  return render(
    <LocaleProvider locale="es">
      <MachineClients machineId="22222222-2222-2222-2222-222222222222" clients={[]} options={[{ ref: "cultor", name: "Cultor" }]} canEdit {...props} />
    </LocaleProvider>,
  );
}

describe("vincular clientes", () => {
  it("vacío: dice que no sirve a ningún cliente y ofrece el selector", () => {
    clients();
    expect(screen.getByText(/no sirve a ningún cliente/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/cliente/i)).toBeInTheDocument();
    expect(screen.getByText(/la consola no teclea rutas/i)).toBeInTheDocument();
  });

  it("vincular envía solo la referencia del cliente, nunca una ruta (7.1)", () => {
    clients();
    fireEvent.change(screen.getByLabelText(/cliente/i), { target: { value: "cultor" } });
    fireEvent.click(screen.getByRole("button", { name: /añadir cliente/i }));
    expect(linkClientAction).toHaveBeenCalledWith({ id: "22222222-2222-2222-2222-222222222222", ref: "cultor" });
    expect(JSON.stringify(linkClientAction.mock.calls[0])).not.toMatch(/workdir|\//);
  });

  it("sin clientes en el partner: la ausencia se diseña, sin selector apagado (8.4)", () => {
    clients({ options: [] });
    expect(screen.getByText(/no tienes clientes todavía/i)).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("todos vinculados: se dice, y no hay selector", () => {
    clients({ clients: [{ ref: "cultor", name: "Cultor", workdir: "/Users/luis/cultor", needs_directory: false }] });
    expect(screen.getByText(/ya están vinculados/i)).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByText("/Users/luis/cultor")).toBeInTheDocument();
  });

  it("sin directorio declarado se muestra como estado (7.5)", () => {
    clients({ clients: [{ ref: "cultor", name: "Cultor", workdir: null, needs_directory: true }] });
    expect(screen.getByText(/pendiente de declarar desde la máquina/i)).toBeInTheDocument();
  });

  it("solo lectura: ni selector ni quitar", () => {
    clients({ canEdit: false, clients: [{ ref: "cultor", name: "Cultor", workdir: null, needs_directory: true }] });
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /quitar/i })).not.toBeInTheDocument();
  });
});
