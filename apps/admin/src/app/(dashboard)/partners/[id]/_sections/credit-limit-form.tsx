"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Button, ConfirmDialog, Input, Label } from "@nexus/ui";

import { formatCents } from "@/lib/format";
import { parseUsdToCents } from "@/lib/money";

import { setPartnerCreditLimitAction } from "../../actions";

/**
 * Spec 041: grant, change or withdraw the postpaid line. It is credit Auphere
 * extends, so it asks for confirmation and says the amount back. A line below
 * what the partner already owes is refused by the API.
 */
export function CreditLimitForm({
  partnerId,
  currentCents,
  owedCents,
}: {
  partnerId: string;
  currentCents: number;
  owedCents: number;
}) {
  const router = useRouter();
  const [raw, setRaw] = useState(String(currentCents / 100));
  const [confirm, setConfirm] = useState(false);
  const [pending, start] = useTransition();
  const cents = parseUsdToCents(raw);
  const valid = cents !== null && cents >= 0;

  return (
    <form
      className="flex max-w-md flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid && cents !== currentCents) setConfirm(true);
      }}
    >
      <Label htmlFor="credit-line">Línea de crédito del pospago (US$)</Label>
      <div className="flex gap-2">
        <Input id="credit-line" inputMode="decimal" value={raw} onChange={(e) => setRaw(e.target.value)} />
        <Button type="submit" variant="outline" disabled={!valid || cents === currentCents || pending}>
          Guardar
        </Button>
      </div>
      <p className="text-xs text-pretty text-muted-foreground">
        0 deja al partner en prepago. Con línea, el partner puede elegir pospago en su consola: consume hasta ese límite
        y el día 1 se cobra lo que debe a su tarjeta.
      </p>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={cents === 0 ? "Quitar la línea de crédito" : `Línea de crédito de ${formatCents(cents ?? 0)}`}
        description={
          cents === 0
            ? "El partner vuelve a prepago. Si estaba en pospago, pasa a compra manual."
            : `El partner podrá consumir hasta ${formatCents(cents ?? 0)} sin saldo y pagarlo el día 1. Debe ahora ${formatCents(owedCents)}.`
        }
        confirmLabel="Confirmar"
        cancelLabel="Cancelar"
        onConfirm={() =>
          new Promise<void>((resolve) =>
            start(async () => {
              const r = await setPartnerCreditLimitAction(partnerId, cents ?? 0);
              if (r.ok) {
                toast.success("Línea de crédito guardada.");
                setConfirm(false);
                router.refresh();
              } else {
                toast.error("No se pudo guardar", { description: r.error });
              }
              resolve();
            }),
          )
        }
      />
    </form>
  );
}
