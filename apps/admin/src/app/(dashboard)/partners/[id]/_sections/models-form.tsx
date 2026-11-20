"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Checkbox } from "@nexus/ui";
import type { PartnerModelItemOut } from "@/lib/backend";
import { FOCUS_RING } from "@/lib/focus-ring";

import { setPartnerModels } from "../../actions";

/**
 * The partner's list of models. Spec 065: every model that can be offered,
 * also the ones not yet enabled to answer in this environment, which say so —
 * the partner does not see them until they are. `enabled: null` is a read that
 * failed: nothing is claimed about it.
 */
export function AllowlistForm({
  partnerId,
  items,
  enabled = null,
}: {
  partnerId: string;
  items: PartnerModelItemOut[];
  /** The models enabled to answer here; `null` when it could not be read. */
  enabled?: string[] | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const answers = enabled === null ? null : new Set(enabled);

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

  if (!items.length) {
    return (
      <p className="text-sm text-pretty text-muted-foreground">
        No hay modelos que se puedan ofrecer a los partners en este entorno.
      </p>
    );
  }

  return (
    <ul className="grid gap-3">
      {items.map((row) => (
        <li key={row.model_id} className="flex items-start gap-3">
          <Checkbox
            checked={row.allowed}
            disabled={busy !== null}
            onCheckedChange={(checked) =>
              onToggle(row.model_id, checked === true)
            }
            aria-label={row.display_name}
            className={FOCUS_RING}
          />
          <div className="flex min-w-0 flex-col gap-1">
            <span className="text-sm font-medium text-pretty break-words">{row.display_name}</span>
            <span className="font-mono text-xs break-all text-muted-foreground">
              {row.model_id}
            </span>
            {answers && !answers.has(row.model_id) ? (
              <span className="text-xs text-pretty text-muted-foreground">
                Sin habilitar para responder en este entorno: el partner no lo ve hasta que se habilite.
              </span>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  );
}
