import { redirect } from "next/navigation";

import { Section } from "@nexus/ui";

import { DraftEditsProvider } from "@/components/agent-draft/draft-edits";
import { AgentPromptEditor } from "@/components/agent-draft/prompt-editor";
import { DraftSaveBar } from "@/components/agent-draft/save-bar";
import { AgentVersionHistory } from "@/components/agent-draft/version-history";
import { AgentSettingsForm } from "@/components/agent-tools/agent-settings-form";
import { ModelPicker } from "@/components/agent-tools/model-picker";
import { AgentVersions } from "@/components/clients/agent-versions";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { agentChoice, getAgentsCached } from "../data";

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
 * Spec 047 (historia 2): un solo borrador por agente y **una sola barra de
 * guardado**. Las instrucciones y los ajustes ya no tienen botón cada uno: la
 * barra guarda todo en el borrador con la revisión que leyó la pantalla, y si
 * otra persona guardó entre medias enseña los dos cambios sin perder ninguno.
 * El historial dice «v{n} de {agente}» con autor, fecha, nota y de cuál partió.
 *
 * Sin agente todavía (un cliente recién creado sin plantilla) no hay borrador
 * que leer: la pantalla de antes ofrece escribir el primero.
 *
 * El selector de modelo se degrada solo: un catálogo que no se puede leer
 * esconde la tarjeta, nunca rompe los ajustes. Spec 030: con varios agentes,
 * `?agent=` dice de cuál son; sin él, del principal. El modelo es del cliente.
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
  // The draft routes name the agent in the path: the principal's id too.
  const listed = await getAgentsCached(principal, ref);
  const draftAgent = agentId ?? listed?.find((a) => a.is_principal)?.id;
  const canWrite = can(principal.role, "agents:write");

  const [bundle, settings, models, current, draft, history] = await Promise.all([
    api.getAgent(ref, agentId),
    api.getAgentSettings(ref, agentId),
    api.listModels().catch(() => null),
    api.getClientModel(ref).catch(() => null),
    draftAgent ? api.getAgentDraft(ref, draftAgent).catch(() => null) : Promise.resolve(null),
    draftAgent ? api.listAgentVersions(ref, draftAgent).catch(() => null) : Promise.resolve(null),
  ]);
  const prompts = Object.fromEntries(bundle.versions.map((v) => [v.version, v.system_prompt]));

  const settingsSection = (
    <Section title={t("agentSettings.title")} description={t("agentSettings.description")} flat headingLevel={2}>
      <AgentSettingsForm key={agentId ?? "principal"} refId={ref} data={settings} canWrite={canWrite} actor={principal.email} agentId={agentId} />
    </Section>
  );
  const modelPicker = models && current ? <ModelPicker refId={ref} models={models} current={current} canWrite={canWrite} /> : null;

  if (!draftAgent || !draft) {
    return (
      <section className="flex min-w-0 flex-col gap-(--space-section)" aria-label={t("agent.title")}>
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("agent.description")}</p>
        <AgentVersions key={agentId ?? "principal"} refId={ref} bundle={bundle} canWrite={canWrite} agentId={agentId} />
        {modelPicker}
        {settingsSection}
      </section>
    );
  }

  return (
    <DraftEditsProvider key={draftAgent} refId={ref} agentId={draftAgent} initial={draft} canWrite={canWrite}>
      {/* The save bar sits at the bottom: a focused field keeps a margin above it (WCAG 2.4.11). */}
      <section
        className="flex min-w-0 flex-col gap-(--space-section) [&_:focus-visible]:scroll-mb-40"
        aria-label={t("agent.title")}
      >
        <AgentPromptEditor />
        {modelPicker}
        {settingsSection}
        <AgentVersionHistory entries={history} prompts={prompts} />
        <DraftSaveBar />
      </section>
    </DraftEditsProvider>
  );
}
