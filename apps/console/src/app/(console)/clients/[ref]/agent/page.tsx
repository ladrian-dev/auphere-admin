import { SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { AgentVersions } from "@/components/clients/agent-versions";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

export default async function AgentPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:read")) redirect(`/clients/${ref}`);
  const { t } = await getT(principal.locale);
  const bundle = await backendFor(principal).getAgent(ref);
  return (
    <section className="flex min-w-0 flex-col gap-4" aria-label={t("agent.title")}>
      <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("agent.description")}</p>
      {/* lane agent-tools (CP-11): structured settings live on their own page */}
      <Link
        href={`/clients/${encodeURIComponent(ref)}/agent/settings`}
        className="flex min-w-0 items-center gap-3 rounded-md bg-card p-4 ring-1 ring-foreground/10 transition-colors hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground">
          <SlidersHorizontal className="size-4" aria-hidden="true" />
        </span>
        <span className="flex min-w-0 flex-col">
          <span className="text-sm font-medium">{t("agentSettings.link.title")}</span>
          <span className="text-xs text-pretty text-muted-foreground">{t("agentSettings.link.body")}</span>
        </span>
      </Link>
      <AgentVersions refId={ref} bundle={bundle} canWrite={can(principal.role, "agents:write")} />
    </section>
  );
}
