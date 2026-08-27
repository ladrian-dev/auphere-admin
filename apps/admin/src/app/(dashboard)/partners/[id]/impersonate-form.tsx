"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

import { startImpersonationAction } from "../actions";

export function ImpersonateForm({ partnerId }: { partnerId: string }) {
  const router = useRouter();
  const [reason, setReason] = useState("");
  const [ttl, setTtl] = useState("900");
  const [busy, setBusy] = useState(false);

  async function onStart() {
    const ttlSeconds = Number(ttl);
    if (reason.trim().length < 8) {
      toast.error("El motivo debe tener al menos 8 caracteres");
      return;
    }
    if (!Number.isInteger(ttlSeconds) || ttlSeconds < 60 || ttlSeconds > 3600) {
      toast.error("TTL entre 60 y 3600 segundos");
      return;
    }
    setBusy(true);
    try {
      const result = await startImpersonationAction(partnerId, reason, ttlSeconds);
      if (!result.ok) {
        toast.error("No se pudo abrir la impersonación", {
          description: result.error,
        });
        return;
      }
      toast.success("Impersonación activa — sigues siendo admin");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-3 md:grid-cols-[1fr_8rem_auto] md:items-end">
      <label className="grid gap-1.5 text-sm">
        <span className="text-muted-foreground">Motivo (mín. 8)</span>
        <Textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Ticket AU-… / revisión de wallet"
          rows={2}
        />
      </label>
      <label className="grid gap-1.5 text-sm">
        <span className="text-muted-foreground">TTL (s)</span>
        <Input
          type="number"
          min={60}
          max={3600}
          step={1}
          value={ttl}
          onChange={(e) => setTtl(e.target.value)}
        />
      </label>
      <Button type="button" onClick={onStart} disabled={busy}>
        {busy ? "Abriendo…" : "Impersonar"}
      </Button>
    </div>
  );
}
