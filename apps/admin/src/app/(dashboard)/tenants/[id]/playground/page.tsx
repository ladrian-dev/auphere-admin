import { notFound } from "next/navigation";

import { PlaygroundShell } from "@/components/qa/playground-shell";
import { backend } from "@/lib/backend";
import { qaApi, type QAThread } from "@/lib/qa-api";
import { requireOperator } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * Spec 037: the Playground as a tab of the client, like the partner console —
 * talk to the agent as a customer without touching real channels. The same
 * shell as `/qa/{client}/chat`, framed inside the profile.
 */
export default async function TenantPlaygroundPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ thread?: string }>;
}) {
  const { id } = await params;
  const { thread } = await searchParams;
  const operator = await requireOperator();
  const [tenant, bundle, threads] = await Promise.all([
    backend.getTenant(id),
    backend.getAgentConfig(id).catch(() => null),
    qaApi.listThreads({ operatorId: operator.id, tenantId: id, limit: 50 }).catch(() => [] as QAThread[]),
  ]);
  if (!tenant) notFound();
  return (
    <PlaygroundShell
      tenant={{ id: tenant.id, name: tenant.name, slug: tenant.slug }}
      agentVersion={bundle?.active?.version ?? null}
      operatorId={operator.id}
      operatorEmail={operator.email ?? null}
      initialThreads={threads}
      initialActiveThread={thread ? (threads.find((t) => t.id === thread) ?? null) : null}
      basePath={`/tenants/${tenant.id}/playground`}
      embedded
    />
  );
}
