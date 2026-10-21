"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { ConfirmDialog, StatusBadge, Switch } from "@nexus/ui";
import type { UnlimitedConsumption } from "@/lib/backend";

import { setUnlimitedConsumptionAction } from "../../actions";

function usd(cents: number): string {
  return (cents / 100).toLocaleString("en-US", { style: "currency", currency: "USD" });
}

/**
 * Consumo ilimitado (owner, 2026-10-20). Encendido, el agente del cliente no
 * se para por falta de saldo ni de tope y su consumo no se descuenta del
 * partner: lo asume Auphere. Solo se cambia aquí; el partner lo ve en su
 * consola sin poder tocarlo.
 */
export function UnlimitedCard({
  tenantId,
  tenantName,
  state,
}: {
  tenantId: string;
  tenantName: string;
  state: UnlimitedConsumption;
}) {
  const router = useRouter();
  const [confirm, setConfirm] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const on = state.unlimited;
  const partner = state.partner_name ?? "su partner";

  async function apply(next: boolean) {
    setError(null);
    const result = await setUnlimitedConsumptionAction(tenantId, next);
    if (!result.ok) {
      setError(result.error);
      toast.error("No se pudo cambiar", { description: result.error });
      return;
    }
    toast.success(next ? "Consumo ilimitado activado" : "Consumo ilimitado desactivado");
    setConfirm(null);
    router.refresh();
  }

  if (!state.partner_id) {
    return (
      <p className="text-sm text-muted-foreground">
        Cliente directo de Auphere: no gasta saldo de ningún partner, así que nunca se para por
        saldo.
      </p>
    );
  }

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="grid gap-1">
          <span id="unlimited-label" className="text-sm font-medium">
            Consumo ilimitado
          </span>
          <span className="text-sm text-muted-foreground">
            {on
              ? `El agente responde siempre y su consumo lo asume Auphere, no ${partner}.`
              : `Gasta del saldo de ${partner} y se para si se queda sin saldo o sin tope.`}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {on ? <StatusBadge tone="info">Lo asume Auphere</StatusBadge> : null}
          <Switch
            aria-label="Consumo ilimitado"
            checked={on}
            onCheckedChange={(v) => setConfirm(Boolean(v))}
          />
        </div>
      </div>
      {on ? (
        <p className="text-sm text-muted-foreground tabular-nums">
          Este mes Auphere ha asumido{" "}
          {state.absorbed_month_cents == null ? "— (no se pudo leer)" : usd(state.absorbed_month_cents)}{" "}
          del consumo de {tenantName}.
        </p>
      ) : null}

      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(open) => {
          if (!open) {
            setConfirm(null);
            setError(null);
          }
        }}
        title={confirm ? "¿Activar el consumo ilimitado?" : "¿Desactivar el consumo ilimitado?"}
        description={
          confirm
            ? `El agente de ${tenantName} no se parará por saldo ni por tope, y su consumo lo pagará Auphere, no ${partner}. ${partner} lo verá en su consola.`
            : `${tenantName} volverá a gastar del saldo de ${partner} y su agente se parará si se queda sin saldo o sin tope.`
        }
        confirmLabel={confirm ? "Activar" : "Desactivar"}
        destructive={confirm === false}
        onConfirm={() => apply(Boolean(confirm))}
        error={error ?? undefined}
      />
    </div>
  );
}
