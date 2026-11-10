"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@nexus/ui";

import { rotateWhatsAppPinAction } from "./setup-actions";

/** What the API's refusal codes mean, in the panel's words. */
export const PIN_ERROR: Record<string, string> = {
  coexistence_number: "Este número está en coexistencia: su PIN es el de la app WhatsApp Business.",
  no_credentials: "El canal no tiene credenciales de Meta. Vuelve a conectarlo primero.",
  meta_refused_the_pin: "Meta no aceptó el PIN nuevo. El anterior sigue vigente.",
  channel_not_found: "El canal ya no existe.",
};

/**
 * Spec 050 (3.2): a new two-step PIN for a Cloud API number. Auphere keeps
 * it encrypted (Meta never returns it, and re-registering the number needs
 * it); nobody sees it, so the dialog only confirms that it changed.
 */
export function WhatsAppPinDialog({ tenantId, channelId }: { tenantId: string; channelId: string }) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)} disabled={pending}>
        Rotar PIN
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rotar el PIN de verificación en dos pasos</DialogTitle>
            <DialogDescription>
              Auphere genera un PIN nuevo, se lo da a Meta y lo guarda cifrado. No se muestra: solo hace falta si el
              número se vuelve a registrar, y eso lo hace Auphere. Queda en la auditoría.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setOpen(false)} disabled={pending}>
              Cancelar
            </Button>
            <Button
              size="sm"
              disabled={pending}
              onClick={() =>
                start(async () => {
                  const res = await rotateWhatsAppPinAction(tenantId, channelId);
                  if (!res.ok) {
                    toast.error(PIN_ERROR[res.error] ?? `No se pudo rotar el PIN: ${res.error}`);
                    return;
                  }
                  toast.success("PIN rotado y guardado.");
                  setOpen(false);
                })
              }
            >
              {pending ? "Rotando…" : "Rotar PIN"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
