"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Badge, Button, Input, NativeSelect } from "@nexus/ui";

import type { ConnectorToolMode } from "@/lib/backend";

import { deleteOverrideAction, putOverrideAction } from "../../_integrations/actions";

export type OverrideTool = {
  name: string;
  description: string;
  destructive: boolean;
  readOnly: boolean;
  mode: ConnectorToolMode | null;
  reason: string | null;
};

const DEFAULT = "";

export const MODE_LABEL: Record<ConnectorToolMode, string> = {
  always: "Siempre",
  needs_approval: "Pide aprobación",
  blocked: "Bloqueada",
};

/** What the agent does by default, before any override (Block L gating). */
function defaultLabel(tool: OverrideTool): string {
  if (tool.destructive) return "Por defecto · pide aprobación";
  return "Por defecto · siempre";
}

/**
 * Spec 035: per-client permissions for a connector's tools. The API had them
 * (Block L overrides) and no screen did. Each row saves on its own, with an
 * optional reason that goes to the audit trail.
 */
export function ToolOverrides({ tenantId, tools }: { tenantId: string; tools: OverrideTool[] }) {
  if (tools.length === 0) {
    return <p className="text-sm text-muted-foreground">Este conector todavía no publica herramientas.</p>;
  }
  return (
    <ul className="divide-y divide-border rounded-md ring-1 ring-foreground/10">
      {tools.map((t) => (
        <ToolRow key={t.name} tenantId={tenantId} tool={t} />
      ))}
    </ul>
  );
}

function ToolRow({ tenantId, tool }: { tenantId: string; tool: OverrideTool }) {
  const [mode, setMode] = useState<string>(tool.mode ?? DEFAULT);
  const [reason, setReason] = useState(tool.reason ?? "");
  const [pending, start] = useTransition();
  const dirty = mode !== (tool.mode ?? DEFAULT) || (mode !== DEFAULT && reason !== (tool.reason ?? ""));

  function save() {
    start(async () => {
      const r =
        mode === DEFAULT
          ? await deleteOverrideAction(tenantId, tool.name)
          : await putOverrideAction(tenantId, tool.name, mode as ConnectorToolMode, reason.trim() || null);
      if (r.ok) toast.success(mode === DEFAULT ? "Vuelve al comportamiento por defecto." : "Permiso guardado.");
      else toast.error("No se pudo guardar el permiso", { description: r.error });
    });
  }

  return (
    <li className="flex flex-col gap-3 px-4 py-3 md:flex-row md:items-center">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs">{tool.name}</span>
          {tool.destructive ? <Badge variant="outline">Cambia datos</Badge> : null}
          {tool.readOnly ? <Badge variant="outline">Solo lectura</Badge> : null}
        </span>
        {tool.description ? (
          <span className="line-clamp-2 text-xs text-pretty text-muted-foreground">{tool.description}</span>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <NativeSelect
          aria-label={`Permiso de ${tool.name}`}
          value={mode}
          onChange={(e) => setMode(e.target.value)}
          disabled={pending}
        >
          <option value={DEFAULT}>{defaultLabel(tool)}</option>
          <option value="always">{MODE_LABEL.always}</option>
          <option value="needs_approval">{MODE_LABEL.needs_approval}</option>
          <option value="blocked">{MODE_LABEL.blocked}</option>
        </NativeSelect>
        {mode !== DEFAULT ? (
          <Input
            aria-label={`Motivo para ${tool.name}`}
            placeholder="Motivo (opcional)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="w-48"
            disabled={pending}
          />
        ) : null}
        <Button
          size="sm"
          variant="outline"
          aria-label={`Guardar el permiso de ${tool.name}`}
          disabled={!dirty || pending}
          onClick={save}
        >
          {pending ? "Guardando…" : "Guardar"}
        </Button>
      </div>
    </li>
  );
}
