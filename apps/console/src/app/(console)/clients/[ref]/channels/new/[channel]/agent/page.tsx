import { Bot, MessageCircle } from "lucide-react";
import Link from "next/link";

import { Button, EmptyState, ErrorState } from "@nexus/ui";

import { f2VisibleChannels } from "@/components/channels/visible-channels";
import { AssignStepForm, type AssignAgent, type AssignNumber } from "@/components/channels/wizard/assign-step-form";
import { wizardPaths } from "@/components/channels/wizard/steps";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { requirePartnerPrincipal } from "@/lib/principal";

import { getAgentsCached } from "../../../../data";

/**
 * Spec 046, step 3: what the number is for and which agent answers on it.
 * The number just connected comes chosen (`?channel=`), else the newest.
 */
export default async function AssignAgentPage({
  params,
  searchParams,
}: {
  params: Promise<{ ref: string; channel: string }>;
  searchParams: Promise<{ channel?: string }>;
}) {
  const { ref, channel } = await params;
  const wanted = (await searchParams).channel;
  const principal = await requirePartnerPrincipal();
  const { t } = await getT(principal.locale);
  const paths = wizardPaths(ref);

  const [overview, agents] = await Promise.all([
    backendFor(principal)
      .channelsOverview(ref)
      .catch(() => null),
    getAgentsCached(principal, ref),
  ]);
  if (!overview || !agents) {
    return <ErrorState title={t("chw.choose.error.title")} description={t("chw.choose.error.body")} />;
  }

  const live = f2VisibleChannels(overview.channels)
    .filter((c) => c.type === channel && c.status !== "disconnected")
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  const active = agents.filter((a) => a.status === "active");
  const head = (
    <div className="flex flex-col gap-1">
      <h2 className="text-lg font-semibold text-balance">{t("chw.agent.title")}</h2>
      <p className="text-sm text-pretty text-muted-foreground">{t("chw.agent.body")}</p>
    </div>
  );

  if (live.length === 0) {
    return (
      <div className="flex flex-col gap-6">
        {head}
        <EmptyState
          icon={MessageCircle}
          title={t("chw.agent.empty.title")}
          description={t("chw.agent.empty.body")}
          action={
            <Button nativeButton={false} render={<Link href={paths.connect(channel)} />}>
              {t("chw.agent.empty.action")}
            </Button>
          }
        />
      </div>
    );
  }
  if (active.length === 0) {
    return (
      <div className="flex flex-col gap-6">
        {head}
        <EmptyState
          icon={Bot}
          title={t("chw.agent.noAgents.title")}
          description={t("chw.agent.noAgents.body")}
          action={
            <Button nativeButton={false} render={<Link href={`/clients/${encodeURIComponent(ref)}/agent`} />}>
              {t("chw.agent.toAgent")}
            </Button>
          }
        />
      </div>
    );
  }

  const ownerOf = (channelId: string) => active.find((a) => a.channels.some((c) => c.id === channelId))?.id ?? null;
  const numbers: AssignNumber[] = live.map((c) => ({
    id: c.id,
    label: c.verified_name ? `${c.verified_name} · ${c.provider_identifier}` : c.provider_identifier,
    agentId: ownerOf(c.id),
    agentEnabled: c.agent_enabled,
  }));
  const options: AssignAgent[] = active.map((a) => ({ id: a.id, name: a.name, published: a.active_version !== null }));
  const first = numbers.find((n) => n.id === wanted) ?? numbers[0];
  const principalAgent = active.find((a) => a.is_principal) ?? active[0];
  if (!first || !principalAgent) return null;

  return (
    <div className="flex flex-col gap-6">
      {head}
      <AssignStepForm
        refId={ref}
        channel={channel}
        numbers={numbers}
        agents={options}
        defaultNumber={first.id}
        defaultAgent={first.agentId ?? principalAgent.id}
      />
    </div>
  );
}
