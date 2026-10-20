"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Button, Label, NativeSelect, Switch } from "@nexus/ui";

import type { ChannelRole } from "@/lib/channels";

import { updateChannelRoleAction } from "../../_integrations/actions";

const UNASSIGNED = "";

/**
 * Ajustes — the two flags an operator can change on a channel: which line
 * business-initiated sends leave from (WhatsApp only) and whether the agent
 * answers here. Saved together, only when something changed.
 */
export function ChannelSettings({
  tenantId,
  channelId,
  showRole,
  soleNumber,
  role,
  agentEnabled,
}: {
  tenantId: string;
  channelId: string;
  showRole: boolean;
  soleNumber: boolean;
  role: ChannelRole | null;
  agentEnabled: boolean;
}) {
  const [nextRole, setNextRole] = useState<string>(role ?? UNASSIGNED);
  const [nextAgent, setNextAgent] = useState(agentEnabled);
  const [pending, start] = useTransition();
  const dirty = nextRole !== (role ?? UNASSIGNED) || nextAgent !== agentEnabled;

  return (
    <form
      className="flex max-w-lg flex-col gap-6"
      onSubmit={(e) => {
        e.preventDefault();
        start(async () => {
          const body: { role?: ChannelRole | null; agent_enabled?: boolean } = {};
          if (showRole && nextRole !== (role ?? UNASSIGNED)) {
            body.role = nextRole === UNASSIGNED ? null : (nextRole as ChannelRole);
          }
          if (nextAgent !== agentEnabled) body.agent_enabled = nextAgent;
          const r = await updateChannelRoleAction(tenantId, channelId, body);
          if (r.ok) toast.success("Ajustes guardados.");
          else toast.error("No se pudieron guardar los ajustes", { description: r.error });
        });
      }}
    >
      {showRole ? (
        <div className="flex flex-col gap-2">
          <Label htmlFor="role">Papel del número</Label>
          <NativeSelect id="role" value={nextRole} onChange={(e) => setNextRole(e.target.value)}>
            <option value={UNASSIGNED}>{soleNumber ? "Avisos y agente" : "Sin asignar"}</option>
            <option value="notifications">Línea de avisos</option>
            <option value="agent">Línea del agente</option>
          </NativeSelect>
          <p className="text-xs text-pretty text-muted-foreground">
            {soleNumber
              ? "Con un solo número activo se usa para todo."
              : "Con dos números o más, uno tiene que ser la línea de avisos. Si no, los recordatorios y las plantillas no salen."}
          </p>
        </div>
      ) : null}
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <Label htmlFor="agent-on">El agente responde aquí</Label>
          <p className="text-xs text-pretty text-muted-foreground">
            Apagado, los mensajes se guardan y se ven en el panel, pero nadie contesta. Los envíos salientes siguen
            funcionando.
          </p>
        </div>
        <Switch id="agent-on" checked={nextAgent} onCheckedChange={setNextAgent} />
      </div>
      <div>
        <Button type="submit" disabled={!dirty || pending}>
          {pending ? "Guardando…" : "Guardar"}
        </Button>
      </div>
    </form>
  );
}
