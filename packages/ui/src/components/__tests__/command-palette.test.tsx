import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CommandPalette, filterCommandItems, type CommandItem } from "../command-palette";

function items(onSelect: (id: string) => void): CommandItem[] {
  return [
    { id: "a", group: "clients", label: "Clínica Boreal", keywords: "boreal", onSelect: () => onSelect("a") },
    { id: "b", group: "clients", label: "Barber Supply", onSelect: () => onSelect("b") },
    { id: "n", group: "actions", label: "Nuevo cliente", onSelect: () => onSelect("n") },
  ];
}

describe("CommandPalette", () => {
  it("is a combobox over a grouped listbox, keyboard-driven", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <CommandPalette
        open
        onOpenChange={onOpenChange}
        query=""
        onQueryChange={() => {}}
        items={items(onSelect)}
        groups={{ clients: "Clientes", actions: "Acciones" }}
        title="Buscar"
      />,
    );
    const input = screen.getByRole("combobox", { name: "Buscar" });
    input.focus(); // jsdom: Base UI's initialFocus runs after animation frames
    expect(screen.getByRole("listbox", { name: "Buscar" })).toBeInTheDocument();
    expect(screen.getAllByRole("group")).toHaveLength(2);
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(3);
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{ArrowDown}{ArrowDown}");
    expect(screen.getByRole("option", { name: /Nuevo cliente/ })).toHaveAttribute("aria-selected", "true");
    expect(input).toHaveAttribute("aria-activedescendant", screen.getByRole("option", { name: /Nuevo cliente/ }).id);
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith("n");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("renders loading, error and empty states", () => {
    const { rerender } = render(
      <CommandPalette open onOpenChange={() => {}} query="zzz" onQueryChange={() => {}} items={[]} title="Buscar" emptyMessage={(q) => `Nada para ${q}`} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Nada para zzz");
    rerender(<CommandPalette open onOpenChange={() => {}} query="zzz" onQueryChange={() => {}} items={[]} title="Buscar" loading />);
    expect(screen.getByRole("listbox")).toHaveAttribute("aria-busy", "true");
    rerender(<CommandPalette open onOpenChange={() => {}} query="zzz" onQueryChange={() => {}} items={[]} title="Buscar" error="Falló" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Falló");
  });

  it("filters case- and diacritic-insensitively", () => {
    const list = items(() => {});
    expect(filterCommandItems(list, "clinica").map((i) => i.id)).toEqual(["a"]);
    expect(filterCommandItems(list, "BOREAL").map((i) => i.id)).toEqual(["a"]);
    expect(filterCommandItems(list, "").length).toBe(3);
  });
});
