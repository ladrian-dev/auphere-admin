"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Checkbox } from "@/components/ui/checkbox";
import type { PartnerModelItemOut } from "@/lib/backend";

import { setPartnerModels } from "../../actions";

export function AllowlistForm({
  partnerId,
  items,
}: {
  partnerId: string;
  items: PartnerModelItemOut[];
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);

  async function onToggle(modelId: string, allowed: boolean) {
    const next = items
      .filter((row) => (row.model_id === modelId ? allowed : row.allowed))
      .map((row) => row.model_id);
    setBusy(modelId);
    try {
      const result = await setPartnerModels(partnerId, next);
      if (!result.ok) {
        toast.error("No se pudo actualizar la allowlist", {
          description: result.error,
        });
        return;
      }
      toast.success(allowed ? `${modelId} permitido` : `${modelId} oculto`);
      router.refresh();
    } finally {
      setBusy(null);
    }
  }

  return (
    <ul className="grid gap-3">
      {items.map((row) => (
        <li key={row.model_id} className="flex items-center gap-3">
          <Checkbox
            checked={row.allowed}
            disabled={busy !== null}
            onCheckedChange={(checked) =>
              onToggle(row.model_id, checked === true)
            }
            aria-label={row.display_name}
          />
          <div>
            <div className="text-sm font-medium">{row.display_name}</div>
            <div className="font-mono text-xs text-muted-foreground">
              {row.model_id}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
