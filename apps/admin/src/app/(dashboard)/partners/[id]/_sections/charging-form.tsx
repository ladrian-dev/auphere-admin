"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Button, Input, Label } from "@nexus/ui";

import { parseUsdToCents } from "@/lib/money";

import { setPartnerChargingAction } from "../../actions";

type Mode = "manual" | "auto_recharge" | "postpaid";

const OPTIONS: Array<{ mode: Mode; label: string; help: string }> = [
  { mode: "manual", label: "Manual", help: "El partner compra saldo cuando lo necesita." },
  {
    mode: "auto_recharge",
    label: "Recarga automática",
    help: "Cuando el saldo baja del mínimo, se cobra la recarga a su tarjeta y se abona.",
  },
  {
    mode: "postpaid",
    label: "Pospago",
    help: "Consume hasta su línea de crédito y el día 1 se cobra lo que debe a su tarjeta.",
  },
];

/**
 * Spec 041: the operator sets how the partner is charged — the same three
 * modes and the same rules as the partner's console. Anything automatic needs
 * the partner's card; postpaid also needs the credit line.
 */
export function ChargingForm({
  partnerId,
  current,
  hasCard,
  hasLine,
}: {
  partnerId: string;
  current: { mode: Mode; threshold: number | null; amount: number | null };
  hasCard: boolean;
  hasLine: boolean;
}) {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>(current.mode);
  const [threshold, setThreshold] = useState(String((current.threshold ?? 1000) / 100));
  const [amount, setAmount] = useState(String((current.amount ?? 2000) / 100));
  const [pending, start] = useTransition();
  const thresholdCents = parseUsdToCents(threshold);
  const amountCents = parseUsdToCents(amount);
  const dirty =
    mode !== current.mode ||
    (mode === "auto_recharge" && (thresholdCents !== current.threshold || amountCents !== current.amount));

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        start(async () => {
          const r = await setPartnerChargingAction(partnerId, {
            mode,
            recharge_threshold_cents: mode === "auto_recharge" ? thresholdCents : null,
            recharge_amount_cents: mode === "auto_recharge" ? amountCents : null,
          });
          if (r.ok) {
            toast.success("Cobro guardado.");
            router.refresh();
          } else {
            toast.error("No se pudo guardar el cobro", { description: r.error });
          }
        });
      }}
    >
      <fieldset className="flex flex-col gap-2" disabled={pending}>
        <legend className="mb-1 text-sm font-medium">Cómo se le cobra</legend>
        {OPTIONS.map((o) => {
          const locked = (o.mode !== "manual" && !hasCard) || (o.mode === "postpaid" && !hasLine);
          return (
            <label key={o.mode} className="flex items-start gap-3 text-sm">
              <input
                type="radio"
                name={`charging-${partnerId}`}
                value={o.mode}
                checked={mode === o.mode}
                disabled={locked}
                onChange={() => setMode(o.mode)}
                className="mt-1"
              />
              <span className={locked ? "text-muted-foreground" : undefined}>
                <span className="font-medium">{o.label}</span>
                <span className="block text-xs text-muted-foreground">
                  {o.help}
                  {locked
                    ? o.mode === "postpaid" && hasCard
                      ? " Necesita una línea de crédito."
                      : " Necesita que el partner guarde su tarjeta."
                    : ""}
                </span>
              </span>
            </label>
          );
        })}
      </fieldset>
      {mode === "auto_recharge" ? (
        <div className="grid max-w-md gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor="op-threshold">Si el saldo baja de (US$)</Label>
            <Input id="op-threshold" inputMode="decimal" value={threshold} onChange={(e) => setThreshold(e.target.value)} />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="op-amount">Recargar (US$, mínimo 5)</Label>
            <Input id="op-amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </div>
        </div>
      ) : null}
      <div>
        <Button type="submit" variant="outline" disabled={!dirty || pending}>
          {pending ? "Guardando…" : "Guardar cobro"}
        </Button>
      </div>
    </form>
  );
}
