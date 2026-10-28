import {
  Callout,
  EmptyState,
  Metric,
  Section,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@nexus/ui";
import type { EvalRun } from "@/lib/backend-builder";

import { DATE, EVAL_TARGETS, actorLabel, evalDelta, formatEvalValue, formatMs, formatPct, type EvalMetric } from "../labels";

const METRICS: { metric: EvalMetric; label: string; target: string }[] = [
  {
    metric: "validator_first_pass_pct",
    label: "Validador a la primera",
    target: `Objetivo ${formatPct(EVAL_TARGETS.validator_first_pass_pct)}`,
  },
  {
    metric: "sector_pass_unedited_pct",
    label: "Batería del sector sin edición",
    target: `Objetivo ${formatPct(EVAL_TARGETS.sector_pass_unedited_pct)}`,
  },
  {
    metric: "draft_p90_ms",
    label: "p90 del borrador",
    target: `Objetivo menos de ${formatMs(EVAL_TARGETS.draft_p90_ms)}`,
  },
];

type Props = { runs: EvalRun[]; operatorId: string };

/**
 * Spec 047 (T100, 54.4, CE-002, CE-003): the builder against the bank of 100
 * descriptions — how many drafts pass the validator first time, how many pass
 * their sector's battery unedited, and the p90 of a draft — compared with the
 * run before.
 */
export function EvalView({ runs, operatorId }: Props) {
  const [latest, previous] = runs;
  if (!latest) {
    return (
      <EmptyState
        readonly
        title="Todavía no se ha corrido la evaluación"
        description="«Correr la evaluación» pasa por el constructor las 100 descripciones del banco y guarda las tres cifras."
      />
    );
  }
  return (
    <div className="flex flex-col gap-6">
      <Section
        title="La última evaluación"
        description={`${DATE.format(new Date(latest.created_at))} · banco ${latest.bank_version} · ${actorLabel(latest.created_by, operatorId)}`}
      >
        {latest.vs_previous ? (
          <p className="text-sm text-muted-foreground text-pretty">
            Comparada con la del {previous ? DATE.format(new Date(previous.created_at)) : "anterior"}.
          </p>
        ) : (
          <p className="text-sm text-muted-foreground text-pretty">Es la primera: todavía no hay con qué compararla.</p>
        )}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {METRICS.map(({ metric, label, target }) => {
            const before = previous ? previous[metric] : null;
            return (
              <Metric
                key={metric}
                label={label}
                value={formatEvalValue(metric, latest[metric])}
                delta={evalDelta(metric, latest.vs_previous?.[metric])}
                hint={`${target}${before !== null && latest.vs_previous ? ` · antes ${formatEvalValue(metric, before)}` : ""}`}
              />
            );
          })}
        </div>
        {latest.sector_pass_unedited_pct === null ? (
          <Callout tone="info" title="La batería del sector sin edición está sin medir">
            Esta evaluación no corrió las pruebas del sector sobre cada borrador, así que esa cifra queda vacía y no se compara.
          </Callout>
        ) : null}
      </Section>
      <Section title="Historial" description="Las últimas evaluaciones, la más reciente primero, con la diferencia con la anterior.">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Fecha</TableHead>
              <TableHead>Banco</TableHead>
              <TableHead>Quién</TableHead>
              <TableHead>Validador a la primera</TableHead>
              <TableHead>Batería sin edición</TableHead>
              <TableHead>p90 del borrador</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {runs.map((run) => (
              <TableRow key={run.id}>
                <TableCell className="whitespace-nowrap text-sm">{DATE.format(new Date(run.created_at))}</TableCell>
                <TableCell>
                  <code className="text-xs">{run.bank_version}</code>
                </TableCell>
                <TableCell className="text-sm" title={run.created_by}>
                  {actorLabel(run.created_by, operatorId)}
                </TableCell>
                {METRICS.map(({ metric }) => {
                  const delta = evalDelta(metric, run.vs_previous?.[metric]);
                  return (
                    <TableCell key={metric} className="whitespace-nowrap tabular-nums">
                      {formatEvalValue(metric, run[metric])}
                      {delta ? <span className="ml-2 text-xs text-muted-foreground">{delta.label}</span> : null}
                    </TableCell>
                  );
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>
    </div>
  );
}
