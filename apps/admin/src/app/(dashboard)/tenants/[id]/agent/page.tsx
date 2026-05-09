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
import { backend, type ToolCatalog } from "@/lib/backend";
import { fullDateTime, relativeTime } from "@/lib/format";

import { AgentEditor } from "./editor";
import {
  promoteAgentConfigAction,
  rollbackAgentConfigAction,
  stageAgentConfigAction,
} from "./actions";

export default async function AgentPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [tenant, bundle, catalog] = await Promise.all([
    backend.getTenant(id),
    backend.getAgentConfig(id),
    backend.listToolCatalog(false),
  ]);
  if (!tenant) return null;

  // Hide internal tools from the whitelist editor entirely.
  const publicCatalog: ToolCatalog[] = catalog.filter(
    (t) => t.status !== "internal",
  );

  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <Eyebrow index="01">Configuración del agente</Eyebrow>
          <CardTitle>
            {bundle.active
              ? `Versión ${bundle.active.version} activa`
              : "Crear primera versión"}
          </CardTitle>
          <CardDescription>
            Cualquier cambio guardado crea una versión <strong>staged</strong>; promovela
            explícitamente para que el agente la use en el siguiente turno.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AgentEditor
            tenantId={tenant.id}
            active={bundle.active}
            catalog={publicCatalog}
            stageAction={stageAgentConfigAction}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Eyebrow index="02">Versiones</Eyebrow>
          <CardTitle>Historial</CardTitle>
          <CardDescription>
            Cada promoción dispara la invalidación de la cache del runtime — el siguiente turno
            usa la nueva versión sin redeploy.
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
                  {isActive ? "Activa" : v.status}
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
