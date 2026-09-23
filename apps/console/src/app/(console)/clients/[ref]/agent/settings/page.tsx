import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Button } from "@nexus/ui";

import { AgentSettingsForm } from "@/components/agent-tools/agent-settings-form";
import { ModelPicker } from "@/components/agent-tools/model-picker";
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
  const api = backendFor(principal);
  // Spec 016 (US4): the model card degrades on its own — a catalogue that
  // cannot be read hides the card, it never breaks the settings.
  const [data, models, current] = await Promise.all([
    api.getAgentSettings(ref),
    api.listModels().catch(() => null),
    api.getClientModel(ref).catch(() => null),
  ]);
  const base = `/clients/${encodeURIComponent(ref)}`;
  const canWrite = can(principal.role, "agents:write");
  return (
    <section className="flex min-w-0 flex-col gap-4" aria-label={t("agentSettings.title")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-base font-medium text-balance">{t("agentSettings.title")}</h1>
          <p className=" text-sm text-pretty text-muted-foreground">{t("agentSettings.description")}</p>
        </div>
        <Button nativeButton={false} render={<Link href={`${base}/agent`} />} variant="outline" size="sm">
          <ArrowLeft aria-hidden="true" />
          {t("agentSettings.back")}
        </Button>
      </div>
      {models && current ? <ModelPicker refId={ref} models={models} current={current} canWrite={canWrite} /> : null}
      <AgentSettingsForm refId={ref} data={data} canWrite={canWrite} actor={principal.email} />
    </section>
  );
}
