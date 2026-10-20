"use client";

import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  NativeSelect,
  StatusBadge,
  Switch,
} from "@nexus/ui";

import type { Capability, CapabilityModeChange } from "@/lib/backend";

import { setCapabilityAction } from "./actions";

const MODE_LABEL = { always: "Siempre", blocked: "Nunca" } as const;

/**
 * Spec 037: one capability, as in the partner console (spec 017 R5) — name,
 * one line and the switch; everything else in a sheet that opens on click.
 * The switch saves on release. Opening is not switching: two targets.
 */
export function CapabilityCard({
  tenantId,
  cap,
  agentId,
  onChanged,
}: {
  tenantId: string;
  cap: Capability;
  agentId?: string;
  onChanged?: () => void;
}) {
  const [enabled, setEnabled] = React.useState(cap.enabled);
  const [pending, start] = React.useTransition();
  const [open, setOpen] = React.useState(false);
  const nameId = `cap-${cap.kind}-${cap.key}`;

  const [seen, setSeen] = React.useState(cap.enabled);
  if (seen !== cap.enabled) {
    setSeen(cap.enabled);
    setEnabled(cap.enabled);
  }

  function save(change: { enabled?: boolean; mode?: CapabilityModeChange }) {
    start(async () => {
      const res = await setCapabilityAction({ tenantId, key: cap.key, kind: cap.kind, ...change, agent: agentId });
      if (!res.ok) {
        if (change.enabled !== undefined) setEnabled(!change.enabled);
        toast.error("No se pudo guardar", { description: res.error });
        return;
      }
      toast.success("Guardado en el borrador.");
      onChanged?.();
    });
  }

  return (
    <li
      className="flex min-w-0 items-start gap-3 rounded-md bg-card p-4 ring-1 ring-foreground/10 focus-within:ring-2 focus-within:ring-ring"
      aria-busy={pending}
    >
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex min-w-0 flex-1 cursor-pointer flex-col gap-1 text-left outline-none"
        aria-haspopup="dialog"
      >
        <span id={nameId} className="font-medium">
          {cap.business_name}
        </span>
        <span className="line-clamp-2 text-sm text-pretty text-muted-foreground">{cap.description}</span>
        {!cap.activatable ? (
          <StatusBadge tone="muted">Aún no disponible</StatusBadge>
        ) : cap.connector && cap.connector.status !== "connected" ? (
          <span className="text-xs text-status-warning-text">Necesita {cap.connector.display_name} para funcionar.</span>
        ) : null}
      </button>
      {cap.activatable ? (
        <Switch
          aria-labelledby={nameId}
          checked={enabled}
          disabled={pending}
          onCheckedChange={(v) => {
            const next = Boolean(v);
            setEnabled(next);
            save({ enabled: next });
          }}
        />
      ) : null}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{cap.business_name}</DialogTitle>
            <DialogDescription>{cap.description}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center gap-2">
              {cap.recommended ? <StatusBadge tone="info">Recomendada para su sector</StatusBadge> : null}
              {cap.enabled_in_active ? (
                <StatusBadge tone="positive">En la versión activa</StatusBadge>
              ) : cap.enabled ? (
                <StatusBadge tone="info">Aún no publicada</StatusBadge>
              ) : null}
              {cap.other_sector ? <StatusBadge tone="muted">De otro sector</StatusBadge> : null}
              {cap.read_only ? <StatusBadge tone="muted">Solo lectura</StatusBadge> : null}
              {cap.destructive ? <StatusBadge tone="danger">Cambia datos</StatusBadge> : null}
            </div>
            {!cap.activatable ? (
              <p className="text-sm text-muted-foreground">
                Todavía no está publicada en este entorno. En cuanto lo esté, se podrá encender aquí.
              </p>
            ) : null}
            {cap.connector && cap.connector.status !== "connected" ? (
              <p className="text-sm text-status-warning-text">
                Necesita {cap.connector.display_name} para funcionar. Se puede encender igual: empieza a funcionar en
                cuanto se conecte.{" "}
                <Link
                  href={`/tenants/${tenantId}/connectors/${encodeURIComponent(cap.connector.slug)}`}
                  className="underline underline-offset-4"
                >
                  Conectarlo
                </Link>
              </p>
            ) : null}
            {cap.mode ? (
              <div className="flex flex-col gap-2">
                <label htmlFor={`mode-${nameId}`} className="text-sm font-medium">
                  Cuándo la usa
                </label>
                <NativeSelect
                  id={`mode-${nameId}`}
                  size="sm"
                  defaultValue={cap.mode.override ?? "__default"}
                  disabled={pending}
                  wrapperClassName="w-52"
                  onChange={(e) => {
                    const v = e.target.value;
                    save({ mode: (v === "__default" ? "default" : v) as CapabilityModeChange });
                  }}
                >
                  <option value="__default">Por defecto ({MODE_LABEL[cap.mode.default]})</option>
                  {cap.mode.options.map((m) => (
                    <option key={m} value={m}>
                      {MODE_LABEL[m]}
                    </option>
                  ))}
                </NativeSelect>
              </div>
            ) : null}
            <details className="min-w-0 text-xs text-muted-foreground">
              <summary className="cursor-pointer">Detalle técnico</summary>
              <p className="mt-1">
                Nombre: <span className="font-mono">{cap.technical.name}</span> · Tipo:{" "}
                {cap.technical.kind === "tool" ? "Herramienta" : "Skill"}
                {cap.technical.version ? ` · Versión ${cap.technical.version}` : ""}
              </p>
            </details>
          </div>
        </DialogContent>
      </Dialog>
    </li>
  );
}
