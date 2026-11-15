import Link from "next/link";

import {
  Callout,
  EmptyState,
  Meter,
  Section,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@nexus/ui";
import type { CalibrationReport } from "@/lib/backend-builder";

import {
  DATE,
  DEFAULT_THRESHOLD,
  agreementOf,
  calibrationState,
  formatShare,
  judgeCalibration,
  thresholdOf,
} from "../labels";
import { CalibrationItems } from "./calibration-items";

type Props = {
  /** The model that judges in this deployment, and whether the API counts it as calibrated. */
  judge: { model: string; calibrated: boolean };
  reports: CalibrationReport[];
  /** The deployment whose report is open; the judge's, or the newest one, when absent. */
  selected?: string;
};

/**
 * Spec 047 (T087, 21.8): the judge of the tests does not block a publication
 * until it agrees with human labels in Spanish. Spec 059 (5.4, 5.5): only the
 * calibration of the model that judges counts, so the screen names it and says
 * whether it is calibrated; another model's passed calibration does not count.
 */
export function CalibrationView({ judge, reports, selected }: Props) {
  const own = judgeCalibration(reports, judge.model);
  const others = reports.some((r) => r.model_id !== judge.model && r.passed && !r.invalidated_at);
  const shown =
    reports.find((r) => r.deployment_id === selected) ?? reports.find((r) => r.model_id === judge.model) ?? reports[0];
  return (
    <div className="flex flex-col gap-6">
      {judge.calibrated ? (
        <Callout tone="positive" title="El juez ya puede bloquear una publicación">
          <span>
            El juez de este despliegue es <code className="break-all">{judge.model}</code>
            {own
              ? `: coincide con las etiquetas humanas en el ${formatShare(agreementOf(own))} de los criterios (umbral: ${formatShare(thresholdOf(own))}).`
              : ", con una calibración aprobada y vigente."}
          </span>{" "}
          Una prueba falla también si el juez da por fallado uno de sus criterios.
        </Callout>
      ) : (
        <Callout tone="warning" title="El juez todavía no bloquea ninguna publicación">
          <span>
            El juez de este despliegue es <code className="break-all">{judge.model}</code> y no tiene una calibración aprobada y
            vigente (umbral: {formatShare(DEFAULT_THRESHOLD)}).
          </span>{" "}
          Hasta entonces, sus veredictos se enseñan en cada prueba, pero la prueba se decide solo por el estado final.
          {others ? " Las calibraciones aprobadas de otros modelos no cuentan: solo cuenta la del modelo que hace de juez." : null}
        </Callout>
      )}
      {shown ? (
        <ReportSection report={shown} />
      ) : (
        <EmptyState
          readonly
          title="Todavía no se ha calibrado ningún juez"
          description="«Calibrar un despliegue» corre su juez sobre el conjunto etiquetado a mano en español y guarda el acuerdo como la certificación de la tarea judge."
        />
      )}
      {reports.length > 1 ? (
        <Section title="Todas las calibraciones" description="Una por despliegue, la más reciente primero. Cada una sustituye a la anterior del mismo despliegue.">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Despliegue</TableHead>
                <TableHead>Acuerdo</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead>Fecha</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {reports.map((r) => {
                const state = calibrationState(r);
                const open = r === shown;
                return (
                  <TableRow key={`${r.deployment_id}:${r.certified_at}`} aria-current={open ? "true" : undefined}>
                    <TableCell>
                      <span className="flex min-w-0 flex-wrap items-center gap-2">
                        {open ? (
                          <code className="break-all font-medium">{r.model_id}</code>
                        ) : (
                          <Link
                            className="rounded-sm underline-offset-2 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
                            href={`/builder/judge-calibration?deployment=${encodeURIComponent(r.deployment_id)}`}
                          >
                            <code className="break-all">{r.model_id}</code>
                          </Link>
                        )}
                        {r.model_id === judge.model ? <StatusBadge tone="info">Juez</StatusBadge> : null}
                      </span>
                    </TableCell>
                    <TableCell className="tabular-nums">{formatShare(agreementOf(r))}</TableCell>
                    <TableCell>
                      <StatusBadge tone={state.tone}>{state.label}</StatusBadge>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-sm">{DATE.format(new Date(r.certified_at))}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Section>
      ) : null}
    </div>
  );
}

function ReportSection({ report }: { report: CalibrationReport }) {
  const agreement = agreementOf(report);
  const threshold = thresholdOf(report);
  const state = calibrationState(report);
  const items = report.scores.items ?? [];
  const hits = items.filter((i) => i.match).length;
  return (
    <Section
      title={`Informe de ${report.model_id}`}
      description={`Calibrado el ${DATE.format(new Date(report.certified_at))}${
        report.scores.set_version ? ` · conjunto etiquetado v${report.scores.set_version}` : ""
      }${report.invalidated_at ? ` · caducó el ${DATE.format(new Date(report.invalidated_at))}` : ""}`}
      actions={<StatusBadge tone={state.tone}>{state.label}</StatusBadge>}
    >
      <Meter
        label="Acuerdo con las etiquetas humanas"
        value={Math.round(agreement * 1000) / 10}
        max={100}
        tone={report.passed ? "positive" : "danger"}
        valueLabel={`${formatShare(agreement)} · umbral ${formatShare(threshold)}`}
        hint={`${hits} de ${items.length} criterios coinciden. Un «No sé» del juez cuenta como desacuerdo, salvo que la etiqueta también lo sea.`}
      />
      <CalibrationItems items={items} />
    </Section>
  );
}
