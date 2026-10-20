import Link from "next/link";

import { Button, EmptyState, ErrorState } from "@nexus/ui";

import { CHANNEL_NAME } from "@/components/channels/labels";
import { backend } from "@/lib/backend";

import { AssignAgentForm } from "./assign-form";

export const dynamic = "force-dynamic";

/** Step 3 — assign the agent. The newest channel of this kind comes chosen. */
export default async function AssignAgentPage({ params }: { params: Promise<{ id: string; channel: string }> }) {
  const { id, channel } = await params;
  const [channels, agents] = await Promise.all([
    backend.listChannels(id).catch(() => null),
    backend.listTenantAgents(id).catch(() => null),
  ]);
  if (!channels || !agents) {
    return <ErrorState title="No se pudieron leer los canales o los agentes" description="La API no respondió." />;
  }
  const ofKind = channels
    .filter((c) => c.type === channel && c.status !== "disconnected")
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  const live = agents.filter((a) => a.status === "active");
  if (ofKind.length === 0) {
    return (
      <EmptyState
        title={`Todavía no hay ningún canal de ${CHANNEL_NAME[channel] ?? channel}`}
        description="Vuelve al paso anterior y termina la conexión."
        action={
          <Button nativeButton={false} render={<Link href={`/tenants/${id}/channels/new/${channel}`} />}>
            Volver a conectar
          </Button>
        }
      />
    );
  }
  const principal = live.find((a) => a.is_principal) ?? live[0];
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-semibold">Asignar agente</h2>
        <p className="text-sm text-muted-foreground">Cada canal lo atiende un solo agente del cliente.</p>
      </div>
      {live.length === 0 ? (
        <EmptyState
          title="Este cliente no tiene agentes activos"
          description="Crea su agente en la pestaña Agente y vuelve aquí."
          action={
            <Button nativeButton={false} render={<Link href={`/tenants/${id}/agent`} />}>
              Ir a Agente
            </Button>
          }
        />
      ) : (
        <AssignAgentForm
          tenantId={id}
          channel={channel}
          channels={ofKind.map((c) => ({ id: c.id, label: `${CHANNEL_NAME[c.type] ?? c.type} · ${c.provider_identifier}` }))}
          agents={live.map((a) => ({ id: a.id, label: a.is_principal && !/principal/i.test(a.name) ? `${a.name} (principal)` : a.name }))}
          defaultChannel={ofKind[0].id}
          defaultAgent={ofKind[0].agent_id ?? principal?.id ?? ""}
        />
      )}
    </div>
  );
}
