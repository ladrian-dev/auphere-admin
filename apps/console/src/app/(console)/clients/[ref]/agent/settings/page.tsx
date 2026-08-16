import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Button } from "@nexus/ui";

import { AgentSettingsForm } from "@/components/agent-tools/agent-settings-form";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Structured agent settings (CP-11 / CP-31): the partner edits
 * `policies.console` of the draft without touching the prompt. Saving
 * creates/reuses a STAGED draft; publishing stays on the versions page.
 */
export default async function AgentSettingsPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:read")) redirect(`/clients/${ref}`);
  const { t } = await getT(principal.locale);
  const data = await backendFor(principal).getAgentSettings(ref);
  const base = `/clients/${encodeURIComponent(ref)}`;
  return (
    <section className="flex min-w-0 flex-col gap-4" aria-label={t("agentSettings.title")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-base font-medium text-balance">{t("agentSettings.title")}</h1>
          <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("agentSettings.description")}</p>
        </div>
        <Button nativeButton={false} render={<Link href={`${base}/agent`} />} variant="outline" size="sm">
          <ArrowLeft aria-hidden="true" />
          {t("agentSettings.back")}
        </Button>
      </div>
      <AgentSettingsForm refId={ref} data={data} canWrite={can(principal.role, "agents:write")} actor={principal.email} />
    </section>
  );
}
