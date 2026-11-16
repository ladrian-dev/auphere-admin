/**
 * QA Playground — main chat view (ADR-020 Phase 5).
 *
 * Server component. Resolves the tenant + the operator's QA threads
 * for this tenant up front so the client side renders with real data
 * already, then defers the live conversation runtime to a client
 * component (``<PlaygroundShell>``).
 *
 * URL shape: ``/qa/[tenantId]/chat?thread=[threadId?]``.
 *
 * Access: gated by the (dashboard) layout's ``requireOperator()``. The
 * operator id is the Better Auth operator.id; the same id is
 * stamped into ``qa.threads.operator_id`` so RLS keeps two operators
 * inspecting the same tenant from seeing each other's threads.
 */
import { notFound } from "next/navigation";

import { AgentPicker } from "@/app/(dashboard)/tenants/[id]/agent/agent-picker";
import { AgentsUnreadable, PlaygroundShell } from "@/components/qa/playground-shell";
import { CrumbName } from "@/components/shell/crumb-names";
import { backend } from "@/lib/backend";
import { qaApi, type QAThread } from "@/lib/qa-api";
import { pickPlaygroundAgent, shellAgent, threadsOfAgent } from "@/lib/qa-playground-agent";
import { requireOperator } from "@/lib/session";

export const metadata = { title: "QA Playground" };

export default async function PlaygroundPage({
  params,
  searchParams,
}: {
  params: Promise<{ tenantId: string }>;
  searchParams: Promise<{ thread?: string; agent?: string }>;
}) {
  const { tenantId } = await params;
  const { thread: activeThreadId, agent } = await searchParams;
  const operator = await requireOperator();
  const operatorId = operator.id;

  // Spec 030: `?agent=` says which agent is tested (the principal without it).
  const listed = await backend.listTenantAgents(tenantId).catch(() => null);
  const { agents, selected } = pickPlaygroundAgent(listed, agent);
  const [tenant, agentBundle, allThreads] = await Promise.all([
    backend.getTenant(tenantId),
    backend.getAgentConfig(
      tenantId,
      selected && !selected.is_principal ? selected.id : undefined,
    ),
    qaApi
      .listThreads({ operatorId, tenantId, limit: 200 })
      .catch(() => [] as QAThread[]),
  ]);
  if (!tenant) notFound();
  const threads = threadsOfAgent(allThreads, selected);

  const activeThread = activeThreadId
    ? (threads.find((t) => t.id === activeThreadId) ?? null)
    : null;

  return (
    <>
    <CrumbName id={tenant.id} label={tenant.name} />
    <PlaygroundShell
      tenant={{
        id: tenant.id,
        name: tenant.name,
        slug: tenant.slug,
      }}
      agent={shellAgent(selected)}
      agentVersion={agentBundle.active?.version ?? null}
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
      operatorId={operatorId}
      operatorEmail={operator.email ?? null}
      initialThreads={threads}
      initialActiveThread={activeThread}
    />
    </>
  );
}
