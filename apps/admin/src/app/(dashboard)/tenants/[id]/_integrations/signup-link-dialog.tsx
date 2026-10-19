"use client";

import { Copy, Link2, Mail, MessageCircle } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  NativeSelect,
} from "@nexus/ui";

import { fullDateTime } from "@/lib/format";

import { createSignupLinkAction } from "../channels/actions";

const MODE_LABEL = {
  coexistence: "Coexistencia (sigue usando la app WhatsApp Business)",
  cloud_api: "Cloud API (número nuevo o migrado)",
} as const;

/**
 * Spec 040: a link the business owner opens on their own phone or computer —
 * already logged in to Meta — to run WhatsApp's signup themselves. Their Meta
 * details never pass through the operator's or the partner's device.
 */
export function SignupLinkDialog({ tenantId, businessName }: { tenantId: string; businessName: string }) {
  const [open, setOpen] = React.useState(false);
  const [mode, setMode] = React.useState<"coexistence" | "cloud_api">("coexistence");
  const [pending, start] = React.useTransition();
  const [link, setLink] = React.useState<{ url: string; expires_at: string } | null>(null);
  const message = link
    ? `Hola. Para conectar el WhatsApp de ${businessName} con su agente, abre este enlace desde tu teléfono y sigue los pasos de Meta: ${link.url}`
    : "";

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <Link2 aria-hidden="true" />
        Crear enlace
      </Button>
      <Dialog
        open={open}
        onOpenChange={(o) => {
          setOpen(o);
          if (!o) setLink(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Que lo conecte el dueño desde su teléfono</DialogTitle>
            <DialogDescription>
              El dueño abre el enlace donde ya tiene abierta su cuenta de Meta y hace él mismo los pasos. El enlace
              sirve una vez y caduca en 7 días.
            </DialogDescription>
          </DialogHeader>
          {link ? (
            <div className="flex flex-col gap-3">
              <div className="flex gap-2">
                <Input readOnly value={link.url} aria-label="Enlace" onFocus={(e) => e.currentTarget.select()} />
                <Button
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(link.url);
                      toast.success("Enlace copiado.");
                    } catch {
                      toast.error("No se pudo copiar. Selecciónalo y cópialo a mano.");
                    }
                  }}
                >
                  <Copy aria-hidden="true" />
                  Copiar
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  nativeButton={false}
                  render={<a href={`https://wa.me/?text=${encodeURIComponent(message)}`} target="_blank" rel="noreferrer" />}
                >
                  <MessageCircle aria-hidden="true" />
                  Enviar por WhatsApp
                </Button>
                <Button
                  variant="outline"
                  nativeButton={false}
                  render={
                    <a
                      href={`mailto:?subject=${encodeURIComponent(`Conecta el WhatsApp de ${businessName}`)}&body=${encodeURIComponent(message)}`}
                    />
                  }
                >
                  <Mail aria-hidden="true" />
                  Enviar por correo
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">Caduca el {fullDateTime(link.expires_at)}.</p>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="link-mode">Modo de conexión</Label>
                <NativeSelect id="link-mode" value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}>
                  <option value="coexistence">{MODE_LABEL.coexistence}</option>
                  <option value="cloud_api">{MODE_LABEL.cloud_api}</option>
                </NativeSelect>
              </div>
              <div>
                <Button
                  disabled={pending}
                  onClick={() =>
                    start(async () => {
                      const r = await createSignupLinkAction(tenantId, mode);
                      if (r.ok) setLink(r.data);
                      else toast.error("No se pudo crear el enlace", { description: r.error });
                    })
                  }
                >
                  {pending ? "Creando…" : "Crear enlace"}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
