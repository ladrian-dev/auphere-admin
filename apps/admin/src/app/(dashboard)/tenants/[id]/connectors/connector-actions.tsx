"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import {
  disconnectAction,
  initiateConsentAction,
  reissueConsentAction,
  syncAction,
} from "./actions";

type CommonProps = {
  tenantId: string;
  slug: string;
  displayName: string;
};

export function InitiateConsentButton({
  tenantId,
  slug,
  displayName,
  ownerPhone,
}: CommonProps & { ownerPhone: string | null }) {
  const [pending, start] = useTransition();
  const [open, setOpen] = useState(false);
  const [link, setLink] = useState<string | null>(null);
  const sentByWhatsApp = ownerPhone !== null;
  return (
    <>
      <Button
        size="sm"
        disabled={pending}
        onClick={() => {
          start(async () => {
            const res = await initiateConsentAction(tenantId, slug);
            if (!res.ok) {
              toast.error(`No se pudo iniciar consent: ${res.error}`);
              return;
            }
            setLink(res.data.signed_consent_url);
            setOpen(true);
            if (sentByWhatsApp) {
              toast.success("Link enviado al owner por WhatsApp");
            } else {
              toast.info("Link generado", {
                description: "Copialo del dialog y compartilo con el owner.",
              });
            }
          });
        }}
      >
        {pending ? "Iniciando…" : "Conectar"}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Link de consent — {displayName}</DialogTitle>
            <DialogDescription>
              {sentByWhatsApp
                ? "El link ya se envió al WhatsApp del owner. Si necesitás compartirlo por otro canal (email, copia manual, fallo de WhatsApp), usá el link de abajo. Expira en 7 días."
                : "Este tenant no tiene WhatsApp del owner configurado, así que el link no se envió automáticamente. Copialo y compartilo por el canal que prefieras. Expira en 7 días."}
            </DialogDescription>
          </DialogHeader>
          <textarea
            readOnly
            className="w-full font-mono text-[11px] p-2 border border-border rounded-sm bg-muted min-h-[120px]"
            value={link ?? ""}
            onFocus={(e) => e.currentTarget.select()}
          />
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                if (link) navigator.clipboard.writeText(link);
                toast.success("Link copiado");
              }}
            >
              Copiar link
            </Button>
            <Button size="sm" onClick={() => setOpen(false)}>
              Cerrar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function DisconnectButton({ tenantId, slug, displayName }: CommonProps) {
  const [pending, start] = useTransition();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        disabled={pending}
      >
        Desconectar
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Desconectar {displayName}</DialogTitle>
            <DialogDescription>
              El agente dejará de usar las tools de este connector en el
              próximo turn. Los tokens upstream se revocan (si aplica).
              Podés reconectar después sin pérdida de configuración.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setOpen(false)}
              disabled={pending}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              size="sm"
              disabled={pending}
              onClick={() => {
                start(async () => {
                  const res = await disconnectAction(tenantId, slug);
                  if (!res.ok) {
                    toast.error(`Error: ${res.error}`);
                    return;
                  }
                  toast.success(`${displayName} desconectado`);
                  setOpen(false);
                });
              }}
            >
              {pending ? "Desconectando…" : "Desconectar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function SyncButton({ tenantId, slug, displayName }: CommonProps) {
  const [pending, start] = useTransition();
  return (
    <Button
      variant="outline"
      size="sm"
      disabled={pending}
      onClick={() => {
        start(async () => {
          const res = await syncAction(tenantId, slug);
          if (!res.ok) {
            toast.error(`Sync falló: ${res.error}`);
            return;
          }
          toast.success(
            `Sync ${displayName}: +${res.data.added} nuevas · ${res.data.deprecated} deprecadas · ${res.data.unchanged} sin cambios`,
          );
        });
      }}
    >
      {pending ? "Sincronizando…" : "Sincronizar tools"}
    </Button>
  );
}

export function ReissueConsentButton({
  tenantId,
  slug,
  displayName,
}: CommonProps) {
  const [pending, start] = useTransition();
  return (
    <Button
      variant="outline"
      size="sm"
      disabled={pending}
      onClick={() => {
        start(async () => {
          const res = await reissueConsentAction(tenantId, slug);
          if (!res.ok) {
            toast.error(`No se pudo reenviar: ${res.error}`);
            return;
          }
          toast.success(`Link reenviado para ${displayName}`);
        });
      }}
    >
      {pending ? "Reenviando…" : "Reenviar consent"}
    </Button>
  );
}
