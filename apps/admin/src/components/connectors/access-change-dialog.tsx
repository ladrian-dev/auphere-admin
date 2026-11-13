"use client";

import * as React from "react";
import { toast } from "sonner";

import { Callout, ConfirmDialog, Field, Textarea } from "@nexus/ui";

import type { AccessOutcome } from "@/app/(dashboard)/connectors/access-actions";
import type { AccessImpact } from "@/lib/backend-connector-access";
import { REASON_MAX, reasonError } from "@/lib/levers";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: React.ReactNode;
  description: React.ReactNode;
  confirmLabel: string;
  /** Lo que dice el aviso al terminar bien. */
  doneLabel: string;
  /** Guarda el cambio. La primera vez va sin `confirm`; si la API devuelve a
   * quién afecta, la segunda va con él. */
  submit: (reason: string, confirm: boolean) => Promise<AccessOutcome>;
  onDone: () => void;
  /** Lo que abrió el diálogo: un selector no es un disparador del diálogo, y sin
   * esto el foco caería en `body` al cerrarse. */
  returnFocus: () => HTMLElement | null;
};

function agentsText(n: number): string {
  return n === 0 ? "ningún agente" : n === 1 ? "1 agente" : `${n} agentes`;
}

/** «Lo tiene conectado 1 cliente; 2 agentes usan sus herramientas». */
function impactTitle(clients: number, agents: number): string {
  const who = clients === 1 ? "Lo tiene conectado 1 cliente" : `Lo tienen conectado ${clients} clientes`;
  const use =
    agents === 0
      ? "ningún agente usa sus herramientas"
      : agents === 1
        ? "1 agente usa sus herramientas"
        : `${agents} agentes usan sus herramientas`;
  return `${who}; ${use}`;
}

/**
 * Spec 060 (requisito 4): cambiar el acceso de un conector pide un motivo, que va a
 * la auditoría. Si el cambio quita el conector a clientes que lo tienen conectado,
 * la API no guarda nada y devuelve a quién afecta: el diálogo lo enseña y pide
 * confirmar. Si es el conector por defecto de un partner, explica qué cambiar antes.
 */
export function AccessChangeDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  doneLabel,
  submit,
  onDone,
  returnFocus,
}: Props) {
  const [reason, setReason] = React.useState("");
  const [touched, setTouched] = React.useState(false);
  const [impact, setImpact] = React.useState<AccessImpact | null>(null);
  const [error, setError] = React.useState<React.ReactNode>(null);
  const invalid = reasonError(reason);

  const reset = React.useCallback(() => {
    setReason("");
    setTouched(false);
    setImpact(null);
    setError(null);
  }, []);

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
      title={title}
      description={description}
      confirmLabel={impact ? "Quitar el acceso" : confirmLabel}
      cancelLabel="Cancelar"
      destructive={impact !== null}
      confirmDisabled={invalid !== null}
      error={error}
      returnFocus={() => {
        const el = returnFocus();
        return el?.isConnected ? el : null;
      }}
      onConfirm={async () => {
        setTouched(true);
        if (invalid) return;
        setError(null);
        const res = await submit(reason.trim(), impact !== null);
        if (res.ok) {
          toast.success(doneLabel);
          reset();
          onDone();
          return;
        }
        if (res.code === "confirm_required" && "impact" in res) {
          setImpact(res.impact);
          return;
        }
        if (res.code === "partner_default_connector" && "partners" in res) {
          setError(
            `Es el conector por defecto para dar de alta clientes de ${res.partners
              .map((p) => p.name)
              .join(", ")}. Cambia antes ese conector por defecto en la ficha del partner.`,
          );
          return;
        }
        setError("error" in res ? res.error : "No se pudo guardar.");
      }}
    >
      <Field
        label="Motivo"
        required
        requiredLabel="Obligatorio"
        hint="Queda en la auditoría con tu nombre."
        error={touched ? invalid : null}
      >
        {(a11y) => (
          <Textarea
            {...a11y}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            onBlur={() => setTouched(true)}
            rows={3}
            maxLength={REASON_MAX}
            placeholder="Por qué cambia quién puede usar este conector"
          />
        )}
      </Field>
      {impact ? (
        <Callout
          tone="warning"
          title={impactTitle(impact.totals.clients, impact.totals.agents)}
        >
          <p>
            Sus agentes dejarán de tenerlas desde el siguiente mensaje. La conexión no se borra:
            si vuelves a habilitarlo, todo vuelve como estaba.
          </p>
          <ul className="mt-2 flex flex-col gap-1">
            {impact.affected.map((group) => (
              <li key={group.partner_id ?? "sin-partner"}>
                <span className="font-medium wrap-anywhere">{group.partner_name ?? "Clientes sin partner"}</span>
                <ul className="mt-1 flex flex-col gap-1 pl-4">
                  {group.clients.map((c) => (
                    <li key={c.tenant_id} className="min-w-0 text-pretty wrap-anywhere">
                      {c.name} · {agentsText(c.agents)}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </Callout>
      ) : null}
    </ConfirmDialog>
  );
}
