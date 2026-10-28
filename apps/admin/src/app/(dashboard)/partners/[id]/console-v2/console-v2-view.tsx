"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import {
  Button,
  EmptyState,
  Section,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@nexus/ui";
import type { ConsoleV2State, MigrationReport } from "@/lib/backend-levers";
import { actorLabel } from "@/lib/levers";

import { consoleV2DisableAction, consoleV2DryRunAction, consoleV2EnableAction } from "./actions";
import { KIND_LABEL, STATUS_LABEL, enableGate, reasonFor, reportSummary, stateText } from "./console-v2";
import { ReasonDialog } from "./reason-dialog";
import { ReportView } from "./report-view";

const DATE = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" });

type Props = {
  partnerId: string;
  partnerName: string;
  reports: MigrationReport[];
  /** Which console the partner sees today; `null` when the API did not answer. */
  state: ConsoleV2State | null;
};

type Write = "dry_run" | "enable" | "disable";

/**
 * Spec 047 (T172; 55.2, 55.4, 55.5): the new console of one partner. It says
 * which console the partner sees today. The dry run compares every agent and
 * every number and leaves its report; «Activar» needs a clean one of the last
 * 24 hours (the API decides, and its refusal is said in words); «Volver a la
 * consola de hoy» works until the partner confirms the split in bags. Each
 * write carries its reason (optional for the dry run). Below, every report.
 */
