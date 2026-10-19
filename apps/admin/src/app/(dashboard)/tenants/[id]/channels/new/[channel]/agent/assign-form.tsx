"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Button, Label, NativeSelect } from "@nexus/ui";

import { assignChannelAgentAction } from "../../../actions";

type Option = { id: string; label: string };

/** Step 3 — which agent of the client answers on the new channel. */
export function AssignAgentForm({
  tenantId,
  channel,
  channels,
  agents,
  defaultChannel,
  defaultAgent,
}: {
  tenantId: string;
  channel: string;
  channels: Option[];
  agents: Option[];
  defaultChannel: string;
  defaultAgent: string;
}) {
  const router = useRouter();
  const [channelId, setChannelId] = useState(defaultChannel);
  const [agentId, setAgentId] = useState(defaultAgent);
  const [pending, start] = useTransition();

  return (
    <form
      className="flex max-w-md flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        start(async () => {
          const r = await assignChannelAgentAction(tenantId, channelId, agentId);
          if (!r.ok) {
            toast.error("No se pudo asignar el agente", { description: r.error });
            return;
          }
          router.push(`/tenants/${tenantId}/channels/new/${channel}/done?channel=${channelId}`);
        });
      }}
    >
      <div className="flex flex-col gap-2">
        <Label htmlFor="ch">Canal</Label>
        <NativeSelect id="ch" value={channelId} onChange={(e) => setChannelId(e.target.value)}>
          {channels.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </NativeSelect>
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="ag">Agente que atiende</Label>
        <NativeSelect id="ag" value={agentId} onChange={(e) => setAgentId(e.target.value)}>
          {agents.map((a) => (
            <option key={a.id} value={a.id}>
              {a.label}
            </option>
          ))}
        </NativeSelect>
      </div>
      <div>
        <Button type="submit" disabled={pending || !channelId || !agentId}>
          {pending ? "Asignando…" : "Asignar y terminar"}
        </Button>
      </div>
    </form>
  );
}
