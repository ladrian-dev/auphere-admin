"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Button, Label, NativeSelect } from "@nexus/ui";

import { assignChannelAgentAction } from "../actions";

/** Agente — which of the client's agents answers on this channel. */
export function ChannelAgentForm({
  tenantId,
  channelId,
  agents,
  current,
}: {
  tenantId: string;
  channelId: string;
  agents: Array<{ id: string; label: string }>;
  current: string;
}) {
  const [agentId, setAgentId] = useState(current);
  const [pending, start] = useTransition();
  return (
    <form
      className="flex max-w-md flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        start(async () => {
          const r = await assignChannelAgentAction(tenantId, channelId, agentId);
          if (r.ok) toast.success("Agente asignado.");
          else toast.error("No se pudo asignar el agente", { description: r.error });
        });
      }}
    >
      <div className="flex flex-col gap-2">
        <Label htmlFor="agent">Agente que atiende</Label>
        <NativeSelect id="agent" value={agentId} onChange={(e) => setAgentId(e.target.value)}>
          {agents.map((a) => (
            <option key={a.id} value={a.id}>
              {a.label}
            </option>
          ))}
        </NativeSelect>
      </div>
      <div>
        <Button type="submit" disabled={pending || agentId === current || !agentId}>
          {pending ? "Asignando…" : "Asignar"}
        </Button>
      </div>
    </form>
  );
}
