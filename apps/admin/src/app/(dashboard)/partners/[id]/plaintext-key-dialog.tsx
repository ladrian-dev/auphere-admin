"use client";

import { useState } from "react";
import { Check, Copy, TriangleAlert } from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { PartnerApiKeyCreatedOut } from "@/lib/backend";

/**
 * One-time reveal of the key plaintext (creación y rotación).
 *
 * CRÍTICO: este dialog NO se puede cerrar por accidente. El backend solo
 * entrega el plaintext una vez; si el operador lo pierde, toca rotar de
 * nuevo. Por eso:
 *
 * - ``onOpenChange`` ignora todo intento de cierre (click fuera, Escape).
 * - ``showCloseButton={false}`` — sin la X de la esquina.
 * - La única salida es el botón explícito "Ya guardé la clave".
 */
export function PlaintextKeyDialog({
  createdKey,
  onClose,
}: {
  createdKey: PartnerApiKeyCreatedOut | null;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    if (!createdKey) return;
    try {
      await navigator.clipboard.writeText(createdKey.plaintext);
      setCopied(true);
      toast.success("Clave copiada al portapapeles");
    } catch {
      toast.error("No se pudo copiar — selecciona el texto manualmente");
    }
  }

  function close() {
    setCopied(false);
    onClose();
  }

  return (
    <Dialog
      open={createdKey !== null}
      // Deliberately swallow every dismiss request (backdrop, Escape):
      // closing is ONLY possible via the explicit button below.
      onOpenChange={() => {}}
    >
      <DialogContent showCloseButton={false} className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>API key generada</DialogTitle>
          <DialogDescription>
            Entrégasela al partner por un canal seguro. El panel no la
            almacena.
          </DialogDescription>
        </DialogHeader>

        <Alert variant="destructive">
          <TriangleAlert aria-hidden="true" />
          <AlertTitle>No volverás a verla</AlertTitle>
          <AlertDescription>
            Esta es la única vez que la clave se muestra en texto plano.
            Cópiala antes de cerrar; si se pierde, habrá que rotarla.
          </AlertDescription>
        </Alert>

        {createdKey ? (
          <div className="grid gap-2">
            <div className="flex items-start gap-2">
              <code className="flex-1 min-w-0 rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-xs break-all select-all">
                {createdKey.plaintext}
              </code>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={copy}
                aria-label="Copiar clave al portapapeles"
              >
                {copied ? (
                  <Check className="size-4" aria-hidden="true" />
                ) : (
                  <Copy className="size-4" aria-hidden="true" />
                )}
                {copied ? "Copiada" : "Copiar"}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Prefijo visible en el panel:{" "}
              <code className="font-mono">{createdKey.prefix_snippet}</code> ·
              tipo <span className="font-mono">{createdKey.type}</span>
            </p>
          </div>
        ) : null}

        <DialogFooter>
          <Button type="button" onClick={close}>
            Ya guardé la clave
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
