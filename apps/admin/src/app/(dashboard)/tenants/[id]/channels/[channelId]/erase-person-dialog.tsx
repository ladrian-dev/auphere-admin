"use client";

import { Eraser } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Input,
  Label,
} from "@nexus/ui";

import { erasePersonAction } from "../actions";

/**
 * Spec 049 (5.5): borrar lo que una persona envió por un canal de Instagram o
 * Messenger. El contenido de sus mensajes se vacía; no se puede deshacer, y la
 * Auditoría guarda quién lo pidió.
 */
export function ErasePersonDialog({ tenantId, channelId }: { tenantId: string; channelId: string }) {
  const [open, setOpen] = React.useState(false);
  const [identifier, setIdentifier] = React.useState("");
  const [requestedBy, setRequestedBy] = React.useState("");
  const [pending, start] = React.useTransition();
  const ready = identifier.trim().length > 0 && requestedBy.trim().length >= 3;

  function erase() {
    start(async () => {
      const res = await erasePersonAction(tenantId, channelId, {
        identifier: identifier.trim(),
        requested_by: requestedBy.trim(),
      });
      if (!res.ok) {
        toast.error(res.error === "person not found" ? "No hay nadie con ese identificador en este canal." : `No se pudo borrar: ${res.error}`);
        return;
      }
      const n = res.data.messages_emptied;
      toast.success(`Datos borrados: ${n === 1 ? "1 mensaje vaciado" : `${n} mensajes vaciados`}.`);
      setOpen(false);
      setIdentifier("");
      setRequestedBy("");
    });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" size="sm" />}>
        <Eraser aria-hidden="true" />
        Borrar datos de una persona
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Borrar los datos de una persona</DialogTitle>
          <DialogDescription>
            Vacía el contenido de lo que envió por este canal. No se puede deshacer. Queda en la Auditoría.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-2">
            <Label htmlFor="erase-identifier">Identificador de la persona</Label>
            <Input id="erase-identifier" value={identifier} maxLength={128} onChange={(e) => setIdentifier(e.target.value)} />
            <p className="text-xs text-muted-foreground">El que muestra la ficha del contacto en la bandeja.</p>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="erase-requested-by">Quién lo pidió</Label>
            <Input id="erase-requested-by" value={requestedBy} maxLength={255} onChange={(e) => setRequestedBy(e.target.value)} />
            <p className="text-xs text-muted-foreground">Su correo o el número de la solicitud.</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => setOpen(false)} disabled={pending}>
            Cancelar
          </Button>
          <Button variant="destructive" size="sm" disabled={pending || !ready} onClick={erase}>
            {pending ? "Borrando…" : "Borrar los datos"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
