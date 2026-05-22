import { Eyebrow } from "@/components/brand/eyebrow";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  backend,
  type AgentConfig,
  type ToolWithInstallStatus,
} from "@/lib/backend";
import { fullDateTime, relativeTime } from "@/lib/format";

import { AgentEditor } from "./editor";
import {
  promoteAgentConfigAction,
  rollbackAgentConfigAction,
  stageAgentConfigAction,
} from "./actions";
import { ApplySeedTemplateButton } from "./apply-seed";
import { EvalsSection } from "./evals/evals-section";
import {
  PromoteVersionButton,
  RollbackVersionButton,
} from "./version-actions";

export default async function AgentPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [tenant, bundle, catalog, seedTemplates, datasets, recentRuns] =
    await Promise.all([
      backend.getTenant(id),
      backend.getAgentConfig(id),
      backend.listTenantToolCatalog(id, false),
      backend.listSeedTemplates(),
      backend.listEvalDatasets(id),
      backend.listEvalRuns(id, { limit: 10 }),
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

  const headerTitle = bundle.active
    ? `Versión ${bundle.active.version} activa`
    : latestStaged
      ? `Borrador v${latestStaged.version} sin promover`
      : "Crear primera versión";

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader className="flex flex-col gap-1">
          <Eyebrow>Configuración del agente</Eyebrow>
          <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
            <div>
              <CardTitle>{headerTitle}</CardTitle>
              <CardDescription>
                Cada cambio que guardás queda como borrador. Promovelo cuando
                quieras que el agente lo use en el siguiente turno.
              </CardDescription>
            </div>
            <ApplySeedTemplateButton
              tenantId={tenant.id}
              tenantName={tenant.name}
              tenantTimezone={tenant.timezone}
              templates={seedTemplates}
              hasActiveConfig={bundle.active !== null}
            />
          </div>
        </CardHeader>
        <CardContent>
          <AgentEditor
            tenantId={tenant.id}
            source={editorSource}
            sourceIsStagedDraft={editorSource?.status === "staged"}
            catalog={publicCatalog}
            stageAction={stageAgentConfigAction}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow>Versiones</Eyebrow>
          <CardTitle>Historial</CardTitle>
          <CardDescription>
            Cada promoción se aplica en el siguiente turno del agente, sin
            necesidad de redeploy.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <VersionTable
            tenantId={tenant.id}
            versions={bundle.versions}
            activeVersion={bundle.active?.version}
            promote={promoteAgentConfigAction}
            rollback={rollbackAgentConfigAction}
          />
        </CardContent>
      </Card>

      <EvalsSection
        tenantId={tenant.id}
        datasets={datasets}
        primaryDataset={primaryDataset}
        recentRuns={recentRuns}
        activeVersion={bundle.active?.version ?? null}
      />
    </div>
  );
}

function VersionTable({
  tenantId,
  versions,
  activeVersion,
  promote,
  rollback,
}: {
  tenantId: string;
  versions: Array<{
    id: string;
    version: number;
    status: string;
    promoted_at: string | null;
    created_at: string;
  }>;
  activeVersion?: number;
  promote: (
    tenantId: string,
    version: number,
  ) => Promise<{ ok: true } | { ok: false; error: string }>;
  rollback: (
    tenantId: string,
    version: number,
  ) => Promise<{ ok: true } | { ok: false; error: string }>;
}) {
  if (versions.length === 0) {
    return (
      <div className="px-6 py-12 text-center text-muted-foreground text-sm">
        Todavía no hay versiones. Guardá el editor para crear la primera.
      </div>
    );
  }
  const sorted = [...versions].sort((a, b) => b.version - a.version);
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Versión</TableHead>
          <TableHead>Estado</TableHead>
          <TableHead>Creada</TableHead>
          <TableHead>Promovida</TableHead>
          <TableHead>ID</TableHead>
          <TableHead className="text-right">Acción</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((v) => {
          const isActive = activeVersion === v.version;
          // A version is promotable when it's a draft that's not already
          // active. Archived versions can be re-applied via rollback.
          const canPromote = !isActive && v.status === "staged";
          const canRollback = !isActive && v.status === "archived";
          return (
            <TableRow key={v.id}>
              <TableCell className="font-mono tabular-nums">
                v{v.version}
              </TableCell>
              <TableCell>
                <Badge variant={isActive ? "default" : "outline"}>
                  {isActive
                    ? "Activa"
                    : v.status === "staged"
                      ? "Borrador"
                      : v.status === "archived"
                        ? "Archivada"
                        : v.status}
                </Badge>
              </TableCell>
              <TableCell className="text-muted-foreground">
                {fullDateTime(v.created_at)}
              </TableCell>
              <TableCell className="text-muted-foreground">
                {v.promoted_at ? relativeTime(v.promoted_at) : "—"}
              </TableCell>
              <TableCell className="text-xs font-mono text-muted-foreground">
                {v.id.slice(0, 8)}
              </TableCell>
              <TableCell className="text-right">
                {canPromote ? (
                  <PromoteVersionButton
                    tenantId={tenantId}
                    version={v.version}
                    promote={promote}
                  />
                ) : canRollback ? (
                  <RollbackVersionButton
                    tenantId={tenantId}
                    version={v.version}
                    rollback={rollback}
                  />
                ) : null}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
