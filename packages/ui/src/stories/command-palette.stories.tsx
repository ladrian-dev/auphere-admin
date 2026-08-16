import type { Meta, StoryObj } from "@storybook/react-vite";
import { Building2, KeyRound, Plus, Users } from "lucide-react";
import * as React from "react";

import { Button } from "../components/button";
import { CommandPalette, filterCommandItems, type CommandItem } from "../components/command-palette";
import { Kbd } from "../components/kbd";

const meta = { title: "Composed/CommandPalette" } satisfies Meta;
export default meta;
type Story = StoryObj;

const CLIENTS = ["Clínica Boreal", "Barber Supply", "Vedhome", "New Air Climatización"];

function Demo({ loading, error, empty }: { loading?: boolean; error?: boolean; empty?: boolean }) {
  const [open, setOpen] = React.useState(true);
  const [q, setQ] = React.useState("");
  const [last, setLast] = React.useState<string | null>(null);
  const items: CommandItem[] = empty
    ? []
    : [
        ...CLIENTS.map((c) => ({
          id: `c-${c}`,
          group: "clients",
          label: c,
          hint: c.toLowerCase().replace(/\s+/g, "-"),
          icon: <Building2 />,
          onSelect: () => setLast(c),
        })),
        { id: "new", group: "actions", label: "Nuevo cliente", icon: <Plus />, trailing: <Kbd>N</Kbd>, onSelect: () => setLast("new") },
        { id: "team", group: "actions", label: "Equipo", icon: <Users />, onSelect: () => setLast("team") },
        { id: "keys", group: "actions", label: "Claves de API", icon: <KeyRound />, onSelect: () => setLast("keys") },
      ];
  return (
    <div className="flex flex-col gap-4">
      <Button variant="outline" onClick={() => setOpen(true)}>
        Buscar… <Kbd>⌘K</Kbd>
      </Button>
      <p className="text-sm text-muted-foreground">Última selección: {last ?? "—"}</p>
      <CommandPalette
        open={open}
        onOpenChange={setOpen}
        query={q}
        onQueryChange={setQ}
        items={filterCommandItems(items, q)}
        groups={{ clients: "Clientes", actions: "Acciones" }}
        loading={loading}
        error={error ? "La búsqueda falló. Inténtalo de nuevo." : undefined}
        emptyMessage={(query) => `Sin resultados para «${query}»`}
        title="Buscar y navegar"
        placeholder="Cliente, agente, acción…"
        hint="↑↓ navegar · ↵ abrir · Esc cerrar"
      />
    </div>
  );
}

export const Ideal: Story = { render: () => <Demo /> };
export const Loading: Story = { render: () => <Demo loading /> };
export const Empty: Story = { render: () => <Demo empty /> };
export const Error: Story = { render: () => <Demo error /> };
