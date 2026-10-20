"use client";

import { FileText, MoreHorizontal } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  ConfirmDialog,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  EmptyState,
  StatusBadge,
} from "@nexus/ui";

import type { AgentConfig, ToolWithInstallStatus } from "@/lib/backend";
import { fullDateTime } from "@/lib/format";

import { promoteAgentConfigAction, rollbackAgentConfigAction } from "./actions";
import { AgentEditor, type StageAction } from "./editor";

const STATUS = {
  active: { label: "Activa", tone: "positive" },
  staged: { label: "Borrador", tone: "info" },
  archived: { label: "Archivada", tone: "muted" },
} as const;

/**
 * Spec 037: the agent's versions as the partner console shows them —
 * «Nuevo borrador» from the active version, one card per version with its
 * state, and «⋯» to publish a draft, go back to an older one or read its
 * prompt. Publishing and going back both swap what answers customers, so both
 * ask first (H5).
 */
export function AgentVersions({
  tenantId,
  agentId,
  versions,
  activeVersion,
  source,
  sourceIsStagedDraft,
  catalog,
  stageAction,
}: {
  tenantId: string;
  agentId?: string;
  versions: AgentConfig[];
  activeVersion: number | null;
  source: AgentConfig | null;
  sourceIsStagedDraft: boolean;
  catalog: ToolWithInstallStatus[];
  stageAction: StageAction;
}) {
  const router = useRouter();
  const [draftOpen, setDraftOpen] = React.useState(versions.length === 0);
  const [expanded, setExpanded] = React.useState<number | null>(null);
  const [publishing, setPublishing] = React.useState<AgentConfig | null>(null);
  const [rollingBack, setRollingBack] = React.useState<AgentConfig | null>(null);
  const sorted = [...versions].sort((a, b) => b.version - a.version);

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => setDraftOpen((o) => !o)} variant={draftOpen ? "secondary" : "default"}>
          Nuevo borrador
        </Button>
        {source ? (
          <span className="text-sm text-muted-foreground">
            {sourceIsStagedDraft ? `Sigue el borrador v${source.version}` : `A partir de la versión ${source.version}`}
          </span>
        ) : null}
      </div>

      {draftOpen ? (
        <Card>
          <CardHeader>
            <CardTitle>Nuevo borrador</CardTitle>
            <CardDescription>
              Escribe el prompt con los datos del cliente ya puestos. Las habilidades se eligen en su pestaña.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <AgentEditor
              key={`${agentId ?? "principal"}:${source?.id ?? "empty"}`}
              tenantId={tenantId}
              agentId={agentId}
              source={source}
              sourceIsStagedDraft={sourceIsStagedDraft}
              catalog={catalog}
              stageAction={stageAction}
              showTools={false}
              onDone={() => setDraftOpen(false)}
            />
          </CardContent>
        </Card>
      ) : null}

      {sorted.length === 0 && !draftOpen ? (
        <EmptyState
          icon={FileText}
          title="Este cliente aún no tiene ninguna versión del agente"
          description="Escribe el primer prompt y guárdalo como borrador. Publícalo cuando lo hayas probado."
          action={<Button onClick={() => setDraftOpen(true)}>Nuevo borrador</Button>}
        />
      ) : null}

      {sorted.length > 0 ? (
        <ol className="flex flex-col gap-2" aria-label="Versiones">
          {sorted.map((v) => {
            const isActive = v.version === activeVersion;
            const open = expanded === v.version;
            const st = isActive ? STATUS.active : STATUS[v.status];
            return (
              <li key={v.id} className="rounded-md bg-card p-4 ring-1 ring-foreground/10">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    className="font-mono text-sm font-semibold hover:underline"
                    onClick={() => setExpanded(open ? null : v.version)}
                    aria-expanded={open}
                  >
                    v{v.version}
                  </button>
                  <StatusBadge tone={st.tone}>{st.label}</StatusBadge>
                  <span className="min-w-0 truncate text-sm text-muted-foreground">
                    {fullDateTime(v.promoted_at ?? v.created_at)}
                    {v.tools.length ? ` · ${v.tools.length} habilidades` : ""}
                  </span>
                  <span className="ml-auto">
                    <DropdownMenu>
                      <DropdownMenuTrigger
                        render={<Button variant="ghost" size="icon-sm" aria-label={`Opciones de la versión ${v.version}`} />}
                      >
                        <MoreHorizontal aria-hidden="true" />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {!isActive && v.status === "staged" ? (
                          <DropdownMenuItem onClick={() => setPublishing(v)}>Publicar</DropdownMenuItem>
                        ) : null}
                        {!isActive && v.status === "archived" ? (
                          <DropdownMenuItem onClick={() => setRollingBack(v)}>Revertir a esta</DropdownMenuItem>
                        ) : null}
                        <DropdownMenuItem onClick={() => setExpanded(open ? null : v.version)}>
                          {open ? "Ocultar prompt" : "Ver prompt"}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </span>
                </div>
                {open ? (
                  <pre className="mt-3 max-h-96 overflow-auto rounded-md bg-muted p-3 font-mono text-xs whitespace-pre-wrap">
                    {v.system_prompt_rendered}
                  </pre>
                ) : null}
              </li>
            );
          })}
        </ol>
      ) : null}

      <ConfirmDialog
        open={publishing !== null}
        onOpenChange={(o) => !o && setPublishing(null)}
        title={`Publicar la versión ${publishing?.version ?? ""}`}
        description="Los próximos mensajes de los clientes los atenderá esta versión. Puedes revertir en un clic."
        confirmLabel="Publicar"
        cancelLabel="Cancelar"
        onConfirm={async () => {
          if (!publishing) return;
          const res = await promoteAgentConfigAction(tenantId, publishing.version);
          if (!res.ok) return void toast.error("No se pudo publicar", { description: res.error });
          toast.success(`Versión ${publishing.version} publicada`);
          setPublishing(null);
          router.refresh();
        }}
      />
      <ConfirmDialog
        open={rollingBack !== null}
        onOpenChange={(o) => !o && setRollingBack(null)}
        title={`Volver a la versión ${rollingBack?.version ?? ""}`}
        description={`Los próximos mensajes los atenderá la versión ${rollingBack?.version ?? ""}. La ${activeVersion ?? ""} se queda en el historial: puedes volver a ella cuando quieras.`}
        confirmLabel="Volver a esta versión"
        cancelLabel="Cancelar"
        onConfirm={async () => {
          if (!rollingBack) return;
          const res = await rollbackAgentConfigAction(tenantId, rollingBack.version);
          if (!res.ok) return void toast.error("No se pudo revertir", { description: res.error });
          toast.success(`Revertido a la versión ${rollingBack.version}`);
          setRollingBack(null);
          router.refresh();
        }}
      />
    </div>
  );
}
