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

import { PlaygroundShell } from "@/components/qa/playground-shell";
import { backend } from "@/lib/backend";
import { qaApi, type QAThread } from "@/lib/qa-api";
import { requireOperator } from "@/lib/session";

export const metadata = { title: "QA Playground" };

export default async function PlaygroundPage({
  params,
  searchParams,
}: {
  params: Promise<{ tenantId: string }>;
  searchParams: Promise<{ thread?: string }>;
}) {
  const { tenantId } = await params;
  const { thread: activeThreadId } = await searchParams;
  const operator = await requireOperator();
  const operatorId = operator.id;

  const [tenant, agentBundle, threads] = await Promise.all([
    backend.getTenant(tenantId),
    backend.getAgentConfig(tenantId),
    qaApi
      .listThreads({ operatorId, tenantId, limit: 50 })
      .catch(() => [] as QAThread[]),
  ]);
  if (!tenant) notFound();

  const activeThread = activeThreadId
    ? (threads.find((t) => t.id === activeThreadId) ?? null)
    : null;

  return (
    <PlaygroundShell
      tenant={{
        id: tenant.id,
        name: tenant.name,
        slug: tenant.slug,
      }}
      agentVersion={agentBundle.active?.version ?? null}
      operatorId={operatorId}
      operatorEmail={operator.email ?? null}
      initialThreads={threads}
      initialActiveThread={activeThread}
    />
  );
}
