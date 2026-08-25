"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

import { blockPartnerLlm } from "../../actions";

export function BlockLlmForm({
  partnerId,
  blocked,
}: {
  partnerId: string;
  blocked: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function onToggle() {
    const next = !blocked;
    const label = next ? "bloquear" : "activar";
    if (
      !window.confirm(
        next
          ? "¿Bloquear la virtual key LiteLLM de este partner? El hop queda fail-closed."
          : "¿Activar de nuevo la virtual key LiteLLM de este partner?",
      )
    ) {
      return;
    }
    setBusy(true);
    try {
      const result = await blockPartnerLlm(partnerId, next);
      if (!result.ok) {
        toast.error(`No se pudo ${label}`, { description: result.error });
        return;
      }
      toast.success(next ? "Virtual key bloqueada" : "Virtual key activa");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-sm">
        Estado:{" "}
        <span className="font-medium">
          {blocked ? "bloqueada" : "activa"}
        </span>
      </p>
      <Button
        type="button"
        variant={blocked ? "default" : "destructive"}
        onClick={onToggle}
        disabled={busy}
      >
        {busy ? "…" : blocked ? "Activar" : "Bloquear"}
      </Button>
    </div>
  );
}
