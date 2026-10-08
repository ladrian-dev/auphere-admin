import { redirect } from "next/navigation";

import { Section } from "@nexus/ui";

import { AgentSettingsForm } from "@/components/agent-tools/agent-settings-form";
import { ModelPicker } from "@/components/agent-tools/model-picker";
import { AgentVersions } from "@/components/clients/agent-versions";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { agentChoice } from "../data";

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
 *
 * Spec 030: con varios agentes, `?agent=` dice de cuál son las versiones y
 * los ajustes; sin él, del principal. El modelo es del cliente, de todos.
 */
export default async function AgentPage({
  params,
  searchParams,
}: {
  params: Promise<{ ref: string }>;
  searchParams: Promise<{ agent?: string }>;
}) {
  const { ref } = await params;
  const principal = await requirePartnerPrincipal();
  if (!can(principal.role, "agents:read")) redirect(`/clients/${ref}`);
  const { t } = await getT(principal.locale);
  const api = backendFor(principal);
  const { agentId } = await agentChoice(principal, ref, (await searchParams).agent);
  const [bundle, settings, models, current] = await Promise.all([
    api.getAgent(ref, agentId),
    api.getAgentSettings(ref, agentId),
    api.listModels().catch(() => null),
    api.getClientModel(ref).catch(() => null),
  ]);
  const canWrite = can(principal.role, "agents:write");

  return (
    <section className="flex min-w-0 flex-col gap-(--space-section)" aria-label={t("agent.title")}>
      <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("agent.description")}</p>

      <AgentVersions key={agentId ?? "principal"} refId={ref} bundle={bundle} canWrite={canWrite} agentId={agentId} />

      {models && current ? <ModelPicker refId={ref} models={models} current={current} canWrite={canWrite} /> : null}

      <Section title={t("agentSettings.title")} description={t("agentSettings.description")} flat headingLevel={2}>
        <AgentSettingsForm key={agentId ?? "principal"} refId={ref} data={settings} canWrite={canWrite} actor={principal.email} agentId={agentId} />
      </Section>
    </section>
  );
}
