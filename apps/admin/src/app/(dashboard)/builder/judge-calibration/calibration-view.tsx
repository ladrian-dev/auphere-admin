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
  blockingCalibration,
  calibrationState,
  formatShare,
  thresholdOf,
} from "../labels";
import { CalibrationItems } from "./calibration-items";

type Props = {
  reports: CalibrationReport[];
  /** The deployment whose report is open; the newest one when absent. */
  selected?: string;
};

/**
 * Spec 047 (T087, 21.8): the judge of the tests does not block a publication
 * until it agrees with human labels in Spanish. Whether it blocks today, the
 * agreement against the threshold, and each labelled criterion.
 */
export function CalibrationView({ reports, selected }: Props) {
  const blocking = blockingCalibration(reports);
  const shown = reports.find((r) => r.deployment_id === selected) ?? reports[0];
  return (
    <div className="flex flex-col gap-6">
      {blocking ? (
        <Callout tone="positive" title="El juez ya puede bloquear una publicación">
          {blocking.model_id} coincide con las etiquetas humanas en el {formatShare(agreementOf(blocking))} de los criterios
          (umbral: {formatShare(thresholdOf(blocking))}). Una prueba falla también si el juez da por fallado uno de sus criterios.
        </Callout>
      ) : (
        <Callout tone="warning" title="El juez todavía no bloquea ninguna publicación">
          Ningún despliegue tiene una calibración aprobada y vigente (umbral: {formatShare(DEFAULT_THRESHOLD)}). Hasta entonces,
          sus veredictos se enseñan en cada prueba, pero la prueba se decide solo por el estado final.
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
                      {open ? (
                        <code className="break-all font-medium">{r.model_id}</code>
                      ) : (
                        <Link
                          className="underline-offset-2 hover:underline"
                          href={`/builder/judge-calibration?deployment=${encodeURIComponent(r.deployment_id)}`}
                        >
                          <code className="break-all">{r.model_id}</code>
                        </Link>
                      )}
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
