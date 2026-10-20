"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Button, ConfirmDialog, Input, Label } from "@nexus/ui";

import { formatCents } from "@/lib/format";
import { parseUsdToCents } from "@/lib/money";

import { rechargePartnerWallet } from "../../actions";

/**
 * Spec 033 (R1, R3): a top-up in dollars. The operator types the amount,
 * confirms seeing the amount and the resulting balance, and the request
 * carries a key generated once per attempt — a double click or a retry of
 * the same confirmation credits once.
 */
export function RechargeWalletForm({ partnerId, purchasedCents }: { partnerId: string; purchasedCents: number }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [confirming, setConfirming] = useState(false);
  // The amount being confirmed, frozen when the dialog opens: clearing the
  // field after a success must not change what the closing dialog says.
  const [pending, setPending] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const key = useRef<string | null>(null);
  const cents = parseUsdToCents(text);
  const invalid = text.trim() !== "" && cents === null;

  async function recharge() {
    const amount = pending;
    if (amount === null) return;
    key.current ??= crypto.randomUUID();
    setBusy(true);
    try {
      const result = await rechargePartnerWallet(partnerId, amount, key.current);
      if (!result.ok) {
        // Same key on the next try: if the first one did land, it is not
        // credited twice.
        toast.error("No se pudo recargar", { description: result.error });
        return;
      }
      toast.success(
        result.data.duplicate
          ? "Esa recarga ya estaba aplicada; no se ha cobrado dos veces"
          : `Recarga de ${formatCents(amount)} aplicada`,
        { description: `Saldo recargado: ${formatCents(result.data.purchased_cents)}` },
      );
      key.current = null;
      setText("");
      setConfirming(false);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      className="grid gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (cents === null) return;
        setPending(cents);
        setConfirming(true);
      }}
    >
      <Label htmlFor="topup-amount">Importe en US$</Label>
      {/* The button sits on the input's line, not on the hint's (owner, 2026-10-20). */}
      <div className="flex flex-wrap items-center gap-2">
        <Input
          id="topup-amount"
          inputMode="decimal"
          autoComplete="off"
          placeholder="50,00"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            key.current = null;
          }}
          aria-invalid={invalid || undefined}
          aria-describedby="topup-help"
          className="w-40"
        />
        <Button type="submit" disabled={cents === null || busy}>
          Recargar
        </Button>
      </div>
      <p id="topup-help" className={invalid ? "text-xs text-destructive" : "text-xs text-muted-foreground"}>
        {invalid ? "Escribe un importe entre 0,01 y 10 000 US$, con dos decimales como mucho." : "Entre 0,01 y 10 000 US$."}
      </p>
      <ConfirmDialog
        open={confirming}
        onOpenChange={(o) => !busy && setConfirming(o)}
        title={`¿Recargar ${formatCents(pending)}?`}
        description={`El saldo recargado pasará de ${formatCents(purchasedCents)} a ${formatCents(purchasedCents + (pending ?? 0))}. Queda en el libro y en la auditoría con tu nombre.`}
        confirmLabel={busy ? "Recargando…" : `Recargar ${formatCents(pending)}`}
        onConfirm={recharge}
      />
    </form>
  );
}
