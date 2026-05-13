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
import { backend, type ToolWithInstallStatus } from "@/lib/backend";
import { fullDateTime, relativeTime } from "@/lib/format";

import { AgentEditor } from "./editor";
import {
  promoteAgentConfigAction,
  rollbackAgentConfigAction,
  stageAgentConfigAction,
} from "./actions";
import { ApplySeedTemplateButton } from "./apply-seed";

export default async function AgentPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [tenant, bundle, catalog, seedTemplates] = await Promise.all([
    backend.getTenant(id),
    backend.getAgentConfig(id),
    backend.listTenantToolCatalog(id, false),
    backend.listSeedTemplates(),
  ]);
  if (!tenant) return null;

  // Filter the whitelist by the seed template applied to this tenant.
  // Look at the active version first (steady state); if there isn't one,
  // fall back to the most recent staged/archived version that carries a
  // seed_template_ref — that covers the "Aplicar plantilla inicial → not
  // yet promoted" path which previously fell through and dumped the full
  // registry on the operator (the gap the audit 2026-05-13 caught).
  const versionWithSeed =
    bundle.active?.seed_template_ref !== undefined &&
    bundle.active?.seed_template_ref !== null
      ? bundle.active
      : [...bundle.versions]
          .sort((a, b) => b.version - a.version)
          .find((v) => v.seed_template_ref) ?? null;
  const seedRef = versionWithSeed?.seed_template_ref ?? null;
  const seedTemplate = seedRef
    ? (seedTemplates.find((t) => t.name === seedRef) ?? null)
    : null;
  // Without a seed template we can't know which vertical-specific tools
  // are relevant — render an empty catalog so the editor surfaces the
  // "Aplicá una plantilla inicial primero" CTA instead of dumping the
  // entire registry on the operator (the regression the 2026-05-13 audit
  // caught: BUG-004 only fixed the post-promote path).
  const publicCatalog: ToolWithInstallStatus[] = seedTemplate
    ? catalog.filter(
        (t) =>
          t.status !== "internal" &&
          seedTemplate.tools_required.includes(t.name),
      )
    : [];

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader className="flex flex-col gap-1">
          <Eyebrow>Configuración del agente</Eyebrow>
          <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
            <div>
              <CardTitle>
                {bundle.active
                  ? `Versión ${bundle.active.version} activa`
                  : "Crear primera versión"}
              </CardTitle>
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
            active={bundle.active}
            catalog={publicCatalog}
            seedTemplateName={seedTemplate?.display_name ?? null}
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
    </div>
  );
}

function VersionTable({
  versions,
  activeVersion,
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
          <TableHead className="text-right">ID</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((v) => {
          const isActive = activeVersion === v.version;
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
              <TableCell className="text-right text-xs font-mono text-muted-foreground">
                {v.id.slice(0, 8)}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
