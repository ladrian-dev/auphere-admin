"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

import { revokeImpersonationAction } from "../actions";

export function ImpersonateBannerView({
  partnerName,
  sessionId,
  reason,
  expiresAt,
}: {
  partnerName: string;
  sessionId: string;
  reason: string;
  expiresAt: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function onRevoke() {
    setBusy(true);
    try {
      const result = await revokeImpersonationAction(sessionId);
      if (!result.ok) {
        toast.error("No se pudo cerrar la impersonación", {
          description: result.error,
        });
        return;
      }
      toast.success("Impersonación cerrada");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Alert>
      <AlertTitle>Impersonación activa — no eres el partner</AlertTitle>
      <AlertDescription>
        <p>
          Viendo {partnerName} como overlay de admin. Recarga de wallet y
          bloqueo LLM siguen actuando como admin. Motivo: {reason}. Caduca{" "}
          {new Date(expiresAt).toLocaleString("es-ES")}.
        </p>
        <div className="mt-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onRevoke}
            disabled={busy}
          >
            {busy ? "Cerrando…" : "Cerrar impersonación"}
          </Button>
        </div>
      </AlertDescription>
    </Alert>
  );
}
