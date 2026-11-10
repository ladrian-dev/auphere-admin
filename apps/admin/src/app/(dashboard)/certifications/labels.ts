/**
 * Spec 047 (T150, 42.7): the words of the certification screen.
 */
import type { StatusBadgeTone } from "@nexus/ui";

import type { AgentCertification, ClassCertification } from "@/lib/backend-models";

const PCT = new Intl.NumberFormat("es", { style: "percent", maximumFractionDigits: 1 });
const DAY = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeZone: "UTC" });

export function formatQuality(quality: number): string {
  return PCT.format(quality);
}

export function formatDay(iso: string): string {
  return DAY.format(new Date(iso));
}

/** Whether a certification still counts for the router. */
export function validity(c: ClassCertification | AgentCertification): { label: string; tone: StatusBadgeTone } {
  if (!c.passed) return { label: "Suspendida", tone: "danger" };
  if (c.invalidated_at) return { label: `Caducada el ${formatDay(c.invalidated_at)}`, tone: "muted" };
  return { label: "Vigente", tone: "positive" };
}

export const PAID_BY_LABEL: Record<AgentCertification["paid_by"], string> = {
  partner: "El partner, en Construcción y pruebas",
  auphere: "Auphere, fuera de las partidas",
};

/** The metrics the battery stores, the ones worth reading in a row. */
export function scoreSummary(scores: Record<string, unknown>): string {
  const metrics = (scores.metrics as Record<string, unknown> | undefined) ?? scores;
  const parts: string[] = [];
  if (typeof metrics.pass3 === "number") parts.push(`pass^3 ${PCT.format(metrics.pass3)}`);
  if (typeof metrics.latency_p95_ms === "number") parts.push(`p95 ${metrics.latency_p95_ms} ms`);
  if (typeof scores.threshold === "number") parts.push(`umbral ${PCT.format(scores.threshold)}`);
  return parts.join(" · ") || "—";
}

export const RUN_ERRORS: Record<string, string> = {
  class_runner_offline:
    "La batería común corre fuera de línea (nexus_worker.certification) hasta que tenga un trabajo de plataforma.",
  agent_runner_pending:
    "La suite del agente con un despliegue es el trabajo quality_check, que aún no tiene manejador (T147).",
  tasks_or_agents: "Elige tareas o agentes, no las dos cosas.",
  unknown_deployment: "Ese despliegue ya no existe.",
};
