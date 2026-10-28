import { Check, X } from "lucide-react";
import Link from "next/link";

import {
  Callout,
  EmptyState,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  cn,
} from "@nexus/ui";
import type { MigrationReport } from "@/lib/backend-levers";
import { actorLabel } from "@/lib/levers";

import {
  KIND_LABEL,
  STATUS_LABEL,
  agentVerdict,
  audienceText,
  channelChanges,
  agentLabel,
  clientLabel,
  diffFirst,
  numberLabel,
  reportSummary,
} from "./console-v2";

const DATE = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" });

/** A row with a difference stands out; the rest stay quiet. */
const DIFF_ROW = "bg-status-danger-bg";

/**
 * Spec 047 (T172, 55.4): one report of the new console — every agent (is the
 * compiled prompt the same, byte by byte, and is the model still pinned?) and
 * every number (who it answers today and who it would answer after), with the
 * differences first and marked.
 */
export function ReportView({ report }: { report: MigrationReport }) {
  const s = reportSummary(report);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <StatusBadge tone={report.status === "clean" ? "positive" : "danger"}>{STATUS_LABEL[report.status]}</StatusBadge>
        <span>
          {KIND_LABEL[report.kind]} del {DATE.format(new Date(report.created_at))} UTC
        </span>
        <span className="text-muted-foreground">{actorLabel(report.created_by)}</span>
      </div>
      {report.reason ? <p className="text-sm text-pretty">Motivo: «{report.reason}»</p> : null}
      {report.status === "diff" ? (
        <Callout tone="danger" title="No se puede activar con este informe">
          {s.agentsDiff ? `${s.agentsDiff} de ${s.agents} agentes cambian. ` : ""}
          {s.channelsDiff ? `${s.channelsDiff} de ${s.channels} números responderían a otra gente. ` : ""}
          Revisa cada diferencia, corrígela y repite el ensayo.
        </Callout>
      ) : null}

      <section aria-label="Agentes" className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">
          Agentes <span className="text-muted-foreground tabular-nums">({s.agents})</span>
        </h3>
        {report.agents.length ? (
          <div className="overflow-x-auto rounded-md ring-1 ring-foreground/10">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Agente</TableHead>
                  <TableHead>Prompt y modelo</TableHead>
                  <TableHead>Resultado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {diffFirst(report.agents).map((a) => {
                  const v = agentVerdict(a);
                  return (
                    <TableRow key={`${a.tenant_id}:${a.agent_id}`} data-diff={!v.same || undefined} className={cn(!v.same && DIFF_ROW)}>
                      <TableCell>
                        <Link className="underline-offset-2 hover:underline" href={`/tenants/${a.tenant_id}`}>
                          {clientLabel(a)}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Link className="underline-offset-2 hover:underline" href={`/tenants/${a.tenant_id}/agent`}>
                          {agentLabel(a)}
                        </Link>
                      </TableCell>
                      <TableCell>
                        {v.checks.length ? (
                          <ul className="flex flex-col gap-1">
                            {v.checks.map((c) => (
                              <li key={c.key} className="flex items-center gap-2 text-sm">
                                {c.ok ? (
                                  <Check className="size-4 shrink-0 text-status-positive-text" aria-hidden="true" />
                                ) : (
                                  <X className="size-4 shrink-0 text-status-danger-text" aria-hidden="true" />
                                )}
                                <span className={cn(!c.ok && "font-medium")}>{c.label}</span>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <span className="text-sm text-pretty text-muted-foreground">{v.note}</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <StatusBadge tone={v.same ? "positive" : "danger"}>{v.label}</StatusBadge>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        ) : (
          <EmptyState readonly title="Ningún agente que comparar" description="Sus clientes no tienen agentes con versión activa hecha con la consola de hoy." />
        )}
      </section>

      <section aria-label="Números" className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">
          Números <span className="text-muted-foreground tabular-nums">({s.channels})</span>
        </h3>
        {report.channels.length ? (
          <div className="overflow-x-auto rounded-md ring-1 ring-foreground/10">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Número</TableHead>
                  <TableHead>Hoy responde a</TableHead>
                  <TableHead>Con la consola nueva</TableHead>
                  <TableHead>Resultado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {diffFirst(report.channels).map((c) => {
                  const changes = channelChanges(c);
                  return (
                    <TableRow key={c.channel_id} data-diff={!c.same || undefined} className={cn(!c.same && DIFF_ROW)}>
                      <TableCell>
                        <Link className="underline-offset-2 hover:underline" href={`/tenants/${c.tenant_id}`}>
                          {clientLabel(c)}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Link
                          className="font-mono text-sm underline-offset-2 hover:underline"
                          href={`/tenants/${c.tenant_id}/channels/${c.channel_id}`}
                        >
                          {numberLabel(c)}
                        </Link>
                      </TableCell>
                      <TableCell className="text-sm text-pretty">{audienceText(c.before)}</TableCell>
                      <TableCell className="text-sm text-pretty">
                        <div className="flex flex-col gap-1">
                          <span className={cn(!c.same && "font-medium")}>{audienceText(c.after)}</span>
                          {changes.map((line) => (
                            <span key={line} className="text-xs text-status-danger-text">
                              {line}
                            </span>
                          ))}
                          {c.pending_migration ? (
                            <span className="text-xs text-muted-foreground">Sin migrar: la activación la guarda así.</span>
                          ) : null}
                        </div>
                      </TableCell>
                      <TableCell>
                        <StatusBadge tone={c.same ? "positive" : "danger"}>{c.same ? "Igual" : "Distinto"}</StatusBadge>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        ) : (
          <EmptyState readonly title="Ningún número que comparar" description="Sus clientes no tienen canales conectados." />
        )}
      </section>
    </div>
  );
}
