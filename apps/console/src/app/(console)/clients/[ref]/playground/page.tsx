import { redirect } from "next/navigation";

import { Badge } from "@nexus/ui";

import { Playground } from "@/components/playground/playground";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import type { PlaygroundBudget } from "@/lib/backend/playground";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { agentChoice, getClientCached } from "../data";

/**
 * Playground tab (CP-16). Server component: loads the member's threads and
 * the partner's budget; the chat itself is a client component that streams
 * over `/api/playground/...` (route handler → API SSE). Analysts (no
 * `playground:run`) are sent back to the client overview.
 *
 * Spec 030: with several agents, the tab tests the agent in `?agent=` (the
 * principal without it) — its threads only, and new ones pinned to it.
 */
export default async function PlaygroundPage({
  params,
  searchParams,
}: {
  params: Promise<{ ref: string }>;
  searchParams: Promise<{ agent?: string }>;
}) {
  const { ref } = await params;
  const principal = await requirePartnerPrincipal();
  if (!can(principal.role, "playground:run")) redirect(`/clients/${ref}`);
  const { t } = await getT(principal.locale);
  const api = backendFor(principal);
  const { agents, agentId } = await agentChoice(principal, ref, (await searchParams).agent);
  // With one agent every thread is its own; with more, the principal's tab
  // names it so the API leaves out the other agents' threads.
  const listed = agentId ?? agents.find((a) => a.is_principal)?.id;
  const [client, threads, budgetRes] = await Promise.all([
    getClientCached(principal, ref),
    api.listPlaygroundThreads(ref, { agent: listed }),
    api.getPlaygroundBudget().then(
      (b): { budget: PlaygroundBudget | null; failed: boolean } => ({ budget: b, failed: false }),
      () => ({ budget: null, failed: true }),
    ),
  ]);
  return (
    <section className="flex min-w-0 flex-col gap-4" aria-label={t("playground.title")}>
      <div className="flex flex-wrap items-center gap-2">
        <p className=" text-sm text-pretty text-muted-foreground">{t("playground.description")}</p>
        <Badge variant="outline">{t("playground.dryRun")}</Badge>
      </div>
      <Playground
        key={agentId ?? "principal"}
        refId={ref}
        agentId={agentId}
        initialThreads={threads}
        initialBudget={budgetRes.budget}
        budgetFailed={budgetRes.failed}
        agentReady={client.health.agent_configured}
      />
    </section>
  );
}
