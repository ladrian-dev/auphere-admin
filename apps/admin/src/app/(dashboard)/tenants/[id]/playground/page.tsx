import { notFound } from "next/navigation";

import { AgentsUnreadable, PlaygroundShell } from "@/components/qa/playground-shell";
import { backend } from "@/lib/backend";
import { qaApi, type QAThread } from "@/lib/qa-api";
import { pickPlaygroundAgent, shellAgent, threadsOfAgent } from "@/lib/qa-playground-agent";
import { requirePageOperator } from "@/lib/session";

import { AgentPicker } from "../agent/agent-picker";

export const dynamic = "force-dynamic";

/**
 * Spec 037: the Playground as a tab of the client, like the partner console —
 * talk to the agent as a customer without touching real channels. The same
 * shell as `/qa/{client}/chat`, framed inside the profile.
 *
 * Spec 030: with several agents, `?agent=` says which one is tested; its
 * threads are listed and new ones are opened with it.
 */
export default async function TenantPlaygroundPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ thread?: string; agent?: string }>;
}) {
  const { id } = await params;
  const { thread, agent } = await searchParams;
  const operator = await requirePageOperator("qa");
  const listed = await backend.listTenantAgents(id).catch(() => null);
  const { agents, selected } = pickPlaygroundAgent(listed, agent);
  const [tenant, bundle, allThreads] = await Promise.all([
    backend.getTenant(id),
    backend
      .getAgentConfig(id, selected && !selected.is_principal ? selected.id : undefined)
      .catch(() => null),
    qaApi.listThreads({ operatorId: operator.id, tenantId: id, limit: 200 }).catch(() => [] as QAThread[]),
  ]);
  if (!tenant) notFound();
  const threads = threadsOfAgent(allThreads, selected);
  return (
    <PlaygroundShell
      tenant={{ id: tenant.id, name: tenant.name, slug: tenant.slug }}
      agent={shellAgent(selected)}
      agentVersion={bundle?.active?.version ?? null}
      agentPicker={
        listed === null ? (
          <AgentsUnreadable />
        ) : (
          <AgentPicker
            tenantId={tenant.id}
            agents={agents}
            selectedId={selected?.id ?? null}
            allowCreate={false}
            inline
          />
        )
      }
      operatorId={operator.id}
      operatorEmail={operator.email ?? null}
      initialThreads={threads}
      initialActiveThread={thread ? (threads.find((t) => t.id === thread) ?? null) : null}
      basePath={`/tenants/${tenant.id}/playground`}
      embedded
    />
  );
}
