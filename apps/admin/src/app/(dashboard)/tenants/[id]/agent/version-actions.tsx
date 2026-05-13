"use client";

import { useTransition } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

type ActionResult = { ok: true } | { ok: false; error: string };

/**
 * Promote a staged ``agent_config`` version to ACTIVE.
 *
 * The promote endpoint publishes a Redis message (``nexus:agent_config:promote``)
 * that invalidates the worker's ``AgentLoader`` cache; the next inbound turn
 * picks up the new version — no redeploy required.
 */
export function PromoteVersionButton({
  tenantId,
  version,
  promote,
}: {
  tenantId: string;
  version: number;
  promote: (tenantId: string, version: number) => Promise<ActionResult>;
}) {
  const [pending, startTransition] = useTransition();
  function onClick() {
    startTransition(async () => {
      const r = await promote(tenantId, version);
      if (r.ok) {
        toast.success(`v${version} activada`, {
          description: "El próximo turno del agente usa esta versión.",
        });
      } else {
        toast.error("No se pudo activar", { description: r.error });
      }
    });
  }
  return (
    <Button size="sm" variant="default" onClick={onClick} disabled={pending}>
      {pending ? "Activando…" : "Activar"}
    </Button>
  );
}

/**
 * Roll back to a previous version. The endpoint stages a copy of the
 * chosen historical version as a new draft and promotes it in one step,
 * preserving the audit trail (no in-place mutation of the historical row).
 */
export function RollbackVersionButton({
  tenantId,
  version,
  rollback,
}: {
  tenantId: string;
  version: number;
  rollback: (tenantId: string, version: number) => Promise<ActionResult>;
}) {
  const [pending, startTransition] = useTransition();
  function onClick() {
    if (
      !window.confirm(
        `Volver a la v${version}? Se va a crear un nuevo borrador y promover en un paso.`,
      )
    ) {
      return;
    }
    startTransition(async () => {
      const r = await rollback(tenantId, version);
      if (r.ok) {
        toast.success(`Rollback a v${version} aplicado`, {
          description: "El próximo turno del agente usa esta versión.",
        });
      } else {
        toast.error("Rollback falló", { description: r.error });
      }
    });
  }
  return (
    <Button size="sm" variant="outline" onClick={onClick} disabled={pending}>
      {pending ? "Volviendo…" : "Volver a esta"}
    </Button>
  );
}
