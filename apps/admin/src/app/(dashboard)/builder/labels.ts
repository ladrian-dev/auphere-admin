/**
 * Spec 047 (T087, T090, T100): the words and the figures of the builder's
 * screens. Pure, so they are tested on their own.
 */
import type { StatusBadgeTone } from "@nexus/ui";

import type { CalibrationReport, JudgeVerdict } from "@/lib/backend-builder";

const PCT = new Intl.NumberFormat("es", { style: "percent", maximumFractionDigits: 1 });
const NUM = new Intl.NumberFormat("es", { maximumFractionDigits: 1 });
const SIGNED = new Intl.NumberFormat("es", { maximumFractionDigits: 1, signDisplay: "exceptZero" });
export const DATE = new Intl.DateTimeFormat("es", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" });

/** A share between 0 and 1 («0,913» → «91,3 %»). */
export function formatShare(fraction: number): string {
  return PCT.format(fraction);
}

/** A percentage between 0 and 100, as the evaluation stores it. */
export function formatPct(pct: number): string {
  return PCT.format(pct / 100);
}

/** A latency: milliseconds under a second, seconds from there. */
export function formatMs(ms: number): string {
  return Math.abs(ms) >= 1000 ? `${NUM.format(ms / 1000)} s` : `${NUM.format(ms)} ms`;
}

/** Who did it, from the actor the API stores. */
export function actorLabel(actor: string | null, operatorId?: string): string {
  if (!actor) return "—";
  if (actor.startsWith("operator:")) {
    const id = actor.slice("operator:".length);
    return id === operatorId ? "Tú" : `Operador ${id.slice(0, 8)}`;
  }
  if (actor.startsWith("auphere:")) return `Semilla (${actor.slice("auphere:".length)})`;
  return actor;
}

// ── la calibración del juez ────────────────────────────────────────────────

export const VERDICT_LABEL: Record<JudgeVerdict, string> = { pass: "Pasa", fail: "Falla", unknown: "No sé" };

/** The agreement of a report: `scores.agreement`, or `quality` (a decimal string). */
export function agreementOf(report: CalibrationReport): number {
  const fromScores = report.scores.agreement;
  return typeof fromScores === "number" ? fromScores : Number(report.quality);
}

/** The judge's threshold (`judge.CALIBRATION_THRESHOLD`) when the report does not carry it. */
export const DEFAULT_THRESHOLD = 0.85;

export function thresholdOf(report: CalibrationReport): number {
  return typeof report.scores.threshold === "number" ? report.scores.threshold : DEFAULT_THRESHOLD;
}

/** Whether a calibration still counts: the same rule as `judge.judge_calibrated`. */
export function calibrationState(report: CalibrationReport): { label: string; tone: StatusBadgeTone } {
  if (!report.passed) return { label: "Suspendida", tone: "danger" };
  if (report.invalidated_at) return { label: "Caducada", tone: "muted" };
  return { label: "Aprobada", tone: "positive" };
}

/** The calibration that lets the judge block a publication, if there is one. */
export function blockingCalibration(reports: CalibrationReport[]): CalibrationReport | null {
  return reports.find((r) => r.passed && !r.invalidated_at) ?? null;
}

export const CALIBRATION_ERRORS: Record<string, string> = {
  unknown_deployment: "Ese despliegue ya no existe en el catálogo.",
};

// ── la evaluación del constructor ──────────────────────────────────────────

/** The descriptions of the bank v1 (`services/builder/eval_bank_v1.json`). */
export const BANK_SIZE = 100;

/** How many descriptions to run: empty is the whole bank (`null`). */
export function parseEvalLimit(raw: string): { ok: true; limit: number | null } | { ok: false; error: string } {
  const text = raw.trim();
  if (!text) return { ok: true, limit: null };
  const value = Number(text);
  if (!Number.isInteger(value) || value < 1 || value > BANK_SIZE) {
    return { ok: false, error: `Un número entero entre 1 y ${BANK_SIZE}, o vacío para todo el banco.` };
  }
  return { ok: true, limit: value === BANK_SIZE ? null : value };
}

/** CE-002 and CE-003: what the builder has to reach. */
export const EVAL_TARGETS = {
  validator_first_pass_pct: 95,
  sector_pass_unedited_pct: 70,
  draft_p90_ms: 30_000,
} as const;

export type EvalMetric = keyof typeof EVAL_TARGETS;

/**
 * The change against the run before, in words and tone: percentage points for
 * the shares, time for the p90 — where going down is the good news.
 */
export function evalDelta(
  metric: EvalMetric,
  delta: number | null | undefined,
): { label: string; tone: "positive" | "negative" | "neutral"; srLabel: string } | undefined {
  if (delta === null || delta === undefined) return undefined;
  const sign = delta > 0 ? "+" : delta < 0 ? "−" : "";
  const label =
    metric === "draft_p90_ms" ? `${sign}${formatMs(Math.abs(delta))}` : `${SIGNED.format(delta).replace("-", "−")} pts`;
  const better = metric === "draft_p90_ms" ? delta < 0 : delta > 0;
  const tone = delta === 0 ? "neutral" : better ? "positive" : "negative";
  const srLabel = delta === 0 ? "Igual que la evaluación anterior" : `${better ? "Mejor" : "Peor"} que la evaluación anterior: ${label}`;
  return { label, tone, srLabel };
}

/** The figure of a run for one metric; «Sin medir» when it was not measured. */
export function formatEvalValue(metric: EvalMetric, value: number | null): string {
  if (value === null) return "Sin medir";
  return metric === "draft_p90_ms" ? formatMs(value) : formatPct(value);
}
