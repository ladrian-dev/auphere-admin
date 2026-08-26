"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { TicketStatus } from "@/lib/backend";

import { patchTicketStatus } from "../../partners/actions";

const OPTIONS: { value: TicketStatus; label: string }[] = [
  { value: "open", label: "Abierto" },
  { value: "pending", label: "Pendiente" },
  { value: "closed", label: "Cerrado" },
];

export function TicketStatusForm({
  ticketId,
  status,
}: {
  ticketId: string;
  status: TicketStatus;
}) {
  const router = useRouter();
  const [next, setNext] = useState<TicketStatus>(status);
  const [busy, setBusy] = useState(false);

  async function onSave() {
    if (next === status) return;
    setBusy(true);
    try {
      const result = await patchTicketStatus(ticketId, next);
      if (!result.ok) {
        toast.error("No se pudo cambiar el estado", { description: result.error });
        return;
      }
      toast.success(`Estado: ${next}`);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
      <label className="grid gap-1.5 text-sm">
        <span className="text-muted-foreground">Estado</span>
        <select
          value={next}
          onChange={(e) => setNext(e.target.value as TicketStatus)}
          className="h-9 rounded-md border border-border bg-background px-3 text-sm"
        >
          {OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>
      <Button type="button" onClick={onSave} disabled={busy || next === status}>
        {busy ? "Guardando…" : "Actualizar estado"}
      </Button>
    </div>
  );
}
