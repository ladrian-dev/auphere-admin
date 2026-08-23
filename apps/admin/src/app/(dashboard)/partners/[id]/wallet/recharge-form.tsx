"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { rechargePartnerWallet } from "../../actions";

export function RechargeWalletForm({ partnerId }: { partnerId: string }) {
  const router = useRouter();
  const [qty, setQty] = useState("1000");
  const [busy, setBusy] = useState(false);

  async function onRecharge() {
    const n = Number(qty);
    if (!Number.isInteger(n) || n <= 0) {
      toast.error("qty debe ser un entero mayor que 0");
      return;
    }
    if (
      !window.confirm(
        `¿Recargar ${n.toLocaleString("es-ES")} tokens purchased a este partner?`,
      )
    ) {
      return;
    }
    setBusy(true);
    try {
      const result = await rechargePartnerWallet(partnerId, n);
      if (!result.ok) {
        toast.error("No se pudo recargar", { description: result.error });
        return;
      }
      toast.success(
        `Recarga aplicada — purchased ${result.data.purchased_remaining.toLocaleString("es-ES")}`,
      );
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
      <label className="grid gap-1.5 text-sm">
        <span className="text-muted-foreground">Qty purchased</span>
        <Input
          type="number"
          min={1}
          step={1}
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          className="w-40"
        />
      </label>
      <Button type="button" onClick={onRecharge} disabled={busy}>
        {busy ? "Recargando…" : "Recargar"}
      </Button>
    </div>
  );
}
