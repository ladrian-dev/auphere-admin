"use client";

/**
 * TikTok Business Messaging connect dialog.
 *
 * Deliberately not a wizard. TikTok authorisation is a plain redirect — the
 * owner leaves for TikTok, authorises the Auphere app over their Business
 * Account, and TikTok posts the code straight to the API callback, which
 * bounces the browser back here with ``?tiktok=<status>``. So the panel's
 * whole job is: explain the two constraints that surprise people, then hand
 * over the URL.
 *
 * The two constraints are shown *before* connecting rather than as an
 * afterthought, because both change what the channel is worth:
 *
 *  - The business can never message first. There is no template mechanism
 *    and no way to address someone who has not written. Anyone expecting
 *    the WhatsApp playbook to transfer needs to know that up front.
 *  - Accounts registered in the EEA, Switzerland or the UK cannot use
 *    Business Messaging at all. The backend refuses those during
 *    authorisation, but saying so here saves a confusing round trip.
 */

import { ArrowUpRight, Clock, MessageCircleOff } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

import { tiktokAuthorizeUrlAction } from "./setup-actions";

interface Props {
  tenantId: string;
  alreadyConnected?: boolean;
}

export function TikTokConnectDialog({ tenantId, alreadyConnected = false }: Props) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  async function startAuthorization() {
    setBusy(true);
    try {
      const result = await tiktokAuthorizeUrlAction(tenantId);
      if (!result.ok) {
        toast.error("No se pudo iniciar la autorización", {
          description: result.error,
        });
        return;
      }
      // Same tab: TikTok's consent screen blocks inside popups on several
      // browsers, and the callback redirects back into the panel anyway.
      window.location.href = result.data.authorize_url;
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button size="sm" variant={alreadyConnected ? "outline" : "default"}>
            {alreadyConnected ? "Reconectar" : "Conectar"}
          </Button>
        }
      />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Conectar TikTok</DialogTitle>
          <DialogDescription>
            El dueño del negocio autoriza la app de Auphere sobre su cuenta
            TikTok Business. Se abrirá TikTok en esta pestaña y volverás acá al
            terminar.
          </DialogDescription>
        </DialogHeader>

        <ul className="grid gap-3 text-sm">
          <li className="flex gap-3">
            <MessageCircleOff
              className="mt-0.5 size-4 shrink-0 text-muted-foreground"
              aria-hidden="true"
            />
            <span>
              <strong className="font-medium">El negocio no puede escribir primero.</strong>{" "}
              TikTok solo permite responder a quien escribió. No hay plantillas
              ni difusiones en este canal.
            </span>
          </li>
          <li className="flex gap-3">
            <Clock
              className="mt-0.5 size-4 shrink-0 text-muted-foreground"
              aria-hidden="true"
            />
            <span>
              <strong className="font-medium">Ventana de 48 horas</strong> desde
              el último mensaje del cliente. Pasada, la conversación se cierra
              hasta que el cliente vuelva a escribir.
            </span>
          </li>
        </ul>

        <p className="text-sm text-muted-foreground">
          Las cuentas registradas en el EEE, Suiza o Reino Unido no pueden usar
          Business Messaging: TikTok no entrega sus mensajes. La autorización se
          rechaza con ese motivo si es el caso.
        </p>

        <DialogFooter>
          <Button
            type="button"
            variant="ghost"
            onClick={() => setOpen(false)}
            disabled={busy}
          >
            Cancelar
          </Button>
          <Button type="button" onClick={startAuthorization} disabled={busy}>
            {busy ? "Abriendo TikTok…" : "Ir a TikTok"}
            <ArrowUpRight className="size-4" aria-hidden="true" />
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