export function ConsoleV2View({ partnerId, partnerName, reports, state }: Props) {
  const router = useRouter();
  const [selected, setSelected] = useState<string | null>(null);
  const [current, setCurrent] = useState<ConsoleV2State | null>(state);
  const [open, setOpen] = useState<Write | null>(null);

  const gate = enableGate(reports);
  const shown = reports.find((r) => r.id === selected) ?? reports[0] ?? null;
  const onV2 = current?.version === "v2";
  const onV1 = current?.version === "v1";

  async function dryRun(reason: string | null): Promise<string | null> {
    const result = await consoleV2DryRunAction(partnerId, reason);
    if (!result.ok) return result.error;
    if (result.data.status === "clean") toast.success("Ensayo sin diferencias: ya se puede activar");
    else toast.warning("El ensayo encontró diferencias");
    setSelected(null);
    router.refresh();
    return null;
  }

  async function toggle(kind: "enable" | "disable", reason: string | null): Promise<string | null> {
    const why = reason ?? "";
    const result = kind === "enable" ? await consoleV2EnableAction(partnerId, why) : await consoleV2DisableAction(partnerId, why);
    if (!result.ok) return result.error;
    setCurrent(result.data);
    toast.success(kind === "enable" ? `${partnerName} ya ve la consola nueva` : `${partnerName} vuelve a la consola de hoy`);
    router.refresh();
    return null;
  }

  return (
    <div className="flex flex-col gap-6">
      <Section
        title="Consola nueva"
        description="Se activa partner a partner. Hasta entonces el partner ve la consola de hoy y la API sirve a las dos. Antes de activar, el ensayo compara cada agente (el prompt, byte a byte, y el modelo fijado) y la audiencia de cada número, antes y después."
        actions={
          <>
            <Button variant="outline" onClick={() => setOpen("dry_run")}>
              Correr el ensayo
            </Button>
            {!onV2 ? (
              <Button onClick={() => setOpen("enable")} disabled={!gate.ok}>
                Activar la consola nueva
              </Button>
            ) : null}
            {!onV1 ? (
              <Button variant="ghost" onClick={() => setOpen("disable")}>
                Volver a la consola de hoy
              </Button>
            ) : null}
          </>
        }
      >
        <div className="flex flex-col gap-2 text-sm">
          <p role="status" className="flex flex-wrap items-center gap-2">
            {current ? (
              <>
                <StatusBadge tone={onV2 ? "positive" : "muted"}>{onV2 ? "Consola nueva" : "Consola de hoy"}</StatusBadge>
                <span>{stateText(current)}</span>
              </>
            ) : (
              <span className="text-muted-foreground">No se pudo leer qué consola ve hoy el partner.</span>
            )}
          </p>
          {!onV2 && !gate.ok ? <p className="text-muted-foreground text-pretty">Para activar: {gate.why}</p> : null}
        </div>
      </Section>

      <Section title={shown && shown.id !== reports[0]?.id ? "Informe elegido" : "Último informe"}>
        {shown ? (
          <ReportView report={shown} />
        ) : (
          <EmptyState
            readonly
            title="Todavía no hay ningún ensayo"
            description="«Correr el ensayo» compara sin cambiar nada y deja aquí su informe."
          />
        )}
      </Section>

      {reports.length ? (
        <Section title="Historial" description="Los ensayos y las activaciones, del último al primero." padded={false}>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Cuándo</TableHead>
                  <TableHead>Qué</TableHead>
                  <TableHead>Resultado</TableHead>
                  <TableHead>Agentes</TableHead>
                  <TableHead>Números</TableHead>
                  <TableHead>Quién</TableHead>
                  <TableHead className="text-right">
                    <span className="sr-only">Acciones</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {reports.map((r) => {
                  const s = reportSummary(r);
                  const isShown = r.id === shown?.id;
                  return (
                    <TableRow key={r.id} aria-current={isShown || undefined}>
                      <TableCell className="whitespace-nowrap text-sm">{DATE.format(new Date(r.created_at))}</TableCell>
                      <TableCell className="text-sm">
                        <span className="flex flex-col">
                          <span>{KIND_LABEL[r.kind]}</span>
                          {r.reason ? (
                            <span className="max-w-xs truncate text-xs text-muted-foreground" title={r.reason}>
                              {r.reason}
                            </span>
                          ) : null}
                        </span>
                      </TableCell>
                      <TableCell>
                        <StatusBadge tone={r.status === "clean" ? "positive" : "danger"}>{STATUS_LABEL[r.status]}</StatusBadge>
                      </TableCell>
                      <TableCell className="text-sm tabular-nums">
                        {s.agents}
                        {s.agentsDiff ? ` · ${s.agentsDiff} distintos` : ""}
                      </TableCell>
                      <TableCell className="text-sm tabular-nums">
                        {s.channels}
                        {s.channelsDiff ? ` · ${s.channelsDiff} distintos` : ""}
                      </TableCell>
                      <TableCell className="text-sm">{actorLabel(r.created_by)}</TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={isShown}
                          aria-label={`Ver el informe del ${DATE.format(new Date(r.created_at))}`}
                          onClick={() => setSelected(r.id)}
                        >
                          Ver
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </Section>
      ) : null}

      <ReasonDialog
        open={open === "dry_run"}
        onOpenChange={(next) => setOpen(next ? "dry_run" : null)}
        title={`Ensayar la consola nueva de ${partnerName}`}
        description="Compara cada agente y cada número sin cambiar nada, y deja su informe."
        confirmLabel="Correr el ensayo"
        pendingLabel="Ensayando…"
        optional
        hint="Queda en el informe y en la auditoría. Por ejemplo: «Revisión antes de activar»."
        validate={(text) => reasonFor("dry_run", text)}
        onConfirm={dryRun}
      />
      <ReasonDialog
        open={open === "enable"}
        onOpenChange={(next) => setOpen(next ? "enable" : null)}
        title={`Activar la consola nueva para ${partnerName}`}
        description="Desde ahora el partner ve la consola nueva. Los números que aún no tenían audiencia guardan la del ensayo. Se puede deshacer hasta que el partner confirme el reparto de su saldo en bolsas."
        confirmLabel="Activar"
        pendingLabel="Activando…"
        hint="Queda en el informe de la activación y en la auditoría con tu nombre."
        validate={(text) => reasonFor("enable", text)}
        onConfirm={(reason) => toggle("enable", reason)}
      />
      <ReasonDialog
        open={open === "disable"}
        onOpenChange={(next) => setOpen(next ? "disable" : null)}
        title={`Devolver a ${partnerName} la consola de hoy`}
        description="El partner vuelve a ver la consola de hoy con sus datos de antes. Solo se puede mientras no haya confirmado el reparto de su saldo en bolsas."
        confirmLabel="Volver a la consola de hoy"
        pendingLabel="Volviendo…"
        destructive
        hint="Queda en la auditoría con tu nombre."
        validate={(text) => reasonFor("disable", text)}
        onConfirm={(reason) => toggle("disable", reason)}
      />
    </div>
  );
}
