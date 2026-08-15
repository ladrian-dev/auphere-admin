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
      <AgentVersions refId={ref} bundle={bundle} canWrite={can(principal.role, "agents:write")} />
    </section>
  );
}
