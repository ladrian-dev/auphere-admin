import { backend, type AgentConfig, type ToolWithInstallStatus } from "@/lib/backend";

import { AgentPicker } from "./agent-picker";
import { stageAgentConfigAction, updateRuntimeCapabilitiesAction } from "./actions";
import { AgentVersions } from "./agent-versions";
import { ApplySeedTemplateButton } from "./apply-seed";
import { EvalsSection } from "./evals/evals-section";
import { RuntimeCapabilities } from "./runtime-capabilities";

/**
 * Spec 037: the agent, as on the partner console's client page — its
 * versions with «Nuevo borrador», then its runtime and its evaluations. The
 * tools left this page for Habilidades.
 */
export default async function AgentPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ agent?: string }>;
}) {
  const { id } = await params;
  // Spec 030: con varios agentes, `?agent=` dice de cuál es lo que se edita;
  // sin él (o con uno que no es de este cliente), el principal. Si la lista
  // no se puede leer, el agente de la URL pasa tal cual y la API decide: caer
  // en el principal sin decirlo haría editar otro agente sin saberlo.
  const listed = await backend.listTenantAgents(id).catch(() => null);
  const agents = listed ?? [];
  const wanted = (await searchParams).agent;
  const selected = agents.find((a) => a.id === wanted && !a.is_principal) ?? null;
  const agentId =
    listed === null && wanted && /^[0-9a-f-]{36}$/i.test(wanted) ? wanted : selected?.id;
  const onScreen = selected ?? agents.find((a) => a.is_principal) ?? null;
  const [
    tenant,
    bundle,
    catalog,
    seedTemplates,
    datasets,
    recentRuns,
    availableSkills,
  ] = await Promise.all([
    backend.getTenant(id),
    backend.getAgentConfig(id, agentId),
    backend.listTenantToolCatalog(id, false),
    backend.listSeedTemplates(),
    backend.listEvalDatasets(id),
    backend.listEvalRuns(id, { limit: 10 }),
    backend.listAvailableSkills(),
  ]);
  if (!tenant) return null;

  // Block P — for v1 each tenant has at most one active dataset; pick
  // the most recent non-archived one.
  const primaryDatasetSummary = datasets[0] ?? null;
  const primaryDataset = primaryDatasetSummary
    ? await backend.getEvalDataset(id, primaryDatasetSummary.id)
    : null;

  // Filter the whitelist by the seed template applied to this tenant.
  // Look at the active version first (steady state); if there isn't one,
  // fall back to the most recent staged/archived version that carries a
  // seed_template_ref — that covers the "Aplicar plantilla inicial → not
  // yet promoted" path which previously fell through and dumped the full
  // registry on the operator (the gap the audit 2026-05-13 caught).
  //
  // We also use the latest staged draft (if any) to *prefill* the editor.
  // Without this the textarea + tool whitelist stay empty after
  // applyTemplate because the editor only initialised from
  // ``bundle.active`` and a first-time tenant has ``active === null``
  // even when the draft v1 exists. Operators couldn't review the
  // rendered prompt before promoting (the P0-2 bug from the
  // 2026-05-13 review).
  const sortedDesc = [...bundle.versions].sort((a, b) => b.version - a.version);
  const latestStaged = sortedDesc.find((v) => v.status === "staged") ?? null;
  const editorSource: AgentConfig | null = bundle.active ?? latestStaged;
  // Tool catalog for the editor = native capabilities (no connector
  // binding — always available) + the tools of every connector INSTALLED
  // on this tenant. Tools belong to connectors, not to verticals: we no
  // longer filter by the seed template. A tenant that hasn't connected a
  // given connector simply doesn't see its tools — connecting it from the
  // Connectors tab unlocks them. The seed template only seeds the initial
  // tool *selection* (applyTemplate writes tools_required into the staged
  // config), never the visible universe. See
  // architecture/connector-tools-binding-analysis.md.
  const publicCatalog: ToolWithInstallStatus[] = catalog.filter(
    (t) =>
      t.status !== "internal" &&
      (t.connector_slug === null || t.tenant_connector_status !== null),
  );


  return (
    <section aria-label="Agente" className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <AgentPicker tenantId={tenant.id} agents={agents} selectedId={onScreen?.id ?? null} />
        <ApplySeedTemplateButton
          tenantId={tenant.id}
          tenantName={tenant.name}
          tenantTimezone={tenant.timezone}
          templates={seedTemplates}
          hasActiveConfig={bundle.active !== null}
          agentId={agentId}
        />
      </div>
      <p className="max-w-prose text-sm text-pretty text-muted-foreground">
        Versiones del prompt{agents.length > 1 && onScreen ? ` de ${onScreen.name}` : ""}. Publicar crea una versión
        activa, revertir vuelve a cualquier anterior. Las habilidades se encienden en su pestaña y van al mismo borrador.
      </p>

      {/* Spec 037: the partner console's version list. */}
      <AgentVersions
        tenantId={tenant.id}
        agentId={agentId}
        versions={bundle.versions}
        activeVersion={bundle.active?.version ?? null}
        source={editorSource}
        sourceIsStagedDraft={editorSource?.status === "staged"}
        catalog={publicCatalog}
        stageAction={stageAgentConfigAction}
      />

      {/* Both blocks carry their own title and description. */}
      {editorSource ? (
        <RuntimeCapabilities
          tenantId={tenant.id}
          config={editorSource}
          availableSkills={availableSkills}
          updateAction={updateRuntimeCapabilitiesAction}
        />
      ) : null}

      <EvalsSection
        tenantId={tenant.id}
        datasets={datasets}
        primaryDataset={primaryDataset}
        recentRuns={recentRuns}
        activeVersion={bundle.active?.version ?? null}
      />
    </section>
  );
}
