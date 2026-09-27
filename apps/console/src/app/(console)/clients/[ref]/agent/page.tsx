import { redirect } from "next/navigation";

import { Section } from "@nexus/ui";

import { AgentSettingsForm } from "@/components/agent-tools/agent-settings-form";
import { ModelPicker } from "@/components/agent-tools/model-picker";
import { AgentVersions } from "@/components/clients/agent-versions";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * El agente, entero (spec 018, R3).
 *
 * «Agente» y «Ajustes» eran dos pestañas y dos mitades de lo mismo: una
 * enseñaba las versiones y la otra la política que esas versiones llevan
 * dentro, y había que recordar cuál guardaba qué. Ahora es una.
 *
 * Esto **no deshace** la separación de la spec 017, que apartó los datos DEL
 * CLIENTE de los ajustes DEL AGENTE: aquella distinción sigue en pie y es la
 * que hace que el punto de «sin publicar» señale la pantalla que cambió.
 *
 * El selector de modelo se degrada solo: un catálogo que no se puede leer
 * esconde la tarjeta, nunca rompe los ajustes.
 */
export default async function AgentPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:read")) redirect(`/clients/${ref}`);
  const { t } = await getT(principal.locale);
  const api = backendFor(principal);
  const [bundle, settings, models, current] = await Promise.all([
    api.getAgent(ref),
    api.getAgentSettings(ref),
    api.listModels().catch(() => null),
    api.getClientModel(ref).catch(() => null),
  ]);
  const canWrite = can(principal.role, "agents:write");

  return (
    <section className="flex min-w-0 flex-col gap-(--space-section)" aria-label={t("agent.title")}>
      <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("agent.description")}</p>

      <AgentVersions refId={ref} bundle={bundle} canWrite={canWrite} />

      {models && current ? <ModelPicker refId={ref} models={models} current={current} canWrite={canWrite} /> : null}

      <Section title={t("agentSettings.title")} description={t("agentSettings.description")} flat headingLevel={2}>
        <AgentSettingsForm refId={ref} data={settings} canWrite={canWrite} actor={principal.email} />
      </Section>
    </section>
  );
}
