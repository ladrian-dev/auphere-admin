import type { Meta, StoryObj } from "@storybook/react-vite";
import * as React from "react";

import { Button } from "../components/button";
import { ConfirmDialog } from "../components/confirm-dialog";
import { Input } from "../components/input";
import { Label } from "../components/label";
import { PageHeader } from "../components/page-header";

const meta = { title: "Composed" } satisfies Meta;
export default meta;
type Story = StoryObj;

function ConfirmDemo(props: Partial<React.ComponentProps<typeof ConfirmDialog>>) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <Button variant="destructive" onClick={() => setOpen(true)}>
        Eliminar cliente
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Eliminar Clínica X"
        description="Se borrarán agente, canales y conversaciones. Esta acción no se puede deshacer."
        confirmLabel="Eliminar definitivamente"
        cancelLabel="Cancelar"
        destructive
        onConfirm={async () => {
          await new Promise((r) => setTimeout(r, 600));
          setOpen(false);
        }}
        {...props}
      />
    </>
  );
}

export const Confirm: Story = { render: () => <ConfirmDemo /> };
export const ConfirmTypeToConfirm: Story = { render: () => <ConfirmDemo typeToConfirm="Clínica X" /> };
export const ConfirmWithError: Story = {
  render: () => <ConfirmDemo error="El cliente tiene facturas y no se puede borrar (RGPD art. 17.3.b)." />,
};

export const Header: Story = {
  render: () => (
    <PageHeader
      eyebrow="Clientes"
      title="Clínica X"
      description="Medspa en Caracas. Agente v7 activo, WhatsApp conectado."
      actions={
        <>
          <Button variant="outline">Pausar</Button>
          <Button>Publicar cambios</Button>
        </>
      }
    />
  ),
};
export const HeaderLongTitle: Story = {
  name: "Header — German string",
  render: () => (
    <div className="w-[360px]">
      <PageHeader eyebrow="Kunden" title="Kundenverwaltungseinstellungen für Zahnarztpraxis Musterstadt GmbH" actions={<Button>Speichern</Button>} />
    </div>
  ),
};
export const FormControls: Story = {
  render: () => (
    <form className="grid max-w-sm gap-4">
      <div className="grid gap-2">
        <Label htmlFor="n">Nombre</Label>
        <Input id="n" placeholder="Clínica X" />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="e">Con error</Label>
        <Input id="e" aria-invalid defaultValue="mal" />
        <p className="text-xs text-status-danger">Este campo es obligatorio.</p>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="d">Deshabilitado</Label>
        <Input id="d" disabled defaultValue="—" />
      </div>
      <div className="flex gap-2">
        <Button type="button" variant="outline">
          Cancelar
        </Button>
        <Button type="submit">Guardar</Button>
      </div>
    </form>
  ),
};
